from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.travel_profile.analyzer import TravelProfileAnalyzer
from app.travel_profile.generator import LLMProfileCopyGenerator
from app.travel_profile.routes import router
from app.travel_profile.schema import TravelProfileRequest


REFERENCE_TIME = "2026-09-13T14:30:00+09:00"


def request_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": "1.0",
        "reference_time": REFERENCE_TIME,
        "searches": [],
        "visits": [],
        "saved_courses": [],
        "reviews": [],
    }
    data.update(overrides)
    return data


def searches(keyword: str, dates: list[str] | None = None) -> list[dict[str, object]]:
    dates = dates or ["2026-09-10T10:00:00+09:00"] * 3
    return [
        {"keyword": keyword, "region": "정선", "searched_at": date}
        for date in dates
    ]


class TravelProfileAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = TravelProfileAnalyzer()

    def analyze(self, **overrides: object):  # type: ignore[no-untyped-def]
        return self.analyzer.analyze(TravelProfileRequest.model_validate(request_data(**overrides)))

    def test_fewer_than_three_signals_is_insufficient(self) -> None:
        result = self.analyze(searches=searches("자연")[:2])
        self.assertEqual("INSUFFICIENT_DATA", result.status.value)
        self.assertIsNone(result.traveler_type)
        self.assertEqual([], result.tags)
        self.assertIsNone(result.confidence)

    def test_exactly_three_signals_is_completed(self) -> None:
        result = self.analyze(searches=searches("자연 산책"))
        self.assertEqual("COMPLETED", result.status.value)

    def test_every_specific_traveler_type(self) -> None:
        cases = {
            "자연 산책 힐링": "NATURE_HEALING",
            "강아지 반려동물 동반": "PET_COMPANION",
            "로컬 맛집 지역 음식": "LOCAL_FOOD_EXPLORER",
            "래프팅 액티비티 체험": "ACTIVITY_ADVENTURE",
            "박물관 역사 문화": "CULTURE_EXPLORER",
        }
        for keyword, expected in cases.items():
            with self.subTest(keyword=keyword):
                result = self.analyze(searches=searches(keyword))
                self.assertEqual(expected, result.traveler_type.value)

    def test_similarly_strong_categories_are_balanced(self) -> None:
        result = self.analyze(searches=searches("자연 맛집 문화"))
        self.assertEqual("BALANCED_TRAVELER", result.traveler_type.value)

    def test_recent_activity_outweighs_old_activity(self) -> None:
        old = searches("자연", ["2025-09-01T10:00:00+09:00"] * 3)
        recent = searches("문화", ["2026-09-12T10:00:00+09:00"] * 2)
        result = self.analyze(searches=old + recent)
        self.assertEqual("CULTURE_EXPLORER", result.traveler_type.value)

    def test_duplicate_saved_place_counts_once_for_sufficiency(self) -> None:
        duplicated = {
            "name": "정선 힐링 여행",
            "saved_at": "2026-09-10T10:00:00+09:00",
            "places": [{"place_type": "ATTRACTION", "place_id": 101, "name": "아우라지"}],
        }
        result = self.analyze(saved_courses=[duplicated, duplicated])
        self.assertEqual("INSUFFICIENT_DATA", result.status.value)

    def test_output_respects_contract_limits_and_is_deterministic(self) -> None:
        payload = TravelProfileRequest.model_validate(request_data(searches=searches("자연 산책")))
        first = self.analyzer.analyze(payload)
        second = self.analyzer.analyze(payload)
        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertLessEqual(len(first.title or ""), 100)
        self.assertLessEqual(len(first.description or ""), 500)
        self.assertLessEqual(len(first.tags), 5)
        self.assertEqual(len(first.tags), len(set(first.tags)))
        self.assertLessEqual(len(first.evidences), 3)
        self.assertTrue(all(len(item) <= 200 for item in first.evidences))

    def test_llm_analyzes_profile_type_and_copy(self) -> None:
        client = Mock()
        client.create_answer.return_value = """{
            "traveler_type": "CULTURE_EXPLORER",
            "title": "숲길을 천천히 발견하는 여행자",
            "description": "최근 정선의 자연과 산책 장소를 살펴본 흐름을 담았어요.",
            "tags": ["정선 자연", "숲길 산책", "정선 자연"],
            "evidences": [
                "최근 검색 기록 3건을 관심 신호로 반영했어요.",
                "최근 검색 기록 3건을 관심 신호로 반영했어요."
            ],
            "confidence": 0.61
        }"""
        analyzer = TravelProfileAnalyzer(LLMProfileCopyGenerator(client=client))
        payload = TravelProfileRequest.model_validate(request_data(searches=searches("정선 자연 산책")))

        with patch.dict(os.environ, {"GANGWON_TRAVEL_PROFILE_LLM_ENABLED": "true"}):
            result = analyzer.analyze(payload)

        self.assertEqual("CULTURE_EXPLORER", result.traveler_type.value)
        self.assertEqual(0.61, result.confidence)
        self.assertEqual("숲길을 천천히 발견하는 여행자", result.title)
        self.assertEqual(["정선 자연", "숲길 산책"], result.tags)
        client.create_answer.assert_called_once()
        call = client.create_answer.call_args.kwargs
        self.assertIn("신뢰할 수 없는 데이터", call["instructions"])
        self.assertIn("직접 선택", call["instructions"])
        self.assertIn("정선 자연 산책", call["input_text"])

    def test_llm_unverifiable_evidence_uses_grounded_fallback(self) -> None:
        client = Mock()
        client.create_answer.return_value = """{
            "title": "자연 여행자",
            "description": "최근 자연을 찾는 흐름이 나타났어요.",
            "tags": ["자연"],
            "evidences": ["입력에 없는 장소를 열 번 방문했어요."]
        }"""
        analyzer = TravelProfileAnalyzer(LLMProfileCopyGenerator(client=client))
        payload = TravelProfileRequest.model_validate(request_data(searches=searches("자연")))

        with patch.dict(os.environ, {"GANGWON_TRAVEL_PROFILE_LLM_ENABLED": "true"}):
            result = analyzer.analyze(payload)

        self.assertEqual("자연 속 여유를 즐기는 힐링 여행자", result.title)
        self.assertNotIn("입력에 없는 장소를 열 번 방문했어요.", result.evidences)

    def test_llm_error_uses_fallback(self) -> None:
        client = Mock()
        client.create_answer.side_effect = TimeoutError("timeout")
        analyzer = TravelProfileAnalyzer(LLMProfileCopyGenerator(client=client))
        payload = TravelProfileRequest.model_validate(request_data(searches=searches("문화")))

        with patch.dict(os.environ, {"GANGWON_TRAVEL_PROFILE_LLM_ENABLED": "true"}):
            result = analyzer.analyze(payload)

        self.assertEqual("CULTURE_EXPLORER", result.traveler_type.value)
        self.assertEqual("지역의 이야기를 발견하는 문화 탐방 여행자", result.title)


class TravelProfileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_app = FastAPI()
        test_app.include_router(router)
        cls.client = TestClient(test_app)

    def test_valid_request_matches_response_contract(self) -> None:
        response = self.client.post(
            "/internal/travel/profile/analyze",
            json=request_data(searches=searches("강아지 반려동물 동반")),
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("PET_COMPANION", response.json()["traveler_type"])
        self.assertEqual("travel-profile-llm-v1", response.json()["analysis_version"])

    def test_invalid_schema_returns_400(self) -> None:
        payload = request_data()
        payload["searches"] = None
        response = self.client.post("/internal/travel/profile/analyze", json=payload)
        self.assertEqual(400, response.status_code, response.text)

    def test_unsupported_schema_version_returns_400(self) -> None:
        response = self.client.post(
            "/internal/travel/profile/analyze",
            json=request_data(schema_version="2.0"),
        )
        self.assertEqual(400, response.status_code, response.text)

    def test_personal_information_field_is_rejected(self) -> None:
        response = self.client.post(
            "/internal/travel/profile/analyze",
            json=request_data(email="user@example.com"),
        )
        self.assertEqual(400, response.status_code, response.text)

    def test_internal_auth_when_key_is_configured(self) -> None:
        with patch.dict(os.environ, {"INTERNAL_API_KEY": "secret"}):
            unauthorized = self.client.post(
                "/internal/travel/profile/analyze",
                json=request_data(searches=searches("자연")),
            )
            authorized = self.client.post(
                "/internal/travel/profile/analyze",
                headers={"X-Internal-API-Key": "secret"},
                json=request_data(searches=searches("자연")),
            )
        self.assertEqual(401, unauthorized.status_code)
        self.assertEqual(200, authorized.status_code)

    def test_naive_timestamp_is_rejected(self) -> None:
        response = self.client.post(
            "/internal/travel/profile/analyze",
            json=request_data(reference_time="2026-09-13T14:30:00"),
        )
        self.assertEqual(400, response.status_code, response.text)

    def test_unknown_place_type_is_rejected(self) -> None:
        response = self.client.post(
            "/internal/travel/profile/analyze",
            json=request_data(
                visits=[
                    {
                        "place_type": "DESTINATION",
                        "place_id": 101,
                        "name": "아우라지",
                        "category": "NATURE",
                        "region": "정선",
                        "visited_at": "2026-09-01T03:00:00Z",
                    }
                ]
            ),
        )
        self.assertEqual(400, response.status_code, response.text)


if __name__ == "__main__":
    unittest.main()

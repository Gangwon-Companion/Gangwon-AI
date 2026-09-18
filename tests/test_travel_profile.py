from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.travel_profile.analyzer import TravelProfileAnalyzer
from app.travel_profile.auth import verify_internal_api_key
from app.travel_profile.routes import router
from app.travel_profile.schema import TravelProfileRequest


REFERENCE_TIME = "2026-09-18T14:30:00+09:00"


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


def searches(keyword: str) -> list[dict[str, object]]:
    return [{"keyword": keyword, "region": "강원", "searched_at": "2026-09-17T10:00:00+09:00"}] * 3


class TravelProfileAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = TravelProfileAnalyzer()

    def analyze(self, **overrides: object):  # type: ignore[no-untyped-def]
        return self.analyzer.analyze(TravelProfileRequest.model_validate(request_data(**overrides)))

    def test_fewer_than_three_signals_is_insufficient(self) -> None:
        result = self.analyze(searches=searches("자연")[:2])
        self.assertEqual("INSUFFICIENT_DATA", result.status.value)
        self.assertIsNone(result.traveler_type)
        self.assertIsNone(result.axis_scores)

    def test_city_active_planned_famous_profile(self) -> None:
        result = self.analyze(searches=searches("도시 액티비티 유명 명소 계획"))
        self.assertEqual("CAPF", result.traveler_type.value)
        self.assertGreater(result.axis_scores.space["C"], result.axis_scores.space["N"])
        self.assertEqual(100, sum(result.axis_scores.place.values()))

    def test_nature_rest_spontaneous_hidden_profile(self) -> None:
        visits = [
            {
                "place_type": "ATTRACTION",
                "place_id": index,
                "name": "한적한 숨은 숲 힐링 산책",
                "category": "자연 휴식 로컬",
                "region": "강원",
                "visited_at": "2026-09-17T10:00:00+09:00",
            }
            for index in range(1, 4)
        ]
        result = self.analyze(visits=visits)
        self.assertEqual("NRSH", result.traveler_type.value)
        self.assertEqual("travel-type-16-v1", result.analysis_version)

    def test_all_axis_scores_are_normalized(self) -> None:
        result = self.analyze(searches=searches("자연 체험 로컬 코스"))
        for axis in result.axis_scores.model_dump().values():
            self.assertEqual(100, sum(axis.values()))


class TravelProfileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_app = FastAPI()
        test_app.include_router(router)
        test_app.dependency_overrides[verify_internal_api_key] = lambda: None
        cls.client = TestClient(test_app)

    def test_valid_request_matches_travel_type_16_contract(self) -> None:
        response = self.client.post(
            "/internal/travel/profile/analyze",
            json=request_data(searches=searches("자연 체험 유명 명소 계획")),
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("NAPF", response.json()["traveler_type"])
        self.assertEqual("travel-type-16-v1", response.json()["analysis_version"])
        self.assertEqual(100, sum(response.json()["axis_scores"]["space"].values()))

    def test_invalid_schema_returns_400(self) -> None:
        payload = request_data()
        payload["searches"] = None
        response = self.client.post("/internal/travel/profile/analyze", json=payload)
        self.assertEqual(400, response.status_code, response.text)


if __name__ == "__main__":
    unittest.main()

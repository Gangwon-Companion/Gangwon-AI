from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.agents.response import build_final_response, response_node
from app.agents.response_llm import render_answer_with_llm
from app.main import app


def valid_state() -> dict[str, object]:
    return {
        "request": {"region": "강릉", "travel_days": 1, "preferences": ["한식"]},
        "preference_profile": {"keywords": ["한식"]},
        "itinerary_status": "READY",
        "hard_validation": {"status": "VALID", "violations": [], "next_actions": []},
        "quality_validation": {"status": "PASS", "score": 91, "issues": [], "next_actions": []},
        "itinerary": [
            {
                "slot": "D1_DINNER",
                "place_id": "R2",
                "name": "저녁 식당",
                "category": "RESTAURANT",
                "start_at": "2026-08-23T18:00:00+09:00",
                "end_at": "2026-08-23T19:30:00+09:00",
                "travel_minutes_from_previous": 20,
                "source_ids": ["restaurant:R2"],
                "tags": ["한식"],
                "address": "강릉시 식당길 2",
                "opens_at": "11:00",
                "closes_at": "21:00",
                "pet_allowed": True,
                "wheelchair_accessible": True,
                "indoor_pet_allowed": None,
                "max_pet_size": None,
                "recommendation_reason": "지역 식재료를 사용하는 식당입니다.",
                "matched_conditions": ["한식"],
            },
            {
                "slot": "D1_DESTINATION",
                "place_id": "D1",
                "name": "바다 전망대",
                "category": "DESTINATION",
                "start_at": "2026-08-23T10:00:00+09:00",
                "end_at": "2026-08-23T12:00:00+09:00",
                "travel_minutes_from_previous": 0,
                "source_ids": ["destination:D1"],
                "tags": ["바다"],
                "address": "강릉시 바다길 1",
                "opens_at": "09:00",
                "closes_at": "18:00",
                "pet_allowed": True,
                "wheelchair_accessible": True,
                "indoor_pet_allowed": False,
                "max_pet_size": "LARGE",
                "recommendation_reason": "바다 경관을 볼 수 있습니다.",
                "matched_conditions": ["바다"],
            },
        ],
    }


def preview_payload() -> dict[str, object]:
    state = valid_state()
    return {
        "request": {
            "message": "강릉에서 반려견과 바다 중심으로 하루 여행하고 싶어요.",
            "region": "강릉",
            "travel_days": 1,
            "nights": 0,
            "pet_allowed": True,
            "pet_size": "SMALL",
            "wheelchair_accessible": True,
            "preferences": ["바다", "한식"],
        },
        "preference_profile": {
            "keywords": ["바다", "한식"],
            "soft": {},
        },
        "itinerary_status": state["itinerary_status"],
        "itinerary": state["itinerary"],
        "hard_validation": state["hard_validation"],
        "quality_validation": state["quality_validation"],
    }


class ResponseAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_patcher = patch.dict(
            "os.environ", {"GANGWON_RESPONSE_LLM_ENABLED": ""}, clear=False
        )
        self._env_patcher.start()

    def tearDown(self) -> None:
        self._env_patcher.stop()

    def test_builds_grounded_response_in_time_order(self) -> None:
        result = build_final_response(valid_state())  # type: ignore[arg-type]

        self.assertEqual(result["response_status"], "READY")
        self.assertEqual(result["title"], "강릉 1일 여행 일정")
        self.assertEqual(result["days"][0]["visits"][0]["place_id"], "D1")
        restaurant = result["days"][0]["visits"][1]
        self.assertEqual(restaurant["address"], "강릉시 식당길 2")
        self.assertEqual(restaurant["operating_hours"], "11:00-21:00")
        self.assertIn("한식", restaurant["recommendation_reason"])
        self.assertEqual(
            result["source_ids"], ["destination:D1", "restaurant:R2"]
        )
        self.assertEqual(result["quality_score"], 91)

    def test_marks_unknown_policy_without_guessing(self) -> None:
        result = build_final_response(valid_state())  # type: ignore[arg-type]
        restaurant = result["days"][0]["visits"][1]

        self.assertIn("운영시간과 이용 가능 여부는 달라질 수 있으니", result["notices"][0])
        self.assertIsNone(restaurant["accessibility"]["indoor_pet_allowed"])
        self.assertIn("indoor_pet_allowed", restaurant["unverified_fields"])
        self.assertTrue(
            any("indoor_pet_allowed" in notice for notice in result["notices"])
        )

    def test_ready_response_always_includes_visit_confirmation_notice(self) -> None:
        result = build_final_response(valid_state())  # type: ignore[arg-type]

        self.assertIn("방문 전 한 번 더 확인", result["answer"])
        self.assertTrue(
            any("운영시간과 이용 가능 여부는 달라질 수 있으니" in notice for notice in result["notices"])
        )

    def test_success_response_explains_search_relaxation(self) -> None:
        state = valid_state()
        state["search_relaxations"] = [
            {
                "agent": "restaurant",
                "domain": "RESTAURANT",
                "slot": "D1_LUNCH",
                "retry_count": 2,
                "original_query": "해산물",
                "used_query": "맛집 음식 식당",
                "original_regions": ["GANGNEUNG"],
                "used_regions": ["GANGNEUNG", "DONGHAE"],
                "strategy": "EXPAND_TO_NEARBY_REGION",
                "reason": "음식점 후보가 부족해 요청 지역에서 인접 지역까지 검색 범위를 넓혔습니다.",
            }
        ]

        result = build_final_response(state)  # type: ignore[arg-type]

        self.assertEqual(result["response_status"], "READY")
        self.assertTrue(any("음식점 후보가 부족해" in notice for notice in result["notices"]))
        self.assertIn("시도한 보완", result["answer"])
        self.assertIn("인접 지역 후보", result["answer"])

    def test_does_not_publish_unvalidated_itinerary(self) -> None:
        for field, value in (
            ("itinerary_status", "NEEDS_CANDIDATES"),
            ("hard_validation", {"status": "INVALID"}),
            ("quality_validation", {"status": "REVISE"}),
        ):
            state = valid_state()
            state[field] = value
            result = build_final_response(state)  # type: ignore[arg-type]
            self.assertEqual(result["response_status"], "PENDING")
            self.assertEqual(result["days"], [])

    def test_failed_response_is_user_friendly(self) -> None:
        state = valid_state()
        state["status"] = "failed"
        state["itinerary_status"] = "NEEDS_CANDIDATES"
        state["missing_slots"] = ["D1_LUNCH", "D1_DINNER"]
        state["search_relaxations"] = [
            {
                "agent": "restaurant",
                "domain": "RESTAURANT",
                "slot": "D1_LUNCH",
                "retry_count": 1,
                "original_query": "해산물",
                "used_query": "해산물 맛집 음식 식당",
                "strategy": "EXPAND_QUERY_TEXT",
                "reason": "음식점 후보가 부족해 검색어를 넓혔습니다.",
            }
        ]
        state["search_diagnostics"] = [
            {
                "agent": "restaurant",
                "domain": "RESTAURANT",
                "slot": "D1_LUNCH",
                "retry_count": 1,
                "requested_limit": 32,
                "returned_count": 1,
                "unique_count": 1,
                "shortage": 2,
                "failure_reasons": ["LOW_RESULT_COUNT"],
                "counts": {},
                "suggested_actions": ["EXPAND_QUERY"],
            }
        ]

        result = build_final_response(state)  # type: ignore[arg-type]

        self.assertEqual(result["response_status"], "FAILED")
        self.assertEqual(result["days"], [])
        self.assertIn("요청 조건에 맞는 장소 후보가 부족해", result["summary"])
        self.assertIn("시도한 보완", result["answer"])
        self.assertIn("확인된 이유", result["answer"])
        self.assertIn("음식점 검색 결과가 필요한 수보다 2개 부족했습니다.", result["notices"])

    def test_failed_response_explains_pet_and_accessible_destination_shortage(self) -> None:
        state = valid_state()
        state["request"] = {
            "region": "속초",
            "travel_days": 2,
            "pet_allowed": True,
            "pet_size": "SMALL",
            "wheelchair_accessible": True,
        }
        state["status"] = "failed"
        state["itinerary_status"] = "NEEDS_CANDIDATES"
        state["missing_slots"] = ["D2_DESTINATION"]
        state["hard_validation"] = None
        state["quality_validation"] = None

        result = build_final_response(state)  # type: ignore[arg-type]

        self.assertEqual("FAILED", result["response_status"])
        self.assertTrue(
            any("반려동물 동반과 휠체어 이용 조건" in notice for notice in result["notices"])
        )
        self.assertIn("방문지를 줄이면", result["answer"])

    def test_missing_evidence_is_explicit(self) -> None:
        state = valid_state()
        visit = state["itinerary"][1]  # type: ignore[index]
        for field in ("address", "opens_at", "closes_at", "source_ids"):
            visit.pop(field, None)  # type: ignore[union-attr]
        result = build_final_response(state)  # type: ignore[arg-type]
        visit = result["days"][0]["visits"][0]

        self.assertIsNone(visit["address"])
        self.assertIn("address", visit["unverified_fields"])
        self.assertIn("source_ids", visit["unverified_fields"])
        self.assertEqual(visit["source_ids"], [])

    def test_uses_itinerary_start_and_end_time_when_iso_times_are_missing(self) -> None:
        state = valid_state()
        visit = state["itinerary"][1]  # type: ignore[index]
        visit.pop("start_at", None)  # type: ignore[union-attr]
        visit.pop("end_at", None)  # type: ignore[union-attr]
        visit["day"] = 1  # type: ignore[index]
        visit["start_time"] = "10:00"  # type: ignore[index]
        visit["end_time"] = "12:00"  # type: ignore[index]

        result = build_final_response(state)  # type: ignore[arg-type]

        self.assertEqual(result["days"][0]["visits"][0]["time"], "10:00-12:00")
        self.assertIn("- 10:00-12:00 바다 전망대", result["answer"])

    def test_response_node_does_not_mutate_input(self) -> None:
        state = valid_state()
        original = copy.deepcopy(state)
        result = response_node(state)  # type: ignore[arg-type]

        self.assertEqual(state, original)
        self.assertIn("final_response", result)

    def test_llm_renderer_can_replace_answer_only(self) -> None:
        with patch("app.agents.response.render_answer_with_llm", return_value="LLM 답변") as renderer:
            result = build_final_response(valid_state())  # type: ignore[arg-type]

        self.assertEqual(result["answer"], "LLM 답변")
        self.assertEqual(result["days"][0]["visits"][0]["place_id"], "D1")
        self.assertEqual(result["source_ids"], ["destination:D1", "restaurant:R2"])
        renderer.assert_called_once()

    def test_llm_renderer_uses_fallback_when_disabled(self) -> None:
        client = Mock()
        with patch.dict("os.environ", {"GANGWON_RESPONSE_LLM_ENABLED": ""}, clear=False):
            result = render_answer_with_llm(
                title="강릉 1일 여행 일정",
                summary="검증을 통과한 일정입니다.",
                days=[],
                notices=[],
                quality_score=91,
                source_ids=[],
                fallback_answer="기본 답변",
                client=client,
            )

        self.assertEqual(result, "기본 답변")
        client.create_answer.assert_not_called()

    def test_llm_renderer_uses_fallback_when_client_fails(self) -> None:
        client = Mock()
        client.create_answer.side_effect = RuntimeError("LLM failed")

        with patch.dict("os.environ", {"GANGWON_RESPONSE_LLM_ENABLED": "true"}, clear=False):
            result = render_answer_with_llm(
                title="강릉 1일 여행 일정",
                summary="검증을 통과한 일정입니다.",
                days=[],
                notices=[],
                quality_score=91,
                source_ids=[],
                fallback_answer="기본 답변",
                client=client,
            )

        self.assertEqual(result, "기본 답변")
        client.create_answer.assert_called_once()

    def test_llm_prompt_contains_safety_rules_and_grounded_input(self) -> None:
        client = Mock()
        client.create_answer.return_value = "LLM 답변"

        with patch.dict("os.environ", {"GANGWON_RESPONSE_LLM_ENABLED": "true"}, clear=False):
            result = render_answer_with_llm(
                title="강릉 1일 여행 일정",
                summary="검증을 통과한 일정입니다.",
                days=[
                    {
                        "day": 1,
                        "date": "2026-08-23",
                        "summary": "바다, 한식 중심의 1일차 코스",
                        "visits": [
                            {
                                "slot": "D1_DESTINATION",
                                "time": "10:00-12:00",
                                "place_id": "D1",
                                "name": "바다 전망대",
                                "category": "DESTINATION",
                                "address": "강릉시 바다길 1",
                                "recommendation_reason": "바다 조건과 일치합니다.",
                                "operating_hours": "09:00-18:00",
                                "accessibility": {
                                    "wheelchair_accessible": True,
                                    "pet_allowed": True,
                                    "indoor_pet_allowed": False,
                                    "max_pet_size": "LARGE",
                                },
                                "travel_minutes_from_previous": 0,
                                "unverified_fields": [],
                                "source_ids": ["destination:D1"],
                            }
                        ],
                    }
                ],
                notices=["저녁 식당: indoor_pet_allowed 정보는 확인되지 않았습니다."],
                quality_score=91,
                source_ids=["destination:D1"],
                fallback_answer="기본 답변",
                client=client,
            )

        call = client.create_answer.call_args.kwargs
        prompt = call["instructions"]
        payload = json.loads(call["input_text"])
        self.assertEqual(result, "LLM 답변")
        self.assertIn("장소를 추가", prompt)
        self.assertIn("일정을 바꾸지", prompt)
        self.assertIn("추정하지", prompt)
        self.assertIn("출처 ID", prompt)
        self.assertEqual(payload["days"][0]["visits"][0]["place_id"], "D1")
        self.assertEqual(payload["notices"][0], "저녁 식당: indoor_pet_allowed 정보는 확인되지 않았습니다.")
        self.assertEqual(payload["source_ids"], ["destination:D1"])

    def test_llm_renderer_accepts_natural_korean_answer_from_fake_client(self) -> None:
        llm_answer = (
            "강릉에서 반려견과 함께 바다 전망을 즐기고, 저녁에는 한식 식당으로 "
            "마무리하는 하루 일정입니다. 미확인 정보는 방문 전에 확인해 주세요."
        )
        client = Mock()
        client.create_answer.return_value = llm_answer

        with patch.dict("os.environ", {"GANGWON_RESPONSE_LLM_ENABLED": "true"}, clear=False):
            result = render_answer_with_llm(
                title="강릉 1일 여행 일정",
                summary="검증을 통과한 일정입니다.",
                days=[],
                notices=["저녁 식당: max_pet_size 정보는 확인되지 않았습니다."],
                quality_score=91,
                source_ids=["destination:D1", "restaurant:R2"],
                fallback_answer="기본 답변",
                client=client,
            )

        self.assertEqual(result, llm_answer)
        client.create_answer.assert_called_once()

    def test_response_preview_api_can_return_fake_llm_answer(self) -> None:
        with patch("app.agents.response.render_answer_with_llm", return_value="API LLM 답변"):
            response = TestClient(app).post(
                "/internal/travel/response/preview",
                json=preview_payload(),
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["answer"], "API LLM 답변")
        self.assertEqual(payload["response_status"], "READY")
        self.assertEqual(payload["days"][0]["visits"][0]["place_id"], "D1")
        self.assertEqual(payload["source_ids"], ["destination:D1", "restaurant:R2"])

    def test_separates_lodging_from_daily_visits(self) -> None:
        state = valid_state()
        state["request"]["travel_days"] = 2  # type: ignore[index]
        state["itinerary"].append(  # type: ignore[union-attr]
            {
                "slot": "D1_LODGING",
                "place_id": "L1",
                "name": "바다 숙소",
                "category": "LODGING",
                "start_time": "20:00",
                "end_time": "21:00",
                "travel_minutes_from_previous": 15,
                "source_ids": ["lodging:L1"],
                "tags": ["숙소"],
                "address": "강릉시 숙소길 3",
                "opens_at": "15:00",
                "closes_at": "23:00",
                "pet_allowed": True,
                "wheelchair_accessible": True,
                "indoor_pet_allowed": True,
                "max_pet_size": "SMALL",
                "recommendation_reason": "동선 중간에 묵기 좋은 숙소입니다.",
                "matched_conditions": ["숙소"],
            }
        )

        result = build_final_response(state)  # type: ignore[arg-type]

        daily_place_ids = [
            visit["place_id"]
            for day in result["days"]
            for visit in day["visits"]
        ]
        self.assertNotIn("L1", daily_place_ids)
        self.assertEqual("L1", result["accommodations"][0]["place_id"])
        self.assertIn("숙소 1개는 별도로 안내합니다.", result["summary"])


if __name__ == "__main__":
    unittest.main()

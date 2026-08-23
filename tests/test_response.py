from __future__ import annotations

import copy
import unittest

from app.agents.response import build_final_response, response_node


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


class ResponseAgentTests(unittest.TestCase):
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

        self.assertIsNone(restaurant["accessibility"]["indoor_pet_allowed"])
        self.assertIn("indoor_pet_allowed", restaurant["unverified_fields"])
        self.assertTrue(
            any("indoor_pet_allowed" in notice for notice in result["notices"])
        )

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

    def test_response_node_does_not_mutate_input(self) -> None:
        state = valid_state()
        original = copy.deepcopy(state)
        result = response_node(state)  # type: ignore[arg-type]

        self.assertEqual(state, original)
        self.assertIn("final_response", result)


if __name__ == "__main__":
    unittest.main()

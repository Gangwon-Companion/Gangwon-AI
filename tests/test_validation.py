from __future__ import annotations

import unittest

from app.agents.supervisor import MAX_VALIDATION_RETRIES, validation_retry_node
from app.agents.validation import evaluate_itinerary, validation_node
from app.validators.hard_validator import validate_itinerary


def slot(
    slot_id: str,
    place_id: str,
    start: str,
    end: str,
    *,
    category: str = "DESTINATION",
    travel: int = 0,
    tags: list[str] | None = None,
) -> dict[str, object]:
    return {
        "slot": slot_id,
        "place_id": place_id,
        "name": place_id,
        "category": category,
        "start_at": start,
        "end_at": end,
        "travel_minutes_from_previous": travel,
        "pet_allowed": True,
        "max_pet_size": "LARGE",
        "indoor_pet_allowed": True,
        "wheelchair_accessible": True,
        "opens_at": "09:00",
        "closes_at": "22:00",
        "source_ids": [f"source:{place_id}"],
        "tags": tags or [],
    }


class HardValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = {
            "pet_allowed": True,
            "pet_size": "LARGE",
            "indoor_pet": True,
            "wheelchair_accessible": True,
        }

    def test_valid_itinerary_passes(self) -> None:
        itinerary = [
            slot("D1_DESTINATION", "P1", "2026-08-23T10:00:00+09:00", "2026-08-23T11:00:00+09:00")
        ]
        result = validate_itinerary(self.request, itinerary)  # type: ignore[arg-type]
        self.assertEqual("VALID", result["status"])
        self.assertEqual([], result["violations"])

    def test_policy_and_missing_evidence_fail(self) -> None:
        denied = slot("D1_LUNCH", "R1", "2026-08-23T12:00:00+09:00", "2026-08-23T13:00:00+09:00", category="RESTAURANT")
        denied["max_pet_size"] = "SMALL"
        missing = slot("D1_DINNER", "R2", "2026-08-23T18:00:00+09:00", "2026-08-23T19:00:00+09:00", category="RESTAURANT")
        missing["source_ids"] = []
        result = validate_itinerary(self.request, [denied, missing])  # type: ignore[arg-type]
        codes = {item["code"] for item in result["violations"]}
        self.assertIn("PET_SIZE_NOT_ALLOWED", codes)
        self.assertIn("EVIDENCE_MISSING", codes)
        self.assertTrue(all(action["agent"] == "restaurant" for action in result["next_actions"]))

    def test_time_travel_and_duplicate_fail(self) -> None:
        first = slot("D1_DESTINATION", "P1", "2026-08-23T10:00:00+09:00", "2026-08-23T11:00:00+09:00")
        second = slot("D1_LUNCH", "P1", "2026-08-23T11:20:00+09:00", "2026-08-23T12:00:00+09:00", category="RESTAURANT", travel=30)
        second["opens_at"] = "12:00"
        result = validate_itinerary({}, [first, second])  # type: ignore[arg-type]
        codes = {item["code"] for item in result["violations"]}
        self.assertEqual(
            {"OUTSIDE_OPERATING_HOURS", "TRAVEL_TIME_INFEASIBLE", "DUPLICATE_PLACE"},
            codes,
        )

    def test_allows_same_lodging_for_consecutive_nights(self) -> None:
        first = slot(
            "D1_LODGING", "L1", "2026-08-23T20:00:00+09:00",
            "2026-08-23T21:00:00+09:00", category="LODGING"
        )
        second = slot(
            "D2_LODGING", "L1", "2026-08-24T20:00:00+09:00",
            "2026-08-24T21:00:00+09:00", category="LODGING"
        )

        result = validate_itinerary({}, [first, second])  # type: ignore[arg-type]

        self.assertEqual("VALID", result["status"])


class QualityValidationTests(unittest.TestCase):
    def test_quality_issues_request_revision(self) -> None:
        itinerary = [
            slot("D1_DESTINATION", "P1", "2026-08-23T10:00:00+09:00", "2026-08-23T11:00:00+09:00", tags=["바다"]),
            slot("D1_LUNCH", "R1", "2026-08-23T15:00:00+09:00", "2026-08-23T16:00:00+09:00", category="RESTAURANT", travel=120),
        ]
        state = {
            "itinerary": itinerary,
            "preference_profile": {"keywords": ["바다", "카페", "산책"]},
        }
        result = evaluate_itinerary(state)  # type: ignore[arg-type]
        issue_types = {item["type"] for item in result["issues"]}
        self.assertEqual("REVISE", result["status"])
        self.assertIn("ROUTE_INEFFICIENCY", issue_types)
        self.assertIn("MEAL_TIME_INAPPROPRIATE", issue_types)
        self.assertIn("PREFERENCE_UNDERREFLECTED", issue_types)

    def test_validation_requires_hard_validator_pass(self) -> None:
        with self.assertRaises(ValueError):
            validation_node({"itinerary": []})  # type: ignore[arg-type]


class SupervisorRetryTests(unittest.TestCase):
    def test_builds_partial_retry_plan(self) -> None:
        state = {
            "retry_count": 0,
            "retry_actions": [
                {"agent": "restaurant", "slots": ["D1_LUNCH"], "instruction": "다시 검색"}
            ],
        }
        result = validation_retry_node(state)  # type: ignore[arg-type]
        agents = [step["agent"] for step in result["execution_plan"]]
        self.assertEqual(
            ["restaurant", "itinerary", "validator", "validation"], agents
        )
        self.assertEqual(1, result["retry_count"])

    def test_stops_after_retry_limit(self) -> None:
        result = validation_retry_node(
            {"retry_count": MAX_VALIDATION_RETRIES, "retry_actions": []}  # type: ignore[arg-type]
        )
        self.assertEqual("failed", result["status"])


if __name__ == "__main__":
    unittest.main()

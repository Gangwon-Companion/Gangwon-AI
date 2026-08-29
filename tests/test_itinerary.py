from __future__ import annotations

import unittest

from app.agents.itinerary import itinerary_node
from app.tools.itinerary_optimizer import (
    OptimizerCandidate,
    SlotSpec,
    optimize_itinerary,
)


def candidate(
    place_id: str,
    category: str,
    score: float,
    *,
    opens_at: str | None = None,
    closes_at: str | None = None,
) -> OptimizerCandidate:
    return OptimizerCandidate(
        place_id=place_id,
        name=place_id,
        category=category,
        score=score,
        opens_at=opens_at,
        closes_at=closes_at,
        source_ids=(f"source:{place_id}",),
    )


class OptimizerTests(unittest.TestCase):
    def test_selects_highest_scoring_combination(self) -> None:
        slots = [
            SlotSpec("D1_DESTINATION", 1, "DESTINATION", "10:00", 120),
            SlotSpec("D1_LUNCH", 1, "RESTAURANT", "12:30", 60),
        ]
        candidates = {
            "D1_DESTINATION": [
                candidate("D1", "DESTINATION", 0.9),
                candidate("D2", "DESTINATION", 0.7),
            ],
            "D1_LUNCH": [
                candidate("R1", "RESTAURANT", 0.8),
                candidate("R2", "RESTAURANT", 0.6),
            ],
        }
        plans, missing = optimize_itinerary(slots, candidates)
        self.assertEqual([], missing)
        self.assertEqual(["D1", "R1"], [visit.place_id for visit in plans[0].visits])
        self.assertLessEqual(len(plans), 3)

    def test_filters_closed_candidate(self) -> None:
        slots = [SlotSpec("D1_LUNCH", 1, "RESTAURANT", "12:30", 60)]
        candidates = {
            "D1_LUNCH": [
                candidate("CLOSED", "RESTAURANT", 1.0, opens_at="18:00", closes_at="22:00"),
                candidate("OPEN", "RESTAURANT", 0.8, opens_at="09:00", closes_at="21:00"),
            ]
        }
        plans, missing = optimize_itinerary(slots, candidates)
        self.assertEqual([], missing)
        self.assertEqual("OPEN", plans[0].visits[0].place_id)

    def test_does_not_repeat_same_place(self) -> None:
        slots = [
            SlotSpec("D1_LUNCH", 1, "RESTAURANT", "12:30", 60),
            SlotSpec("D1_DINNER", 1, "RESTAURANT", "18:00", 90),
        ]
        candidates = {
            "D1_LUNCH": [candidate("R1", "RESTAURANT", 0.9)],
            "D1_DINNER": [candidate("R1", "RESTAURANT", 0.9)],
        }
        plans, missing = optimize_itinerary(slots, candidates)
        self.assertEqual([], plans)
        self.assertEqual(["D1_DINNER"], missing)

    def test_allows_same_restaurant_on_different_days(self) -> None:
        slots = [
            SlotSpec("D1_LUNCH", 1, "RESTAURANT", "12:30", 60),
            SlotSpec("D2_LUNCH", 2, "RESTAURANT", "12:30", 60),
        ]
        restaurant = candidate("R1", "RESTAURANT", 0.9)
        plans, missing = optimize_itinerary(
            slots,
            {"D1_LUNCH": [restaurant], "D2_LUNCH": [restaurant]},
        )
        self.assertEqual([], missing)
        self.assertEqual(["R1", "R1"], [visit.place_id for visit in plans[0].visits])

    def test_reports_empty_slot(self) -> None:
        slots = [SlotSpec("D1_LODGING", 1, "LODGING", "20:00", 60)]
        plans, missing = optimize_itinerary(slots, {"D1_LODGING": []})
        self.assertEqual([], plans)
        self.assertEqual(["D1_LODGING"], missing)

    def test_allows_same_lodging_for_consecutive_nights(self) -> None:
        slots = [
            SlotSpec("D1_LODGING", 1, "LODGING", "20:00", 60),
            SlotSpec("D2_LODGING", 2, "LODGING", "20:00", 60),
        ]
        lodging = candidate("L1", "LODGING", 0.9)
        plans, missing = optimize_itinerary(
            slots,
            {"D1_LODGING": [lodging], "D2_LODGING": [lodging]},
        )
        self.assertEqual([], missing)
        self.assertEqual(["L1", "L1"], [visit.place_id for visit in plans[0].visits])


class ItineraryAgentTests(unittest.TestCase):
    def test_builds_itinerary_from_agent_candidates(self) -> None:
        state = {
            "slots": ["D1_DESTINATION", "D1_LUNCH", "D1_DINNER"],
            "preference_profile": {"keywords": ["바다"]},
            "destination_candidates": [
                {
                    "destination_id": 1,
                    "title": "경포해변",
                    "map_x": 128.90,
                    "map_y": 37.80,
                    "theme_code": "바다",
                    "source_types": ["KOREAN"],
                    "score": 0.9,
                }
            ],
            "restaurant_candidates": [
                {
                    "place_id": "R1",
                    "name": "점심 식당",
                    "score": 0.9,
                    "status": "OK",
                    "cuisine": ["KOREAN"],
                    "address": "강릉시 중앙로 1",
                    "opens_at": "09:00",
                    "closes_at": "21:00",
                    "pet_allowed": True,
                    "wheelchair_accessible": True,
                    "reason": "한식 선호와 일치합니다.",
                    "matched_conditions": ["한식"],
                    "source_ids": ["restaurant:R1"],
                },
                {
                    "place_id": "R2",
                    "name": "저녁 식당",
                    "score": 0.8,
                    "status": "OK",
                    "cuisine": ["SEAFOOD"],
                },
            ],
        }
        result = itinerary_node(state)  # type: ignore[arg-type]
        self.assertEqual("READY", result["itinerary_status"])
        self.assertEqual(3, len(result["itinerary"]))
        self.assertEqual([], result["missing_slots"])
        restaurant = next(
            item for item in result["itinerary"] if item["place_id"] == "R1"
        )
        self.assertEqual(restaurant["address"], "강릉시 중앙로 1")
        self.assertEqual(restaurant["opens_at"], "09:00")
        self.assertTrue(restaurant["pet_allowed"])
        self.assertEqual(restaurant["source_ids"], ["restaurant:R1"])
        self.assertEqual(restaurant["matched_conditions"], ["한식"])

    def test_requests_only_missing_domain(self) -> None:
        state = {
            "slots": ["D1_DESTINATION", "D1_LUNCH"],
            "destination_candidates": [
                {
                    "destination_id": 1,
                    "title": "경포해변",
                    "source_types": ["KOREAN"],
                    "score": 0.9,
                }
            ],
            "restaurant_candidates": [],
        }
        result = itinerary_node(state)  # type: ignore[arg-type]
        self.assertEqual("NEEDS_CANDIDATES", result["itinerary_status"])
        self.assertEqual(["D1_LUNCH"], result["missing_slots"])
        self.assertEqual("restaurant", result["retry_actions"][0]["agent"])


if __name__ == "__main__":
    unittest.main()

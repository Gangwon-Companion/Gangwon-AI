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
    tags: tuple[str, ...] = (),
    matched_conditions: tuple[str, ...] = (),
    pet_allowed: bool | None = None,
    wheelchair_accessible: bool | None = None,
) -> OptimizerCandidate:
    return OptimizerCandidate(
        place_id=place_id,
        name=place_id,
        category=category,
        score=score,
        opens_at=opens_at,
        closes_at=closes_at,
        source_ids=(f"source:{place_id}",),
        tags=tags,
        matched_conditions=matched_conditions,
        pet_allowed=pet_allowed,
        wheelchair_accessible=wheelchair_accessible,
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

    def test_does_not_repeat_same_restaurant_on_different_days(self) -> None:
        slots = [
            SlotSpec("D1_LUNCH", 1, "RESTAURANT", "12:30", 60),
            SlotSpec("D2_LUNCH", 2, "RESTAURANT", "12:30", 60),
        ]
        restaurant = candidate("R1", "RESTAURANT", 0.9)
        plans, missing = optimize_itinerary(
            slots,
            {"D1_LUNCH": [restaurant], "D2_LUNCH": [restaurant]},
        )
        self.assertEqual([], plans)
        self.assertEqual(["D2_LUNCH"], missing)

    def test_uses_alternative_restaurant_to_avoid_repetition(self) -> None:
        slots = [
            SlotSpec("D1_LUNCH", 1, "RESTAURANT", "12:30", 60),
            SlotSpec("D2_LUNCH", 2, "RESTAURANT", "12:30", 60),
        ]
        plans, missing = optimize_itinerary(
            slots,
            {
                "D1_LUNCH": [candidate("R1", "RESTAURANT", 0.9)],
                "D2_LUNCH": [
                    candidate("R1", "RESTAURANT", 0.95),
                    candidate("R2", "RESTAURANT", 0.7),
                ],
            },
        )
        self.assertEqual([], missing)
        self.assertEqual(["R1", "R2"], [visit.place_id for visit in plans[0].visits])

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

    def test_can_require_different_lodgings_when_requested(self) -> None:
        slots = [
            SlotSpec("D1_LODGING", 1, "LODGING", "20:00", 60),
            SlotSpec("D2_LODGING", 2, "LODGING", "20:00", 60),
        ]
        plans, missing = optimize_itinerary(
            slots,
            {
                "D1_LODGING": [
                    candidate("L1", "LODGING", 0.9),
                    candidate("L2", "LODGING", 0.7),
                ],
                "D2_LODGING": [
                    candidate("L1", "LODGING", 0.9),
                    candidate("L2", "LODGING", 0.7),
                ],
            },
            allow_lodging_repeats=False,
        )

        self.assertEqual([], missing)
        self.assertEqual(["L1", "L2"], [visit.place_id for visit in plans[0].visits])

    def test_filters_required_policy_unknown_candidates_before_validation(self) -> None:
        slots = [SlotSpec("D1_DESTINATION", 1, "DESTINATION", "10:00", 120)]
        plans, missing = optimize_itinerary(
            slots,
            {
                "D1_DESTINATION": [
                    candidate("UNKNOWN", "DESTINATION", 1.0, wheelchair_accessible=None),
                    candidate("ACCESSIBLE", "DESTINATION", 0.6, wheelchair_accessible=True),
                ]
            },
            required_policy={"wheelchair_accessible": True},
        )

        self.assertEqual([], missing)
        self.assertEqual("ACCESSIBLE", plans[0].visits[0].place_id)

    def test_prefers_direct_keyword_match_over_generic_high_score_candidate(self) -> None:
        slots = [SlotSpec("D1_LUNCH", 1, "RESTAURANT", "12:30", 60)]
        plans, missing = optimize_itinerary(
            slots,
            {
                "D1_LUNCH": [
                    candidate("GENERAL", "RESTAURANT", 0.95, tags=("맛집",)),
                    candidate("MULHOE", "RESTAURANT", 0.75, tags=("물회", "회")),
                ]
            },
            preferences=["물회", "회"],
        )

        self.assertEqual([], missing)
        self.assertEqual("MULHOE", plans[0].visits[0].place_id)


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

    def test_filters_cafes_out_of_meal_slots(self) -> None:
        state = {
            "slots": ["D1_LUNCH", "D1_CAFE"],
            "restaurant_candidates": [
                {
                    "place_id": "C1",
                    "name": "바다 카페",
                    "score": 0.95,
                    "status": "OK",
                    "cuisine": ["카페"],
                },
                {
                    "place_id": "R1",
                    "name": "해산물 식당",
                    "score": 0.8,
                    "status": "OK",
                    "cuisine": ["해산물"],
                },
            ],
        }

        result = itinerary_node(state)  # type: ignore[arg-type]

        self.assertEqual("READY", result["itinerary_status"])
        by_slot = {item["slot"]: item for item in result["itinerary"]}
        self.assertEqual("R1", by_slot["D1_LUNCH"]["place_id"])
        self.assertEqual("C1", by_slot["D1_CAFE"]["place_id"])
        self.assertEqual("CAFE", by_slot["D1_CAFE"]["subtype"])

    def test_extra_destination_slot_uses_destination_candidates(self) -> None:
        state = {
            "slots": ["D1_DESTINATION", "D1_EXTRA_DESTINATION"],
            "destination_candidates": [
                {
                    "destination_id": 1,
                    "title": "경포해변",
                    "source_types": ["KOREAN"],
                    "score": 0.9,
                },
                {
                    "destination_id": 2,
                    "title": "오죽헌",
                    "source_types": ["KOREAN"],
                    "score": 0.8,
                },
            ],
        }

        result = itinerary_node(state)  # type: ignore[arg-type]

        self.assertEqual("READY", result["itinerary_status"])
        self.assertEqual(
            ["D1_DESTINATION", "D1_EXTRA_DESTINATION"],
            [item["slot"] for item in result["itinerary"]],
        )
        self.assertEqual(
            ["10:00", "15:00"],
            [item["start_time"] for item in result["itinerary"]],
        )

    def test_itinerary_excludes_unknown_required_policy_candidates(self) -> None:
        state = {
            "request": {"wheelchair_accessible": True},
            "slots": ["D1_DESTINATION"],
            "destination_candidates": [
                {
                    "destination_id": 1,
                    "title": "근거 없는 해변",
                    "source_types": ["TOUR_API"],
                    "score": 1.0,
                    "wheelchair_accessible": None,
                },
                {
                    "destination_id": 2,
                    "title": "휠체어 접근 가능 해변",
                    "source_types": ["TOUR_API"],
                    "score": 0.6,
                    "wheelchair_accessible": True,
                },
            ],
        }

        result = itinerary_node(state)  # type: ignore[arg-type]

        self.assertEqual("READY", result["itinerary_status"])
        self.assertEqual("D2", result["itinerary"][0]["place_id"])

    def test_itinerary_allows_unknown_restaurant_policy_when_domain_has_no_data(self) -> None:
        state = {
            "request": {"pet_allowed": True, "pet_size": "SMALL", "wheelchair_accessible": True},
            "slots": ["D1_DESTINATION", "D1_LUNCH"],
            "destination_candidates": [
                {
                    "destination_id": 1,
                    "title": "반려동물 가능 해변",
                    "source_types": ["TOUR_API"],
                    "score": 0.8,
                    "pet_allowed": True,
                    "wheelchair_accessible": True,
                },
            ],
            "restaurant_candidates": [
                {
                    "place_id": "R1",
                    "name": "정책 데이터 없는 식당",
                    "score": 0.8,
                    "status": "OK",
                    "source_ids": ["restaurant:R1"],
                    "pet_allowed": None,
                    "wheelchair_accessible": None,
                },
            ],
        }

        result = itinerary_node(state)  # type: ignore[arg-type]

        self.assertEqual("READY", result["itinerary_status"])
        by_slot = {item["slot"]: item for item in result["itinerary"]}
        self.assertEqual("R1", by_slot["D1_LUNCH"]["place_id"])

    def test_itinerary_uses_different_lodgings_for_multiple_lodging_slots(self) -> None:
        state = {
            "slots": ["D1_LODGING", "D2_LODGING"],
            "lodging_candidates": [
                {
                    "place_id": "L1",
                    "name": "첫 번째 숙소",
                    "score": 0.9,
                    "status": "OK",
                    "source_ids": ["lodging:L1"],
                },
                {
                    "place_id": "L2",
                    "name": "두 번째 숙소",
                    "score": 0.7,
                    "status": "OK",
                    "source_ids": ["lodging:L2"],
                },
            ],
        }

        result = itinerary_node(state)  # type: ignore[arg-type]

        self.assertEqual("READY", result["itinerary_status"])
        self.assertEqual(
            ["L1", "L2"],
            [item["place_id"] for item in result["itinerary"]],
        )


if __name__ == "__main__":
    unittest.main()

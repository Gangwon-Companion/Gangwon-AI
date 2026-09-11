from __future__ import annotations

import unittest

from app.agents.supervisor import supervisor_node


class SupervisorSlotTests(unittest.TestCase):
    def test_default_slots_use_lunch_dinner_and_one_or_two_destinations(self) -> None:
        result = supervisor_node(
            {
                "request": {
                    "message": "강릉으로 1일 여행가고 싶어.",
                    "region": "강릉",
                    "travel_days": 1,
                },
                "preference_profile": {"keywords": []},
            }  # type: ignore[arg-type]
        )

        self.assertEqual(
            ["D1_DESTINATION", "D1_LUNCH", "D1_EXTRA_DESTINATION", "D1_DINNER"],
            result["slots"],
        )

    def test_cafe_request_replaces_optional_destination_slot(self) -> None:
        result = supervisor_node(
            {
                "request": {
                    "message": "강릉에서 바다 보고 카페도 가고 싶어.",
                    "region": "강릉",
                    "travel_days": 1,
                    "preferences": ["바다", "카페"],
                },
                "preference_profile": {"keywords": ["바다", "카페"]},
            }  # type: ignore[arg-type]
        )

        self.assertEqual(
            ["D1_DESTINATION", "D1_LUNCH", "D1_CAFE", "D1_DINNER"],
            result["slots"],
        )

    def test_deprioritized_cafe_request_keeps_destination_slot(self) -> None:
        result = supervisor_node(
            {
                "request": {
                    "message": "카페보다는 관광지 위주로 보고 싶어.",
                    "region": "강릉",
                    "travel_days": 1,
                    "preferences": ["관광지"],
                },
                "preference_profile": {"keywords": ["관광지"]},
            }  # type: ignore[arg-type]
        )

        self.assertEqual(
            ["D1_DESTINATION", "D1_LUNCH", "D1_EXTRA_DESTINATION", "D1_DINNER"],
            result["slots"],
        )

    def test_simple_lunch_first_request_changes_slot_order(self) -> None:
        result = supervisor_node(
            {
                "request": {
                    "message": "점심 먹고 카페 갔다가 바다 보고 저녁 먹고 싶어.",
                    "region": "강릉",
                    "travel_days": 1,
                    "preferences": ["카페", "바다"],
                },
                "preference_profile": {"keywords": ["카페", "바다"]},
            }  # type: ignore[arg-type]
        )

        self.assertEqual(
            ["D1_LUNCH", "D1_CAFE", "D1_DESTINATION", "D1_DINNER"],
            result["slots"],
        )

    def test_lodging_stays_as_internal_slot_for_multi_day_trip(self) -> None:
        result = supervisor_node(
            {
                "request": {"region": "강릉", "travel_days": 3},
                "preference_profile": {"keywords": []},
            }  # type: ignore[arg-type]
        )

        self.assertIn("D1_LODGING", result["slots"])
        self.assertNotIn("D2_LODGING", result["slots"])

    def test_multiple_lodging_request_adds_lodging_per_night(self) -> None:
        result = supervisor_node(
            {
                "request": {
                    "message": "속초로 3일 여행 갈 건데 매일 다른 숙소에서 자고 싶어.",
                    "region": "속초",
                    "travel_days": 3,
                },
                "preference_profile": {"keywords": ["숙소"]},
            }  # type: ignore[arg-type]
        )

        self.assertIn("D1_LODGING", result["slots"])
        self.assertIn("D2_LODGING", result["slots"])
        self.assertNotIn("D3_LODGING", result["slots"])

    def test_different_lodging_by_day_request_adds_lodging_per_night(self) -> None:
        result = supervisor_node(
            {
                "request": {
                    "message": (
                        "강릉으로 3일 여행 갈거야. 바다가 보고 싶고 맛있는 해산물도 많이 먹고 싶어. "
                        "반려동물은 없어. 첫째날이랑 둘째날 머물 숙소를 다르게 하고 싶어"
                    ),
                    "region": "강릉",
                    "travel_days": 3,
                },
                "preference_profile": {"keywords": ["바다", "해산물"]},
            }  # type: ignore[arg-type]
        )

        self.assertIn("D1_LODGING", result["slots"])
        self.assertIn("D2_LODGING", result["slots"])
        self.assertNotIn("D3_LODGING", result["slots"])


if __name__ == "__main__":
    unittest.main()

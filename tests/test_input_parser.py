from __future__ import annotations

import unittest

from app.agents.input_parser import form_binder_node, preference_extractor_node


class PreferenceExtractorTests(unittest.TestCase):
    def test_extracts_korean_day_words(self) -> None:
        cases = [
            ("강릉으로 하루 여행 갈 거야. 반려동물은 없어.", 1, 0),
            ("강릉으로 이틀 여행 갈 거야. 반려동물은 없어.", 2, None),
            ("강릉으로 1일 여행 갈 거야. 반려동물은 없어.", 1, None),
            ("강릉 당일치기 여행 갈 거야. 반려동물은 없어.", 1, 0),
        ]

        for message, expected_days, expected_nights in cases:
            with self.subTest(message=message):
                result = form_binder_node(
                    {
                        "request": {
                            "message": message,
                            "region": None,
                            "travel_days": None,
                            "nights": None,
                            "pet_allowed": None,
                        }
                    }  # type: ignore[arg-type]
                )

                self.assertEqual(result["request"]["travel_days"], expected_days)
                self.assertEqual(result["request"]["nights"], expected_nights)

    def test_pet_size_with_companion_context_sets_pet_allowed(self) -> None:
        result = form_binder_node(
            {
                "request": {
                    "message": "강릉으로 이틀 여행 갈 거야. 소형견이랑 같이 바다 산책하고 싶어.",
                    "region": None,
                    "travel_days": None,
                    "nights": None,
                    "pet_allowed": None,
                    "pet_size": None,
                }
            }  # type: ignore[arg-type]
        )

        self.assertTrue(result["request"]["pet_allowed"])
        self.assertEqual(result["request"]["pet_size"], "SMALL")

    def test_extracts_food_and_scenery_preferences_from_natural_language(self) -> None:
        result = preference_extractor_node(
            {
                "request": {
                    "message": "강릉으로 4일 여행갈거야. 바다가 보고 싶어. 맛있는 해산물도 먹고 싶어.",
                    "preferences": [],
                }
            }  # type: ignore[arg-type]
        )

        self.assertEqual(result["request"]["preferences"], ["바다", "해산물"])
        self.assertEqual(result["preference_profile"]["keywords"], ["바다", "해산물"])
        self.assertEqual(result["preference_profile"]["soft"]["oceanView"], 0.9)
        self.assertEqual(result["preference_profile"]["soft"]["food"], 0.9)

    def test_extracts_common_gangwon_travel_preferences(self) -> None:
        result = preference_extractor_node(
            {
                "request": {
                    "message": "오션뷰 숙소에서 쉬고, 물회랑 막국수 먹고, 케이블카도 타고 싶어.",
                    "preferences": [],
                }
            }  # type: ignore[arg-type]
        )

        keywords = result["preference_profile"]["keywords"]
        soft = result["preference_profile"]["soft"]
        self.assertIn("오션뷰", keywords)
        self.assertIn("물회", keywords)
        self.assertIn("막국수", keywords)
        self.assertIn("케이블카", keywords)
        self.assertEqual(soft["oceanView"], 0.9)
        self.assertEqual(soft["food"], 0.9)
        self.assertEqual(soft["nature"], 0.85)

    def test_preserves_existing_form_preferences(self) -> None:
        result = preference_extractor_node(
            {
                "request": {
                    "message": "바다도 보고 싶어.",
                    "preferences": ["한식"],
                }
            }  # type: ignore[arg-type]
        )

        self.assertEqual(result["request"]["preferences"], ["한식", "바다"])
        self.assertEqual(result["preference_profile"]["soft"]["food"], 0.8)
        self.assertEqual(result["preference_profile"]["soft"]["oceanView"], 0.9)

    def test_ignores_deprioritized_cafe_preference(self) -> None:
        result = preference_extractor_node(
            {
                "request": {
                    "message": "카페보다는 관광지 위주로 보고 싶고 저녁은 해산물 먹고 싶어.",
                    "preferences": [],
                }
            }  # type: ignore[arg-type]
        )

        self.assertNotIn("카페", result["request"]["preferences"])
        self.assertIn("관광지", result["request"]["preferences"])
        self.assertIn("해산물", result["request"]["preferences"])


if __name__ == "__main__":
    unittest.main()

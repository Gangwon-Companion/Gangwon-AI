from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from app.agents.answer_grounding import validate_final_answer
from app.agents.response_llm import render_answer_with_llm


class AnswerGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.days = [{
            "day": 1,
            "visits": [{
                "place_id": "RESTAURANT:101",
                "source_ids": ["RESTAURANT:101"],
                "time": "12:00-13:00",
                "operating_hours": "11:00-21:00",
                "travel_minutes_from_previous": 20,
            }],
        }]

    def test_accepts_grounded_place_and_time(self) -> None:
        ok, reason = validate_final_answer(
            "RESTAURANT:101 방문 시간은 12:00이며 운영시간은 11:00-21:00입니다.",
            days=self.days,
            notices=[],
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_rejects_unknown_place_id(self) -> None:
        ok, reason = validate_final_answer(
            "RESTAURANT:999를 추천합니다.", days=self.days, notices=[]
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_place_id")

    def test_accepts_a_new_domain_id_without_code_changes(self) -> None:
        days = [{"visits": [{"place_id": "ACTIVITY:42", "source_ids": ["ACTIVITY:42"]}]}]
        ok, reason = validate_final_answer(
            "ACTIVITY:42를 일정에 포함합니다.", days=days, notices=[]
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_rejects_unknown_new_domain_id(self) -> None:
        days = [{"visits": [{"place_id": "ACTIVITY:42", "source_ids": ["ACTIVITY:42"]}]}]
        ok, reason = validate_final_answer(
            "ACTIVITY:99를 일정에 포함합니다.", days=days, notices=[]
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_place_id")

    def test_rejects_unknown_time(self) -> None:
        ok, reason = validate_final_answer(
            "RESTAURANT:101 방문 시간은 22:00입니다.",
            days=self.days,
            notices=[],
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_time")

    def test_checks_accommodation_grounding(self) -> None:
        accommodations = [{
            "place_id": "LODGING:7",
            "source_ids": ["LODGING:7"],
            "time": "15:00-11:00",
            "operating_hours": "15:00-11:00",
        }]
        ok, reason = validate_final_answer(
            "숙소는 LODGING:7이며 체크인은 15:00입니다.",
            days=[],
            notices=[],
            accommodations=accommodations,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

        ok, reason = validate_final_answer(
            "숙소는 LODGING:99입니다.",
            days=[],
            notices=[],
            accommodations=accommodations,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_place_id")

    def test_rejects_unknown_number(self) -> None:
        ok, reason = validate_final_answer(
            "RESTAURANT:101까지 이동시간은 99분입니다.",
            days=self.days,
            notices=[],
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_number")

    def test_renderer_falls_back_for_unknown_place(self) -> None:
        client = Mock()
        client.create_answer.return_value = "ACTIVITY:999를 추천합니다."
        with patch.dict("os.environ", {"GANGWON_RESPONSE_LLM_ENABLED": "true"}, clear=False):
            result = render_answer_with_llm(
                title="강원 여행 일정",
                summary="검증된 일정",
                days=self.days,
                notices=[],
                quality_score=90,
                source_ids=["RESTAURANT:101"],
                fallback_answer="검증된 일정만 안내합니다.",
                client=client,
            )
        self.assertEqual(result, "검증된 일정만 안내합니다.")


    def test_renderer_accepts_structured_grounded_answer(self) -> None:
        client = Mock()
        client.create_answer.return_value = json.dumps({
            "answer": "RESTAURANT:101의 운영시간은 11:00-21:00입니다.",
            "claims": [{
                "text": "운영시간",
                "place_id": "RESTAURANT:101",
                "evidence_fields": ["operating_hours"],
                "evidence": [{"field": "operating_hours", "value": "11:00-21:00"}],
                "confidence": "SUPPORTED",
            }],
            "uncertainties": [],
        }, ensure_ascii=False)
        with patch.dict("os.environ", {"GANGWON_RESPONSE_LLM_ENABLED": "true"}, clear=False):
            result = render_answer_with_llm(
                title="여행 일정",
                summary="검증된 일정",
                days=self.days,
                notices=[],
                quality_score=90,
                source_ids=["RESTAURANT:101"],
                fallback_answer="fallback",
                client=client,
            )
        self.assertIn("RESTAURANT:101", result)


if __name__ == "__main__":
    unittest.main()

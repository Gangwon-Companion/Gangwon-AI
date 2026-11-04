from __future__ import annotations

import unittest

from app.agents.rag_context import build_rag_context


class RagContextTests(unittest.TestCase):
    def test_builds_only_selected_itinerary_documents(self) -> None:
        context = build_rag_context(
            days=[{
                "visits": [{
                    "place_id": "D369",
                    "name": "정동진항",
                    "address": "강릉시",
                    "operating_hours": "00:00-22:00",
                    "accessibility": {"pet_allowed": True, "wheelchair_accessible": None},
                    "unverified_fields": ["wheelchair_accessible"],
                    "source_ids": ["destination:369"],
                }]
            }],
            accommodations=[],
            notices=["방문 전 확인"],
        )

        self.assertEqual(["D369"], [item["document_id"] for item in context["documents"]])
        document = context["documents"][0]
        self.assertEqual("00:00-22:00", document["content"]["operating_hours"])
        self.assertNotIn("wheelchair_accessible", document["content"].get("accessibility", {}))
        self.assertNotIn("unverified_fields", document["evidence"])
        self.assertEqual(["방문 전 확인"], context["notices"])

    def test_deduplicates_place_documents(self) -> None:
        visit = {"place_id": "RESTAURANT:1", "source_ids": ["restaurant:1"]}
        context = build_rag_context(days=[{"visits": [visit]}], accommodations=[visit])
        self.assertEqual(1, len(context["documents"]))


if __name__ == "__main__":
    unittest.main()

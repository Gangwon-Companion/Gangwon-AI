from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.input_parser import preference_extractor_node
from app.agents.supervisor import supervisor_node
from app.graph import travel_graph
from app.search.models import (
    Evidence,
    Location,
    PlaceDomain,
    SearchCandidate,
    SearchResponse,
    SearchStatus,
)


def _response(domain: PlaceDomain, count: int) -> SearchResponse:
    return SearchResponse(
        results=[
            SearchCandidate(
                place_id=f"{domain.value}:{index}",
                domain=domain,
                name=f"{domain.value}-{index}",
                address="Gangwon",
                location=Location(
                    lat=37.75 + index * 0.001,
                    lon=128.88 + index * 0.001,
                ),
                distance_km=float(index),
                score=1.0 - index * 0.01,
                status=SearchStatus.OK,
                evidence=[
                    Evidence(field="opens_at", value="07:00", source="FIXTURE"),
                    Evidence(field="closes_at", value="23:00", source="FIXTURE"),
                ],
            )
            for index in range(1, count + 1)
        ]
    )


class TravelGraphIntegrationTests(unittest.TestCase):
    def test_experience_preferences_are_handled_by_destination_agent(self) -> None:
        parsed = preference_extractor_node(
            {"request": {"message": "체험과 레저 중심 여행", "preferences": []}}
        )
        planned = supervisor_node(
            {
                "request": {"region": "GANGNEUNG", "travel_days": 1},
                "preference_profile": parsed["preference_profile"],
            }
        )

        self.assertIn("체험", parsed["preference_profile"]["keywords"])
        self.assertIn("레저", parsed["preference_profile"]["keywords"])
        self.assertEqual(["destination", "restaurant"], planned["selected_agents"])
        self.assertEqual(
            ["D1_DESTINATION", "D1_LUNCH", "D1_DINNER"],
            planned["slots"],
        )

    @patch("app.agents.destination.search_client")
    @patch("app.agents.restaurant.search_client")
    def test_main_graph_validates_and_builds_final_response(
        self, restaurant_client, destination_client
    ) -> None:
        destination_client.search.return_value = _response(PlaceDomain.DESTINATION, 4)
        restaurant_client.search.return_value = _response(PlaceDomain.RESTAURANT, 8)

        result = travel_graph.invoke(
            {
                "request": {
                    "message": "Gangneung day trip",
                    "region": "GANGNEUNG",
                    "travel_days": 1,
                    "nights": 0,
                    "pet_allowed": False,
                    "wheelchair_accessible": False,
                    "preferences": [],
                }
            }
        )

        self.assertEqual("READY", result["itinerary_status"])
        self.assertEqual("VALID", result["hard_validation"]["status"])
        self.assertEqual("PASS", result["quality_validation"]["status"])
        self.assertEqual("READY", result["final_response"]["response_status"])
        self.assertTrue(result["final_response"]["days"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from app.agents.candidate_collector import candidate_collector_node
from app.agents.supervisor import MAX_ITINERARY_RETRIES, candidate_retry_node
from app.graph import travel_graph


class CandidateCollectorTests(unittest.TestCase):
    def test_accepts_only_selected_agents(self) -> None:
        result = candidate_collector_node(
            {
                "selected_agents": ["destination", "restaurant"],
                "completed_agents": ["destination", "restaurant"],
                "destination_candidates": [],
                "restaurant_candidates": [],
            }
        )
        self.assertTrue(result["candidates_ready"])

    def test_fails_when_completion_signal_is_missing(self) -> None:
        result = candidate_collector_node(
            {
                "selected_agents": ["destination", "restaurant"],
                "completed_agents": ["destination"],
            }
        )
        self.assertFalse(result["candidates_ready"])
        self.assertEqual("failed", result["status"])

    def test_graph_collects_candidates_and_builds_day_trip(self) -> None:
        state = travel_graph.invoke(
            {
                "request": {
                    "message": "Gangneung trip",
                    "region": "강릉",
                    "travel_days": 1,
                    "nights": 0,
                    "pet_allowed": False,
                    "preferences": ["바다"],
                }
            }
        )
        self.assertEqual({"destination", "restaurant"}, set(state["completed_agents"]))
        self.assertTrue(state["candidates_ready"])
        self.assertEqual("READY", state["itinerary_status"])
        self.assertEqual("completed", state["status"])
        self.assertEqual(3, len(state["itinerary"]))

    def test_retry_supervisor_selects_only_requested_agent(self) -> None:
        result = candidate_retry_node(
            {
                "retry_count": 0,
                "retry_actions": [
                    {
                        "agent": "restaurant",
                        "slots": ["D1_LUNCH"],
                        "instruction": "음식점을 다시 검색한다.",
                    }
                ],
            }
        )
        self.assertEqual(["restaurant"], result["retry_agents"])
        self.assertEqual(1, result["retry_count"])

    def test_retry_supervisor_stops_after_limit(self) -> None:
        result = candidate_retry_node(
            {
                "retry_count": MAX_ITINERARY_RETRIES,
                "retry_actions": [
                    {
                        "agent": "restaurant",
                        "slots": ["D1_LUNCH"],
                        "instruction": "음식점을 다시 검색한다.",
                    }
                ],
            }
        )
        self.assertEqual("failed", result["status"])
        self.assertEqual([], result["retry_agents"])

    def test_graph_stops_when_mock_candidates_remain_insufficient(self) -> None:
        state = travel_graph.invoke(
            {
                "request": {
                    "message": "Unknown region trip",
                    "region": "UNKNOWN",
                    "travel_days": 1,
                    "nights": 0,
                    "pet_allowed": False,
                }
            }
        )
        self.assertEqual("failed", state["status"])
        self.assertEqual(MAX_ITINERARY_RETRIES + 1, state["retry_count"])
        self.assertEqual(["D1_LUNCH", "D1_DINNER"], state["missing_slots"])


if __name__ == "__main__":
    unittest.main()

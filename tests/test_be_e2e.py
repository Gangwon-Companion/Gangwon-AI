from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.search.be_client import BeSearchClient
from app.search.models import HardFilters, PlaceDomain, RegionCode, SearchRequest


RUN_LIVE_TESTS = os.getenv("RUN_BE_INTEGRATION_TESTS", "").lower() in {
    "1",
    "true",
    "yes",
}


@unittest.skipUnless(
    RUN_LIVE_TESTS,
    "Set RUN_BE_INTEGRATION_TESTS=1 while BE and Elasticsearch are running.",
)
class LiveBeIntegrationTests(unittest.TestCase):
    def test_search_response_matches_contract_for_every_domain(self) -> None:
        client = BeSearchClient(timeout_seconds=10)
        slots = {
            PlaceDomain.DESTINATION: "D1_DESTINATION",
            PlaceDomain.RESTAURANT: "D1_LUNCH",
            PlaceDomain.LODGING: "D1_LODGING",
        }

        for domain, slot in slots.items():
            with self.subTest(domain=domain.value):
                response = client.search(
                    SearchRequest(
                        domain=domain,
                        slot=slot,
                        region_codes=[RegionCode.GANGNEUNG],
                        hard_filters=HardFilters(),
                        limit=3,
                    )
                )
                self.assertIsInstance(response.results, list)

    def test_travel_plan_reaches_a_terminal_response(self) -> None:
        response = TestClient(app).post(
            "/internal/travel/plan",
            json={
                "message": "강릉에서 하루 여행하고 싶어",
                "region": "강릉",
                "travel_days": 1,
                "nights": 0,
                "pet_allowed": False,
                "preferences": [],
            },
        )

        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertIn(payload["status"], {"completed", "failed"})
        self.assertIsNotNone(payload["final_response"])
        self.assertIn(
            payload["final_response"]["response_status"],
            {"READY", "FAILED"},
        )


if __name__ == "__main__":
    unittest.main()

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

    def test_day_trip_reaches_ready_response(self) -> None:
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
        self.assertEqual("completed", payload["status"])
        self.assertEqual("READY", payload["itinerary_status"])
        self.assertEqual("VALID", payload["hard_validation"]["status"])
        self.assertEqual("PASS", payload["quality_validation"]["status"])
        self.assertEqual("READY", payload["final_response"]["response_status"])
        self.assertFalse(payload["missing_slots"])
        self.assertGreaterEqual(len(payload["itinerary"]), 3)

    def test_one_night_two_day_trip_reaches_ready_response(self) -> None:
        response = TestClient(app).post(
            "/internal/travel/plan",
            json={
                "message": "평창에서 1박 2일 여행하고 싶어",
                "region": "평창",
                "travel_days": 2,
                "nights": 1,
                "pet_allowed": False,
                "preferences": [],
            },
        )

        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("completed", payload["status"], payload)
        self.assertEqual("READY", payload["itinerary_status"], payload)
        self.assertEqual("VALID", payload["hard_validation"]["status"], payload)
        self.assertEqual("PASS", payload["quality_validation"]["status"], payload)
        self.assertEqual("READY", payload["final_response"]["response_status"], payload)
        self.assertFalse(payload["missing_slots"], payload)
        self.assertEqual(8, len(payload["itinerary"]), payload)
        self.assertEqual(2, len(payload["final_response"]["days"]), payload)
        non_lodging_ids = [
            visit["place_id"]
            for visit in payload["itinerary"]
            if visit["category"] != "LODGING"
        ]
        self.assertEqual(len(non_lodging_ids), len(set(non_lodging_ids)), payload)
        self.assertTrue(
            all(visit["travel_minutes_from_previous"] >= 0 for visit in payload["itinerary"]),
            payload,
        )

    def test_gangwon_ocean_two_night_three_day_trip_reaches_ready_response(self) -> None:
        response = TestClient(app).post(
            "/internal/travel/plan",
            json={
                "message": "강원도 바다를 둘러볼 수 있는 2박 3일 코스를 짜줘",
                "region": "강원도",
                "travel_days": 3,
                "nights": 2,
                "pet_allowed": False,
                "preferences": ["바다"],
            },
        )

        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("completed", payload["status"], payload)
        self.assertEqual("READY", payload["itinerary_status"], payload)
        self.assertEqual("VALID", payload["hard_validation"]["status"], payload)
        self.assertEqual("PASS", payload["quality_validation"]["status"], payload)
        self.assertEqual("READY", payload["final_response"]["response_status"], payload)
        self.assertEqual(13, len(payload["itinerary"]), payload)
        self.assertEqual(3, len(payload["final_response"]["days"]), payload)
        destinations = [
            visit for visit in payload["itinerary"] if visit["category"] == "DESTINATION"
        ]
        self.assertEqual(3, len(destinations), payload)
        self.assertTrue(
            all("oceanView" in visit["matched_conditions"] for visit in destinations),
            payload,
        )

    def test_pet_trip_fails_without_restaurant_policy_evidence(self) -> None:
        response = TestClient(app).post(
            "/internal/travel/plan",
            json={
                "message": "반려견과 강릉에서 하루 여행하고 싶어",
                "region": "강릉",
                "travel_days": 1,
                "nights": 0,
                "pet_allowed": True,
                "preferences": [],
            },
        )

        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("failed", payload["status"], payload)
        self.assertEqual("FAILED", payload["final_response"]["response_status"], payload)
        self.assertEqual("INVALID", payload["hard_validation"]["status"], payload)
        self.assertTrue(
            any(
                violation["code"] == "EVIDENCE_MISSING"
                and any(slot.endswith(("_LUNCH", "_DINNER")) for slot in violation["slots"])
                for violation in payload["hard_validation"]["violations"]
            ),
            payload,
        )

    def test_wheelchair_trip_fails_without_restaurant_policy_evidence(self) -> None:
        response = TestClient(app).post(
            "/internal/travel/plan",
            json={
                "message": "휠체어로 강릉에서 하루 여행하고 싶어",
                "region": "강릉",
                "travel_days": 1,
                "nights": 0,
                "pet_allowed": False,
                "wheelchair_accessible": True,
                "preferences": [],
            },
        )

        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("failed", payload["status"], payload)
        self.assertEqual("FAILED", payload["final_response"]["response_status"], payload)
        self.assertEqual("INVALID", payload["hard_validation"]["status"], payload)
        self.assertTrue(
            any(
                violation["code"] == "EVIDENCE_MISSING"
                and any(slot.endswith(("_LUNCH", "_DINNER")) for slot in violation["slots"])
                for violation in payload["hard_validation"]["violations"]
            ),
            payload,
        )


if __name__ == "__main__":
    unittest.main()

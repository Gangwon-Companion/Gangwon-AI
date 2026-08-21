import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.search.models import SearchRequest, SearchResponse


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, object]:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as fixture:
        return json.load(fixture)


class SearchContractTest(unittest.TestCase):
    def test_request_fixture_round_trip(self) -> None:
        payload = load_fixture("search_request.json")
        request = SearchRequest.model_validate(payload)

        self.assertEqual(request.model_dump(mode="json"), payload)

    def test_response_fixture_round_trip(self) -> None:
        payload = load_fixture("search_response.json")
        response = SearchResponse.model_validate(payload)

        self.assertEqual(response.model_dump(mode="json"), payload)

    def test_pet_size_requires_explicit_pet_allowed(self) -> None:
        payload = load_fixture("search_request.json")
        payload["hard_filters"] = {"pet_size": "SMALL"}

        with self.assertRaises(ValidationError):
            SearchRequest.model_validate(payload)

    def test_unknown_fields_are_rejected(self) -> None:
        payload = load_fixture("search_request.json")
        payload["engine_specific_query"] = "must not cross the contract boundary"

        with self.assertRaises(ValidationError):
            SearchRequest.model_validate(payload)

    def test_false_is_distinct_from_missing_filter(self) -> None:
        payload = load_fixture("search_request.json")
        payload["hard_filters"] = {
            "pet_allowed": False,
            "pet_size": None,
            "wheelchair_accessible": False,
        }

        request = SearchRequest.model_validate(payload)

        self.assertIs(request.hard_filters.pet_allowed, False)
        self.assertIs(request.hard_filters.wheelchair_accessible, False)
        self.assertIsNone(request.hard_filters.pet_size)

    def test_evidence_status_requires_missing_fields(self) -> None:
        payload = load_fixture("search_response.json")
        payload["results"][1]["missing_fields"] = []

        with self.assertRaises(ValidationError):
            SearchResponse.model_validate(payload)

    def test_all_search_scenarios_have_unique_ids_and_valid_requests(self) -> None:
        scenarios = load_fixture("search_scenarios.json")

        self.assertGreaterEqual(len(scenarios), 20)
        self.assertEqual(len({scenario["id"] for scenario in scenarios}), len(scenarios))
        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                SearchRequest.model_validate(scenario["request"])
                self.assertTrue(scenario["expectation"].strip())


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.agents.destination import _build_search_request as destination_request
from app.agents.lodging import lodging_node
from app.agents.restaurant import restaurant_node
from app.search.be_client import BeSearchClient
from app.search.models import PlaceDomain, SearchResponse


FIXTURE = Path(__file__).parent / "fixtures" / "search_response.json"


def response_fixture() -> SearchResponse:
    return SearchResponse.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


class SearchIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "request": {"region": "강릉", "pet_allowed": True, "pet_size": "SMALL", "wheelchair_accessible": None},
            "preference_profile": {"keywords": ["바다"], "soft": {"ocean_view": 0.8}},
            "slots": ["D1_DESTINATION", "D1_LUNCH", "D1_LODGING"],
        }

    def test_request_factory_uses_common_contract(self) -> None:
        request = destination_request(self.state)

        self.assertEqual(request.domain, PlaceDomain.DESTINATION)
        self.assertEqual(request.region_codes[0].value, "GANGNEUNG")
        self.assertEqual(request.hard_filters.pet_size.value, "SMALL")
        self.assertEqual(request.query_text, "바다")

    @patch("app.agents.restaurant.search_client")
    def test_restaurant_agent_maps_common_response(self, client: Mock) -> None:
        client.search.return_value = response_fixture()

        result = restaurant_node(self.state)

        self.assertEqual(len(result["restaurant_candidates"]), 2)
        self.assertEqual(result["restaurant_candidates"][1]["status"], "INSUFFICIENT_EVIDENCE")
        candidate = result["restaurant_candidates"][0]
        self.assertEqual(candidate["address"], "강원특별자치도 강릉시 창해로 14번길")
        self.assertTrue(candidate["pet_allowed"])
        self.assertTrue(candidate["source_ids"])

    @patch("app.agents.lodging.search_client")
    def test_lodging_agent_distinguishes_search_failure(self, client: Mock) -> None:
        from app.search.client import SearchUnavailableError
        client.search.side_effect = SearchUnavailableError("연결 실패")

        result = lodging_node(self.state)

        self.assertEqual(result["lodging_candidates"], [])
        self.assertEqual(result["errors"], ["연결 실패"])

    @patch("app.search.be_client.urlopen")
    def test_be_client_validates_response_contract(self, urlopen_mock: Mock) -> None:
        response = Mock()
        response.read.return_value = FIXTURE.read_bytes()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        urlopen_mock.return_value = response

        result = BeSearchClient("http://be").search(destination_request(self.state))

        self.assertEqual(len(result.results), 2)


if __name__ == "__main__":
    unittest.main()

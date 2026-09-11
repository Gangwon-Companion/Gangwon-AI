import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.agents.destination import _build_search_request as destination_request
from app.agents.lodging import _build_search_request as lodging_request, lodging_node
from app.agents.restaurant import _build_search_request as restaurant_request, restaurant_node
from app.search.be_client import BeSearchClient
from app.search.models import PlaceDomain, RegionCode, SearchResponse
from app.search.request_factory import build_search_relaxation


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
        self.assertTrue(request.hard_filters.pet_allowed)
        self.assertEqual(request.hard_filters.pet_size.value, "SMALL")
        self.assertEqual(request.query_text, "바다")

    def test_restaurant_and_lodging_omit_unsupported_policy_filters(self) -> None:
        restaurant = restaurant_request(self.state)
        lodging = lodging_request(self.state)

        self.assertIsNone(restaurant.hard_filters.pet_allowed)
        self.assertIsNone(restaurant.hard_filters.pet_size)
        self.assertIsNone(restaurant.hard_filters.wheelchair_accessible)
        self.assertIsNone(lodging.hard_filters.pet_allowed)
        self.assertIsNone(lodging.hard_filters.pet_size)
        self.assertIsNone(lodging.hard_filters.wheelchair_accessible)

    def test_broad_gangwon_ocean_request_targets_east_coast_regions(self) -> None:
        self.state["request"]["region"] = "강원도"
        self.state["preference_profile"] = {
            "keywords": ["바다"],
            "soft": {"oceanView": 0.9},
        }

        request = destination_request(self.state)

        self.assertEqual(
            request.region_codes,
            [
                RegionCode.GOSEONG,
                RegionCode.SOKCHO,
                RegionCode.YANGYANG,
                RegionCode.GANGNEUNG,
                RegionCode.DONGHAE,
                RegionCode.SAMCHEOK,
            ],
        )

        self.assertEqual(restaurant_request(self.state).region_codes, [])

    def test_pet_friendly_east_coast_restaurant_search_starts_in_requested_region(self) -> None:
        self.state["request"]["region"] = "속초"

        request = restaurant_request(self.state)

        self.assertEqual(request.region_codes, [RegionCode.SOKCHO])

    def test_multi_day_east_coast_restaurant_search_starts_in_requested_region(self) -> None:
        self.state["request"].update({
            "region": "속초", "travel_days": 2, "pet_allowed": False, "pet_size": None,
        })

        request = restaurant_request(self.state)

        self.assertEqual(request.region_codes, [RegionCode.SOKCHO])

    def test_restaurant_retry_expands_regions_in_steps(self) -> None:
        self.state["request"].update({
            "region": "강릉",
            "travel_days": 4,
            "pet_allowed": False,
            "pet_size": None,
        })

        self.state["retry_count"] = 0
        self.assertEqual([RegionCode.GANGNEUNG], restaurant_request(self.state).region_codes)

        self.state["retry_count"] = 1
        self.assertEqual([RegionCode.GANGNEUNG], restaurant_request(self.state).region_codes)

        self.state["retry_count"] = 2
        self.assertEqual(
            [RegionCode.YANGYANG, RegionCode.GANGNEUNG, RegionCode.DONGHAE],
            restaurant_request(self.state).region_codes,
        )

        self.state["retry_count"] = 3
        self.assertEqual(
            [
                RegionCode.GOSEONG,
                RegionCode.SOKCHO,
                RegionCode.YANGYANG,
                RegionCode.GANGNEUNG,
                RegionCode.DONGHAE,
                RegionCode.SAMCHEOK,
            ],
            restaurant_request(self.state).region_codes,
        )

    def test_restaurant_retry_relaxes_query_text(self) -> None:
        self.state["request"].update({
            "travel_days": 4,
            "pet_allowed": False,
            "pet_size": None,
        })
        self.state["preference_profile"] = {
            "keywords": ["바다", "해산물"],
            "soft": {"oceanView": 0.9, "food": 0.9},
        }

        self.state["retry_count"] = 0
        self.assertEqual("해산물", restaurant_request(self.state).query_text)
        self.assertEqual(32, restaurant_request(self.state).limit)

        self.state["retry_count"] = 1
        relaxed = restaurant_request(self.state)
        self.assertEqual("해산물 맛집 음식 식당", relaxed.query_text)
        self.assertEqual(36, relaxed.limit)

        self.state["retry_count"] = 2
        broad = restaurant_request(self.state)
        self.assertEqual("맛집 음식 식당", broad.query_text)
        self.assertEqual(40, broad.limit)

        self.state["retry_count"] = 3
        fallback = restaurant_request(self.state)
        self.assertEqual("", fallback.query_text)
        self.assertEqual(40, fallback.limit)

    def test_food_keywords_do_not_leak_into_destination_or_lodging_queries(self) -> None:
        self.state["request"].update({
            "travel_days": 2,
            "pet_allowed": False,
            "pet_size": None,
        })
        self.state["preference_profile"] = {
            "keywords": ["바다", "물회", "회", "오션뷰"],
            "soft": {"oceanView": 0.9, "food": 0.9},
        }

        self.assertEqual("바다", destination_request(self.state).query_text)
        self.assertEqual("물회 회", restaurant_request(self.state).query_text)
        self.assertEqual("바다 오션뷰", lodging_request(self.state).query_text)

    def test_restaurant_retry_records_relaxation_context(self) -> None:
        self.state["request"].update({
            "travel_days": 4,
            "pet_allowed": False,
            "pet_size": None,
        })
        self.state["preference_profile"] = {
            "keywords": ["바다", "해산물"],
            "soft": {"oceanView": 0.9, "food": 0.9},
        }
        self.state["retry_count"] = 2

        relaxation = build_search_relaxation(
            self.state, PlaceDomain.RESTAURANT, "_LUNCH"
        )

        self.assertIsNotNone(relaxation)
        self.assertEqual("restaurant", relaxation["agent"])  # type: ignore[index]
        self.assertEqual("RESTAURANT", relaxation["domain"])  # type: ignore[index]
        self.assertEqual("D1_LUNCH", relaxation["slot"])  # type: ignore[index]
        self.assertEqual(2, relaxation["retry_count"])  # type: ignore[index]
        self.assertEqual("해산물", relaxation["original_query"])  # type: ignore[index]
        self.assertEqual("맛집 음식 식당", relaxation["used_query"])  # type: ignore[index]
        self.assertEqual("EXPAND_TO_NEARBY_REGION", relaxation["strategy"])  # type: ignore[index]
        self.assertEqual(["GANGNEUNG"], relaxation["original_regions"])  # type: ignore[index]
        self.assertEqual(
            ["YANGYANG", "GANGNEUNG", "DONGHAE"],
            relaxation["used_regions"],  # type: ignore[index]
        )

    def test_restaurant_retry_uses_diagnostics_to_drop_query_text(self) -> None:
        self.state["request"].update({
            "travel_days": 4,
            "pet_allowed": False,
            "pet_size": None,
        })
        self.state["preference_profile"] = {
            "keywords": ["해산물"],
            "soft": {"food": 0.9},
        }
        self.state["retry_count"] = 1
        self.state["search_diagnostics"] = [
            {
                "agent": "restaurant",
                "domain": "RESTAURANT",
                "slot": "D1_LUNCH",
                "retry_count": 0,
                "requested_limit": 32,
                "returned_count": 0,
                "unique_count": 0,
                "shortage": 32,
                "failure_reasons": ["NO_TEXT_MATCH"],
                "counts": {"current": 0, "without_query": 21},
                "suggested_actions": ["DROP_QUERY_TEXT", "INCREASE_LIMIT"],
            }
        ]

        request = restaurant_request(self.state)
        relaxation = build_search_relaxation(
            self.state, PlaceDomain.RESTAURANT, "_LUNCH"
        )

        self.assertEqual("", request.query_text)
        self.assertEqual([RegionCode.GANGNEUNG], request.region_codes)
        self.assertEqual(64, request.limit)
        self.assertEqual("DROP_QUERY_TEXT", relaxation["strategy"])  # type: ignore[index]
        self.assertEqual("diagnostics", relaxation["source"])  # type: ignore[index]
        self.assertEqual(["NO_TEXT_MATCH"], relaxation["failure_reasons"])  # type: ignore[index]

    def test_restaurant_diagnostics_can_expand_to_nearby_regions(self) -> None:
        self.state["request"].update({
            "region": "강릉",
            "travel_days": 4,
            "pet_allowed": False,
            "pet_size": None,
        })
        self.state["preference_profile"] = {
            "keywords": ["해산물"],
            "soft": {"food": 0.9},
        }
        self.state["retry_count"] = 1
        self.state["search_diagnostics"] = [
            {
                "agent": "restaurant",
                "domain": "RESTAURANT",
                "slot": "D1_LUNCH",
                "retry_count": 0,
                "requested_limit": 32,
                "returned_count": 1,
                "unique_count": 1,
                "shortage": 31,
                "failure_reasons": ["LOW_RESULT_COUNT", "NOT_ENOUGH_UNIQUE_CANDIDATES"],
                "counts": {"current": 1, "region_only": 20},
                "suggested_actions": ["INCREASE_LIMIT"],
            }
        ]

        request = restaurant_request(self.state)
        relaxation = build_search_relaxation(
            self.state, PlaceDomain.RESTAURANT, "_LUNCH"
        )

        self.assertEqual(
            [RegionCode.YANGYANG, RegionCode.GANGNEUNG, RegionCode.DONGHAE],
            request.region_codes,
        )
        self.assertEqual("EXPAND_TO_NEARBY_REGION", relaxation["strategy"])  # type: ignore[index]
        self.assertEqual(["GANGNEUNG"], relaxation["original_regions"])  # type: ignore[index]
        self.assertEqual(
            ["YANGYANG", "GANGNEUNG", "DONGHAE"],
            relaxation["used_regions"],  # type: ignore[index]
        )

    def test_policy_diagnostics_do_not_add_unsupported_restaurant_filters(self) -> None:
        self.state["request"].update({
            "travel_days": 2,
            "pet_allowed": True,
            "pet_size": "SMALL",
            "wheelchair_accessible": True,
        })
        self.state["preference_profile"] = {
            "keywords": ["해산물"],
            "soft": {"food": 0.9},
        }
        self.state["retry_count"] = 1
        self.state["search_diagnostics"] = [
            {
                "agent": "restaurant",
                "domain": "RESTAURANT",
                "slot": "D1_LUNCH",
                "retry_count": 0,
                "requested_limit": 16,
                "returned_count": 0,
                "unique_count": 0,
                "shortage": 16,
                "failure_reasons": ["NO_POLICY_EVIDENCE"],
                "counts": {"current": 0, "without_policy_filters": 30},
                "suggested_actions": ["ASK_USER_TO_ADJUST_REQUIRED_CONDITION"],
            }
        ]

        request = restaurant_request(self.state)

        self.assertIsNone(request.hard_filters.pet_allowed)
        self.assertIsNone(request.hard_filters.pet_size)
        self.assertIsNone(request.hard_filters.wheelchair_accessible)
        self.assertEqual("해산물 맛집 음식 식당", request.query_text)

    @patch("app.agents.restaurant.search_client")
    def test_restaurant_agent_maps_common_response(self, client: Mock) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["results"][0].update(
            {
                "domain": "RESTAURANT",
                "place_subtype": "CAFE",
                "matched_preferences": ["cafe"],
                "matched_keywords": ["카페"],
                "pet_allowed": True,
                "max_pet_size": "SMALL",
                "wheelchair_accessible": True,
                "evidence": [],
            }
        )
        client.search.return_value = SearchResponse.model_validate(payload)

        result = restaurant_node(self.state)

        self.assertEqual(len(result["restaurant_candidates"]), 2)
        self.assertEqual(result["restaurant_candidates"][1]["status"], "INSUFFICIENT_EVIDENCE")
        candidate = result["restaurant_candidates"][0]
        self.assertEqual(candidate["address"], "강원특별자치도 강릉시 창해로 14번길")
        self.assertEqual("CAFE", candidate["place_subtype"])
        self.assertEqual("CAFE", candidate["subtype"])
        self.assertEqual(["카페"], candidate["matched_keywords"])
        self.assertEqual("GANGNEUNG", candidate["region_code"])
        self.assertTrue(candidate["pet_allowed"])
        self.assertEqual("SMALL", candidate["max_pet_size"])
        self.assertTrue(candidate["wheelchair_accessible"])
        self.assertTrue(candidate["source_ids"])

    @patch("app.agents.restaurant.search_client")
    def test_restaurant_agent_returns_relaxation_context_on_retry(self, client: Mock) -> None:
        client.search.return_value = response_fixture()
        self.state["preference_profile"] = {
            "keywords": ["해산물"],
            "soft": {"food": 0.9},
        }
        self.state["retry_count"] = 1

        result = restaurant_node(self.state)

        self.assertEqual("해산물 맛집 음식 식당", result["restaurant_search_request"].query_text)
        self.assertEqual(1, len(result["search_relaxations"]))
        self.assertEqual("EXPAND_QUERY_TEXT", result["search_relaxations"][0]["strategy"])

    @patch("app.agents.restaurant.search_client")
    def test_restaurant_agent_records_search_diagnostics(self, client: Mock) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["diagnostics"] = {
            "requested_limit": 32,
            "returned_count": 2,
            "unique_count": 2,
            "shortage": 30,
            "failure_reasons": ["LOW_RESULT_COUNT"],
            "under_matched_preferences": ["food"],
            "unmatched_query_terms": ["해산물"],
            "missing_evidence_fields": ["pet_allowed"],
            "counts": {"current": 2, "region_only": 50},
            "suggested_actions": ["INCREASE_LIMIT"],
        }
        client.search.return_value = SearchResponse.model_validate(payload)

        result = restaurant_node(self.state)

        self.assertEqual(1, len(result["search_diagnostics"]))
        diagnostic = result["search_diagnostics"][0]
        self.assertEqual("restaurant", diagnostic["agent"])
        self.assertEqual("RESTAURANT", diagnostic["domain"])
        self.assertEqual(30, diagnostic["shortage"])
        self.assertEqual(["해산물"], diagnostic["unmatched_query_terms"])
        self.assertEqual(["pet_allowed"], diagnostic["missing_evidence_fields"])

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

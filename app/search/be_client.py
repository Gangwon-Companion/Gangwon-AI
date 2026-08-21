import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pydantic import ValidationError
from app.search.client import SearchClient, SearchClientError, SearchTimeoutError, SearchUnavailableError
from app.search.models import SearchRequest, SearchResponse

class BeSearchClient(SearchClient):
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 3.0):
        self._base_url = (base_url or os.getenv("GANGWON_BE_BASE_URL", "http://localhost:8080")).rstrip("/")
        self._timeout_seconds = timeout_seconds

    def search(self, request: SearchRequest) -> SearchResponse:
        http_request = Request(f"{self._base_url}/internal/search/places", data=request.model_dump_json().encode(), headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        try:
            with urlopen(http_request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise SearchTimeoutError("BE 검색 요청 시간이 초과됐습니다.") from exc
        except (HTTPError, URLError) as exc:
            raise SearchUnavailableError("BE 검색 서비스에 연결할 수 없습니다.") from exc
        except json.JSONDecodeError as exc:
            raise SearchClientError("BE 검색 응답이 JSON이 아닙니다.") from exc
        try:
            return SearchResponse.model_validate(payload)
        except ValidationError as exc:
            raise SearchClientError("BE 검색 응답이 공통 계약과 다릅니다.") from exc

search_client: SearchClient = BeSearchClient()

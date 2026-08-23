from typing import Protocol
from app.search.models import SearchRequest, SearchResponse

class SearchClientError(RuntimeError): pass
class SearchTimeoutError(SearchClientError): pass
class SearchUnavailableError(SearchClientError): pass

class SearchClient(Protocol):
    def search(self, request: SearchRequest) -> SearchResponse: ...

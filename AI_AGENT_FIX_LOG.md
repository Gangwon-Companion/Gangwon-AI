# AI Agent 개선 문제 해결 기록

기준일: 2026-09-03

이 문서는 AI Agent 테스트 중 발견한 문제를 하나씩 해결하며 남기는 기록이다.

각 항목은 다음 구조를 유지한다.

```text
1. 어떤 문제가 있었는지
2. 왜 문제가 발생했는지
3. 어떻게 처리했는지
4. 결과가 어떻게 나왔는지
5. 남은 확인 사항
```

## 1. 최종 응답 시간 표시 누락 문제

### 1.1 어떤 문제가 있었는지

프론트/Swagger 테스트 중 최종 응답의 방문 시간이 다음처럼 표시되는 문제가 확인됐다.

```text
시간 미확인-시간 미확인
```

내부 itinerary에는 방문 시간이 있었지만, 최종 응답인 `final_response.days[].visits[].time`에는 시간이 없는 것처럼 표시됐다.

예상 표시:

```text
10:00-12:00
```

실제 표시:

```text
시간 미확인-시간 미확인
```

### 1.2 왜 문제가 발생했는지

Response Agent는 기존에 `start_at`, `end_at` 필드만 보고 방문 시간을 만들었다.

```text
Response Agent가 기대한 형식:
start_at="2026-08-23T10:00:00+09:00"
end_at="2026-08-23T12:00:00+09:00"
```

하지만 전체 LangGraph 흐름에서 Itinerary Agent가 넘기는 일정은 다음처럼 `start_time`, `end_time`을 사용할 수 있다.

```text
Itinerary Agent 결과 형식:
start_time="10:00"
end_time="12:00"
```

즉 시간 정보는 있었지만, Response Agent가 읽는 필드 이름과 Itinerary Agent가 넘기는 필드 이름이 달라서 시간이 누락됐다.

### 1.3 어떻게 처리했는지

수정 파일:

```text
app/agents/response.py
tests/test_response.py
```

Response Agent의 시간 표시 로직을 다음 순서로 바꿨다.

```text
1. start_at/end_at이 있으면 ISO 8601 값에서 HH:MM 추출
2. start_at/end_at이 없으면 start_time/end_time 사용
3. 둘 다 없으면 시간 미확인 표시
```

이제 Response Agent는 두 일정 형식을 모두 처리한다.

```text
start_at/end_at 기반 일정
→ 10:00-12:00

start_time/end_time 기반 일정
→ 10:00-12:00

시간 필드 없음
→ 시간 미확인-시간 미확인
```

추가 테스트:

```text
test_uses_itinerary_start_and_end_time_when_iso_times_are_missing
```

테스트 내용:

- itinerary 항목에서 `start_at`, `end_at`을 제거한다.
- 대신 `start_time="10:00"`, `end_time="12:00"`을 넣는다.
- 최종 응답의 `days[].visits[].time`이 `10:00-12:00`으로 표시되는지 확인한다.
- fallback `answer` 문자열에도 `10:00-12:00`이 포함되는지 확인한다.

### 1.4 결과가 어떻게 나왔는지

Response Agent 테스트:

```text
python -B -m unittest tests.test_response

Ran 12 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 58 tests
OK (skipped=6)
```

결과적으로 Itinerary Agent가 `start_time/end_time` 형식으로 일정을 넘겨도 최종 응답 시간이 정상 표시되도록 개선됐다.

### 1.5 남은 확인 사항

이번 수정은 호환성 개선이다.

추후 전체 연결 시에는 아래 계약을 팀에서 확정하는 것이 좋다.

- 최종 itinerary 표준 시간 필드를 `start_at/end_at`으로 통일할지
- 또는 `day/start_time/end_time`을 계속 유지할지
- 여행 시작 날짜가 없는 경우 `date`를 어떻게 표시할지
- API 스키마에서 `ScheduledVisit`과 `ItinerarySlot`의 시간 필드를 통합할지

현재 Response Agent는 안전하게 두 형식을 모두 지원한다.

## 2. 관광지/식당 중복 배치 문제

### 2.1 어떤 문제가 있었는지

프론트/Swagger 테스트 중 4일 여행 일정이 `READY/PASS`로 생성됐지만, 실제 일정에는 같은 장소가 여러 번 반복되는 문제가 확인됐다.

예시:

```text
강릉항여객터미널       4회
커피씨엘             4회
송정해변막국수        4회
신라모노그램 강릉     3회
순두부젤라또 1호점    3회
```

숙소는 한 곳에 연박하는 것이 자연스러울 수 있다.

하지만 관광지와 식당이 여러 번 반복되면 4일 일정임에도 실제 여행 경험이 매우 단조로워진다.

사용자 정책:

```text
LODGING
→ 같은 숙소 반복 허용

DESTINATION
→ 여행 전체에서 중복 금지

RESTAURANT
→ 여행 전체에서 중복 금지
```

### 2.2 왜 문제가 발생했는지

기존 Itinerary Optimizer는 같은 장소 중복을 여행 전체 기준으로 막지 않았다.

기존 정책은 사실상 다음과 같았다.

```text
같은 날짜 안에서 같은 비숙소 장소 반복은 제한
다른 날짜에 같은 식당/관광지 반복은 허용 가능
숙소 반복도 허용
```

그래서 다일 일정에서 점수가 높은 상위 후보가 여러 날짜에 반복 선택될 수 있었다.

또한 Validator/Quality Validator도 다일 일정에서 같은 식당이나 관광지가 반복되는 문제를 충분히 잡지 못했다.

문제 흐름:

```text
후보 수는 충분함
→ Optimizer가 상위 후보를 반복 선택
→ Validator가 통과
→ Quality Validator도 PASS
→ 사용자에게 반복 많은 일정이 제공
```

### 2.3 어떻게 처리했는지

수정 파일:

```text
app/tools/itinerary_optimizer.py
app/validators/hard_validator.py
app/agents/validation.py
tests/test_itinerary.py
tests/test_validation.py
```

Itinerary Optimizer에서는 기존 `used_place_days` 대신 `used_non_lodging_place_ids`를 사용하도록 바꿨다.

기존 관리 기준:

```text
(place_id, day)
```

변경 후 관리 기준:

```text
place_id
```

단, 숙소는 예외로 둔다.

처리 방식:

```text
candidate.category == LODGING
→ 중복 검사에서 제외

candidate.category != LODGING
→ 이미 사용한 place_id면 선택하지 않음
```

Hard Validator도 같은 정책으로 맞췄다.

```text
LODGING 중복
→ 허용

DESTINATION/RESTAURANT 중복
→ DUPLICATE_PLACE 위반
```

Quality Validator에도 방어 검사를 추가했다.

```text
LODGING 중복
→ 품질 이슈로 보지 않음

DESTINATION/RESTAURANT 중복
→ DUPLICATE_PLACE MAJOR 이슈
→ status=REVISE
```

Hard Validator가 먼저 잡는 것이 기본이지만, 향후 외부 입력이나 수정 요청 흐름에서 중복 일정이 들어올 수 있으므로 Quality Validator에도 방어선을 추가했다.

### 2.4 결과가 어떻게 나왔는지

추가/수정한 테스트:

```text
tests.test_itinerary
```

확인 내용:

- 같은 식당을 같은 날 반복하지 않는다.
- 같은 식당을 다른 날에도 반복하지 않는다.
- 대체 식당이 있으면 반복 후보 대신 대체 후보를 선택한다.
- 같은 숙소는 연박으로 반복 사용해도 된다.

```text
tests.test_validation
```

확인 내용:

- 같은 숙소를 연박으로 사용하는 것은 VALID
- 같은 식당을 다른 날짜에 반복하면 INVALID
- 위반 코드는 DUPLICATE_PLACE
- 같은 관광지가 반복되면 Quality Validator가 REVISE 처리

테스트 결과:

```text
python -B -m unittest tests.test_itinerary

Ran 9 tests
OK
```

```text
python -B -m unittest tests.test_validation

Ran 10 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 61 tests
OK (skipped=6)
```

이제 관광지와 식당은 여행 전체에서 한 번만 선택된다.

숙소는 기존 사용자 기대에 맞게 같은 곳에 연박할 수 있다.

### 2.5 남은 확인 사항

이번 수정은 AI Agent 내부에서 중복 선택을 막는 1차 개선이다.

추후 Search Tool과 전체 LangGraph 연결 후 실제 데이터로 다음을 확인해야 한다.

- 3일 이상 일정에서 충분한 unique 관광지 후보가 확보되는지
- 3일 이상 일정에서 충분한 unique 식당 후보가 확보되는지
- 후보가 부족할 때 중복 금지 때문에 일정 생성 실패가 과도하게 늘어나지 않는지
- 후보 부족 시 Search Agent가 조건 완화 또는 추가 검색을 수행하는지
- 사용자에게 후보 부족 사유를 자연스럽게 안내할 수 있는지

특히 장기 일정에서는 중복 금지를 적용하면 후보 부족이 더 자주 드러날 수 있다.

따라서 다음 개선 후보는 다음과 같다.

```text
후보 부족 시 retry 전략 개선
Search Agent의 조건 완화 ladder 추가
Restaurant/Destination 후보 수 확보 전략 개선
실패 사유 구조화
```

## 3. 후보 부족 시 같은 검색 조건 반복 문제

### 3.1 어떤 문제가 있었는지

후보가 부족할 때 Search Agent를 정해진 횟수만큼 재실행하지만, 매번 같은 SearchRequest를 보내는 문제가 있었다.

예시 흐름:

```text
Restaurant 후보 0개
→ Restaurant Agent 재실행
→ query_text="해산물"로 다시 검색
→ 또 0개
→ 같은 조건으로 다시 검색
→ 또 0개
→ retry_count 초과 후 실패
```

이 방식은 검색 서비스나 DB 상태가 그대로라면 결과가 바뀔 가능성이 거의 없다.

또한 사용자가 요청한 키워드와 정확히 일치하는 후보가 부족할 때, 어떤 조건을 완화했는지 state에 남지 않았다.

따라서 나중에 Response Agent가 다음과 같은 설명을 만들 근거도 부족했다.

```text
요청하신 해산물 식당 후보가 부족해 일반 음식점까지 검색 범위를 넓혔습니다.
```

### 3.2 왜 문제가 발생했는지

기존 SearchRequest 생성 로직은 `retry_count`를 고려하지 않았다.

즉 최초 검색과 재시도 검색이 같은 조건으로 만들어졌다.

예시:

```text
retry_count=0
→ query_text="해산물"

retry_count=1
→ query_text="해산물"

retry_count=2
→ query_text="해산물"
```

또한 SearchRequest는 최종적으로 Search Tool에 보내는 요청만 담고 있었고, 다음 정보는 따로 기록하지 않았다.

```text
원래 검색어
실제로 사용한 검색어
몇 번째 재시도인지
어떤 완화 전략을 사용했는지
왜 조건을 완화했는지
```

그래서 개발자는 재시도 실패 원인을 추적하기 어렵고, 사용자에게도 조건 완화 이유를 설명하기 어려웠다.

### 3.3 어떻게 처리했는지

수정 파일:

```text
app/search/request_factory.py
app/agents/destination.py
app/agents/restaurant.py
app/agents/lodging.py
app/core/state.py
app/schemas/travel.py
app/api/routes.py
tests/test_search_integration.py
```

#### 3.3.1 재시도 단계별 검색어 완화

`build_search_request()`가 `state.retry_count`를 보고 검색어와 limit을 다르게 만들도록 수정했다.

Restaurant 예시:

```text
retry_count=0
→ query_text="해산물"
→ limit=32

retry_count=1
→ query_text="해산물 맛집 음식 식당"
→ limit=36

retry_count=2
→ query_text="맛집 음식 식당"
→ limit=40

retry_count>=3
→ query_text=""
→ limit=40
```

의미:

```text
1차
→ 사용자가 말한 검색어 중심

2차
→ 사용자 검색어 + 도메인 일반 키워드

3차
→ 도메인 일반 키워드

4차
→ 검색어를 제거하고 지역/필터/선호 중심으로 검색
```

Destination과 Lodging도 같은 구조를 사용할 수 있게 했다.

예시:

```text
DESTINATION 완화 키워드: 관광지, 산책
LODGING 완화 키워드: 숙소
RESTAURANT 완화 키워드: 맛집, 음식, 식당
```

#### 3.3.2 완화 과정 state 기록

완화 검색이 발생했는지 기록하기 위해 `SearchRelaxation` 타입을 추가했다.

추가 필드:

```text
TravelState.search_relaxations
```

기록 예시:

```json
{
  "agent": "restaurant",
  "domain": "RESTAURANT",
  "slot": "D1_LUNCH",
  "retry_count": 2,
  "original_query": "해산물",
  "used_query": "맛집 음식 식당",
  "strategy": "GENERIC_DOMAIN_QUERY",
  "reason": "'해산물' 조건과 직접 일치하는 음식점 후보가 부족해 도메인 일반 검색어로 넓혔습니다."
}
```

전략 종류:

```text
EXPAND_QUERY_TEXT
→ 원래 검색어에 일반 키워드를 추가

GENERIC_DOMAIN_QUERY
→ 원래 검색어 대신 도메인 일반 검색어 사용

DROP_QUERY_TEXT_KEEP_REGION
→ 검색어를 제거하고 지역 중심으로 검색
```

#### 3.3.3 Agent 응답에 완화 기록 포함

다음 Agent가 검색 완화 기록을 반환하도록 연결했다.

```text
Destination Agent
Restaurant Agent
Lodging Agent
```

성공/실패와 관계없이 완화 검색을 시도했다면 `search_relaxations`에 기록한다.

#### 3.3.4 API 응답에 완화 기록 포함

Swagger와 프론트에서 확인할 수 있도록 API 스키마와 라우트에도 필드를 추가했다.

추가 응답 필드:

```text
TravelPlanResponse.search_relaxations
```

이제 `/internal/travel/plan` 응답에서 어떤 검색 완화가 사용됐는지 확인할 수 있다.

### 3.4 결과가 어떻게 나왔는지

추가 테스트:

```text
tests.test_search_integration
```

확인 내용:

- Restaurant 재시도 시 `retry_count`에 따라 `query_text`가 달라진다.
- Restaurant 재시도 시 후보 limit이 늘어난다.
- 완화 검색이 발생하면 `SearchRelaxation` 기록이 생성된다.
- Restaurant Agent가 재시도 검색에서 `search_relaxations`를 반환한다.

테스트 결과:

```text
python -B -m unittest tests.test_search_integration

Ran 10 tests
OK
```

Search 계약/통합 테스트:

```text
python -B -m unittest tests.test_search_contract tests.test_search_integration

Ran 18 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 64 tests
OK (skipped=6)
```

이번 수정으로 같은 조건을 반복 검색하는 문제를 줄이고, 검색 조건을 어떻게 완화했는지 state/API 응답에 남길 수 있게 됐다.

### 3.5 남은 확인 사항

이번 수정은 AI Agent 쪽에서 Search Tool에 넘기는 요청을 단계적으로 바꾸는 1차 개선이다.

실제 검색 결과가 좋아지는지는 Spring Search Tool이 해당 요청을 어떻게 처리하는지에 따라 달라진다.

추후 확인할 것:

- Spring Search Tool이 빈 `query_text`를 지역 인기순 또는 필터 기반 검색으로 처리하는지
- `query_text="맛집 음식 식당"` 같은 일반 검색어가 실제 결과 확장에 도움이 되는지
- `soft_preferences`가 결과 제거 조건이 아니라 랭킹/점수화 조건으로 쓰이는지
- 각 Search Agent가 슬롯별 실패 원인을 더 구체적으로 기록할 필요가 있는지
- 완화 검색으로 선택된 후보를 Response Agent가 사용자에게 자연스럽게 설명할지

아직 완전히 해결되지 않은 부분:

```text
검색 실패 원인 구조화
슬롯별 완화 이력 관리
조건 완화 후 선택된 후보 표시
사용자-facing 대체 추천 사유 생성
```

즉 현재는 다음 단계의 기반을 만든 상태다.

```text
SearchRequest 완화
→ 완화 기록 state 저장
→ API 응답 노출
→ 추후 Itinerary/Response에서 대체 추천 설명에 활용
```


## 4. Elasticsearch 검색 문서 품질 개선

### 4.1 어떤 문제가 있었는지

AI Agent 쪽에서 검색어 완화 전략을 추가했지만, Spring Search Tool이 Elasticsearch 문서에 충분한 원본 텍스트를 담지 않으면 실제 후보 확장 효과가 제한된다.

실제 DB 데이터를 확인했을 때 식당과 숙소에는 검색에 유용한 상세 칼럼이 있었다.

```text
restaurants.first_menu
restaurants.treat_menu
lodgings.room_type
lodgings.sub_facility
lodgings.parking
```

하지만 기존 Elasticsearch 검색 문서의 `searchText`에는 이 정보가 충분히 포함되지 않았다.

기존 Restaurant searchText:

```text
name
menuType
region
address
```

기존 Lodging searchText:

```text
name
description
region
address
```

그래서 사용자가 다음처럼 구체적인 표현을 했을 때 검색 품질이 떨어질 수 있었다.

```text
물회 먹고 싶어
대게 먹고 싶어
해산물 먹고 싶어
바베큐 가능한 숙소
수영장 있는 숙소
주차 가능한 숙소
가족룸 숙소
```

### 4.2 왜 문제가 발생했는지

Elasticsearch 방식에서는 DB를 직접 검색하지 않고, `PlaceSearchDocumentAssembler`가 DB 데이터를 검색 문서로 만든 뒤 Elasticsearch index에 저장한다.

즉 DB에 좋은 값이 있어도 `searchText`에 들어가지 않으면 일반 텍스트 검색에서 충분히 활용되지 않는다.

문제 흐름은 다음과 같다.

```text
DB에는 first_menu/treat_menu가 있음
→ ES searchText에는 포함되지 않음
→ query_text="물회" 같은 요청이 들어옴
→ 이름/menuType/address에 없으면 매칭이 약하거나 실패
```

숙소도 비슷했다.

```text
DB에는 room_type/sub_facility/parking이 있음
→ ES searchText에는 포함되지 않음
→ "바베큐", "수영장", "주차", "가족룸" 같은 요청 대응이 약함
```

### 4.3 어떻게 처리했는지

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssembler.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssemblerTest.java
```

Restaurant 검색 문서의 `searchText`에 다음 칼럼을 추가했다.

```text
name
menuType
firstMenu
treatMenu
region
address
parking
```

Lodging 검색 문서의 `searchText`에 다음 칼럼을 추가했다.

```text
name
description
roomType
subFacility
parking
region
address
```

또한 검색 문서 구조가 바뀐 것을 구분하기 위해 document version을 올렸다.

```text
DOCUMENT_VERSION=3
→ DOCUMENT_VERSION=4
```

추가 테스트:

```text
PlaceSearchDocumentAssemblerTest
```

확인 내용:

```text
Restaurant 문서 searchText에 firstMenu/treatMenu/parking이 포함되는지
Lodging 문서 searchText에 roomType/subFacility/parking이 포함되는지
생성된 문서 버전이 4인지
```

### 4.4 결과가 어떻게 나왔는지

Elasticsearch 관련 단위 테스트를 실행했다.

```text
.\gradlew.bat test --tests com.gangwon.companion.domain.search.elasticsearch.PlaceSearchDocumentAssemblerTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchIndexServiceTest
```

테스트 결과:

```text
BUILD SUCCESSFUL
6 tests successful
```

통과한 테스트:

```text
ElasticsearchIndexServiceTest
ElasticsearchPlaceSearchEngineTest
PlaceSearchDocumentAssemblerTest
```

이번 수정으로 Elasticsearch index에 들어가는 검색 문서가 실제 DB의 메뉴/숙소 시설 정보를 더 잘 포함하게 됐다.

### 4.5 남은 확인 사항

이번 수정은 Elasticsearch 문서 생성 품질 개선이다.

실제 검색 결과에 반영하려면 Spring 서버가 Elasticsearch 방식으로 실행되어야 하고, Elasticsearch index 재생성이 필요하다.

현재 로컬 `.env`는 다음처럼 변경했다.

```text
SEARCH_ENGINE=elasticsearch
SEARCH_INDEXER_ENABLED=true
```

추후 확인할 것:

```text
Spring 재기동 후 SEARCH_ENGINE=elasticsearch로 뜨는지
Elasticsearch index를 재생성했는지
query_text="물회", "대게", "해산물"로 Restaurant 후보가 늘어나는지
query_text="바베큐", "수영장", "주차"로 Lodging 후보가 잘 나오는지
AI Agent의 retry_count 완화 검색과 연결했을 때 후보 0건이 줄어드는지
```

아직 남은 Search Tool 개선 후보:

```text
soft_preferences food/nature/nightView 매핑 보강
pet_infos 정규화 boolean 백필
accessibility_infos 정규화 boolean 백필
opensAt/closesAt hard filter 정책 재검토
0건 실패 원인 diagnostics 구조화
```

## 5. Elasticsearch soft_preferences 매핑 보강 및 실제 검색 확인

### 5.1 어떤 문제가 있었는지

AI Agent는 사용자 선호를 `soft_preferences`로 Search Tool에 전달한다.

예시:

```json
{
  "soft_preferences": {
    "food": 0.9,
    "oceanView": 0.8
  }
}
```

하지만 Spring Search Tool의 Elasticsearch 검색 엔진은 일부 preference key만 알고 있었다.

기존 지원 key:

```text
quiet
ocean_view
oceanView
cafe
```

그래서 AI Agent가 넘기는 다음 key들은 랭킹에 충분히 반영되지 않았다.

```text
food
nature
nightView
```

특히 `food`는 음식점 추천에서 핵심인데, 이 매핑이 없으면 `query_text`를 완화하거나 비웠을 때 음식 관련 선호가 검색 점수에 거의 도움을 주지 못한다.

### 5.2 왜 문제가 발생했는지

Elasticsearch Search Tool은 `soft_preferences`를 보고 내부 키워드 목록으로 바꾼 뒤 `searchText`에 boost 쿼리를 건다.

문제는 `PREFERENCE_TERMS`에 없는 key가 들어오면 key 이름 자체를 검색어로 사용한다는 점이다.

예시:

```text
soft_preferences.food=0.9
→ 기존에는 "food"라는 문자열을 searchText에서 찾음
→ 한국어 데이터에는 거의 매칭되지 않음
```

즉 AI Agent는 음식 선호를 보냈지만, Search Tool은 실제 한국어 메뉴/식당 데이터와 연결하지 못했다.

### 5.3 어떻게 처리했는지

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngineTest.java
src/main/resources/application.yaml
compose.yaml
.env
```

Elasticsearch preference 매핑을 보강했다.

추가/보강한 key:

```text
food
→ 맛집, 음식, 식당, 해산물, 회, 물회, 대게, 홍게, 막국수, 순두부

oceanView
→ 바다, 해변, 오션뷰, 항구, 전망

cafe
→ 카페, 커피, 라떼, 디저트

nature
→ 숲, 계곡, 호수, 산책, 둘레길, 자연, 등산, 산림

nightView
→ 야경, 밤바다, 밤산책, 조명, 일몰, 노을
```

중간에 테스트에서 중요한 오탐도 잡았다.

처음에는 `nature`에 `산`을 넣었는데, `해산물` 안의 `산` 때문에 nature가 잘못 매칭됐다.

또 `nightView`에 `전망`을 넣으면 오션뷰/전망성 장소까지 야경으로 매칭될 수 있었다.

그래서 다음처럼 너무 넓거나 짧은 단어는 제거했다.

```text
nature에서 "산" 제거
nightView에서 "전망" 제거
```

또한 실제 재색인 과정에서 Elasticsearch 요청 timeout이 3초로 고정되어 재색인이 실패했다.

그래서 timeout을 환경변수로 받을 수 있게 변경했다.

```text
search.elasticsearch.request-timeout: ${ELASTICSEARCH_REQUEST_TIMEOUT:3s}
```

로컬 Docker 실행 값:

```text
ELASTICSEARCH_REQUEST_TIMEOUT=30s
```

그리고 Docker Compose 환경에서 Spring 컨테이너가 Elasticsearch에 접근할 수 있도록 `.env`의 URL을 조정했다.

```text
ELASTICSEARCH_URL=http://elasticsearch:9200
```

### 5.4 결과가 어떻게 나왔는지

Elasticsearch 관련 단위 테스트를 실행했다.

```text
.\gradlew.bat test --tests com.gangwon.companion.domain.search.elasticsearch.PlaceSearchDocumentAssemblerTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchIndexServiceTest
```

테스트 결과:

```text
BUILD SUCCESSFUL
7 tests successful
```

Spring 컨테이너 설정도 확인했다.

```text
SEARCH_ENGINE=elasticsearch
ELASTICSEARCH_URL=http://elasticsearch:9200
ELASTICSEARCH_REQUEST_TIMEOUT=30s
```

재색인 결과:

```json
{
  "index": "gangwon-places-v1-20260904091820875",
  "sourceCount": 3567,
  "indexedCount": 3567,
  "failedIds": [],
  "retriedIds": [],
  "aliasSwitched": true,
  "retryCount": 0
}
```

실제 Search API 확인 결과:

```text
restaurant 물회
→ count=2
→ 사돈집, 황대구탕

restaurant 대게
→ count=2
→ 속초보스대게, 유진게찜

restaurant 해산물 + food/oceanView
→ count=4
→ 신대게나라, 송정해변막국수, 사돈집 등
→ matched_preferences에 food/oceanView 반영 확인

lodging 바베큐
→ count=5

lodging 수영장
→ count=5

lodging 주차
→ count=5
```

이번 수정으로 AI Agent가 보내는 `food`, `oceanView` 같은 soft preference가 Elasticsearch 랭킹에 실제로 반영되는 것을 확인했다.

### 5.5 남은 확인 사항

이번 작업으로 다음은 처리됐다.

```text
Elasticsearch 문서에 메뉴/숙소 상세 텍스트 포함
food/nature/nightView soft preference 매핑 추가
짧은 단어로 인한 preference 오탐 방지
Spring Docker 실행을 Elasticsearch 방식으로 전환
Elasticsearch 재색인 성공
실제 Search API 검색 확인
```

아직 남은 Search Tool 개선 후보:

```text
pet_infos 정규화 boolean 백필
accessibility_infos 정규화 boolean 백필
opensAt/closesAt hard filter 정책 재검토
query_text="" fallback 품질 확인
0건 실패 원인 diagnostics 구조화
```

특히 다음 단계는 반려동물/무장애 쪽이 좋아 보인다.

현재 실제 DB에는 다음 문제가 있다.

```text
pet_infos.accompany_type, need_items, caution에는 의미 있는 텍스트가 있음
하지만 pet_allowed, small_pet_allowed, medium_pet_allowed, large_pet_allowed는 null이 많음

accessibility_infos.entrance, parking, restroom에는 의미 있는 텍스트가 있음
하지만 wheelchair_accessible은 null이 많음
```

따라서 다음 개선은 원문 텍스트를 boolean/evidence로 정규화하는 백필 흐름을 확인하는 것이 좋다.

## 6. Search Tool 반려동물/무장애 Elasticsearch 문서 보강

### 6.1 어떤 문제가 있었는지

반려동물 동반 또는 무장애 조건이 있는 요청에서 관광지 후보가 있어도 Search Tool 응답이 `INSUFFICIENT_EVIDENCE`로 떨어질 수 있었다.

특히 실제 DB를 확인해보면 `pet_infos`, `accessibility_infos`에는 의미 있는 자연어 설명이 들어있지만, 조건 판단에 바로 쓰는 boolean 컬럼은 `null`인 경우가 많았다.

예시:

```text
pet_infos.accompany_type
→ 일부구역 동반가능
→ 전구역 동반가능

pet_infos.need_items
→ 목줄 착용
→ 입마개 착용

pet_infos.caution
→ 대형견(25kg이상)까지 가능

accessibility_infos.entrance
→ 출입구까지 턱이 없어 휠체어 접근 가능함

accessibility_infos.parking
→ 장애인 주차장 있음

accessibility_infos.restroom
→ 장애인 화장실 있음
```

하지만 다음 컬럼은 실제 데이터에서 비어 있는 경우가 많았다.

```text
pet_infos.pet_allowed
pet_infos.small_pet_allowed
pet_infos.medium_pet_allowed
pet_infos.large_pet_allowed
accessibility_infos.wheelchair_accessible
```

그래서 AI Agent가 다음 조건을 Search Tool에 보내도, Spring Search Tool이 확실한 근거를 내려주지 못할 수 있었다.

```json
{
  "hard_filters": {
    "pet_allowed": true,
    "pet_size": "SMALL",
    "wheelchair_accessible": true
  }
}
```

### 6.2 왜 문제가 발생했는지

Elasticsearch 검색은 DB 테이블을 그때그때 직접 보는 방식이 아니라, Spring이 DB 데이터를 모아 `PlaceSearchDocument`라는 검색 문서를 만든 뒤 그 문서를 Elasticsearch index에 넣는 방식이다.

기존에도 관광지 문서에는 다음 텍스트 필드가 들어가고 있었다.

```text
petInfoText
accessibilityInfoText
```

하지만 조건 판단용 필드는 정규화 boolean 컬럼을 거의 그대로 사용했다.

기존 흐름:

```text
pet_infos 행이 있음
→ petInfoText에는 반려동물 설명이 들어감
→ pet_allowed 컬럼이 null이면 ES 문서의 petAllowed도 null
→ pet_allowed=true 요청에서 evidence 부족
```

무장애도 비슷했다.

```text
accessibility_infos 행이 있음
→ accessibilityInfoText에는 무장애 설명이 들어감
→ wheelchair_accessible 컬럼이 null이면 ES 문서의 wheelchairAccessible도 null
→ wheelchair_accessible=true 요청에서 evidence 부족
```

즉 원문 텍스트는 있었지만, Search Tool이 그 텍스트를 조건 판단에 충분히 활용하지 못했다.

### 6.3 어떻게 처리했는지

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssembler.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssemblerTest.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngineTest.java
```

#### 6.3.1 pet_infos 행을 반려동물 동반 가능 신호로 사용

정규화 컬럼 값이 있으면 기존 값을 우선 사용한다.

```text
pet_allowed=true/false 값 있음
→ 그 값을 그대로 사용
```

정규화 컬럼이 `null`이면 `pet_infos` 행과 자연어 텍스트를 fallback으로 사용한다.

```text
pet_infos 행이 있음
명확한 동반 불가 문구가 없음
→ petAllowed=true
```

명확한 부정 문구가 있으면 `false`로 본다.

```text
동반 불가
입장 불가
출입 불가
반려동물 금지
반려견 금지
```

#### 6.3.2 반려동물 크기 조건을 자연어에서 보강

`small_pet_allowed`, `medium_pet_allowed`, `large_pet_allowed` 값이 있으면 기존 값을 우선 사용한다.

값이 없으면 `petInfoText`에서 다음 표현을 찾아 보강한다.

```text
소형견
중형견
중소형견
대형견
10kg 이하
15kg 이하
25kg 이상
대형견까지 가능
크기 제한 없음
견종 제한 없음
```

예시:

```text
caution="대형견(25kg이상)까지 가능"
→ largePetAllowed=true
→ smallPetAllowed/mediumPetAllowed도 가능한 쪽으로 보강
```

#### 6.3.3 무장애 휠체어 접근 가능 여부를 자연어에서 보강

`wheelchair_accessible` 값이 있으면 기존 값을 우선 사용한다.

값이 없으면 `accessibilityInfoText`에서 다음 표현을 찾아 보강한다.

```text
휠체어 접근 가능
휠체어 출입 가능
휠체어 이용 가능
턱이 없어
턱이 없음
경사로
무단차
단차 없음
장애인용 엘리베이터
```

명확한 부정 문구가 있으면 `false`로 본다.

```text
휠체어 접근 불가
휠체어 출입 불가
휠체어 이용 불가
경사로 없음
계단만 이용
진입 불가
```

#### 6.3.4 pet/accessibility soft preference도 전용 텍스트 필드를 보도록 개선

기존 soft preference boost는 주로 `searchText`를 봤다.

이번 수정 후 반려동물 관련 key는 `petInfoText`를 더 강하게 보고, 무장애 관련 key는 `accessibilityInfoText`를 더 강하게 본다.

추가한 key:

```text
pet
petFriendly
smallPet
mediumPet
largePet
accessibility
wheelchair
accessibleRestroom
accessibleParking
elevator
helpDog
```

예시:

```text
soft_preferences.smallPet
→ petInfoText에서 소형견, 10kg 이하 등을 더 강하게 반영

soft_preferences.wheelchair
→ accessibilityInfoText에서 휠체어, 경사로, 턱이 없어 등을 더 강하게 반영
```

검색 문서 구조가 바뀌었기 때문에 document version도 올렸다.

```text
DOCUMENT_VERSION=4
→ DOCUMENT_VERSION=5
```

### 6.4 결과가 어떻게 나왔는지

Elasticsearch 관련 단위 테스트를 실행했다.

```text
.\gradlew.bat test --tests com.gangwon.companion.domain.search.elasticsearch.PlaceSearchDocumentAssemblerTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchIndexServiceTest
```

테스트 결과:

```text
BUILD SUCCESSFUL
10 tests successful
```

추가 확인한 테스트:

```text
pet_infos 행은 있지만 정규화 boolean 컬럼이 null인 경우
→ petAllowed=true로 ES 문서 생성

petInfoText에 대형견/25kg 이상 문구가 있는 경우
→ pet_size evidence 생성

accessibility_infos 행은 있지만 wheelchair_accessible 컬럼이 null인 경우
→ 휠체어 접근 가능 문구를 보고 wheelchairAccessible=true로 ES 문서 생성

pet/accessibility soft preference
→ petInfoText/accessibilityInfoText에 boost 쿼리 생성
```

Spring 컨테이너를 다시 빌드하고 Elasticsearch index를 재생성했다.

재색인 결과:

```json
{
  "index": "gangwon-places-v1-20260905113603637",
  "sourceCount": 3567,
  "indexedCount": 3567,
  "failedIds": [],
  "retriedIds": [],
  "aliasSwitched": true,
  "retryCount": 0
}
```

실제 Search API 확인 결과:

```text
반려동물 동반 가능 검색
→ matched_preferences에 petFriendly 반영
→ evidence에 pet_allowed=true 포함

소형견 조건 검색
→ pet_allowed=true 후보 반환
→ 소형견 근거가 있는 후보는 pet_size=true evidence 포함

휠체어 접근 가능 검색
→ wheelchair_accessible=true 후보 반환
→ matched_preferences에 wheelchair/accesssibleRestroom 반영
```

이번 수정으로 관광지의 반려동물/무장애 자연어 데이터가 단순 검색 텍스트를 넘어 조건 판단과 랭킹에도 반영되기 시작했다.

### 6.5 남은 확인 사항

이번 수정은 실제 DB 상태에 맞춘 fallback 처리다.

아직 모든 조건을 완벽하게 판정하는 것은 아니다.

남은 확인 사항:

```text
소형견/중형견/대형견 문구가 애매한 경우 오판이 없는지
"안내견 외 동반 금지"처럼 보조견과 일반 반려동물이 섞인 문구를 어떻게 처리할지
휠체어 접근 가능과 장애인 화장실/주차장/엘리베이터를 각각 별도 evidence로 내릴지
식당/숙소에는 반려동물/무장애 데이터가 없으므로 별도 데이터 수집이 필요한지
AI Agent가 smallPet/wheelchair/accessibility 같은 soft preference key를 안정적으로 보내는지
```

중요한 한계:

```text
restaurants/lodgings에는 현재 반려동물/무장애 전용 데이터가 없음
따라서 이번 개선은 주로 DESTINATION 검색 품질을 올리는 작업
식당/숙소까지 반려동물/무장애 조건을 확실히 보장하려면 데이터 모델 또는 외부 데이터 보강이 필요
```

## 7. Search Tool 운영시간 추정 evidence 보강

### 7.1 어떤 문제가 있었는지

AI Agent의 일정 검증에서는 장소가 해당 시간에 방문 가능한지 확인하기 위해 Search Tool이 내려주는 운영시간 근거를 사용한다.

기존 Search Tool은 `usage_time`, `open_time`, `check_in_time/check_out_time` 같은 원문에서 명확한 시간 범위를 찾으면 `opens_at`, `closes_at`을 만들었다.

하지만 실제 DB에는 다음처럼 시간이 명확하지 않은 운영 문구도 많았다.

```text
상시 개방
상시 운영
연중무휴
```

이런 값은 일정 후보로는 사용할 수 있지만, 실제 운영시간이 정확히 확인된 것은 아니다.

기존에는 이런 문구를 너무 강하게 `00:00-24:00`처럼 처리하거나, 반대로 운영시간 없음으로 처리할 수 있어 일정 검증과 최종 사용자 안내가 어색해질 수 있었다.

### 7.2 왜 문제가 발생했는지

운영시간 원문에는 서로 다른 의미가 섞여 있다.

```text
09:00~18:00
→ 명확한 운영시간

24시간 운영
→ 명확한 상시 운영

상시 개방
→ 운영 가능성이 높지만 정확한 종료 시간은 불명확

연중무휴
→ 휴무일 정보에 가깝고, 하루 운영시간은 불명확
```

그런데 기존 구조에서는 `opens_at`, `closes_at`만 내려갔기 때문에, AI Agent가 다음 두 경우를 구분하기 어려웠다.

```text
정확히 확인된 09:00-18:00
추정으로 잡은 00:00-22:00
```

즉 일정 검증에는 시간을 써야 하지만, 최종 답변에서는 “운영시간 확인 필요” 같은 안내가 필요한 상태였다.

### 7.3 어떻게 처리했는지

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/service/OperatingHours.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssembler.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
src/test/java/com/gangwon/companion/domain/search/service/OperatingHoursTest.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssemblerTest.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngineTest.java
```

운영시간 파싱 정책을 다음처럼 나눴다.

```text
명확한 시간 범위
→ 원문에서 추출한 opens_at/closes_at 사용

24시간 운영
→ 00:00-24:00
→ estimated=false

상시 개방 / 상시 운영 / 연중무휴
→ 00:00-22:00
→ estimated=true
```

`OperatingHours.Range`에 추정 여부를 나타내는 값을 추가했다.

```text
opensAt
closesAt
estimated
```

Elasticsearch 문서에도 추정 운영시간 evidence를 남긴다.

```text
opens_at
closes_at
operating_hours_estimated
```

Search API 응답에는 AI Agent가 사용자 안내를 만들 수 있도록 원문도 함께 내려준다.

```json
{
  "field": "operating_hours_estimated",
  "value": true,
  "source": "TOUR_API"
}
```

```json
{
  "field": "operating_hours_raw",
  "value": "상시 개방",
  "source": "TOUR_API"
}
```

검색 문서의 운영시간 해석이 바뀌었기 때문에 document version도 올렸다.

```text
DOCUMENT_VERSION=5
→ DOCUMENT_VERSION=6
```

### 7.4 결과가 어떻게 나왔는지

Elasticsearch/운영시간 관련 단위 테스트를 실행했다.

```text
.\gradlew.bat test --tests com.gangwon.companion.domain.search.service.OperatingHoursTest --tests com.gangwon.companion.domain.search.elasticsearch.PlaceSearchDocumentAssemblerTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchIndexServiceTest
```

테스트 결과:

```text
BUILD SUCCESSFUL
17 tests successful
```

Spring 컨테이너를 다시 빌드하고 Elasticsearch index를 재생성했다.

재색인 결과:

```json
{
  "index": "gangwon-places-v1-20260905123838151",
  "sourceCount": 3567,
  "indexedCount": 3567,
  "failedIds": [],
  "retriedIds": [],
  "aliasSwitched": true,
  "retryCount": 0
}
```

실제 Search API 확인 결과:

```text
아바이마을
→ opens_at=00:00
→ closes_at=22:00
→ operating_hours_estimated=true
→ operating_hours_raw="상시 개방"
```

이제 AI Agent는 이런 후보를 일정에는 사용할 수 있지만, 최종 답변에서는 다음처럼 안내할 수 있다.

```text
이 장소는 상시 개방 정보 기반으로 일정을 구성했으므로 방문 전 정확한 운영시간 확인이 필요합니다.
```

### 7.5 남은 확인 사항

이번 수정은 운영시간이 애매한 장소를 무조건 실패시키지 않기 위한 현실적인 보강이다.

남은 확인 사항:

```text
00:00-22:00 추정 시간이 실제 일정 품질에 적절한지
연중무휴를 open_time이 아니라 rest_date에서만 볼 경우에는 추정 운영시간으로 쓰지 않도록 주의할지
AI Agent Response Agent가 operating_hours_estimated evidence를 사용자 친화 문장으로 바꿔주는지
Validator가 추정 운영시간과 정확한 운영시간을 구분해 점수나 경고 수준을 다르게 볼지
식당의 브레이크타임/라스트오더를 별도로 반영할지
```

현재 Search Tool은 다음 구분을 할 수 있다.

```text
정확한 운영시간
→ opens_at/closes_at만 제공

추정 운영시간
→ opens_at/closes_at + operating_hours_estimated=true + operating_hours_raw 제공

운영시간 없음
→ operating_hours missing 처리
```

## 8. Search Tool 후보 부족 diagnostics 보강

### 8.1 어떤 문제가 있었는지

AI Agent는 후보가 부족할 때 `retry_count`에 따라 SearchRequest를 단계적으로 완화하도록 개선되어 있었다.

예시:

```text
retry 0
→ query_text="해산물"

retry 1
→ query_text="해산물 맛집 음식 식당"

retry 2
→ query_text="맛집 음식 식당"

retry 3+
→ query_text=""
```

하지만 이 방식은 실패 원인을 직접 보고 움직이는 것이 아니라, 정해진 순서대로 조건을 완화하는 방식이다.

그래서 후보가 부족한 이유가 다음 중 무엇인지 구분하기 어려웠다.

```text
검색어가 너무 좁은지
지역에 후보가 부족한지
운영시간 근거 때문에 후보가 줄었는지
반려동물/무장애 근거 때문에 후보가 줄었는지
중복 제거 후 unique 후보가 부족한지
단순히 limit보다 결과가 적은지
```

특히 반려동물/무장애 조건은 사용자의 필수 조건일 가능성이 높기 때문에 자동으로 완화하면 안 된다.

따라서 Search Tool은 조건을 직접 풀어버리기보다, AI Agent가 판단할 수 있도록 후보 부족 원인을 구조화해서 내려줘야 한다.

### 8.2 왜 문제가 발생했는지

기존 Search Tool 응답은 후보 목록 중심이었다.

```json
{
  "results": []
}
```

이 응답만 보면 AI Agent는 다음을 알 수 없다.

```text
검색어를 빼면 후보가 있는지
지역을 넓히면 후보가 있는지
운영시간 조건 때문에 빠진 후보가 있는지
반려동물/무장애 근거가 부족한지
```

즉 AI Agent가 재검색 전략을 세우려면 필요한 관측값이 부족했다.

문제 흐름:

```text
Search Tool 결과 부족
→ AI Agent가 원인을 모름
→ retry_count 기반 고정 완화
→ 필요 없는 완화를 하거나, 필요한 완화를 늦게 수행
```

### 8.3 어떻게 처리했는지

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/dto/PlaceSearchResponse.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngineTest.java
```

Search Tool 응답에 `diagnostics` 필드를 추가했다.

기존 응답:

```json
{
  "results": []
}
```

변경 후 후보가 부족하면 다음 형태로 내려준다.

```json
{
  "results": [],
  "diagnostics": {
    "requested_limit": 10,
    "returned_count": 0,
    "unique_count": 0,
    "shortage": 10,
    "failure_reasons": [
      "NO_TEXT_MATCH"
    ],
    "counts": {
      "current": 0,
      "without_query": 12,
      "without_policy_filters": 0,
      "without_operating_hours": 3,
      "region_only": 20,
      "domain_only": 100
    },
    "suggested_actions": [
      "EXPAND_QUERY_TEXT",
      "DROP_QUERY_TEXT",
      "INCREASE_LIMIT"
    ]
  }
}
```

`diagnostics`는 후보가 충분할 때는 `null`로 둔다.

```text
unique_count >= requested_limit
→ diagnostics=null

unique_count < requested_limit
→ diagnostics 생성
```

#### 8.3.1 진단용 count 쿼리 추가

Search Tool이 실제 추천 결과를 바꾸지는 않고, 원인 파악을 위해 Elasticsearch `_count` 쿼리를 추가로 수행한다.

계산하는 count:

```text
current
→ 현재 요청 조건 그대로 몇 개인지

without_query
→ 검색어만 빼면 몇 개인지

without_policy_filters
→ 반려동물/무장애 필터만 빼면 몇 개인지

without_operating_hours
→ 운영시간 필터만 빼면 몇 개인지

region_only
→ 도메인 + 지역 기준으로 몇 개인지

domain_only
→ 해당 도메인 전체 후보가 몇 개인지
```

중요한 점:

```text
without_policy_filters는 진단용 숫자일 뿐이다.
Search Tool이 반려동물/무장애 조건을 자동으로 풀어서 추천하지 않는다.
```

#### 8.3.2 실패 이유 추가

Search Tool이 count 값을 보고 `failure_reasons`를 만든다.

추가한 실패 이유:

```text
NO_TEXT_MATCH
→ 검색어 때문에 후보가 부족함

NO_REGION_MATCH
→ 해당 지역에 후보가 부족함

NO_POLICY_EVIDENCE
→ 반려동물/무장애 근거 때문에 후보가 부족함

NO_OPERATING_HOURS
→ 운영시간 근거 때문에 후보가 부족함

NOT_ENOUGH_UNIQUE_CANDIDATES
→ 중복 제거 후 사용할 수 있는 후보가 부족함

LOW_RESULT_COUNT
→ 요청 limit보다 반환 후보가 부족함
```

#### 8.3.3 suggested_actions 추가

AI Agent가 참고할 수 있도록 완화 방향도 함께 내려준다.

추가한 action:

```text
EXPAND_QUERY_TEXT
DROP_QUERY_TEXT
EXPAND_REGION
INCREASE_LIMIT
USE_OPERATING_HOURS_ESTIMATES
ASK_USER_TO_ADJUST_REQUIRED_CONDITION
```

반려동물/무장애 조건은 자동 완화하지 않는 정책이므로, 다음과 같은 action은 만들지 않았다.

```text
RELAX_PET_ALLOWED
RELAX_WHEELCHAIR_ACCESSIBLE
```

정책 조건 문제가 있으면 Search Tool은 다음 action만 제안한다.

```text
ASK_USER_TO_ADJUST_REQUIRED_CONDITION
```

의미:

```text
Search Tool
→ 이 조건 때문에 후보가 부족하다고 알려줌

AI Agent
→ 사용자에게 물어볼지
→ 근거 부족 후보를 안내와 함께 쓸지
→ 지역이나 검색어를 먼저 완화할지 판단
```

### 8.4 결과가 어떻게 나왔는지

테스트 실행:

```text
.\gradlew.bat test --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest --tests com.gangwon.companion.domain.search.dto.PlaceSearchContractTest
```

테스트 결과:

```text
BUILD SUCCESSFUL
11 tests successful
```

추가한 테스트:

```text
returnsDiagnosticsWhenResultsAreShort
→ 후보가 부족하면 diagnostics가 생성되는지 확인
→ NO_TEXT_MATCH, NO_OPERATING_HOURS, LOW_RESULT_COUNT 확인
→ EXPAND_QUERY_TEXT, DROP_QUERY_TEXT, USE_OPERATING_HOURS_ESTIMATES, INCREASE_LIMIT 확인

reportsPolicyEvidenceButDoesNotSuggestAutomaticallyRelaxingRequiredPolicy
→ 반려동물/무장애 조건 때문에 후보가 부족해도 자동 완화 action을 주지 않는지 확인
→ NO_POLICY_EVIDENCE 확인
→ ASK_USER_TO_ADJUST_REQUIRED_CONDITION만 정책 관련 action으로 제공
```

Spring 컨테이너를 다시 빌드하고 실제 Search API도 확인했다.

실제 요청 예:

```text
domain=RESTAURANT
region_codes=SOKCHO
query_text="없는없는해산물키워드"
limit=100
```

실제 응답 요약:

```text
returned_count=21
unique_count=21
shortage=79

counts.current=0
counts.without_query=21
counts.region_only=121
counts.domain_only=1716

failure_reasons:
NO_TEXT_MATCH
NOT_ENOUGH_UNIQUE_CANDIDATES
LOW_RESULT_COUNT

suggested_actions:
EXPAND_QUERY_TEXT
DROP_QUERY_TEXT
INCREASE_LIMIT
```

의미:

```text
원래 검색어로는 0개
검색어를 빼면 속초 식당 21개 사용 가능
따라서 AI Agent는 query_text 완화 또는 제거를 우선 검토할 수 있음
```

### 8.5 남은 확인 사항

이번 작업은 Search Tool이 후보 부족 원인을 AI Agent에 알려주는 1차 연결 작업이다.

남은 확인 사항:

```text
AI Agent가 diagnostics.failure_reasons를 보고 기존 retry_count ladder보다 우선해서 재검색 전략을 선택하는지
diagnostics가 있는 경우 search_relaxations에 어떤 원인 기반 완화를 했는지 함께 기록하는지
NO_POLICY_EVIDENCE가 있을 때 반려동물/무장애 조건을 자동 완화하지 않는지
EXPAND_REGION은 사용자 요청 지역을 벗어날 수 있으므로 Agent 정책에서 허용 조건을 둘지
NOT_ENOUGH_UNIQUE_CANDIDATES일 때 limit 증가만으로 충분한지, 검색어 완화도 같이 해야 하는지
```

추천 연결 방식:

```text
1순위
→ diagnostics 기반 재검색

2순위
→ diagnostics가 없거나 애매하면 기존 retry_count ladder 사용
```

예시:

```text
NO_TEXT_MATCH
→ query_text 완화 또는 제거

NO_REGION_MATCH
→ 사용자가 허용한 경우 인접 지역 확장

NO_OPERATING_HOURS
→ 추정 운영시간 후보 사용 또는 사용자 안내 강화

NO_POLICY_EVIDENCE
→ 자동 완화 금지
→ 사용자 확인 또는 근거 부족 후보 안내

NOT_ENOUGH_UNIQUE_CANDIDATES / LOW_RESULT_COUNT
→ limit 증가
→ 필요 시 query_text 완화
```

## 9. Search Tool diagnostics 기반 재검색 연동

### 9.1 어떤 문제가 있었는지

Search Tool 쪽에서 후보 부족 원인을 `diagnostics`로 내려주도록 개선됐지만, AI Agent는 아직 그 값을 SearchResponse 계약으로 받거나 다음 재검색 전략에 활용하지 못했다.

기존 AI Agent 재검색은 다음처럼 `retry_count` 기반 고정 ladder만 사용했다.

```text
retry 0
→ 사용자 검색어 그대로 사용

retry 1
→ 사용자 검색어 + 도메인 일반 키워드

retry 2
→ 도메인 일반 키워드

retry 3+
→ query_text 제거
```

이 방식은 fallback으로는 유용하지만, Search Tool이 이미 `NO_TEXT_MATCH`, `NO_POLICY_EVIDENCE`, `LOW_RESULT_COUNT` 같은 원인을 알려주는 상황에서는 그 정보를 우선 활용하는 편이 더 정확하다.

### 9.2 왜 문제가 발생했는지

AI Agent의 기존 SearchResponse 모델은 다음 필드만 받을 수 있었다.

```json
{
  "results": []
}
```

따라서 Search Tool이 다음처럼 응답하더라도 계약상 받을 수 없었다.

```json
{
  "results": [],
  "diagnostics": {
    "failure_reasons": ["NO_TEXT_MATCH"],
    "suggested_actions": ["DROP_QUERY_TEXT", "INCREASE_LIMIT"]
  }
}
```

또한 diagnostics를 받더라도 state에 저장하지 않으면 다음 retry에서 request_factory가 이전 검색 실패 원인을 알 수 없다.

### 9.3 어떻게 처리했는지

수정 파일:

```text
app/search/models.py
app/search/request_factory.py
app/agents/destination.py
app/agents/restaurant.py
app/agents/lodging.py
app/core/state.py
app/schemas/travel.py
app/api/routes.py
tests/test_search_contract.py
tests/test_search_integration.py
```

SearchResponse 계약에 `diagnostics`를 추가했다.

```text
SearchResponse.results
SearchResponse.diagnostics
```

diagnostics 필드:

```text
requested_limit
returned_count
unique_count
shortage
failure_reasons
counts
suggested_actions
```

각 검색 Agent는 Search Tool 응답에 diagnostics가 있으면 `TravelState.search_diagnostics`에 저장한다.

저장 예시:

```json
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
  "counts": {
    "current": 0,
    "without_query": 21
  },
  "suggested_actions": ["DROP_QUERY_TEXT", "INCREASE_LIMIT"]
}
```

이후 `build_search_request()`는 같은 domain의 최신 diagnostics를 먼저 확인한다.

적용 정책:

```text
diagnostics가 있음
→ failure_reasons/suggested_actions 기반으로 query_text와 limit 조정

diagnostics가 없음
→ 기존 retry_count ladder 사용
```

대표 처리:

```text
DROP_QUERY_TEXT
→ query_text=""

EXPAND_QUERY_TEXT
→ 사용자 검색어 + 도메인 일반 키워드

INCREASE_LIMIT 또는 LOW_RESULT_COUNT/NOT_ENOUGH_UNIQUE_CANDIDATES
→ limit 증가, 최대 100

NO_POLICY_EVIDENCE
→ pet_allowed/pet_size/wheelchair_accessible hard filter는 자동 완화하지 않음
```

그리고 diagnostics 기반으로 완화한 경우 `search_relaxations`에도 근거를 함께 남긴다.

예시:

```json
{
  "agent": "restaurant",
  "domain": "RESTAURANT",
  "slot": "D1_LUNCH",
  "retry_count": 1,
  "original_query": "해산물",
  "used_query": "",
  "strategy": "DROP_QUERY_TEXT",
  "source": "diagnostics",
  "failure_reasons": ["NO_TEXT_MATCH"],
  "suggested_actions": ["DROP_QUERY_TEXT", "INCREASE_LIMIT"],
  "reason": "검색어 때문에 음식점 후보가 부족하다는 진단에 따라 검색어를 비우고 지역과 필터 중심으로 넓혔습니다."
}
```

Swagger/API 응답에서도 확인할 수 있도록 다음 필드를 노출했다.

```text
TravelPlanResponse.search_diagnostics
TravelPlanResponse.search_relaxations
```

### 9.4 결과가 어떻게 나왔는지

추가 테스트:

```text
tests.test_search_contract
```

확인 내용:

```text
SearchResponse가 diagnostics를 optional 필드로 받을 수 있음
diagnostics가 없어도 기존 search_response fixture는 정상 처리됨
```

```text
tests.test_search_integration
```

확인 내용:

```text
NO_TEXT_MATCH + DROP_QUERY_TEXT 진단이 있으면 다음 retry에서 query_text를 비움
INCREASE_LIMIT 진단이 있으면 limit을 증가시킴
NO_POLICY_EVIDENCE가 있어도 반려동물/무장애 hard filter는 유지함
Restaurant Agent가 Search Tool diagnostics를 state에 기록함
diagnostics 기반 완화는 search_relaxations.source="diagnostics"로 남김
```

테스트 결과:

```text
python -B -m unittest tests.test_search_contract tests.test_search_integration

Ran 22 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 68 tests
OK (skipped=6)
```

이제 Search Tool의 diagnostics와 AI Agent 재검색 전략이 연결됐다.

### 9.5 남은 확인 사항

이번 수정은 AI Agent가 diagnostics를 받아 활용하는 1차 연동이다.

아직 남은 확인 사항:

```text
실제 Spring Search Tool 응답에서 diagnostics 필드명이 AI Agent 계약과 정확히 일치하는지
NO_REGION_MATCH일 때 지역 확장을 자동으로 할지, 사용자 확인을 받을지
USE_OPERATING_HOURS_ESTIMATES를 일정 검증/최종 응답 안내에 어떻게 반영할지
ASK_USER_TO_ADJUST_REQUIRED_CONDITION이 반복될 때 사용자에게 어떤 질문을 돌려줄지
diagnostics가 여러 domain에서 동시에 쌓일 때 domain별 최신 진단만 잘 사용하는지
```

현재 정책상 반려동물/무장애 조건은 자동 완화하지 않는다.

```text
pet_allowed=true
→ 유지

pet_size=SMALL/MEDIUM/LARGE
→ 유지

wheelchair_accessible=true
→ 유지
```

`without_policy_filters`는 원인 파악용 숫자로만 사용하고, AI Agent가 정책 필터를 자동으로 제거하지 않는다.

## 10. 식당 검색 지역이 첫 검색부터 과하게 확장되는 문제

### 10.1 어떤 문제가 있었는지

1차 개선 후 프론트 시나리오 테스트에서 사용자가 `강릉`을 명확히 요청했는데도 식당 검색 범위가 첫 검색부터 동해안 전체로 확장되는 문제가 확인됐다.

재현 입력:

```text
강릉으로 4일 여행 갈 거야. 바다, 카페, 해산물 위주로 가고 싶어. 반려동물은 안 데려가.
```

기존 Restaurant SearchRequest:

```json
{
  "domain": "RESTAURANT",
  "region_codes": [
    "GOSEONG",
    "SOKCHO",
    "YANGYANG",
    "GANGNEUNG",
    "DONGHAE",
    "SAMCHEOK"
  ]
}
```

그 결과 강릉 여행 일정에 고성, 속초, 양양, 동해 식당이 많이 섞였다.

예시:

```text
보배진 - 고성
카페 긷 - 속초
레드인블루커피 - 고성
베이커리카페 클램 - 동해
카페 로그 - 양양
앤커피스토리 - 속초
```

### 10.2 왜 문제가 발생했는지

SearchRequest를 만드는 함수는 하나지만, 내부 `_region_codes()` 함수에서 `RESTAURANT` 도메인만 별도 예외 처리를 하고 있었다.

기존 정책:

```text
domain == RESTAURANT
요청 지역이 동해안 지역
그리고 아래 중 하나라도 해당
- 반려동물 동반
- 2일 이상 여행
- oceanView 선호
- 바다 키워드

→ 동해안 전체 지역으로 검색
```

즉 Search Tool이 임의로 전 지역을 검색한 것이 아니라, AI Agent가 첫 SearchRequest부터 넓은 `region_codes`를 만들어 보냈다.

이 정책은 식당 후보 부족을 줄이기 위한 임시 성격의 확장이었지만, diagnostics/retry 기반 재검색이 생긴 뒤에는 첫 검색부터 넓힐 필요가 줄었다.

### 10.3 어떻게 처리했는지

수정 파일:

```text
app/search/request_factory.py
app/core/state.py
app/schemas/travel.py
tests/test_search_integration.py
```

Restaurant 지역 검색 정책을 단계형으로 바꿨다.

변경 후 정책:

```text
retry_count=0
→ 요청 지역만 검색

retry_count=1
→ 요청 지역 유지, query_text/limit 중심 완화

retry_count=2
→ 요청 지역 + 인접 지역

retry_count>=3
→ 동해안 권역 전체
```

강릉 기준 예시:

```text
1차
→ GANGNEUNG

2차
→ GANGNEUNG

3차
→ YANGYANG, GANGNEUNG, DONGHAE

4차
→ GOSEONG, SOKCHO, YANGYANG, GANGNEUNG, DONGHAE, SAMCHEOK
```

인접 지역 매핑도 추가했다.

```text
GOSEONG  → GOSEONG, SOKCHO
SOKCHO   → GOSEONG, SOKCHO, YANGYANG
YANGYANG → SOKCHO, YANGYANG, GANGNEUNG
GANGNEUNG → YANGYANG, GANGNEUNG, DONGHAE
DONGHAE  → GANGNEUNG, DONGHAE, SAMCHEOK
SAMCHEOK → DONGHAE, SAMCHEOK
```

Search Tool diagnostics에서 지역 확장이 필요하다고 판단되는 경우에는 retry 1에서도 인접 지역으로 넓힐 수 있게 했다.

지역 확장 판단에 사용하는 신호:

```text
EXPAND_REGION
NO_REGION_MATCH
NOT_ENOUGH_UNIQUE_CANDIDATES
LOW_RESULT_COUNT
```

또한 지역 확장이 발생했는지 추적할 수 있도록 `SearchRelaxation`에 지역 정보를 추가했다.

추가 필드:

```text
original_regions
used_regions
```

기록 예시:

```json
{
  "agent": "restaurant",
  "domain": "RESTAURANT",
  "slot": "D1_LUNCH",
  "retry_count": 2,
  "original_query": "해산물",
  "used_query": "맛집 음식 식당",
  "original_regions": ["GANGNEUNG"],
  "used_regions": ["YANGYANG", "GANGNEUNG", "DONGHAE"],
  "strategy": "EXPAND_TO_NEARBY_REGION",
  "reason": "음식점 후보가 부족해 요청 지역에서 인접 지역까지 검색 범위를 넓혔습니다."
}
```

새 전략 이름:

```text
EXPAND_TO_NEARBY_REGION
EXPAND_TO_COASTAL_REGION
```

### 10.4 결과가 어떻게 나왔는지

추가/수정한 테스트:

```text
tests.test_search_integration
```

확인 내용:

```text
반려동물 동반 조건이 있어도 식당 첫 검색은 요청 지역만 사용
2일 이상 여행이어도 식당 첫 검색은 요청 지역만 사용
retry_count=0/1에서는 요청 지역 유지
retry_count=2에서는 인접 지역으로 확장
retry_count=3 이상에서는 동해안 권역 전체로 확장
diagnostics가 지역 확장 필요를 암시하면 인접 지역으로 확장
search_relaxations에 original_regions/used_regions가 기록됨
```

테스트 결과:

```text
python -B -m unittest tests.test_search_integration

Ran 15 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 70 tests
OK (skipped=6)
```

이제 식당 검색도 첫 요청에서는 사용자가 말한 지역을 우선한다.

후보 부족이 확인된 뒤에만 인접 지역 또는 동해안 권역으로 단계적으로 확장된다.

### 10.5 남은 확인 사항

이번 수정은 SearchRequest 생성 정책을 개선한 것이다.

추후 프론트/실제 Search Tool 연결 테스트에서 아래를 확인해야 한다.

```text
강릉 4일 여행에서 첫 restaurant_search_request.region_codes가 ["GANGNEUNG"]으로 나오는지
강릉 후보가 충분하면 타 지역 식당이 일정에 섞이지 않는지
후보 부족 시 search_relaxations에 지역 확장 이유가 남는지
retry_count=2 이후 인접 지역 확장이 실제 후보 확보에 도움이 되는지
동해안 전체 확장이 필요한 경우 최종 응답에서 사용자에게 이유를 설명할지
```

아직 남은 관련 개선:

```text
사용자가 "강릉 안에서만", "멀리 이동하기 싫어"라고 말한 경우 지역 확장을 금지하는 정책
지역 확장으로 선택된 후보를 Response Agent가 자연스럽게 설명하는 기능
식당 후보를 일차별 동선 기준으로 다시 보정하는 기능
```

## 11. 기본 슬롯 경직성 및 식당/카페 혼입 문제

### 11.1 어떤 문제가 있었는지

프론트 시나리오 테스트를 보면서 일정 슬롯 구조가 너무 고정적이라는 문제가 확인됐다.

기존 기본 일정은 다음 성격이 강했다.

```text
아침
관광지
점심
저녁
숙소
```

이 구조에서는 하루에 식사를 너무 많이 고정하고, 관광지는 상대적으로 적게 들어갈 수 있었다.

또한 Search Tool이 식당 후보와 카페 후보를 같은 `RESTAURANT` 후보군으로 내려줄 수 있어서, 점심/저녁 슬롯에 카페가 들어가는 문제가 있었다.

예시 문제:

```text
점심 슬롯에 카페가 들어감
저녁 슬롯에 카페/디저트 가게가 들어감
사용자가 카페를 원하지 않았는데 식사 일정처럼 카페가 배치됨
```

숙소도 일정 계산에는 필요하지만, 최종 응답의 하루 방문 코스에 매일 방문지처럼 들어가면 사용자가 보기에는 일정이 불필요하게 복잡해진다.

사용자 요구 방향:

```text
기본 일정은 점심 + 저녁 + 관광지 1~2개 중심으로 구성
아침, 카페, 추가 활동, 휴식은 기본 고정 슬롯이 아니라 선택적 슬롯으로 취급
사용자가 카페를 요청하면 카페 슬롯을 일정에 반영
숙소는 일정 계산에는 사용하되 최종 답변에서는 별도 영역으로 안내
사용자가 말한 순서가 있으면 슬롯 순서도 일부 반영
```

### 11.2 왜 문제가 발생했는지

기존 `Supervisor Agent`는 여행 일수만 보고 슬롯을 고정 생성했다.

수정 전 슬롯 생성 방식:

```text
2일차 이후 BREAKFAST 추가
DESTINATION
LUNCH
DINNER
숙박일이면 LODGING
```

사용자의 여행 스타일이나 문장 순서를 보고 슬롯 구조를 바꾸는 흐름이 거의 없었다.

그리고 `Itinerary Agent`는 `RESTAURANT` 카테고리 후보를 점심/저녁 슬롯에 그대로 넣었다.

즉 Search Tool이 아래처럼 후보를 내려주면:

```text
RESTAURANT 후보군
- 해산물 식당
- 막국수집
- 카페
- 디저트 가게
```

Itinerary Agent는 카페와 일반 식당을 구분하지 못하고 점심/저녁 슬롯에 배치할 수 있었다.

또한 `Response Agent`는 itinerary에 들어온 `LODGING` 항목도 일반 방문지처럼 `days[].visits`에 포함했다.

그래서 숙소가 최종 사용자 응답에서 관광지/식당과 같은 코스 항목처럼 보였다.

### 11.3 어떻게 처리했는지

수정 파일:

```text
app/agents/supervisor.py
app/agents/itinerary.py
app/agents/response.py
app/agents/response_llm.py
app/tools/itinerary_optimizer.py
app/core/state.py
app/schemas/travel.py
tests/test_supervisor_slots.py
tests/test_itinerary.py
tests/test_response.py
tests/test_candidate_collector.py
```

#### 11.3.1 기본 슬롯 구조 변경

`Supervisor Agent`의 기본 슬롯을 다음처럼 바꿨다.

수정 전:

```text
D1_DESTINATION
D1_LUNCH
D1_DINNER
```

다일 일정에서는 2일차부터 아침 슬롯도 추가됐다.

수정 후:

```text
D1_DESTINATION
D1_LUNCH
D1_EXTRA_DESTINATION
D1_DINNER
```

이제 기본 하루 일정은 다음 의미를 가진다.

```text
관광지
점심
관광지
저녁
```

즉 아침을 기본 고정 슬롯에서 제외하고, 관광지를 1~2개 배치할 수 있게 했다.

#### 11.3.2 카페 요청 시 선택 슬롯 반영

사용자 요청이나 preference에 아래 키워드가 있으면 카페 요청으로 판단한다.

```text
카페
커피
디저트
베이커리
브런치
```

카페 요청이 없을 때:

```text
D1_DESTINATION
D1_LUNCH
D1_EXTRA_DESTINATION
D1_DINNER
```

카페 요청이 있을 때:

```text
D1_DESTINATION
D1_LUNCH
D1_CAFE
D1_DINNER
```

즉 카페는 무조건 추가해서 하루 일정을 과하게 늘리는 방식이 아니라, 선택적 중간 슬롯으로 반영한다.

#### 11.3.3 사용자 문장 순서 일부 반영

사용자가 일정 순서를 자연어로 말한 경우 일부 패턴을 반영한다.

예시 요청:

```text
점심 먹고 카페 갔다가 바다 보고 저녁 먹고 싶어.
```

생성 슬롯:

```text
D1_LUNCH
D1_CAFE
D1_DESTINATION
D1_DINNER
```

또한 `build_slot_specs()`에서 슬롯 순서에 따라 시간도 함께 배정되도록 바꿨다.

기본 순서:

```text
10:00
12:30
15:00
18:00
```

점심이 먼저 오는 요청:

```text
12:00
14:00
16:00
18:00
```

관광지만 있는 슬롯:

```text
10:00
15:00
17:00
19:00
```

현재는 모든 자연어 순서를 완벽히 해석하는 수준은 아니고, 자주 나오는 간단한 순서 요청을 반영하는 1차 개선이다.

#### 11.3.4 식당/카페 후보 분리

`RestaurantCandidate`와 `ScheduledVisit`에 `subtype`을 추가했다.

Search Tool이 `RESTAURANT` 후보로 내려준 항목 중 이름, cuisine, matched_conditions에 카페 관련 키워드가 있으면 내부적으로 다음처럼 표시한다.

```text
subtype="CAFE"
```

후보 배치 정책:

```text
D1_LUNCH, D1_DINNER
→ subtype=CAFE 후보 제외

D1_CAFE
→ subtype=CAFE 후보만 사용
```

이제 Search Tool이 음식점과 카페를 같은 응답에 섞어 내려줘도, Itinerary Agent가 점심/저녁과 카페 슬롯을 분리해서 사용한다.

#### 11.3.5 숙소 최종 응답 분리

숙소 슬롯은 itinerary 계산과 검증에는 계속 사용한다.

예시:

```text
D1_LODGING
```

하지만 최종 응답에서는 `days[].visits`에 넣지 않고 별도 필드로 분리했다.

수정 전 최종 응답:

```json
{
  "days": [
    {
      "visits": [
        "관광지",
        "식당",
        "숙소"
      ]
    }
  ]
}
```

수정 후 최종 응답:

```json
{
  "days": [
    {
      "visits": [
        "관광지",
        "식당"
      ]
    }
  ],
  "accommodations": [
    "숙소"
  ]
}
```

LLM 답변 생성에도 `accommodations`를 같이 넘기도록 수정했다.

### 11.4 결과가 어떻게 나왔는지

추가/수정한 테스트:

```text
tests/test_supervisor_slots.py
tests/test_itinerary.py
tests/test_response.py
tests/test_candidate_collector.py
```

확인 내용:

```text
기본 슬롯이 관광지 + 점심 + 추가 관광지 + 저녁으로 생성됨
카페 요청이 있으면 추가 관광지 슬롯 대신 카페 슬롯이 생성됨
간단한 "점심 먹고 카페 갔다가..." 순서 요청이 슬롯 순서에 반영됨
다일 일정에서 숙소 슬롯은 내부 슬롯으로 유지됨
카페 후보는 점심/저녁 슬롯에 들어가지 않음
카페 슬롯에는 카페 후보만 들어감
추가 관광지 슬롯은 관광지 후보를 사용함
숙소는 최종 응답의 days[].visits에서 제외되고 accommodations로 분리됨
```

관련 테스트:

```text
python -B -m unittest tests.test_supervisor_slots tests.test_itinerary tests.test_response

Ran 28 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 77 tests
OK (skipped=6)
```

### 11.5 남은 확인 사항

이번 수정은 "요청 1번 안에서" 슬롯을 더 유연하게 만드는 개선이다.

즉 처음 요청이 다음처럼 들어오면:

```text
강릉에서 바다 보고 카페도 가고 싶어.
```

카페 슬롯이 반영된다.

하지만 이미 생성된 일정에 대해 사용자가 후속으로 다음처럼 말하는 경우:

```text
카페도 넣어줘.
점심은 빼고 관광지 위주로 바꿔줘.
첫날은 쉬고 둘째 날에 바다를 보고 싶어.
```

현재 구조만으로는 이전 일정과 이전 state를 안정적으로 기억해 부분 수정한다고 보기 어렵다.

대화형 일정 수정을 제대로 지원하려면 별도 개선이 필요하다.

추가 개선 방향:

```text
프론트 또는 백엔드에서 이전 TravelState 저장
후속 사용자 message와 기존 request/preferences 병합
수정 요청 의도 분류: add/remove/replace/reorder
기존 itinerary를 유지할지 새로 생성할지 결정
변경된 슬롯만 재검색/재생성하는 부분 갱신 흐름 추가
사용자에게 변경 전/변경 후를 자연스럽게 안내
```

정리하면 이번 개선은 기본 슬롯과 카페/식당/숙소 표시 문제를 해결한 1차 개선이고, "생성된 일정을 대화로 수정하는 기능"은 다음 단계 개선 사항으로 남긴다.

## 12. 선호 부족 시 재검색 대상 Agent가 엇갈리는 문제

### 12.1 어떤 문제가 있었는지

1차 개선 후 시나리오 테스트에서 선호 키워드가 일정에 충분히 반영되지 않으면 `Quality Validator`가 `PREFERENCE_UNDERREFLECTED`로 재시도를 요청했다.

하지만 부족한 선호가 음식 관련인지, 관광지 관련인지, 숙소 관련인지에 따라 재검색해야 하는 Agent가 달라야 한다.

예시:

```text
해산물 선호 부족
→ Restaurant Agent 재검색 필요

바다/산책 선호 부족
→ Destination Agent 재검색 필요

오션뷰 숙소/호텔 선호 부족
→ Lodging Agent 재검색 필요
```

그런데 기존 구조에서는 선호 부족 이슈가 전체 itinerary 슬롯을 대상으로 잡힐 수 있었다.

그 결과 첫 슬롯이 관광지이면, 실제로는 해산물 식당이 부족한 상황인데도 Destination Agent를 다시 실행하는 식의 엇갈림이 생길 수 있었다.

### 12.2 왜 문제가 발생했는지

기존 `_evaluate_preferences()`는 선호 반영 비율이 낮으면 다음처럼 이슈를 만들었다.

```text
type=PREFERENCE_UNDERREFLECTED
slots=전체 itinerary 슬롯
reason=사용자 선호 N개 중 M개만 일정에 반영됨
```

그리고 `_actions_for()`는 이슈의 첫 번째 slot을 보고 해당 slot의 category로 retry 대상 Agent를 정했다.

기존 판단 방식:

```text
issue.slots[0]의 category 확인
DESTINATION이면 destination 재검색
RESTAURANT이면 restaurant 재검색
LODGING이면 lodging 재검색
```

이 방식은 일반적인 category 이슈에는 쓸 수 있지만, `PREFERENCE_UNDERREFLECTED`처럼 여러 선호가 섞인 이슈에는 부정확하다.

예를 들어:

```text
사용자 선호: 바다, 해산물
일정 슬롯: D1_DESTINATION, D1_LUNCH
부족한 선호: 해산물
```

이 상황에서 `slots`가 전체 itinerary로 들어가면 첫 슬롯 `D1_DESTINATION` 때문에 Destination Agent가 재검색 대상으로 잡힐 수 있다.

### 12.3 어떻게 처리했는지

수정 파일:

```text
app/agents/validation.py
app/core/state.py
app/schemas/travel.py
tests/test_validation.py
```

`QualityIssue`에 재검색 대상과 관련 선호를 명시할 수 있는 필드를 추가했다.

추가 필드:

```text
target_agent
target_preferences
```

이제 `PREFERENCE_UNDERREFLECTED` 이슈를 만들 때 부족한 선호를 담당 Agent별로 나눈다.

음식/식당 관련 선호:

```text
음식
맛집
식당
해산물
회
물회
생선
대게
홍게
조개
막국수
순두부
한식
양식
중식
카페
커피
디저트
베이커리
브런치
food
cafe
```

위 선호가 부족하면:

```text
target_agent=restaurant
```

숙소 관련 선호:

```text
숙소
숙박
호텔
펜션
리조트
민박
게스트하우스
lodging
accommodation
```

또는 선호 문구에 `숙소`가 포함되면:

```text
target_agent=lodging
```

그 외 선호는 관광지/활동 성격으로 보고:

```text
target_agent=destination
```

그리고 `_actions_for()`는 `target_agent`가 있으면 첫 번째 슬롯의 category를 추정하지 않고, 명시된 `target_agent`를 그대로 사용한다.

수정 전:

```text
PREFERENCE_UNDERREFLECTED
→ 첫 슬롯 category 기준으로 retry agent 결정
```

수정 후:

```text
PREFERENCE_UNDERREFLECTED
→ 부족한 선호 키워드 기준으로 retry agent 결정
```

### 12.4 결과가 어떻게 나왔는지

추가 테스트:

```text
tests/test_validation.py
```

확인 내용:

```text
해산물/회 선호가 부족하면 restaurant Agent로 retry action 생성
바다/산책 선호가 부족하면 destination Agent로 retry action 생성
오션뷰 숙소/호텔 선호가 부족하면 lodging Agent로 retry action 생성
```

테스트 결과:

```text
python -B -m unittest tests.test_validation

Ran 13 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 80 tests
OK (skipped=6)
```

이제 선호 부족 문제가 발생했을 때 부족한 선호의 성격에 맞는 Agent를 다시 실행한다.

예를 들어 해산물 식당이 부족한 경우 Destination Agent를 반복 실행하는 대신 Restaurant Agent를 재검색 대상으로 지정한다.

### 12.5 남은 확인 사항

이번 수정은 AI Agent 내부 retry 대상 결정 로직을 개선한 것이다.

다만 선호 만족 여부 자체를 얼마나 엄격하게 볼지는 아직 Search Tool 고도화와 함께 다시 봐야 한다.

남은 관련 개선:

```text
food 같은 넓은 matched_conditions를 구체 선호 만족으로 볼지 판단 기준 정교화
Search Tool이 matched_preferences를 더 구체적으로 내려주도록 개선
Quality Validator가 name/cuisine/tags/matched_conditions를 함께 보고 선호 만족도를 계산하는 방식 개선
조건 완화 또는 대체 추천 이유를 최종 Response Agent 답변에 반영
실패 응답을 사용자 친화적인 문장으로 정리
```

정리하면 이번 개선은 "선호 부족 판단 후 어떤 Agent를 다시 실행할지"를 바로잡은 것이고, "선호를 만족했다고 볼 수 있는 기준 자체"는 Search Tool 개선과 함께 다음 단계에서 다루는 것이 좋다.

## 13. 조건 완화 및 실패 결과가 사용자에게 충분히 설명되지 않는 문제

### 13.1 어떤 문제가 있었는지

후보가 부족해서 검색 조건을 완화하거나, 결국 일정을 만들지 못했을 때 사용자가 이해할 수 있는 설명이 부족했다.

내부 state에는 다음 정보가 남아 있었다.

```text
search_relaxations
search_diagnostics
missing_slots
hard_validation.violations
quality_validation.issues
errors
```

하지만 최종 사용자가 보는 `final_response.answer`와 `final_response.notices`에는 이 정보가 충분히 자연스럽게 정리되지 않았다.

문제 상황:

```text
조건을 완화해서 일정 생성 성공
→ 사용자는 왜 일부 장소가 원래 요청과 조금 다르게 추천됐는지 알기 어려움

후보 부족 또는 검증 실패로 일정 생성 실패
→ 사용자는 어떤 조건 때문에 실패했는지, 무엇을 바꿔 다시 요청하면 좋을지 알기 어려움
```

### 13.2 왜 문제가 발생했는지

기존 `Response Agent`는 검증 완료 일정이 있을 때는 일정 내용 중심으로만 답변을 만들었다.

조건 완화 기록인 `search_relaxations`는 state와 API 응답에는 포함됐지만, 최종 답변 문장에는 반영되지 않았다.

또한 실패 상태에서는 `_pending_response()`가 짧은 안내만 만들었다.

수정 전 실패 응답 성격:

```text
여행 일정을 완성하지 못했습니다. 검색 및 검증 결과를 확인해 주세요.
```

이 문장은 개발자가 내부 JSON을 함께 보면 이해할 수 있지만, 사용자 입장에서는 다음을 알기 어렵다.

```text
어떤 후보가 부족했는지
어떤 조건을 완화해서 다시 찾아봤는지
검증에서 어떤 이유로 걸렸는지
다음 요청에서 무엇을 바꾸면 좋은지
```

### 13.3 어떻게 처리했는지

수정 파일:

```text
app/agents/response.py
tests/test_response.py
```

#### 13.3.1 조건 완화 안내 생성

`Response Agent`가 `search_relaxations`를 읽어서 사용자용 안내 문장을 만들도록 했다.

예시 입력:

```json
{
  "domain": "RESTAURANT",
  "original_query": "해산물",
  "used_query": "맛집 음식 식당",
  "original_regions": ["GANGNEUNG"],
  "used_regions": ["GANGNEUNG", "DONGHAE"]
}
```

생성 안내:

```text
음식점 후보가 부족해 검색어를 '해산물'에서 '맛집 음식 식당'으로 넓히고, 인접 지역 후보까지 함께 검토했습니다.
```

조건 완화 유형별 안내:

```text
검색어만 바뀐 경우
→ 검색어를 넓혀 다시 찾았다고 설명

지역만 바뀐 경우
→ 요청 지역 주변 후보까지 검토했다고 설명

검색어와 지역이 모두 바뀐 경우
→ 검색어와 지역을 모두 넓혔다고 설명
```

#### 13.3.2 성공 응답에 "시도한 보완" 섹션 추가

일정 생성에 성공했더라도 조건 완화가 있었다면 fallback answer에 별도 섹션을 추가한다.

수정 후 답변 구조:

```text
강릉 1일 여행 일정

1일차 - ...
- ...

숙소
- ...

시도한 보완
- 음식점 후보가 부족해 검색어를 넓혀 다시 찾았습니다.

방문 전 확인
- 운영시간과 이용 가능 여부는 달라질 수 있으니 방문 전 한 번 더 확인해 주세요.
- 운영시간 또는 접근성 미확인 안내
```

`notices`에도 조건 완화 안내를 포함한다.

프론트가 `answer`만 보여줘도 설명이 나오고, 나중에 `notices`를 별도 UI로 보여줘도 같은 정보를 활용할 수 있다.

또한 일정이 생성된 경우에는 항상 방문 전 확인 안내를 포함하도록 했다.

```text
운영시간과 이용 가능 여부는 달라질 수 있으니 방문 전 한 번 더 확인해 주세요.
```

오픈 데이터나 검색 결과가 실제 최신 운영 정보와 다를 수 있고, 일부 시간 정보가 추정 기반일 수 있기 때문이다.

#### 13.3.3 실패 응답 사용자 친화화

실패 상태에서는 다음 정보를 모아 사용자용 안내를 만든다.

```text
missing_slots
hard_validation.violations[].reason
quality_validation.issues[].reason
search_diagnostics[].shortage
errors
search_relaxations
```

수정 후 실패 답변 구조:

```text
요청 조건에 맞는 장소 후보가 부족해 여행 일정을 완성하지 못했습니다.

시도한 보완
- 음식점 후보가 부족해 검색어를 '해산물'에서 '해산물 맛집 음식 식당'으로 넓혀 다시 찾았습니다.

확인된 이유
- 일정에 필요한 장소 후보가 부족한 슬롯이 2개 있습니다.
- 음식점 검색 결과가 필요한 수보다 2개 부족했습니다.

다시 요청하실 때는 지역, 여행 기간, 꼭 필요한 조건을 조금 더 좁히거나 완화해 주세요.
```

즉 실패하더라도 단순히 `failed`만 내려주는 것이 아니라, 사용자가 다음 행동을 이해할 수 있는 문장형 응답을 제공한다.

### 13.4 결과가 어떻게 나왔는지

추가 테스트:

```text
tests/test_response.py
```

확인 내용:

```text
조건 완화가 있었던 성공 응답은 notices와 answer에 완화 이유를 포함한다.
검색어와 지역이 함께 완화된 경우 "인접 지역 후보까지 함께 검토"했다고 설명한다.
실패 응답은 response_status=FAILED를 유지한다.
실패 응답은 days를 비워 둔다.
실패 응답 summary는 사용자용 실패 이유를 담는다.
실패 응답 answer에는 "시도한 보완", "확인된 이유" 섹션이 들어간다.
search_diagnostics.shortage를 사용해 후보 부족 수를 사용자용 문장으로 안내한다.
```

테스트 결과:

```text
python -B -m unittest tests.test_response

Ran 15 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 82 tests
OK (skipped=6)
```

### 13.5 남은 확인 사항

이번 수정은 Search Tool을 바꾸지 않고, 이미 AI Agent state에 남는 정보를 사용자용 응답으로 정리하는 개선이다.

추후 실제 프론트 연결 테스트에서 확인할 것:

```text
프론트가 final_response.answer를 사용자에게 표시하는지
프론트가 final_response.notices를 별도 안내 영역으로 보여줄지
조건 완화 안내가 너무 장황하지 않은지
지역 확장으로 선택된 장소가 있을 때 사용자에게 충분히 납득 가능한지
LLM 응답을 켰을 때도 accommodations, notices, 조건 완화 안내를 자연스럽게 반영하는지
```

남은 관련 개선:

```text
Search Tool이 더 구체적인 matched_preferences와 diagnostics를 내려주도록 개선
food 같은 넓은 매칭을 선호 만족으로 볼지 판단 기준 정교화
대화형 일정 수정 기능에서 변경 전/후 차이를 사용자에게 설명
실패 원인별 추천 재요청 문구를 더 세분화
```

정리하면 이번 개선은 조건 완화와 실패 원인을 개발자용 state에만 두지 않고, 최종 사용자에게 이해 가능한 답변으로 풀어주는 작업이다.

## 14. Search Tool 2차 개선 응답 필드 AI Agent 연동

### 14.1 어떤 문제가 있었는지

Search Tool 2차 개선으로 후보 판단 근거가 더 구체적으로 내려오게 됐다.

추가된 주요 필드:

```text
matched_keywords
matched_preference_details
place_subtype
region_code
region_match
diagnostics.under_matched_preferences
diagnostics.unmatched_query_terms
diagnostics.missing_evidence_fields
```

하지만 AI Agent의 Search 응답 계약 모델은 `extra="forbid"`를 사용한다.

즉 AI Agent가 새 필드를 모르면 Search Tool 응답을 파싱하는 단계에서 실패할 수 있다.

또한 새 필드를 단순히 허용만 하고 state에 보존하지 않으면, 다음 개선 효과를 얻을 수 없다.

```text
세부 키워드가 실제로 매칭됐는지 판단
카페/식당/베이커리/디저트 구분
후보의 실제 지역 확인
선호 부족/근거 부족 diagnostics를 사용자 응답에 반영
```

### 14.2 왜 문제가 발생했는지

기존 AI Agent는 Search Tool의 예전 응답 필드만 알고 있었다.

기존 후보 근거:

```text
matched_preferences
missing_fields
evidence
status
```

이 구조에서는 `food` 같은 넓은 선호 범주와 `해산물`, `물회`, `대게` 같은 세부 키워드를 구분하기 어려웠다.

또한 카페/식당 구분도 Search Tool이 명시적으로 내려주는 값이 없어서 AI Agent가 이름과 cuisine을 보고 추정했다.

수정 전 카페 판단:

```text
name/cuisine/matched_conditions에 카페, 커피, 베이커리, 디저트 등이 있으면 CAFE로 추정
```

Search Tool이 이제 `place_subtype`을 내려주므로, AI Agent는 추정보다 명시 필드를 우선해야 한다.

### 14.3 어떻게 처리했는지

수정 파일:

```text
app/search/models.py
app/search/request_factory.py
app/agents/destination.py
app/agents/restaurant.py
app/agents/lodging.py
app/agents/itinerary.py
app/agents/response.py
app/core/state.py
app/schemas/travel.py
tests/fixtures/search_response.json
tests/test_search_contract.py
tests/test_search_integration.py
```

#### 14.3.1 Search 응답 계약 모델 확장

`SearchCandidate`에 새 필드를 추가했다.

```text
place_subtype
region_code
region_match
matched_keywords
matched_preference_details
```

`SearchDiagnostics`에도 새 필드를 추가했다.

```text
under_matched_preferences
unmatched_query_terms
missing_evidence_fields
```

이제 Search Tool이 새 응답 필드를 내려줘도 AI Agent 계약 모델에서 정상 파싱된다.

#### 14.3.2 각 Agent 후보 state에 새 근거 보존

`Destination Agent`, `Restaurant Agent`, `Lodging Agent`가 Search Tool 응답의 새 필드를 각 후보 state에 담도록 했다.

보존하는 후보 정보:

```text
matched_conditions
matched_keywords
matched_preference_details
region_code
region_match
place_subtype 또는 subtype
```

`matched_conditions`에는 기존 `matched_preferences`와 새 `matched_keywords`를 함께 넣는다.

예시:

```json
{
  "matched_preferences": ["food"],
  "matched_keywords": ["해산물", "물회"]
}
```

AI Agent 내부 후보:

```json
{
  "matched_conditions": ["food", "해산물", "물회"],
  "matched_keywords": ["해산물", "물회"]
}
```

이렇게 하면 기존 로직은 `matched_conditions`를 그대로 사용할 수 있고, 새 세부 키워드도 일정 후보 태그와 검증 근거로 반영된다.

#### 14.3.3 place_subtype 우선 사용

`Itinerary Agent`의 식당/카페 구분 로직을 수정했다.

수정 전:

```text
name/cuisine/matched_conditions를 보고 카페 여부 추정
```

수정 후:

```text
place_subtype 또는 subtype이 있으면 명시 값을 우선 사용
명시 값이 없을 때만 기존 키워드 추정 사용
```

처리 정책:

```text
place_subtype=RESTAURANT
→ 점심/저녁 식사 슬롯에 사용 가능

place_subtype=CAFE, BAKERY, DESSERT
→ 카페 슬롯에 사용
→ 점심/저녁 슬롯에서는 제외
```

#### 14.3.4 diagnostics 새 필드 보존 및 실패 응답 반영

`build_search_diagnostic()`이 Search Tool diagnostics의 새 필드를 state에 저장하도록 했다.

보존 필드:

```text
under_matched_preferences
unmatched_query_terms
missing_evidence_fields
```

그리고 `Response Agent` 실패 응답에서 이 정보를 사용자용 문장으로 풀어준다.

예시:

```text
음식점 검색에서 해산물 조건과 직접 맞는 후보가 부족했습니다.
음식점 후보에서 pet_allowed 정보를 충분히 확인하지 못했습니다.
```

### 14.4 결과가 어떻게 나왔는지

추가/수정한 테스트:

```text
tests/test_search_contract.py
tests/test_search_integration.py
tests/fixtures/search_response.json
```

확인 내용:

```text
SearchResponse가 새 후보 필드를 정상 파싱한다.
SearchDiagnostics가 unmatched_query_terms, missing_evidence_fields 등을 정상 파싱한다.
Restaurant Agent가 place_subtype을 subtype으로 보존한다.
Restaurant Agent가 matched_keywords와 region_code를 후보 state에 보존한다.
Search diagnostics의 새 필드가 search_diagnostics state에 남는다.
Itinerary Agent는 명시 place_subtype을 카페/식당 구분에 우선 사용한다.
```

관련 테스트:

```text
python -B -m unittest tests.test_search_contract tests.test_search_integration tests.test_itinerary tests.test_response

Ran 51 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 83 tests
OK (skipped=6)
```

### 14.5 남은 확인 사항

이번 수정은 Search Tool 2차 개선 응답을 AI Agent가 받을 수 있게 연결한 작업이다.

실제 효과는 Search Tool 재색인과 전체 프론트 시나리오 테스트로 확인해야 한다.

확인할 것:

```text
해산물/물회/대게 요청에서 matched_keywords가 후보 state에 남는지
food만 있고 해산물 matched_keywords가 없을 때 Quality Validator가 선호 부족을 잘 판단하는지
place_subtype=CAFE/BAKERY/DESSERT 후보가 점심/저녁 슬롯에서 제외되는지
place_subtype=RESTAURANT 후보가 카페 슬롯에 잘못 들어가지 않는지
강릉 요청에서 다른 지역 후보가 섞일 경우 region_code/region_match로 설명 가능한지
missing_evidence_fields가 반려동물/무장애 실패 응답에 사용자 친화적으로 반영되는지
```

정리하면 Search Tool이 준 "후보 판단 근거"를 AI Agent가 계약 모델, 후보 state, 일정 생성, 실패 응답까지 이어받도록 연결했다.

## 14. Search Tool 2차 응답 근거 보강

### 14.1 왜 다시 Search Tool을 봤나

AI Agent 2차 개선으로 슬롯 생성, 카페/식당 분리, 재검색 대상 선택, 실패 응답 안내는 좋아졌다.

하지만 Search Tool 응답이 아직 후보 판단 근거를 충분히 구체적으로 내려주지 않으면 다음 문제가 남는다.

```text
food만 내려오면 해산물/물회/대게가 실제로 맞았는지 알기 어렵다.
카페 후보가 RESTAURANT 도메인 안에 섞여 있으면 식사 슬롯과 카페 슬롯을 안정적으로 나누기 어렵다.
후보가 부족할 때 어떤 선호 단어가 실제로 안 맞았는지 알기 어렵다.
반려동물/무장애 필수 조건에서 어떤 evidence가 부족한지 AI Agent가 사용자에게 설명하기 어렵다.
```

즉 이번 작업은 후보를 더 많이 찾는 작업이라기보다, AI Agent가 후보를 더 정확히 판단할 수 있도록 Search Tool 응답 근거를 세분화한 작업이다.

### 14.2 후보별 세부 매칭 키워드 추가

기존 응답:

```json
{
  "matched_preferences": ["food", "oceanView"]
}
```

이 응답만으로는 후보가 정말 `물회`, `대게`, `해산물`, `오션뷰`를 만족했는지 알기 어렵다.

수정 후에는 후보별로 실제 매칭된 키워드를 함께 내려준다.

```json
{
  "matched_preferences": ["food", "oceanView"],
  "matched_keywords": ["물회", "대게", "해산물", "바다", "항구"],
  "matched_preference_details": [
    {
      "preference": "food",
      "matched_keywords": ["해산물", "물회", "대게"],
      "fields": ["searchText"]
    },
    {
      "preference": "oceanView",
      "matched_keywords": ["바다", "항구"],
      "fields": ["searchText"]
    }
  ]
}
```

AI Agent에서 활용할 수 있는 방식:

```text
matched_preferences:
- food, oceanView 같은 큰 선호 범주가 반영됐는지 확인

matched_keywords:
- 사용자가 말한 세부 선호가 실제 후보 텍스트에 걸렸는지 확인
- 예: 물회, 대게, 해산물, 오션뷰

matched_preference_details:
- 어떤 선호가 어떤 키워드로, 어떤 ES 문서 필드에서 맞았는지 확인
- Quality Validator의 PREFERENCE_UNDERREFLECTED 판단 근거로 사용
```

### 14.3 카페/식당 구분을 위한 place_subtype 추가

Restaurant 도메인 안에는 일반 식당뿐 아니라 카페, 베이커리, 디저트 후보가 함께 들어 있다.

그래서 Search Tool 응답에 `place_subtype`을 추가했다.

```json
{
  "domain": "RESTAURANT",
  "place_subtype": "CAFE"
}
```

현재 구분값:

```text
RESTAURANT
CAFE
BAKERY
DESSERT
LODGING
DESTINATION
```

판단 기준:

```text
menuType, name을 먼저 보고 장소 정체성을 분류한다.
베이커리/빵집/제과 신호가 있으면 BAKERY
디저트/젤라또/아이스크림/빙수/케이크 신호가 있으면 DESSERT
카페/커피 신호가 있으면 CAFE
그래도 분류되지 않으면 firstMenu, treatMenu를 보조 판단에 사용한다.
그 외 RESTAURANT
```

AI Agent에서 활용할 수 있는 방식:

```text
LUNCH/DINNER:
- place_subtype=RESTAURANT 우선
- CAFE/BAKERY/DESSERT는 사용자가 명확히 카페 식사를 원할 때만 허용

CAFE 슬롯:
- place_subtype=CAFE, BAKERY, DESSERT 우선
```

### 14.4 지역 판단 필드 추가

후보별 실제 지역을 AI Agent가 바로 알 수 있도록 응답에 `region_code`와 `region_match`를 추가했다.

```json
{
  "region_code": "SOKCHO",
  "region_match": true
}
```

의미:

```text
region_code:
- 후보가 실제로 속한 지역 코드

region_match:
- 현재 SearchRequest의 region_codes 안에 후보 지역이 포함되면 true
```

주의:

```text
Search Tool은 현재 요청 지역의 원래 값과 AI Agent가 확장한 지역을 구분해서 알지는 못한다.
따라서 "강릉 요청이었지만 동해까지 확장했다" 같은 설명은 AI Agent의 search_relaxations와 함께 판단해야 한다.
Search Tool은 후보의 실제 region_code를 내려주고, AI Agent가 원 요청 지역과 비교하는 방식이 안전하다.
```

### 14.5 diagnostics 세부 정보 추가

후보가 부족하거나, 선호/근거가 부족하면 diagnostics에 더 구체적인 정보를 넣는다.

추가 필드:

```json
{
  "under_matched_preferences": ["food"],
  "unmatched_query_terms": ["해산물"],
  "missing_evidence_fields": ["pet_allowed", "pet_size"]
}
```

의미:

```text
under_matched_preferences:
- soft_preferences 중 어떤 선호 범주가 결과 후보에서 매칭되지 않았는지

unmatched_query_terms:
- query_text 안의 단어 중 결과 후보 텍스트에서 확인되지 않은 단어

missing_evidence_fields:
- 후보 검증에 필요한 evidence 중 부족한 필드
```

AI Agent에서 활용할 수 있는 방식:

```text
under_matched_preferences에 food가 있음
→ 음식 선호가 후보에 잘 반영되지 않았다고 판단
→ Restaurant Agent 재검색 또는 query_text 보강

unmatched_query_terms에 해산물이 있음
→ 해산물 직접 매칭이 부족하다고 판단
→ 물회/대게/회 등 동의어 확장 또는 사용자 안내

missing_evidence_fields에 pet_allowed가 있음
→ 반려동물 필수 근거 부족
→ 조건을 자동 완화하지 말고 사용자에게 대안 선택 안내
```

### 14.6 수정 파일

```text
src/main/java/com/gangwon/companion/domain/search/dto/PlaceSearchResponse.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocument.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssembler.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchIndexService.java
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngineTest.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/PlaceSearchDocumentAssemblerTest.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchIndexServiceTest.java
src/test/java/com/gangwon/companion/domain/search/indexer/SearchIndexEventServiceTest.java
```

### 14.7 테스트 결과

```text
./gradlew.bat test --tests com.gangwon.companion.domain.search.elasticsearch.* --tests com.gangwon.companion.domain.search.dto.PlaceSearchContractTest --tests com.gangwon.companion.domain.search.indexer.SearchIndexEventServiceTest

BUILD SUCCESSFUL
```

확인한 내용:

```text
기존 SearchResponse fixture 역직렬화가 깨지지 않음
후보별 matched_keywords가 내려감
후보별 matched_preference_details가 내려감
restaurant 후보의 place_subtype이 내려감
diagnostics에 unmatched_query_terms와 missing_evidence_fields가 포함됨
ES strict mapping에 placeSubtype이 포함됨
```

### 14.8 재색인 필요

이번 작업은 ES 문서 필드에 `placeSubtype`을 추가했기 때문에 실제 검색 환경에서는 재색인이 필요하다.

```text
PlaceSearchDocument documentVersion: 6 → 7
```

재색인 후 확인할 것:

```text
RESTAURANT 문서에 placeSubtype이 들어갔는지
카페 후보가 place_subtype=CAFE/BAKERY/DESSERT로 내려오는지
해산물/물회/대게 요청에서 matched_keywords가 세부 키워드로 내려오는지
food의 한 글자 키워드 "회"는 전용 오탐 방지 규칙을 통과할 때만 매칭되는지
oceanView의 넓은 키워드 "전망"처럼 과매칭 위험이 큰 단어가 결과를 흐리지 않는지
후보 부족 시 diagnostics.unmatched_query_terms가 실제 부족 키워드를 보여주는지
```

정리하면 이번 Search Tool 2차 개선은 AI Agent가 "이 후보가 왜 선택됐는지"와 "왜 아직 부족한지"를 더 명확히 판단하도록 응답 근거를 보강한 작업이다.

### 14.9 한 글자 키워드 오탐 방지 규칙 추가

`회`, `산`은 사용자가 실제로 자주 쓰는 자연스러운 키워드다.

하지만 단순 포함 검색으로 처리하면 문제가 생긴다.

```text
해산물 안의 "산"이 산 선호로 잡힘
설악산로 같은 도로명 안의 "산"이 산 선호로 잡힘
회의실/회관 같은 단어 안의 "회"가 음식 선호로 잡힐 수 있음
```

그래서 `회`, `산`을 완전히 제거하지 않고, 위험한 짧은 키워드로 보고 전용 매칭 규칙을 추가했다.

#### 회 매칭 규칙

`회`는 음식 문맥일 때만 `matched_keywords`로 인정한다.

인정 예:

```text
회
횟집
회센터
회센타
생선회
모둠회
활어회
광어회
우럭회
오징어회
물회
회덮밥
회 맛집
회 전문
```

이제 `food` 확장 키워드에 `회`를 다시 포함하되, 위 규칙을 통과한 경우에만 `matched_keywords=["회"]`로 내려간다.

#### 산 매칭 규칙

`산`은 산/등산/산림 문맥일 때만 `matched_keywords`로 인정한다.

인정 예:

```text
산
설악산
오대산
치악산
태백산
가리왕산
두타산
등산
산 정상
산림
산자락
산길
산속
```

제외 예:

```text
해산물
설악산로
부동산
계산
생산
산업
```

특히 `설악산`은 인정하지만 `설악산로`, `설악산 로`, `설악산길`, `설악산번길`처럼 도로명으로 보이는 경우는 산 선호 근거로 보지 않는다.
또 `설악산코코`처럼 산 이름 뒤에 다른 글자가 바로 붙은 상품명/메뉴명도 산 선호 근거로 보지 않는다.

#### AI Agent가 이해하면 좋은 점

```text
Search Tool의 matched_keywords는 단순 문자열 포함 결과가 아니다.
짧은 위험 키워드는 오탐 방지 규칙을 통과한 경우만 들어간다.
따라서 matched_keywords에 "회" 또는 "산"이 있으면 그 후보는 해당 문맥 검사를 통과한 후보로 보면 된다.
반대로 query_text에 "물회"를 보냈는데 unmatched_query_terms에 "물회"가 있으면, 단순히 "회"가 걸린 후보를 물회 만족 후보로 보지 않았다는 뜻이다.
```

테스트 추가:

```text
allowsShortHoeKeywordOnlyInFoodContext
rejectsShortMountainKeywordWhenItOnlyAppearsInsideUnrelatedWordsOrRoadNames
allowsShortMountainKeywordInMountainContext
```

## 15. AI Agent 3차 개선: 입력 파싱, 검색 요청 분리, 검증 재시도 정책 보강

### 15.1 해결하려던 문제

2차 개선 후 프론트에서 실제 자연어 시나리오를 테스트하면서 다음 문제가 확인됐다.

```text
1. 하루, 이틀, 1일 같은 여행 기간 표현을 제대로 읽지 못함
2. 소형견이랑 같이 간다는 표현에서 pet_size만 잡고 pet_allowed=true를 못 잡음
3. 카페보다는 관광지 위주 같은 비교/부정 표현을 카페 선호로 잘못 해석함
4. 물회, 회 같은 식당 키워드가 관광지/숙소 SearchRequest에도 섞임
5. 장소의 max_pet_size 근거가 없다는 이유만으로 전체 일정이 실패함
6. 반려동물/무장애 evidence 부족만 반복되는데도 같은 재검색 루프가 계속 돎
```

이번 작업에서는 notice 출력 정책은 건드리지 않았다.

현재 프론트에서는 notice를 사용자에게 직접 보여주지 않고, 개발자들이 JSON으로 확인하는 용도에 가깝기 때문이다.

### 15.2 음식 키워드가 관광지/숙소 검색으로 흘러간 이유

AI Agent의 선호 추출 흐름은 다음과 같다.

```text
PreferenceExtractor
→ request.preferences / preference_profile.keywords에 선호 키워드를 공용 리스트로 저장
→ SearchRequest 생성 시 domain별 query_text 생성
```

문제는 SearchRequest 생성부의 도메인별 키워드 분류 목록이 충분하지 않았다는 점이다.

수정 전에는 `_keywords_for()`가 다음 정책으로 동작했다.

```text
도메인에 허용된 키워드면 사용
어느 도메인에도 분류되지 않은 키워드면 일단 사용
```

이 정책 자체는 새로운 키워드를 너무 쉽게 버리지 않기 위한 안전장치였다.

하지만 `물회`, `회`, `대게`, `홍게`, `조개구이` 같은 음식 키워드가 도메인 분류 목록에 충분히 들어가 있지 않으면, 이 키워드들이 “분류되지 않은 키워드”로 취급되어 관광지/숙소 검색에도 그대로 들어갈 수 있었다.

예시:

```text
사용자 요청:
강릉으로 2일 여행 갈 거야. 바다 보고 물회나 회를 먹고 싶어.

추출 키워드:
["바다", "물회", "회"]

수정 전 위험:
DESTINATION query_text = "바다 물회 회"
LODGING query_text = "바다 물회 회"
RESTAURANT query_text = "바다 물회 회"
```

이렇게 되면 Search Tool 입장에서는 관광지/숙소 검색에서도 음식 키워드를 만족해야 하는 것처럼 보일 수 있고, diagnostics에서 불필요한 `NO_TEXT_MATCH`, `unmatched_query_terms`가 발생할 수 있다.

### 15.3 수정 내용: 여행 기간 파싱 보강

#### 수정 전

숫자 기반 `n박 m일`, `m일`, `당일치기` 중심으로만 여행 기간을 읽었다.

그래서 실제 사용자가 자주 쓰는 표현인 `하루`, `이틀`이 누락될 수 있었다.

#### 수정 후

`app/agents/input_parser.py`에 한국어 기간 표현을 추가했다.

```text
하루 → travel_days=1
당일 → travel_days=1
당일치기 → travel_days=1, nights=0
이틀 → travel_days=2
사흘 → travel_days=3
나흘 → travel_days=4
1일 → travel_days=1
```

#### 동작 변화

```text
강릉으로 이틀 여행 갈 거야.
→ travel_days=2

강릉으로 하루 여행 갈 거야.
→ travel_days=1
```

이제 사용자가 이미 기간을 말했는데도 “여행 기간이 며칠인가요?”라고 다시 묻는 상황을 줄일 수 있다.

### 15.4 수정 내용: 반려동물 크기 표현에서 동반 여부 함께 추론

#### 수정 전

```text
소형견이랑 같이 갈 수 있는 곳
```

위 문장에서 `pet_size=SMALL`은 추출됐지만 `pet_allowed=true`가 함께 추출되지 않았다.

그 결과 사용자는 이미 반려동물과 함께 간다고 말했는데도 다음 질문을 다시 받았다.

```text
반려동물과 함께 가시는지 알려주세요.
```

#### 수정 후

`소형견`, `중형견`, `대형견`, `강아지`, `반려견`, `반려동물` 같은 표현이 다음 문맥과 같이 나오면 `pet_allowed=true`도 함께 채운다.

```text
같이
함께
동반
데려
데리고
```

#### 동작 변화

```text
소형견이랑 같이 바다 산책하고 싶어.
→ pet_allowed=true
→ pet_size=SMALL
```

### 15.5 수정 내용: 부정/비교 선호 표현 처리

#### 수정 전

```text
카페보다는 관광지 위주로 보고 싶어.
```

위 문장에서 `카페`라는 단어가 포함되어 있다는 이유로 카페가 긍정 선호로 들어갈 수 있었다.

그 결과 슬롯이 다음처럼 만들어질 수 있었다.

```text
D1_DESTINATION
D1_LUNCH
D1_CAFE
D1_DINNER
```

하지만 실제 의도는 카페를 우선하겠다는 뜻이 아니라 관광지를 더 보고 싶다는 뜻이다.

#### 수정 후

다음 표현은 앞쪽 키워드를 긍정 선호에서 제외하도록 했다.

```text
A보다는 B
A보다 B
A 말고 B
A 빼고 B
A 제외
A 적게
```

또 Supervisor에서도 `카페보다는`, `카페보다`, `카페 말고`, `카페 빼고` 같은 문장이 있으면 카페 슬롯을 만들지 않도록 했다.

#### 동작 변화

```text
카페보다는 관광지 위주로 보고 싶어.
→ preferences에 카페를 넣지 않음
→ 관광지 중심 기본 슬롯 유지
```

슬롯 예:

```text
D1_DESTINATION
D1_LUNCH
D1_EXTRA_DESTINATION
D1_DINNER
```

### 15.6 수정 내용: 도메인별 검색 키워드 분리

#### 수정 전

도메인별 키워드 목록이 부족해서 음식 키워드가 관광지/숙소 검색으로 흘러갈 수 있었다.

#### 수정 후

`app/search/request_factory.py`의 `_DOMAIN_KEYWORDS`를 확장했다.

도메인별 키워드 예시는 다음과 같다.

```text
DESTINATION:
바다, 해변, 해수욕장, 자연, 산책, 트레킹, 등산, 전망대, 야경, 체험, 박물관 등

RESTAURANT:
해산물, 회, 물회, 대게, 홍게, 조개, 막국수, 순두부, 닭갈비, 한식, 카페 등

LODGING:
오션뷰, 오션뷰숙소, 조용한, 한적한, 숙소, 호텔, 펜션, 리조트, 풀빌라 등
```

#### 동작 변화

예시 입력:

```text
preferences = ["바다", "물회", "회", "오션뷰"]
```

SearchRequest 생성 결과:

```text
DESTINATION query_text = "바다"
RESTAURANT query_text = "물회 회"
LODGING query_text = "바다 오션뷰"
```

즉 음식 키워드는 식당 검색에 집중되고, 관광지/숙소 검색에서는 해당 도메인에 맞는 키워드만 사용된다.

### 15.7 수정 내용: pet_size 근거 부족은 실패 조건에서 제외

#### 수정 전

사용자가 `pet_size=SMALL`을 요청했는데 장소 후보에 `max_pet_size` 근거가 없으면 Hard Validator가 `EVIDENCE_MISSING`으로 실패 처리했다.

```text
필수 근거 데이터가 없습니다: maxPetSize
```

하지만 현재 데이터에서는 장소별 허용 반려동물 크기 정보가 안정적으로 제공되지 않을 수 있다.

#### 수정 후

`max_pet_size`가 없다는 이유만으로는 전체 일정을 실패시키지 않도록 했다.

단, 장소에 `max_pet_size`가 있고 사용자가 요청한 크기보다 작으면 기존처럼 실패한다.

```text
사용자 요청 pet_size=LARGE
장소 max_pet_size=SMALL
→ PET_SIZE_NOT_ALLOWED
```

#### 동작 변화

```text
사용자 요청 pet_size=SMALL
장소 pet_allowed=true
장소 max_pet_size=null
→ Hard Validator 통과
```

이 경우 허용 가능한 반려동물 크기는 별도 확인이 필요한 정보로 남는다.

### 15.8 수정 내용: 필수 evidence 부족 반복 시 재검색 조기 종료

#### 수정 전

반려동물/무장애 조건에서 후보는 받았지만 근거 데이터가 부족하면 다음 흐름이 반복됐다.

```text
Hard Validator EVIDENCE_MISSING
→ validation retry
→ 다시 검색
→ 다시 EVIDENCE_MISSING
→ 최대 재시도 초과
```

#### 수정 후

`validation_retry_node()`에서 다음 조건이면 재검색을 반복하지 않고 실패 상태로 전환한다.

```text
hard_validation.status == INVALID
모든 violation.code == EVIDENCE_MISSING
reason에 petAllowed / indoorPetAllowed / wheelchairAccessible 근거 부족이 포함됨
```

#### 동작 변화

후보 수 부족이나 실제 조건 위반은 기존처럼 재검색/재구성 대상으로 남긴다.

하지만 필수 evidence 자체가 부족한 상황은 같은 검색을 반복해도 해결되기 어렵기 때문에 조기 종료한다.

```text
휠체어 접근 가능 여부 근거 부족
→ 동일 재검색 반복하지 않음
→ 실패 응답으로 전환
```

### 15.9 수정 파일

```text
app/agents/input_parser.py
app/agents/supervisor.py
app/search/request_factory.py
app/validators/hard_validator.py
tests/test_input_parser.py
tests/test_supervisor_slots.py
tests/test_search_integration.py
tests/test_validation.py
```

### 15.10 테스트 결과

```text
python -B -m unittest

Ran 90 tests in 0.143s
OK (skipped=6)
```

확인한 내용:

```text
하루/이틀/1일 표현을 travel_days로 추출함
소형견 동반 문맥에서 pet_allowed=true와 pet_size=SMALL을 함께 추출함
카페보다는 관광지 문장에서 카페를 긍정 선호로 넣지 않음
카페 비선호 문맥에서는 CAFE 슬롯을 만들지 않음
음식 키워드가 관광지/숙소 SearchRequest로 흘러가지 않음
max_pet_size 근거만 없을 때는 Hard Validator가 실패시키지 않음
반려동물/무장애 필수 evidence 부족만 반복되는 경우 조기 실패 처리함
```

### 15.11 남은 과제

이번 작업은 AI Agent에서 바로 개선 가능한 부분을 처리한 것이다.

아직 Search Tool/ES 데이터 쪽에서 확인해야 할 내용은 남아 있다.

```text
반려동물 동반 가능 여부 evidence 제공
휠체어 접근 가능 여부 evidence 제공
hard filter를 만족한다고 판단한 근거를 candidate에 함께 제공
가격 데이터가 없다면 가격 필터는 지원 불가 조건으로 분리
```

이후 다시 프론트 시나리오 테스트를 진행하면서 다음을 확인해야 한다.

```text
1일/하루/이틀 표현이 더 이상 추가 질문으로 이어지지 않는지
소형견 동반 요청이 바로 일정 생성으로 넘어가는지
카페보다는 관광지 요청에서 카페 슬롯이 빠지는지
물회/회 요청에서 관광지/숙소 검색어가 오염되지 않는지
반려동물/무장애 evidence 부족 시 불필요한 반복 재검색이 줄어드는지
```

## 16. Search Tool 3차 개선: 정책 조건값 응답 계약 보강

### 16.1 왜 다시 Search Tool을 봤나

AI Agent 3차 개선 후에는 자연어 이해와 재검색 정책이 더 정리됐다.

특히 다음 흐름이 개선됐다.

```text
소형견이랑 같이 가고 싶어
→ pet_allowed=true
→ pet_size=SMALL
→ Search Tool에 반려동물 조건을 유지한 채 검색 요청
```

하지만 Search Tool 응답에서 반려동물/무장애 근거를 AI Agent가 안정적으로 읽을 수 있어야 한다.

AI Agent가 기대하는 외부 응답 계약은 다음 이름이다.

```text
pet_allowed
wheelchair_accessible
max_pet_size
```

반면 Search Tool 내부 Elasticsearch 문서에서는 Java 필드명 때문에 다음 이름을 사용한다.

```text
petAllowed
wheelchairAccessible
smallPetAllowed
mediumPetAllowed
largePetAllowed
```

내부 문서 필드명이 camelCase인 것은 괜찮다.

문제는 AI Agent로 내려가는 최종 응답에서는 snake_case 계약으로 안정적으로 변환되어야 한다는 점이다.

### 16.2 수정 전 상태

Search Tool은 이미 evidence 안에서는 snake_case 필드명을 내려주고 있었다.

예:

```json
{
  "evidence": [
    {
      "field": "pet_allowed",
      "value": true,
      "source": "TOUR_API"
    },
    {
      "field": "wheelchair_accessible",
      "value": true,
      "source": "TOUR_API"
    }
  ]
}
```

하지만 후보 본문에는 다음 필드가 없었다.

```text
candidate.pet_allowed
candidate.max_pet_size
candidate.wheelchair_accessible
```

그래서 AI Agent가 evidence를 읽는 경로에서는 조건값을 알 수 있지만, 후보 객체의 top-level 필드를 읽는 경로에서는 값이 비어 있을 수 있었다.

쉽게 말하면:

```text
Search Tool: evidence 안에는 pet_allowed=true라고 말함
AI Agent 후보 객체: pet_allowed 값은 null처럼 보일 수 있음
```

이러면 Validator나 후보 변환부가 어느 경로를 보느냐에 따라 결과가 흔들릴 수 있다.

### 16.3 수정 내용: 후보 본문에도 정책 필드 추가

`PlaceSearchResponse.Candidate` 응답 DTO에 AI Agent가 바로 읽을 수 있는 필드를 추가했다.

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/dto/PlaceSearchResponse.java
```

추가한 필드:

```java
@JsonProperty("pet_allowed") Boolean petAllowed,
@JsonProperty("max_pet_size") String maxPetSize,
@JsonProperty("wheelchair_accessible") Boolean wheelchairAccessible,
```

의미:

```text
pet_allowed
→ 이 후보가 반려동물 동반 가능 근거를 가진 것으로 판단됐는지

max_pet_size
→ 확인 가능한 경우 허용 가능한 최대 반려동물 크기

wheelchair_accessible
→ 이 후보가 휠체어 접근 가능 근거를 가진 것으로 판단됐는지
```

응답 JSON에서는 다음처럼 내려간다.

```json
{
  "place_id": "DESTINATION:10",
  "pet_allowed": true,
  "max_pet_size": "SMALL",
  "wheelchair_accessible": true
}
```

### 16.4 수정 내용: ES 문서 필드를 응답 계약으로 변환

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
```

Search Tool은 ES 문서에서 다음 값을 읽는다.

```text
doc.petAllowed()
doc.smallPetAllowed()
doc.mediumPetAllowed()
doc.largePetAllowed()
doc.wheelchairAccessible()
```

그리고 AI Agent 응답 후보에는 다음 값으로 변환해서 넣는다.

```text
doc.petAllowed()
→ candidate.pet_allowed

doc.wheelchairAccessible()
→ candidate.wheelchair_accessible
```

반려동물 크기는 boolean 필드 여러 개를 보고, 알 수 있는 경우 가장 큰 허용 크기를 계산한다.

```text
largePetAllowed=true
→ max_pet_size=LARGE

mediumPetAllowed=true
→ max_pet_size=MEDIUM

smallPetAllowed=true
→ max_pet_size=SMALL
```

어떤 크기까지 가능한지 알 수 없으면 억지로 값을 만들지 않는다.

```text
smallPetAllowed=null
mediumPetAllowed=null
largePetAllowed=null
→ max_pet_size=null
```

이렇게 둔 이유는 잘 모르는 값을 true처럼 꾸미면 나중에 실제 사용자 일정에서 더 위험하기 때문이다.

이때 `max_pet_size`가 비어 있다는 이유만으로 후보를 실패 처리하지 않는다.

AI Agent 3차 개선에서 `max_pet_size` 근거 부족만으로 Hard Validator가 실패하지 않게 조정했기 때문에, Search Tool도 같은 방향으로 맞췄다.

```text
pet_allowed=true
max_pet_size=null
wheelchair_accessible=true
→ 반려동물 동반 가능/휠체어 접근 가능 근거는 인정
→ 크기 정보는 모르는 값으로 유지
→ pet_size를 필수 missing evidence로 만들지 않음
```

### 16.5 evidence와 candidate top-level 값의 역할

이번 개선 후 Search Tool 응답은 같은 정책 근거를 두 층으로 내려준다.

```text
candidate.pet_allowed
→ AI Agent 내부 후보에 바로 옮겨 담을 수 있는 조건값

candidate.evidence[].field = "pet_allowed"
→ 후보 변환 코드가 조건값을 보완해서 읽을 수 있는 근거 필드
```

즉 둘은 중복이 아니라 역할이 다르다.

예:

```json
{
  "pet_allowed": true,
  "wheelchair_accessible": true,
  "evidence": [
    {
      "field": "pet_allowed",
      "value": true,
      "source": "TOUR_API"
    },
    {
      "field": "wheelchair_accessible",
      "value": true,
      "source": "TOUR_API"
    }
  ]
}
```

정확한 흐름은 다음과 같다.

```text
Search Tool candidate
→ AI Agent 후보 변환 코드가 candidate top-level 값 또는 evidence 값을 읽음
→ AI Agent 내부 후보의 pet_allowed / wheelchair_accessible 필드에 값을 채움
→ Itinerary Agent가 내부 후보로 일정 슬롯을 만듦
→ Hard Validator는 최종 일정 슬롯의 pet_allowed / wheelchair_accessible 값을 검사함
```

즉 Hard Validator가 Search Tool의 `evidence[]`를 직접 검사하는 구조는 아니다.
검증이 성공하려면 후보 변환 이후 최종 일정 슬롯에 다음 값이 들어가 있어야 한다.

```json
{
  "pet_allowed": true,
  "wheelchair_accessible": true
}
```

### 16.6 값이 없을 때의 처리

값이 없거나 확정할 수 없는 경우에는 `true`를 억지로 넣지 않는다.

예:

```text
pet_allowed 요청 있음
하지만 Search Tool이 반려동물 근거를 찾지 못함
→ candidate.pet_allowed=null
→ evidence에 pet_allowed 없음
→ missing_fields에 pet_allowed 포함 가능
→ diagnostics.missing_evidence_fields에 pet_allowed 포함 가능
→ failure_reasons에 NO_POLICY_EVIDENCE 포함 가능
```

이 흐름이 중요한 이유는 AI Agent가 필수 조건을 임의로 완화하면 안 되기 때문이다.

반려동물/무장애 조건은 후보가 부족하다고 마음대로 풀 조건이 아니다.

따라서 Search Tool은 다음처럼 동작해야 한다.

```text
확실히 가능함
→ true와 evidence 제공

확실히 불가능함
→ false 또는 후보 제외

모름
→ null + missing evidence/diagnostics 제공
```

단, diagnostics는 AI Agent가 전체 재검색/조기 종료 판단에 쓰는 값이므로 너무 넓게 잡으면 안 된다.

그래서 후보별 근거 부족과 검색 전체 근거 부족을 분리했다.

```text
일부 후보만 pet_allowed 근거가 없음
→ 해당 후보의 missing_fields에만 pet_allowed 표시
→ diagnostics.missing_evidence_fields에는 바로 올리지 않음

반환된 후보 전체가 pet_allowed 근거를 갖지 못함
→ diagnostics.missing_evidence_fields에 pet_allowed 표시
→ failure_reasons에 NO_POLICY_EVIDENCE 포함 가능
```

이렇게 해야 AI Agent가 사용 가능한 OK 후보가 있는데도 전체 검색 실패로 오해해 조기 종료하지 않는다.

### 16.7 가격 조건 처리

AI Agent 3차 개선 내용에 맞춰 Search Tool에서도 현재 가격 데이터는 안정적인 필터처럼 다루지 않는 방향을 유지한다.

현재 상황:

```text
숙소 price는 0이 많음
식당 가격 비교용 필드 없음
관광지 가격도 일정 검증에 쓸 만큼 구조화되어 있지 않음
```

따라서 현재 단계에서는 `max_price`를 실제 hard filter처럼 적용하지 않는 것이 안전하다.

가격 조건은 추후 데이터가 정리되기 전까지 사용자 안내 또는 soft 정보 수준으로 분리하는 것이 좋다.

### 16.8 테스트

수정 파일:

```text
src/test/java/com/gangwon/companion/domain/search/dto/PlaceSearchContractTest.java
src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngineTest.java
src/test/resources/search-contract/search_response.json
```

추가/확인한 테스트:

```text
Search Tool 응답 fixture에서 pet_allowed, max_pet_size, wheelchair_accessible을 파싱함
ES 문서의 petAllowed/wheelchairAccessible 값을 AI Agent 계약 필드로 변환함
정책 조건 evidence.field가 pet_allowed, wheelchair_accessible로 내려감
확인 가능한 반려동물 크기는 evidence.field=max_pet_size로 내려감
pet_size를 필수 missing evidence로 취급하지 않음
```

테스트 결과:

```text
./gradlew.bat test --tests com.gangwon.companion.domain.search.dto.PlaceSearchContractTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest

BUILD SUCCESSFUL
PlaceSearchContractTest 3개 성공
ElasticsearchPlaceSearchEngineTest 12개 성공
```

### 16.9 정리

이번 Search Tool 3차 개선은 검색 문서를 더 많이 만드는 작업이 아니라, AI Agent가 정책 조건을 안정적으로 읽도록 응답 계약을 보강한 작업이다.

정리하면:

```text
ES 내부 문서
→ petAllowed, wheelchairAccessible

Search Tool 외부 응답
→ pet_allowed, wheelchair_accessible

AI Agent
→ candidate 필드와 evidence를 같은 기준으로 읽음
```

이제 AI Agent 3차 개선과 Search Tool 응답 계약이 더 잘 맞는다.

다음 프론트/시나리오 테스트에서는 다음을 보면 된다.

```text
소형견 동반 요청에서 후보의 pet_allowed가 채워지는지
무장애 요청에서 후보의 wheelchair_accessible이 채워지는지
evidence가 있으면 Hard Validator가 근거 부족으로 실패하지 않는지
evidence가 없으면 NO_POLICY_EVIDENCE로 조기 종료되는지
max_pet_size가 없어도 pet_allowed 근거가 있으면 크기 근거 부족만으로 실패하지 않는지
```

## 17. Search Tool 연결 진단 보강: 프론트 시나리오 candidate 0건 추적

### 17.1 확인된 문제

프론트 시나리오 테스트에서 AI Agent 결과가 다음처럼 나왔다.

```text
destination_candidates=[]
restaurant_candidates=[]
lodging_candidates=[]
candidate_counts=0
diagnostics=[]
```

그런데 Search Tool을 직접 호출하면 같은 조건에서 후보가 반환됐다.

예:

```text
DESTINATION / GANGNEUNG / query_text=바다
→ 후보 4개 반환

RESTAURANT / GANGNEUNG / query_text=물회 회 해산물
→ 후보 1개 반환

LODGING / GANGNEUNG / query_text=오션뷰 바다
→ 후보 2개 반환
```

즉 Search Tool의 ES 검색 자체가 완전히 0건인 상황은 아니었다.

그래서 현재 의심 지점은 다음 둘이다.

```text
1. FastAPI가 실제 Spring Search Tool을 호출하지 못함
2. Search Tool 응답을 받은 뒤 AI Agent가 파싱/매핑 중 후보를 버림
```

### 17.2 수정 내용: Search Tool 요청/응답 로그 추가

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/controller/InternalPlaceSearchController.java
```

Search Tool API 경계에서 요청과 응답 요약을 로그로 남기도록 했다.

로그로 확인할 수 있는 값:

```text
domain
slot
region_codes
query_text
hard_filters
soft_preferences
limit
resultCount
diagnostics failure_reasons
```

이제 프론트 시나리오를 다시 돌렸을 때 Spring 로그에서 다음을 바로 확인할 수 있다.

```text
AI Agent가 Search Tool을 실제로 호출했는지
DESTINATION / RESTAURANT / LODGING 요청이 각각 들어왔는지
region_codes가 의도대로 들어왔는지
query_text가 도메인별로 분리되어 들어왔는지
Search Tool이 몇 개의 후보를 돌려줬는지
diagnostics가 만들어졌는지
```

### 17.3 수정 내용: 단수 endpoint alias 추가

기존 Search Tool 검색 API는 다음 경로였다.

```text
POST /internal/search/places
```

혹시 AI Agent나 테스트 코드가 실수로 단수형을 호출하면 404가 날 수 있다.

```text
POST /internal/search/place
```

그래서 두 경로를 모두 받도록 했다.

```text
POST /internal/search/places
POST /internal/search/place
```

보안 설정도 함께 열었다.

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/controller/InternalPlaceSearchController.java
src/main/java/com/gangwon/companion/global/security/SecurityConfig.java
```

### 17.4 수정 내용: ES 검색 요약 로그 추가

수정 파일:

```text
src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
```

ES 검색 후 다음 값을 로그로 남긴다.

```text
totalHits
fetchedHits
returned
diagnostics failure_reasons
```

그리고 ES 검색 요청에 `track_total_hits=true`를 추가했다.

이제 다음 차이를 로그에서 볼 수 있다.

```text
ES totalHits는 있음
하지만 returned가 0
→ Search Tool 내부 후보 변환/필터/limit 쪽 확인

ES totalHits 자체가 0
→ query_text, region_codes, hard_filters 조건 확인

Spring Search Tool request 로그가 없음
→ FastAPI가 Spring Search Tool을 호출하지 못한 것
```

### 17.5 테스트 결과

```text
./gradlew.bat test --tests com.gangwon.companion.domain.search.dto.PlaceSearchContractTest --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest

BUILD SUCCESSFUL
PlaceSearchContractTest 3개 성공
ElasticsearchPlaceSearchEngineTest 12개 성공
```

### 17.6 다음 시나리오 테스트에서 볼 것

프론트에서 같은 시나리오를 다시 돌린 뒤 Spring 로그에서 다음 로그가 찍히는지 확인한다.

```text
Search Tool request: domain=DESTINATION ...
Search Tool request: domain=RESTAURANT ...
Search Tool request: domain=LODGING ...

Elasticsearch search summary: domain=DESTINATION ...
Elasticsearch search summary: domain=RESTAURANT ...
Elasticsearch search summary: domain=LODGING ...

Search Tool response: domain=DESTINATION ..., resultCount=...
Search Tool response: domain=RESTAURANT ..., resultCount=...
Search Tool response: domain=LODGING ..., resultCount=...
```

만약 이 로그가 없으면 Search Tool 문제가 아니라 AI Agent와 Spring 연결 URL/API 경로 문제다.

로그는 있는데 resultCount가 0이면 Search Tool 조건 적용 문제다.

로그상 resultCount가 1개 이상인데 AI Agent 결과만 0이면 AI Agent 응답 파싱/후보 변환 문제다.

## 18. AI Agent SearchResponse 계약 보강: top-level 정책 필드 수용

### 18.1 해결하려던 문제

Search Tool 3차 개선 후 직접 검색 API를 확인했을 때는 후보가 반환됐다.

예:

```text
DESTINATION / GANGNEUNG / query_text=바다
→ 후보 4개 반환

RESTAURANT / GANGNEUNG / query_text=물회 회 해산물
→ 후보 1개 반환

LODGING / GANGNEUNG / query_text=오션뷰 바다
→ 후보 2개 반환
```

하지만 프론트에서 AI Agent 전체 시나리오를 돌리면 다음 문제가 발생했다.

```text
destination_candidates = 0
restaurant_candidates = 0
lodging_candidates = 0
search_diagnostics = []
messages:
- 관광지 검색 서비스 호출에 실패했습니다.
- 음식점 검색 서비스 호출에 실패했습니다.
```

즉 Search Tool이 후보를 못 찾는 문제가 아니라, AI Agent가 Search Tool 응답을 정상적으로 파싱하거나 내부 후보로 변환하지 못하는 문제가 의심됐다.

### 18.2 원인

Search Tool은 3차 개선에서 candidate top-level에 정책 필드를 추가했다.

```json
{
  "pet_allowed": true,
  "max_pet_size": "SMALL",
  "wheelchair_accessible": true
}
```

하지만 AI Agent의 `SearchCandidate` 모델에는 해당 top-level 필드가 아직 없었다.

AI Agent의 검색 계약 모델은 `extra="forbid"` 정책을 사용한다.

따라서 Search Tool 응답에 AI Agent가 모르는 필드가 추가되면 다음 흐름으로 실패할 수 있다.

```text
Search Tool은 후보를 반환함
→ 응답 candidate에 pet_allowed / max_pet_size / wheelchair_accessible 포함
→ AI Agent SearchCandidate 모델이 해당 필드를 모름
→ Pydantic ValidationError 발생
→ BeSearchClient가 SearchClientError로 변환
→ 각 Agent가 검색 서비스 호출 실패로 처리
→ candidates=[]
```

### 18.3 수정 전

정책 조건값은 주로 `evidence` 배열에서만 읽었다.

예:

```python
next((e.value for e in item.evidence if e.field == "pet_allowed"), None)
```

이 경우 Search Tool이 top-level에 값을 내려줘도 AI Agent가 읽지 못한다.

또 top-level 필드가 계약 모델에 없으면 응답 파싱 자체가 실패할 수 있다.

### 18.4 수정 후

`app/search/models.py`의 `SearchCandidate`에 다음 top-level 필드를 추가했다.

```text
pet_allowed
max_pet_size
indoor_pet_allowed
wheelchair_accessible
```

또 `field_value()` 헬퍼를 추가했다.

동작 순서:

```text
1. candidate top-level 값을 먼저 확인
2. top-level 값이 없으면 evidence.field에서 fallback으로 확인
```

즉 Search Tool이 다음 두 방식 중 어떤 방식으로 값을 줘도 AI Agent가 읽을 수 있다.

top-level 방식:

```json
{
  "pet_allowed": true
}
```

evidence 방식:

```json
{
  "evidence": [
    {
      "field": "pet_allowed",
      "value": true,
      "source": "TOUR_API"
    }
  ]
}
```

### 18.5 후보 변환 코드 수정

다음 Agent의 후보 변환 코드를 `item.field_value(...)`를 쓰도록 변경했다.

```text
app/agents/destination.py
app/agents/restaurant.py
app/agents/lodging.py
```

수정 후 내부 후보에는 다음 값이 채워진다.

```text
pet_allowed
max_pet_size
indoor_pet_allowed
wheelchair_accessible
opens_at
closes_at
```

최종 흐름:

```text
Search Tool candidate top-level 또는 evidence
→ AI Agent 후보 변환 코드
→ 내부 후보 필드
→ Itinerary Agent 일정 슬롯
→ Hard Validator가 일정 슬롯의 필드값 검증
```

### 18.6 디버깅 메시지 보강

`app/search/be_client.py`에서 Search Tool 응답 계약이 맞지 않을 때 ValidationError 내용을 함께 남기도록 했다.

수정 전:

```text
BE 검색 응답이 공통 계약과 다릅니다.
```

수정 후:

```text
BE 검색 응답이 공통 계약과 다릅니다: {ValidationError detail}
```

이제 다음에 계약 불일치가 생기면 어떤 필드 때문에 실패했는지 JSON 응답의 `messages`나 `errors`에서 더 빨리 확인할 수 있다.

### 18.7 수정 파일

```text
app/search/models.py
app/search/be_client.py
app/agents/destination.py
app/agents/restaurant.py
app/agents/lodging.py
tests/fixtures/search_response.json
tests/test_search_contract.py
tests/test_search_integration.py
```

### 18.8 테스트 결과

```text
python -B -m unittest

Ran 91 tests in 0.190s
OK (skipped=6)
```

추가로 확인한 내용:

```text
SearchResponse가 candidate top-level 정책 필드를 파싱함
evidence가 비어 있어도 top-level pet_allowed / max_pet_size / wheelchair_accessible을 읽음
후보 변환 코드가 top-level 값을 내부 후보 필드로 옮김
기존 evidence 기반 응답도 fallback으로 계속 지원함
```

### 18.9 다음 시나리오 테스트에서 볼 것

FastAPI 서버를 재시작하거나 reload 적용을 확인한 뒤 프론트 시나리오를 다시 돌린다.

확인할 것:

```text
관광지 검색 서비스 호출에 실패했습니다 메시지가 사라지는지
음식점 검색 서비스 호출에 실패했습니다 메시지가 사라지는지
destination_candidates / restaurant_candidates / lodging_candidates에 후보가 들어오는지
Search Tool 로그의 resultCount와 AI Agent candidate_counts가 일치하는지
pet_allowed / wheelchair_accessible 값이 내부 후보와 일정 슬롯까지 전달되는지
```

## 19. AI Agent 4차 개선: 필수 정책 후보 선택 방어 및 세부 키워드 우선 반영

### 19.1 해결하려던 문제

3차 개선 후 Search Tool 후보가 AI Agent로 정상 변환되고, 기본 일정 생성도 `completed`까지 도달했다.

하지만 반려동물/무장애 시나리오와 음식 선호 시나리오에서 다음 문제가 남았다.

```text
1. hard_filters.wheelchair_accessible=true 요청에도 wheelchair_accessible=null 후보가 일정에 들어감
2. hard_filters.pet_allowed=true 요청에도 pet_allowed=null 식당/숙소 후보가 일정에 들어감
3. 물회/회 요청에서 직접 매칭 후보가 있는데도 일반 음식점이 식사 슬롯에 들어갈 수 있음
```

이번 작업에서는 대화형 새 요청/수정 요청 분리는 구현하지 않았다.

대화형 일정 수정은 기존 state를 유지할지 초기화할지 결정해야 하는 별도 기능이므로, 이번 범위에서는 단일 요청의 일정 생성 품질과 검증 전 방어만 개선했다.

### 19.2 문제 원인

수정 전 흐름은 다음과 같았다.

```text
Search Tool 후보 반환
→ Itinerary Optimizer가 후보 점수와 이동시간 중심으로 장소 선택
→ 필수 정책값이 null인 후보도 일정에 들어갈 수 있음
→ Hard Validator가 마지막에 EVIDENCE_MISSING으로 실패 처리
```

즉 검증 단계에서는 막고 있었지만, 일정 생성 단계에서 위험 후보를 미리 걸러내지는 못했다.

음식 선호도도 비슷하다.

```text
Search Tool이 matched_keywords=["물회", "회"] 후보를 내려줌
→ Itinerary Optimizer가 candidate.score를 더 크게 반영
→ 직접 키워드 매칭 후보보다 일반 고득점 후보가 선택될 수 있음
```

### 19.3 수정 전 내용

`app/tools/itinerary_optimizer.py`의 후보 점수는 대략 다음 구조였다.

```text
candidate.score * 100
+ preference_matches * 5
- travel_minutes * 2
- evidence_penalty
```

여기서 `preference_matches` 가중치가 낮아 사용자가 직접 말한 키워드 일치가 후보 선택에 충분히 반영되지 않았다.

또 필수 정책 조건은 optimizer 단계에서 보지 않았다.

```text
pet_allowed=true 요청
→ pet_allowed=null 후보도 선택 가능

wheelchair_accessible=true 요청
→ wheelchair_accessible=null 후보도 선택 가능
```

### 19.4 수정 후 내용

#### 필수 정책값 후보 필터링 추가

`optimize_itinerary()`에 `required_policy` 인자를 추가했다.

AI Agent는 `itinerary_node()`에서 사용자 요청을 보고 다음 값을 넘긴다.

```python
required_policy={
    "pet_allowed": request.get("pet_allowed") is True,
    "indoor_pet_allowed": request.get("indoor_pet") is True,
    "wheelchair_accessible": request.get("wheelchair_accessible") is True,
}
```

Optimizer는 후보를 일정에 넣기 전에 다음 조건을 확인한다.

```text
required_policy.pet_allowed=true
→ candidate.pet_allowed가 true인 후보만 사용

required_policy.wheelchair_accessible=true
→ candidate.wheelchair_accessible이 true인 후보만 사용

required_policy.indoor_pet_allowed=true
→ candidate.indoor_pet_allowed가 true인 후보만 사용
```

`null`은 “조건을 만족한다고 확정할 수 없음”이므로 필수 조건 요청 시 일정 후보에서 제외된다.

#### 세부 키워드 매칭 가중치 강화

후보 점수 계산에서 사용자 선호 키워드 직접 매칭 가중치를 높였다.

수정 전:

```text
preference_matches * 5
```

수정 후:

```text
preference_matches * 35
```

또 `candidate.tags`뿐 아니라 `candidate.matched_conditions`도 함께 비교해 직접 매칭 여부를 계산한다.

이제 식당 슬롯에서 다음 후보가 있으면 더 우선될 수 있다.

```text
matched_keywords=["물회", "회"]
matched_conditions=["물회", "회"]
```

### 19.5 동작 변화

무장애 요청:

```text
사용자 요청: wheelchair_accessible=true
후보 A: wheelchair_accessible=null, score=1.0
후보 B: wheelchair_accessible=true, score=0.6
```

수정 전:

```text
후보 A가 일정에 들어갈 수 있음
→ Hard Validator에서 EVIDENCE_MISSING 실패
```

수정 후:

```text
후보 A는 optimizer 단계에서 제외
후보 B 선택
```

반려동물 요청:

```text
사용자 요청: pet_allowed=true
후보 A: pet_allowed=null
후보 B: pet_allowed=true
```

수정 후:

```text
후보 B만 일정 후보로 사용
```

음식 선호 요청:

```text
사용자 요청: 물회, 회
후보 A: 일반 맛집, score=0.95
후보 B: matched_keywords=["물회", "회"], score=0.75
```

수정 후:

```text
후보 B가 직접 키워드 매칭 보너스를 받아 우선 선택됨
```

### 19.6 수정 파일

```text
app/tools/itinerary_optimizer.py
app/agents/itinerary.py
tests/test_itinerary.py
```

### 19.7 테스트 결과

```text
python -B -m unittest

Ran 94 tests in 0.389s
OK (skipped=6)
```

추가로 확인한 내용:

```text
wheelchair_accessible=true 요청 시 wheelchair_accessible=null 후보를 일정에 넣지 않음
조건을 만족하는 낮은 점수 후보가 있으면 null 후보 대신 선택함
물회/회 직접 매칭 후보가 일반 고득점 후보보다 우선될 수 있음
기존 일정 생성, 중복 방지, 카페/식당 분리 테스트가 계속 통과함
```

### 19.8 남은 과제

이번 수정은 AI Agent가 검증 실패 가능성이 큰 후보를 일정 생성 단계에서 미리 피하도록 한 방어 로직이다.

하지만 Search Tool 쪽 정책은 여전히 정리해야 한다.

```text
hard_filters.pet_allowed=true 요청 시 pet_allowed=null 후보를 OK 후보로 반환할지
hard_filters.wheelchair_accessible=true 요청 시 wheelchair_accessible=null 후보를 OK 후보로 반환할지
null 후보를 반환한다면 INSUFFICIENT_EVIDENCE로 표시할지
candidate missing_fields와 diagnostics.missing_evidence_fields를 어떤 기준으로 나눌지
```

Search Tool이 필수 조건 true 후보를 충분히 내려주지 못하면 AI Agent는 해당 슬롯을 `missing_slots`로 보고 재검색 또는 실패 처리하게 된다.

즉 다음 단계는 Search Tool에서 hard filter와 null evidence 후보 반환 정책을 확정하는 것이다.

## 20. Search Tool 4차 개선: 필수 정책 조건 true 근거 우선 검색

### 20.1 문제 배경

AI Agent 4차 개선에서는 `pet_allowed=true`, `wheelchair_accessible=true` 같은 필수 조건이 요청됐을 때 값이 `null`인 후보를 일정 생성 단계에서 제외하도록 바꿨다.

이 상태에서 Search Tool이 `pet_allowed=null`, `wheelchair_accessible=null` 후보만 많이 내려주면 AI Agent는 사용할 수 있는 후보가 없다고 판단한다.

핵심 문제는 Search Tool의 기존 정책 필터가 다음처럼 동작했다는 점이다.

```text
pet_allowed=true 요청
→ petAllowed=false 후보는 제외
→ petAllowed=null 후보는 통과 가능
```

즉 `false가 아닌 후보`를 넓게 가져오는 방식이라, 실제 `true` 근거가 있는 후보보다 근거가 없는 후보가 결과 상단에 섞일 수 있었다.

### 20.2 개선 목표

이번 개선의 목표는 Search Tool이 필수 정책 조건을 더 명확하게 다루도록 만드는 것이다.

```text
hard_filters.pet_allowed=true
→ petAllowed=true 근거가 있는 후보를 먼저 검색

hard_filters.wheelchair_accessible=true
→ wheelchairAccessible=true 근거가 있는 후보를 먼저 검색

정책 값을 모르는 후보
→ OK가 아니라 INSUFFICIENT_EVIDENCE로 구분
```

단, true 근거 후보가 아예 없을 때는 후보를 완전히 0개로 숨기지 않고, 근거 부족 상태와 diagnostics를 AI Agent가 볼 수 있게 fallback 검색을 수행한다.

### 20.3 수정 파일

```text
Gangwon-Companion/src/main/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngine.java
Gangwon-Companion/src/test/java/com/gangwon/companion/domain/search/elasticsearch/ElasticsearchPlaceSearchEngineTest.java
```

### 20.4 주요 수정 내용

#### 필수 정책 조건을 strict filter로 우선 검색

`hard_filters.pet_allowed=true` 또는 `hard_filters.wheelchair_accessible=true`가 있으면 첫 ES 검색에서는 `term` 조건으로 true 후보만 가져오도록 바꿨다.

```text
petAllowed = true
wheelchairAccessible = true
```

이제 반려동물/무장애 필수 조건이 있는 요청에서는 `null` 후보가 `true` 후보보다 먼저 반환되는 일이 줄어든다.

#### true 후보가 없을 때만 근거 부족 fallback 검색

strict 검색 결과가 0건이면 Search Tool은 한 번 더 완화 검색을 수행한다.

이 fallback은 조건을 자동으로 풀어 일정에 넣으려는 목적이 아니다.

목적은 AI Agent에게 다음 정보를 전달하는 것이다.

```text
요청 조건을 만족하는 true 근거 후보는 없음
조건 근거가 없는 후보는 있음
따라서 사용자에게 조건 조정이 필요할 수 있음
```

fallback 후보는 `OK`가 아니라 `INSUFFICIENT_EVIDENCE` 상태로 내려간다.

예시:

```json
{
  "status": "INSUFFICIENT_EVIDENCE",
  "pet_allowed": null,
  "wheelchair_accessible": null,
  "missing_fields": ["pet_allowed", "wheelchair_accessible"]
}
```

#### diagnostics에 정책 근거 부족 사유 유지

반환 후보 전체가 필수 정책 근거를 갖지 못하면 diagnostics에 다음 정보가 포함된다.

```json
{
  "failure_reasons": ["NO_POLICY_EVIDENCE"],
  "missing_evidence_fields": ["pet_allowed", "wheelchair_accessible"],
  "suggested_actions": ["ASK_USER_TO_ADJUST_REQUIRED_CONDITION"]
}
```

이 정보는 AI Agent가 같은 검색을 반복하지 않고, 사용자에게 "반려동물/무장애 조건을 만족한다고 확인되는 후보가 부족하다"는 식으로 설명하거나 조건 조정을 요청하는 근거가 된다.

#### max_pet_size는 여전히 선택 근거로만 사용

`max_pet_size`는 데이터가 있을 때만 내려준다.

```text
pet_allowed=true
max_pet_size=null
→ 반려동물 동반 가능 근거는 있음
→ 허용 크기 정보는 모름
```

AI Agent는 이미 `max_pet_size`가 없다는 이유만으로 후보를 실패시키지 않도록 조정되어 있다.

### 20.5 동작 변화

수정 전:

```text
요청: pet_allowed=true, wheelchair_accessible=true
후보 A: pet_allowed=null, wheelchair_accessible=null, status=INSUFFICIENT_EVIDENCE
후보 B: pet_allowed=true, wheelchair_accessible=true, status=OK

ES 점수에 따라 후보 A가 먼저 내려올 수 있음
```

수정 후:

```text
첫 검색에서는 후보 B처럼 true 근거가 있는 후보만 검색
true 근거 후보가 없을 때만 후보 A 같은 근거 부족 후보를 fallback으로 반환
fallback 후보는 missing_fields와 diagnostics를 통해 근거 부족임을 명확히 표시
```

### 20.6 테스트 결과

```text
./gradlew.bat test --tests com.gangwon.companion.domain.search.elasticsearch.ElasticsearchPlaceSearchEngineTest --tests com.gangwon.companion.domain.search.dto.PlaceSearchContractTest

BUILD SUCCESSFUL
```

확인한 테스트 내용:

```text
pet_allowed=true 요청 시 ES 검색 바디에 petAllowed=true term filter가 들어감
wheelchair_accessible=true 요청 시 ES 검색 바디에 wheelchairAccessible=true term filter가 들어감
true 근거 후보가 있으면 OK 후보로 내려감
true 근거 후보가 없으면 fallback 후보를 INSUFFICIENT_EVIDENCE로 내려감
fallback 후보에는 missing_fields=["pet_allowed", "wheelchair_accessible"]가 포함됨
diagnostics에는 NO_POLICY_EVIDENCE와 ASK_USER_TO_ADJUST_REQUIRED_CONDITION이 포함됨
기존 응답 계약 테스트가 계속 통과함
```

### 20.7 실제 API 확인 결과

백엔드 컨테이너를 새 코드로 다시 빌드하고 실행했다.

```text
docker compose up -d --build spring
```

컨테이너 상태:

```text
elasticsearch_gangwon healthy
spring_gangwon healthy
```

관광지 요청:

```json
{
  "domain": "DESTINATION",
  "region_codes": ["SOKCHO"],
  "hard_filters": {
    "pet_allowed": true,
    "pet_size": "SMALL",
    "wheelchair_accessible": true
  },
  "limit": 5
}
```

결과:

```text
아바이마을: pet_allowed=true, max_pet_size=LARGE, wheelchair_accessible=true, status=OK
영금정: pet_allowed=true, max_pet_size=null, wheelchair_accessible=true, status=OK
diagnostics.missing_evidence_fields=[]
```

즉 true 근거가 있는 관광지는 OK 후보로 내려간다.

식당 요청:

```json
{
  "domain": "RESTAURANT",
  "region_codes": ["GANGNEUNG"],
  "hard_filters": {
    "pet_allowed": true,
    "wheelchair_accessible": true
  },
  "limit": 5
}
```

결과:

```text
반환 후보들은 pet_allowed=null, wheelchair_accessible=null
status=INSUFFICIENT_EVIDENCE
missing_fields=["pet_allowed", "wheelchair_accessible"]
diagnostics.failure_reasons=["NO_POLICY_EVIDENCE"]
diagnostics.suggested_actions=["ASK_USER_TO_ADJUST_REQUIRED_CONDITION"]
diagnostics.counts.current=0
diagnostics.counts.without_policy_filters=22
```

즉 식당처럼 정책 데이터 자체가 없는 도메인은 OK 후보처럼 내려가지 않고, AI Agent가 조건 근거 부족을 명확히 판단할 수 있게 된다.

## 21. AI Agent 5차 개선: 도메인별 반려동물·무장애 정책 분리

### 21.1 문제 배경

4차 개선 후 반려동물 또는 무장애 조건이 있는 시나리오를 다시 테스트했다.

관광지는 DB에 반려동물/무장애 데이터가 있어 다음처럼 조건 근거를 가진 후보를 받을 수 있었다.

```json
{
  "category": "DESTINATION",
  "pet_allowed": true,
  "wheelchair_accessible": true
}
```

하지만 식당과 숙소는 애초에 DB에 해당 정보가 없어서 대부분 다음처럼 내려왔다.

```json
{
  "category": "RESTAURANT",
  "pet_allowed": null,
  "wheelchair_accessible": null,
  "missing_fields": ["pet_allowed", "wheelchair_accessible"]
}
```

### 21.2 문제 이유

AI Agent는 기존에 사용자 요청의 정책 조건을 모든 도메인에 동일하게 적용했다.

```text
pet_allowed=true
wheelchair_accessible=true
→ 관광지, 식당, 숙소 모두 필수 조건으로 검사
```

하지만 실제 데이터 보유 범위는 다르다.

```text
관광지:
  반려동물/무장애 데이터 있음

식당/숙소:
  반려동물/무장애 데이터 없음
```

따라서 식당/숙소에 같은 기준을 적용하면, 후보가 있어도 `pet_allowed=null`, `wheelchair_accessible=null`이라는 이유로 일정 생성에서 제외되거나 Hard Validator에서 실패할 수 있었다.

이 문제는 Search Tool이 고칠 문제가 아니다.

Search Tool은 DB에 없는 값을 임의로 만들 수 없고, AI Agent가 도메인별로 검증 가능한 조건과 안내해야 할 조건을 분리해야 한다.

### 21.3 수정 전 내용

SearchRequest 생성:

```text
DESTINATION / RESTAURANT / LODGING 모두
hard_filters.pet_allowed = 사용자 요청값
hard_filters.pet_size = 사용자 요청값
hard_filters.wheelchair_accessible = 사용자 요청값
```

Itinerary Optimizer:

```text
모든 후보에 required_policy 적용
→ 식당/숙소 후보도 pet_allowed, wheelchair_accessible이 true여야 선택 가능
```

Hard Validator:

```text
모든 일정 슬롯에서 정책 필드 근거 확인
→ 식당/숙소의 null 값도 EVIDENCE_MISSING으로 실패 가능
```

### 21.4 수정 후 내용

도메인별 정책을 다음처럼 분리했다.

```text
DESTINATION:
  반려동물/무장애 조건을 SearchRequest hard_filters에 포함
  Itinerary Optimizer에서 true 근거 후보만 선택
  Hard Validator에서 정책 필드 누락/불일치를 검증

RESTAURANT / LODGING:
  반려동물/무장애 조건을 SearchRequest hard_filters에 포함하지 않음
  Itinerary Optimizer에서 정책 필드 null 후보를 제외하지 않음
  Hard Validator에서 정책 필드 null을 실패로 보지 않음
```

수정 파일:

```text
app/search/request_factory.py
app/tools/itinerary_optimizer.py
app/agents/itinerary.py
app/validators/hard_validator.py
tests/test_search_integration.py
tests/test_itinerary.py
tests/test_validation.py
```

### 21.5 어떻게 동작하는가

사용자 요청:

```text
속초로 2일 여행 갈 거야. 소형견이랑 같이 가고 휠체어로 이동하기 편한 바다 코스로 추천해줘.
```

관광지 검색:

```json
{
  "domain": "DESTINATION",
  "hard_filters": {
    "pet_allowed": true,
    "pet_size": "SMALL",
    "wheelchair_accessible": true
  }
}
```

식당/숙소 검색:

```json
{
  "domain": "RESTAURANT",
  "hard_filters": {}
}
```

```json
{
  "domain": "LODGING",
  "hard_filters": {}
}
```

이제 관광지는 조건을 만족하는 후보를 우선 찾고, 식당/숙소는 정책 데이터가 없다는 이유만으로 후보 검색과 일정 생성을 실패시키지 않는다.

### 21.6 결과

관련 테스트를 추가하고 통과를 확인했다.

```text
python -B -m unittest tests.test_search_integration tests.test_itinerary tests.test_validation

Ran 49 tests
OK
```

확인한 내용:

```text
DESTINATION SearchRequest에는 pet_allowed/pet_size/wheelchair_accessible hard filter가 유지됨
RESTAURANT SearchRequest에는 반려동물/무장애 hard filter가 들어가지 않음
LODGING SearchRequest에는 반려동물/무장애 hard filter가 들어가지 않음
Itinerary Agent는 식당 정책 필드가 null이어도 일정에 포함할 수 있음
Hard Validator는 식당/숙소 정책 필드 null을 실패로 보지 않음
Hard Validator는 관광지 정책 필드 null은 여전히 실패로 봄
식당/숙소에서도 운영시간, 장소 출처, 중복, 이동시간 검증은 그대로 유지됨
```

### 21.7 남은 확인

프론트 시나리오에서 반려동물/무장애 조건이 있는 요청을 다시 확인해야 한다.

기대 결과:

```text
관광지:
  pet_allowed/wheelchair_accessible 조건 반영

식당/숙소:
  정책 데이터 null이어도 일정 생성 진행

최종 응답:
  READY로 완료
  식당/숙소의 반려동물·무장애 여부는 방문 전 확인 안내 필요
```

## 22. AI Agent 5차 마무리: 반려동물+무장애 관광지 부족 실패 메시지 개선

### 22.1 문제 배경

5차 개선 후 식당/숙소의 반려동물·무장애 데이터 부족은 일정 실패 원인에서 제외됐다.

하지만 다음처럼 반려동물과 무장애 조건을 동시에 요청한 경우에는 여전히 관광지 후보 자체가 부족할 수 있다.

```text
속초로 2일 여행 갈 거야. 소형견이랑 같이 가고 휠체어로 이동하기 편한 바다 코스로 추천해줘.
```

이 경우 실패 자체는 맞지만, 사용자에게는 단순히 "장소 후보가 부족하다"보다 왜 부족한지와 어떻게 다시 요청하면 좋은지 안내가 필요했다.

### 22.2 문제 이유

현재 DB 기준으로 반려동물/무장애 정책 데이터는 관광지에만 있다.

따라서 반려동물+무장애 조건을 동시에 만족하는 관광지가 부족하면, AI Agent는 안전하게 일정을 확정하기 어렵다.

이때 사용자에게는 다음 선택지를 알려주는 것이 자연스럽다.

```text
조건을 조금 넓히기
방문지를 줄이기
```

### 22.3 수정 전 내용

실패 응답은 일반적인 후보 부족 메시지만 제공했다.

```text
요청 조건에 맞는 장소 후보가 부족해 여행 일정을 완성하지 못했습니다.
```

### 22.4 수정 후 내용

반려동물 동반과 휠체어 이용 조건이 모두 있고, 부족한 슬롯이 관광지일 때 사용자 친화적인 안내 문구를 추가했다.

```text
반려동물 동반과 휠체어 이용 조건을 모두 확인할 수 있는 관광지가 아직 충분하지 않아요.
조건을 조금 넓히거나 방문지를 줄이면 더 여유로운 일정으로 다시 추천해드릴 수 있어요.
```

수정 파일:

```text
app/agents/response.py
tests/test_response.py
```

### 22.5 함께 보강한 내용

일정 생성 전 단계에서 실패하면 `hard_validation` 또는 `quality_validation`이 아직 `null`일 수 있다.

Response Agent가 이 값을 dict로 가정하면 실패 응답 생성 중 오류가 날 수 있으므로, `None`이어도 안전하게 처리하도록 보강했다.

### 22.6 테스트 결과

```text
python -B -m unittest tests.test_response

Ran 17 tests
OK
```

확인한 내용:

```text
반려동물+무장애 조건에서 관광지 슬롯이 부족하면 사용자 안내 문구가 notices와 answer에 포함됨
hard_validation/quality_validation이 null이어도 실패 응답을 정상 생성함
기존 성공/실패 응답 테스트가 계속 통과함
```

## 23. 숙소 슬롯 정책 개선: 기본 연박 숙소 1개 추천

### 23.1 문제 배경

프론트에서 3일 여행 결과를 확인했을 때 `final_response.accommodations`에 숙소가 2개 표시됐다.

처음에는 추천 숙소 후보 여러 개처럼 보일 수 있지만, 실제 의미는 후보 목록이 아니라 일정에 배정된 숙박 슬롯이었다.

기존 슬롯 구조는 다음과 같았다.

```text
2일 여행 → D1_LODGING
3일 여행 → D1_LODGING, D2_LODGING
4일 여행 → D1_LODGING, D2_LODGING, D3_LODGING
```

즉 여행 일수가 늘어나면 숙소 슬롯도 `days - 1`개씩 늘어났다.

### 23.2 문제 이유

일반적인 여행에서는 2박 3일이나 3박 4일이어도 한 숙소에 연박하는 경우가 많다.

그런데 기본 슬롯이 숙박일마다 숙소를 하나씩 만들면 다음 문제가 생긴다.

```text
사용자는 추천 숙소 후보 여러 개로 오해할 수 있음
프론트는 숙소를 1박차/2박차처럼 표시해야 함
AI Agent가 사용자가 요청하지 않은 숙소 이동을 암묵적으로 만든 것처럼 보임
```

### 23.3 수정 전 내용

Supervisor가 모든 숙박일에 숙소 슬롯을 추가했다.

```text
for day in range(1, days + 1):
    if day < days:
        slots.append(f"D{day}_LODGING")
```

### 23.4 수정 후 내용

기본은 한 숙소 연박으로 보고 `D1_LODGING` 하나만 생성하도록 바꿨다.

```text
2일 이상 여행 → D1_LODGING 1개
```

단, 사용자가 숙소 이동을 명시하면 숙박일 수만큼 숙소 슬롯을 만든다.

감지 표현 예시:

```text
매일 다른 숙소
숙소를 여러
숙소 여러
다른 숙소
숙소 이동
옮겨 다니
```

예:

```text
속초로 3일 여행 갈 건데 매일 다른 숙소에서 자고 싶어.
→ D1_LODGING, D2_LODGING 생성
```

수정 파일:

```text
app/agents/supervisor.py
tests/test_supervisor_slots.py
```

### 23.5 결과

관련 테스트를 추가하고 통과를 확인했다.

```text
python -B -m unittest tests.test_supervisor_slots tests.test_candidate_collector tests.test_be_e2e tests.test_response

Ran 35 tests
OK (skipped=6)
```

확인한 내용:

```text
3일 기본 여행에서는 D1_LODGING만 생성됨
3일 여행에서 "매일 다른 숙소"를 요청하면 D1_LODGING, D2_LODGING이 생성됨
기존 일정/응답/E2E 테스트가 계속 통과함
```

### 23.6 추가 보완

실제 프론트 테스트에서 다음 요청은 여러 숙소 의도가 분명했지만 숙소 슬롯이 1개만 생성됐다.

```text
강릉으로 3일 여행 갈거야. 바다가 보고 싶고 맛있는 해산물도 많이 먹고 싶어.
반려동물은 없어. 첫째날이랑 둘째날 머물 숙소를 다르게 하고 싶어
```

원인은 여러 숙소 감지 패턴이 `"다른 숙소"` 같은 표현만 보고, `"숙소를 다르게"`를 잡지 못했기 때문이다.

다음 표현을 추가했다.

```text
숙소를 다르게
숙소 다르게
머물 숙소를 다르게
숙박을 다르게
각각 다른 숙소
```

테스트도 실제 사용자 문장을 그대로 추가했다.

```text
python -B -m unittest tests.test_supervisor_slots tests.test_candidate_collector tests.test_be_e2e

Ran 19 tests
OK (skipped=6)
```

### 23.7 추가 보완: 여러 숙소 요청 시 같은 숙소가 반복 선택되는 문제

숙소 슬롯은 `D1_LODGING`, `D2_LODGING`처럼 여러 개 생성됐지만, Itinerary Optimizer가 숙소 중복은 항상 연박으로 허용하고 있었다.

그 결과 사용자가 "첫째날이랑 둘째날 머물 숙소를 다르게 하고 싶어"라고 요청해도 같은 숙소가 1박차와 2박차에 반복 선택될 수 있었다.

수정 전:

```text
숙소는 언제나 중복 허용
→ 여러 숙소 요청에서도 같은 숙소가 다시 선택될 수 있음
```

수정 후:

```text
기본 숙소 슬롯 1개:
  한 숙소 연박으로 간주하므로 기존처럼 중복 허용

숙소 슬롯 2개 이상:
  사용자가 여러 숙소를 명시한 상황으로 보고 숙소도 중복 금지
```

수정 파일:

```text
app/tools/itinerary_optimizer.py
app/agents/itinerary.py
tests/test_itinerary.py
```

테스트:

```text
python -B -m unittest tests.test_itinerary tests.test_supervisor_slots tests.test_response

Ran 41 tests
OK
```

확인한 내용:

```text
기본 연박 테스트에서는 같은 숙소 반복이 계속 허용됨
allow_lodging_repeats=False이면 L1, L2처럼 서로 다른 숙소를 선택함
Itinerary Agent는 숙소 슬롯이 2개 이상일 때 자동으로 숙소 중복을 막음
```

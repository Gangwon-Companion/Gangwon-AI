## 0. Input Parser

사용자가 입력한 자연어와 Form 데이터를 Supervisor Agent가 처리할 수 있는 표준 요청 형태로 변환한다.

Input Parser는 세 개의 단계로 구성한다.

```
사용자 입력
    ↓
FormBinder
    ↓
Preference Extractor
    ↓
Conflict Checker
    ↓
Supervisor Agent
```

### 0.1 FormBinder

Spring Boot 또는 FastAPI에서 전달한 입력을 하나의 표준 요청 객체로 묶는다.

표준 요청에는 다음 정보가 포함된다.

```
{
  "message": "반려견과 강릉에서 2박 3일 여행하고 싶어요.",
  "region": "강릉",
  "travelDays": 3,
  "nights": 2,
  "petAllowed": true,
  "petSize": "SMALL",
  "wheelchairAccessible": false,
  "preferences": ["카페", "바다"]
}
```

필수 정보가 누락된 경우에는 Supervisor를 실행하지 않고 추가 질문을 반환한다.

필수 정보 예시:

- 여행 지역
- 여행 일수 또는 여행 날짜
- 반려동물 동반 여부

### 0.2 Preference Extractor

사용자의 자연어 요청에서 선호조건을 추출한다.

예를 들어 다음과 같은 정보를 추출한다.

- 카페 중심
- 바다 근처
- 조용한 장소
- 반려동물 동반
- 휠체어 접근 가능
- 맛집 중심
- 액티비티 선호

명시적으로 입력된 Form 값이 있으면 Form 값을 우선하고, 자연어에서 추출한 값은 누락된 선호조건을 보완하는 데 사용한다.

### 0.3 Conflict Checker

입력값 사이의 충돌과 필수 정보 누락을 확인한다.

검사 예시는 다음과 같다.

- 여행 일수와 숙박 일수가 일치하지 않는 경우
- 반려동물 미동반인데 반려동물 크기가 입력된 경우
- 휠체어 접근 조건과 접근 불가 장소 조건이 함께 입력된 경우
- 지역이나 여행 기간이 누락된 경우

검사 결과는 구조화한다.

```
{
  "inputComplete": false,
  "missingFields": ["travelDays"],
  "conflicts": [],
  "questions": ["여행 기간이 며칠인가요?"]
}
```

입력 상태에 따른 흐름은 다음과 같다.

```
입력 정상
→ Supervisor Agent

정보 누락 또는 충돌
→ 추가 질문 반환
→ 사용자 답변 수신
→ Input Parser 재실행
```

## 1. Supervisor Agent

사용자 요청을 분석하고 필요한 전문 Agent를 선택해 작업을 분배한다.

주요 역할은 다음과 같다.

- 여행 일수와 슬롯을 정의한다.
- 필요한 Agent를 선택한다.
- Agent 실행 순서를 결정한다.
- 병렬 실행 가능한 Agent를 동시에 호출한다.
- 각 Agent의 결과를 통합한다.
- 검증 실패 시 재실행할 Agent를 선택한다.
- 전체 실행 상태와 재시도 횟수를 관리한다.

예를 들어 사용자가 “반려견과 강릉에서 2박 3일 동안 카페와 바다 중심으로 여행하고 싶다”고 요청하면 다음과 같이 판단한다.

```
Supervisor 판단

필요 Agent:
- Destination Agent
- Restaurant Agent
- Lodging Agent

생략 가능 Agent:
- Activity Agent

실행 방식:
1. Destination·Restaurant·Lodging Agent 병렬 실행
2. Itinerary Agent 실행
3. 검증 실행
4. 실패한 슬롯만 재검색
```

Supervisor는 직접 장소를 검색하거나 일정을 만들기보다, **누가 어떤 작업을 수행할지 결정하는 역할**을 맡는다. Supervisor 패턴은 주 Agent가 대화 문맥을 유지하면서 하위 Agent를 동적으로 호출하는 방식이다.

---

## 2. Destination Agent

관광지와 방문 장소 후보를 담당한다.

### 입력

```
지역
여행 날짜
시간대
반려동물 조건
이동제약 조건
사용자 선호
이전 슬롯 위치
```

### 역할

- 관광지 관련 검색어를 생성한다.
- 필수조건과 선호조건을 분리한다.
- Search Tool을 호출한다.
- 검색 후보를 슬롯별로 정리한다.
- 각 후보의 추천 근거를 반환한다.

### 사용 Tool

```
Place Search Tool
Geo Distance Tool
Operating Hours Tool
```

---

## 3. Restaurant Agent

점심과 저녁 장소 후보를 담당한다.

### 역할

- 음식 종류와 사용자 선호를 분석한다.
- 식사 시간에 영업 중인 장소를 검색한다.
- 이전·다음 관광지와 이동거리를 고려한다.
- 반려동물 동반과 휠체어 접근 조건을 적용한다.
- 동일 음식 종류가 반복되지 않도록 후보를 구성한다.

### 사용 Tool

```
Restaurant Search Tool
Operating Hours Tool
Geo Distance Tool
```

Restaurant Agent가 최종 음식점을 확정하지는 않는다. 조건에 맞는 후보와 점수를 Itinerary Agent에 전달한다.

---

## 4. Lodging Agent

숙소 후보를 담당한다.

숙소는 일정 전체 동선에 영향을 크게 주므로 관광지 Agent와 구분하는 것이 적합하다.

### 역할

- 반려동물 크기와 숙소 정책을 확인한다.
- 무장애 객실과 접근성 정보를 확인한다.
- 관광지와 숙소 간 이동거리를 계산한다.
- 연박 가능 여부를 확인한다.
- 숙소를 중심으로 일정 동선을 평가한다.

### 사용 Tool

```
Lodging Search Tool
Policy Verification Tool
Geo Distance Tool
```

숙소 데이터가 불확실하면 임의로 추천하지 않고 다음과 같이 반환한다.

```
{
  "status":"INSUFFICIENT_EVIDENCE",
  "placeId":"L102",
  "missingFields": ["petSizePolicy","wheelchairAccessibleRoom"
  ]
}
```

---

## 5. Activity Agent

레저, 체험, 액티비티 요청이 있을 때만 실행한다.

### 역할

- 계절과 시간대를 고려한다.
- 예약 필요 여부를 확인한다.
- 연령과 이동제약 조건을 반영한다.
- 반려동물 참여 가능 여부를 확인한다.
- 날씨 의존 여부를 표시한다.

항상 실행하지 않고 Supervisor가 필요성을 판단해 선택적으로 호출한다.

---

## 6. 공통 Search Tool

각 Agent가 Elasticsearch 쿼리를 직접 작성하게 하면 검색 정책이 중복되고 결과 형식도 달라질 수 있다. 따라서 모든 Agent는 동일한 Search Tool을 사용한다.

```
전문 Agent
    ↓
표준 SearchRequest 생성
    ↓
Search Tool
    ↓
Elasticsearch Query DSL 변환
    ↓
검색 결과 반환
```

Elasticsearch는 BM25, dense vector, Geo 검색 및 필터를 함께 사용하고 RRF로 순위를 결합한다. Elasticsearch는 텍스트 검색과 벡터 검색을 하나의 엔진에서 수행하고, RRF를 이용해 하이브리드 결과를 결합할 수 있다.

```
{
  "domain":"LODGING",
  "slot":"LODGING",
  "regionCodes": ["GANGNEUNG"],
  "queryText":"바다 근처 조용한 반려동물 동반 숙소",
  "hardFilters": {
    "petAllowed":true,
    "petSize":"SMALL",
    "wheelchairAccessible":true
  },
  "softPreferences": {
    "quiet":0.9,
    "oceanView":0.8
  },
  "geo": {
    "center": {
      "lat":37.75,
      "lon":128.90
    },
    "radiusKm":15
  },
  "limit":5
}
```

---

## 7. Itinerary Agent

전문 Agent가 찾은 후보를 조합하여 전체 일정을 구성한다.

이 Agent는 자유롭게 장소를 지어내는 Agent가 아니라, **코드 기반 일정 최적화 Tool을 사용하는 Agent**로 구성한다.

### 역할

- 슬롯별 후보를 수집한다.
- 일정 최적화 Tool을 호출한다.
- 후보가 부족한 슬롯을 찾는다.
- 필요한 경우 Supervisor에 재검색을 요청한다.
- 최적화 결과에 설명을 붙인다.

### 사용 Tool

```
Itinerary Optimizer Tool
Travel Time Tool
Operating Hours Tool
Duplicate Checker
```

실제 조합 계산은 LLM이 아니라 코드가 수행한다.

```
Itinerary Agent
    ↓
Optimizer Tool 호출
    ↓
완전탐색 또는 Beam Search
    ↓
상위 일정 K개 반환
    ↓
Agent가 결과 해석
```

따라서 최적성을 요구하는 부분은 코드가 담당하고, Agent는 검색 보완과 결과 해석을 담당한다.

---

## 8. Hard Validator

Hard Validator는 Agent가 아니라 일반 코드 모듈로 유지한다.

### 검증 항목

- 반려동물 동반 조건을 만족하는가
- 반려동물 크기 제한을 만족하는가
- 휠체어 접근 조건을 만족하는가
- 운영시간 안에 방문할 수 있는가
- 이동시간을 포함해 일정 수행이 가능한가
- 같은 장소가 중복되었는가
- 장소 근거 데이터가 존재하는가

```
위반 없음
→ Validation Agent

위반 있음
→ 실패 코드 생성
→ Supervisor에 반환
→ 해당 Agent만 재실행
```

안전 필수조건은 LLM 판단에 맡기지 않는다.

---

## 9. Validation Agent

일정의 정성적 품질을 평가하는 Evaluator 역할을 한다.

### 검토 항목

- 동선이 자연스러운가
- 일정이 지나치게 빡빡하지 않은가
- 점심과 저녁 시간이 적절한가
- 동일 유형의 장소가 반복되는가
- 사용자 선호가 충분히 반영되었는가
- 여행의 주요 목적이 일정에 드러나는가

출력은 구조화한다.

```
{
  "status":"REVISE",
  "score":72,
  "issues": [
    {
      "type":"ROUTE_INEFFICIENCY",
      "slots": ["LUNCH","AFTERNOON_MAIN"
      ],
      "reason":"두 장소의 이동 동선이 크게 역행한다."
    }
  ],
  "nextAction": {
    "agent":"RestaurantAgent",
    "instruction":"오후 관광지 반경 내 점심 후보를 다시 검색한다."
  }
}
```

Validation Agent는 직접 일정을 수정하지 않는다. 문제와 재실행 대상을 Supervisor에 전달한다.

이 구조는 **Evaluator-Optimizer 패턴**에 해당한다.

```
일정 생성
→ 품질 평가
→ 수정 요청
→ 재생성
→ 재평가
```

---

## 10. Response Agent

최종 검증이 끝난 일정만 사용자용 답변으로 생성한다.

### 역할

- 검색된 원본 데이터를 근거로 설명한다.
- 날짜별 코스를 정리한다.
- 추천 이유를 작성한다.
- 주소, 운영시간, 접근성 정보를 표시한다.
- 확인되지 않은 정보는 명확하게 구분한다.
- 검색 결과의 문서 ID를 근거로 유지한다.

```
최종 일정
+ Elasticsearch 원본 문서
+ 사용자 선호
+ 검증 결과
    ↓
Response Agent
    ↓
RAG 기반 최종 답변
```

# AI 여행 취향 프로필 — AI 구현 명세

## 현재 구현 상태

**AI 서버 MVP 구현 완료** (`travel-profile-llm-v1`)

- 독립 모듈과 `POST /internal/travel/profile/analyze` API 구현 완료
- 규칙 기반 데이터 충분성 판정과 LLM-first 여행자 유형·태그·설명·근거 분석 구현 완료
- 규칙 엔진은 신뢰도 상한과 장애 fallback을 담당하고 정상 경로에서는 LLM이 유형을 직접 결정
- LLM 비활성화·호출 실패·검증 실패 시 입력에 근거한 고정 문구로 대체
- 요청·응답 스키마, 내부 API 키 인증, 개인정보 필드 차단 및 계약 테스트 구현 완료

AI 서버가 담당하는 분석 기능은 완료됐다. 다음 항목은 이 저장소의 MVP 범위 밖이며 BE 작업이 필요하다.

- 분석 결과의 DB 저장과 갱신·만료 정책
- FE 공개 API와 사용자 인증
- 저장된 `traveler_type`, `tags`를 기존 여행 추천 요청에 전달하는 개인화 연동
- 배포 환경에서 BE가 실제 전송하는 DTO와 인증 키를 사용한 최종 통합 테스트

## 목표

BE가 전달한 비식별 사용자 활동 데이터를 분석하여 구조화된 여행 취향 프로필을 반환한다.

AI 저장소는 분석과 문장 생성만 담당한다. BE DB에 직접 접근하거나 결과를 영구 저장하지 않으며, 사용자 인증과 FE 공개 API를 담당하지 않는다.

이 기능은 기존 여행지·코스 추천 Multi-Agent를 수정해 그 안에 새 Agent로 넣지 않는다. 같은 AI 저장소와 같은 서버에 배포하되, 독립된 `Travel Profile Analyzer` 모듈과 API로 구현한다. 기존 추천 기능과 LLM Client, 설정, 로깅 같은 공통 기반 코드는 재사용할 수 있다.

권장 구조:

```text
AI 저장소
├── travel_plan/                  # 기존 여행 추천 Multi-Agent
│   └── ...
└── travel_profile/               # 신규 독립 분석 기능
    ├── analyzer
    ├── classifier
    ├── prompt
    └── schema
```

두 기능의 경계:

| 기능 | 역할 | API |
|---|---|---|
| 기존 여행 추천 Multi-Agent | 장소·일정·코스 추천 | `POST /internal/travel/plan` |
| Travel Profile Analyzer | 활동 기록으로 여행 성향 분석 | `POST /internal/travel/profile/analyze` |

별도의 AI 모델을 새로 학습해야 한다는 의미는 아니다. 같은 LLM을 사용해도 프롬프트, 입출력 스키마, 분석 로직, 테스트와 버전은 분리한다.

## MVP 결과

- 대표 여행자 유형 1개
- 한국어 제목과 설명
- 핵심 취향 태그 최대 5개
- 입력 데이터로 검증 가능한 분석 근거 최대 3개
- 결과 신뢰도
- 분석 로직·모델 버전
- 데이터 부족 판정

## 내부 API

```http
POST /internal/travel/profile/analyze
Content-Type: application/json
```

배포 환경에서는 BE와 합의한 내부 인증 헤더를 검증한다.

## 요청 계약

요청과 응답 필드는 `snake_case`를 사용한다.

```json
{
  "schema_version": "1.0",
  "reference_time": "2026-09-13T14:30:00+09:00",
  "searches": [
    {
      "keyword": "강아지 산책",
      "region": "정선",
      "searched_at": "2026-09-10T10:20:00+09:00"
    }
  ],
  "visits": [
    {
      "place_type": "ATTRACTION",
      "place_id": 101,
      "name": "정선 아우라지",
      "category": "NATURE",
      "region": "정선",
      "visited_at": "2026-09-01T12:00:00+09:00"
    }
  ],
  "saved_courses": [
    {
      "name": "정선 힐링 여행",
      "saved_at": "2026-08-27T09:00:00+09:00",
      "places": [
        {
          "place_type": "ATTRACTION",
          "place_id": 101,
          "name": "정선 아우라지",
          "region": "정선"
        }
      ]
    }
  ],
  "reviews": [
    {
      "place_type": "ATTRACTION",
      "place_id": 101,
      "name": "정선 아우라지",
      "rating": 4.5,
      "reviewed_at": "2026-09-02T18:00:00+09:00"
    }
  ]
}
```

규칙:

- 최상위 배열이 비어 있으면 `null`이 아니라 `[]`이 전달된다.
- 개별 선택 필드는 누락 또는 `null`일 수 있다.
- `schema_version`이 지원되지 않으면 명확한 4xx 오류를 반환한다.
- 사용자 이름, 이메일, 닉네임 등의 개인정보는 입력 계약에 포함하지 않는다.

## 응답 계약

정상 분석:

```json
{
  "status": "COMPLETED",
  "traveler_type": "NATURE_HEALING",
  "title": "한적한 자연을 즐기는 힐링 여행자",
  "description": "최근 자연 관광지와 산책하기 좋은 장소를 자주 선택했어요.",
  "tags": ["자연", "한적한 곳", "산책"],
  "evidences": [
    "최근 방문한 장소 중 자연 관광지의 비중이 높아요.",
    "저장한 코스에 산책하기 좋은 장소가 자주 포함됐어요."
  ],
  "confidence": 0.86,
  "analysis_version": "travel-profile-llm-v1"
}
```

데이터 부족:

```json
{
  "status": "INSUFFICIENT_DATA",
  "traveler_type": null,
  "title": null,
  "description": null,
  "tags": [],
  "evidences": [],
  "confidence": null,
  "analysis_version": "travel-profile-llm-v1"
}
```

출력 제한:

- `title`: 1~100자
- `description`: 1~500자
- `tags`: 최대 5개, 항목당 1~30자, 중복 금지
- `evidences`: 최대 3개, 항목당 1~200자
- `confidence`: 0~1
- 모든 사용자 노출 문장은 한국어

## Enum

응답 상태:

- `COMPLETED`
- `INSUFFICIENT_DATA`

여행자 유형:

- `NATURE_HEALING`
- `PET_COMPANION`
- `LOCAL_FOOD_EXPLORER`
- `ACTIVITY_ADVENTURE`
- `CULTURE_EXPLORER`
- `BALANCED_TRAVELER`

화면 표시 문구는 코드 자체가 아니라 `title`로 전달한다. 유형을 추가하거나 이름을 변경하려면 BE 계약도 함께 수정해야 한다.

## 분석 원칙

권장 신호 강도:

```text
방문 기록·높은 평점 리뷰·저장 코스 > 검색 기록
```

- 최근 활동에 더 높은 가중치를 준다.
- 동일 장소의 반복 신호는 취향 강도에 반영할 수 있다.
- 활동량과 신호 일관성이 낮을수록 `confidence`를 낮춘다.
- 서로 다른 취향 신호가 비슷하면 `BALANCED_TRAVELER`를 사용할 수 있다.
- 근거는 반드시 입력 데이터로 설명할 수 있어야 한다.
- 횟수나 비율을 문장에 포함하면 실제 계산값과 일치해야 한다.
- 질병, 장애, 경제 상태 등 민감한 특성을 추론하지 않는다.
- 부정적이거나 평가적인 표현을 피한다.
- 취향을 영구적 특성처럼 단정하지 않고 최근 활동 기반으로 설명한다.

정상 경로에서는 LLM이 활동 전체를 종합해 유형, 제목, 설명, 태그, 근거와 신뢰도를 직접 분석한다. 결정론적 계산은 최소 데이터 판정, 신뢰도 상한, 출력 검증과 장애 fallback을 담당한다.

## 기존 여행 추천 AI와의 연동

MVP에서는 두 기능을 직접 연결하지 않는다. 프로필 분석 결과는 BE가 저장한다.

후속 단계에서는 BE가 저장된 `traveler_type`과 `tags`를 기존 여행 추천 요청의 사용자 컨텍스트로 전달할 수 있다.

```text
Travel Profile Analyzer → BE에 결과 저장
                              ↓
사용자 코스 요청 → BE → 기존 여행 추천 Multi-Agent
                         + 저장된 여행 취향 컨텍스트
```

여행 추천 요청 시마다 Travel Profile Analyzer를 Multi-Agent의 하위 Agent로 실행하지 않는다. 저장된 프로필이 없거나 만료된 경우의 재분석 여부는 BE가 결정한다.

## 데이터 부족 기준

MVP 권장 기준은 유효 활동 신호 합계가 3건 미만이면 `INSUFFICIENT_DATA`를 반환하는 것이다.

유효 신호:

- 검색 기록 1건
- 방문 기록 1건
- 저장 코스 내부 장소 1건
- 리뷰 1건

동일 장소가 여러 저장 코스에 반복 포함된 경우 데이터 충분성 계산에서 과도하게 중복 계산하지 않는다.

## 오류 응답

- 요청 스키마 오류: `400 Bad Request`
- 지원하지 않는 `schema_version`: `400 Bad Request`
- 내부 인증 실패: `401` 또는 `403`
- 분석 처리 실패: `500 Internal Server Error`
- 처리 제한 시간을 초과하지 않도록 서버 타임아웃을 BE 제한 시간보다 짧게 설정

오류 시 부분 분석 결과를 `COMPLETED`로 반환하지 않는다.

## 구현 체크리스트

- [x] 요청·응답 스키마 모델 구현
- [x] 기존 여행 추천 기능과 분리된 `travel_profile` 모듈 구성
- [x] 내부 인증 검증 구현
- [x] 데이터 정규화 및 중복 제거 구현
- [x] 데이터 부족 판정 구현
- [x] 신호별 가중치와 최근성 점수 구현
- [x] 여행자 유형 분류 구현
- [x] 제목·설명·태그·근거 생성 구현
- [x] 출력 후처리와 길이 제한 구현
- [x] `analysis_version` 관리 구현
- [x] API 및 계약 테스트 작성
- [x] 기존 여행 추천 입력의 선택적 `travel_profile` 계약 구현
- [x] 프로필 태그를 낮은 가중치의 soft preference로 병합
- [x] 사용자 직접 입력 우선순위 회귀 테스트
- [ ] 활동 원본 ID가 연결된 구조화 근거 계약

## 구현된 안전장치

- 허용하지 않은 요청 필드와 정의되지 않은 Enum을 거부한다.
- 모든 활동 시각에 시간대 정보가 없으면 `400 Bad Request`를 반환한다.
- 개인정보 필드는 요청 스키마에 없으며 추가 필드는 거부한다.
- LLM은 허용된 여행자 유형과 0~1 범위의 신뢰도만 반환할 수 있다.
- 최종 신뢰도는 결정론적 데이터 품질 점수를 상한으로 제한한다.
- LLM 근거 문장은 규칙 엔진이 만든 `evidence_candidates`에서만 선택할 수 있다.
- LLM 출력이 형식·길이·한국어 조건을 만족하지 않거나 호출에 실패하면 안전한 fallback을 사용한다.

## 테스트 조건

- 유효·잘못된 요청 스키마
- 데이터 부족 판정 경계값
- 모든 여행자 유형 분류
- 최근 데이터 가중치 적용
- 중복 장소 처리
- 제목·설명 글자 수 제한
- 태그·근거 배열 최대 크기와 중복 제거
- 정의되지 않은 Enum 반환 방지
- 근거가 입력 데이터에 기반하는지 검증
- 동일 입력에 대한 구조적 일관성

## 완료 조건

- [x] 합의된 BE 요청 DTO 스키마를 처리할 수 있다.
- [x] 기존 여행 추천 Multi-Agent의 동작과 API 계약에 영향을 주지 않는다.
- [x] 모든 응답이 정의된 JSON 스키마를 만족한다.
- [x] 데이터 부족이 정상 상태로 구분된다.
- [x] 생성된 근거를 입력 데이터로 검증할 수 있다.
- [x] 개인정보를 요구하거나 추론하지 않는다.
- [x] AI 저장소 내부 API·계약 테스트를 작성했다.
- [ ] 실행 중인 BE와 배포 환경 인증 설정을 사용한 최종 통합 테스트를 완료한다.

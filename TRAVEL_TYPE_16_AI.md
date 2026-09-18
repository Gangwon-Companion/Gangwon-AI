# Travel Type 16 — AI 구현 및 운영 명세

## 구현 상태

- 상태: 구현 완료
- 분석 버전: `travel-type-16-v1`
- 입력: 검색, 방문, 저장 코스, 리뷰 활동
- 출력: 16유형 코드, 네 축 점수, 사용자용 설명, 태그, 근거, 신뢰도
- 반려동물 동반 여부는 여행 유형 축에 포함하지 않는다.

## 분석 축

| 순서 | 축 | 성향 |
|---:|---|---|
| 1 | 공간 | `C` 도시 / `N` 자연 |
| 2 | 활동 | `A` 체험 / `R` 휴식 |
| 3 | 일정 | `P` 계획 / `S` 즉흥 |
| 4 | 장소 | `F` 유명 명소 / `H` 숨은 로컬 |

허용 코드는 다음과 같다.

```text
CAPF CAPH CASF CASH CRPF CRPH CRSF CRSH
NAPF NAPH NASF NASH NRPF NRPH NRSF NRSH
```

## 입력 계약

```http
POST /internal/travel/profile/analyze
```

주요 입력:

- `schema_version`
- `reference_time`
- `searches`
- `visits`
- `saved_courses`
- `reviews`

개인식별정보는 입력받지 않는다. 유효 활동 신호가 3건 미만이면 `INSUFFICIENT_DATA`를 반환한다.

## 점수 계산

- 검색 기본 가중치: `1.0`
- 방문 기본 가중치: `3.0`
- 저장 코스의 고유 장소: `2.5`
- 리뷰: 평점에 따라 `0.2`, `0.5`, `1.0` 비율로 기본 가중치 조정
- 약 90일 반감의 최신성 가중치 적용
- 중복 저장 장소는 한 번만 계산

행동 보조 신호:

- 검색·저장 코스 → `P`
- 실제 방문 → `S`
- 장소명·카테고리·검색어의 축별 키워드 → 해당 성향 점수

각 축은 합계 100으로 정규화한다. 근거가 없는 축은 `50:50`, 동점은 왼쪽 성향을 선택한다. 이 정책은 결과를 만들 수 있게 하지만 신뢰도가 낮아질 수 있으므로 향후 분석 보류 정책을 검토한다.

## LLM 역할

규칙 엔진이 `traveler_type`과 `axis_scores`를 확정한다. LLM은 이를 재분류하지 않는다.

LLM이 담당하는 항목:

- 한국어 제목과 설명 보정
- 태그 생성
- 제공된 근거 후보 중 최대 3개 선택
- 규칙 엔진 신뢰도보다 높은 값으로 임의 상승하지 않도록 상한 적용

LLM 호출이 실패하면 16유형별 고정 문구를 fallback으로 사용한다.

## 응답 계약

```json
{
  "status": "COMPLETED",
  "traveler_type": "CAPF",
  "title": "도시 정복 플래너",
  "description": "도시의 대표 명소와 체험을 촘촘한 일정으로 완주하는 여행자예요.",
  "tags": ["도시", "체험", "계획", "대표 명소"],
  "evidences": ["최근 검색 기록 3건을 관심 선호로 반영했어요."],
  "confidence": 0.56,
  "axis_scores": {
    "space": { "C": 100, "N": 0 },
    "activity": { "A": 50, "R": 50 },
    "schedule": { "P": 100, "S": 0 },
    "place": { "F": 50, "H": 50 }
  },
  "analysis_version": "travel-type-16-v1"
}
```

코스 추천 입력의 `travel_profile`에도 선택적 `axis_scores`를 허용한다. 최종 유형뿐 아니라 경계 성향을 추천에 전달하기 위한 계약이다.

## 실행

로컬 BE와 연결:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Docker BE와 연결:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Docker BE의 기본 AI 주소는 `http://host.docker.internal:8001`이다. Windows 방화벽 승인이 필요하면 개인 네트워크만 허용한다.

## 트러블슈팅

### BE Job이 `AI_SERVICE_UNAVAILABLE`

- AI 프로세스 실행 여부 확인
- BE 실행 방식에 맞는 포트 확인
- Docker BE가 호스트 AI에 접근하려면 AI가 `127.0.0.1`이 아닌 `0.0.0.0`에 바인딩되어야 함
- 상태 확인: `Invoke-RestMethod http://127.0.0.1:8001/health`

### BE Job이 `INTERNAL_SERVER_ERROR`

AI 응답 이후 약 1~2초 뒤 실패하면 BE 저장 로그를 확인한다. 실제 발생 사례는 DB의 기존 유형 체크 제약조건이 `CAPF`를 거부한 문제였다. AI 분석 자체는 정상 완료된 상태였다.

### 내부 API 키 오류

연결 불가와 구분한다. 키가 불일치하면 일반적으로 HTTP 401/클라이언트 오류가 발생한다. 테스트에서는 환경값을 읽지 않고 FastAPI dependency override로 인증을 격리한다.

## 테스트

환경 파일을 로딩하는 `app.main` 없이 관련 모듈만 테스트한다.

```powershell
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests\test_travel_profile.py tests\test_input_parser.py
```

검증 항목:

- 활동 기록 부족
- `CAPF`, `NRSH` 대표 조합
- 모든 축 합계 100
- `travel-type-16-v1` 응답 계약
- 코스 추천 입력의 `axis_scores` 수용

## 남은 개선 과제

- 관광지 인기도 데이터를 통한 `F/H` 정확도 개선
- 저장과 실제 방문의 시간 관계를 통한 `P/S` 정확도 개선
- 축별 근거가 부족할 때 전체 분석을 보류하는 최소 커버리지 정책

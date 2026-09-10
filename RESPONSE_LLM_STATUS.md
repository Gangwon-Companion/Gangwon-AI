# Response Agent LLM 연동 진행상황

## 1. 현재 결론

Response Agent의 LLM 표현 계층은 코드 구현과 비용 없는 테스트까지 완료됐다.

실제 OpenAI API 키를 넣고 `GANGWON_RESPONSE_LLM_ENABLED=true` 상태에서 `/internal/travel/response/preview`를 호출해 실제 모델 답변 생성까지 확인했다.

즉 현재 상태는 다음과 같다.

```text
구조화된 최종 응답 생성: 완료
LLM answer 교체 구조: 완료
LLM 실패 시 fallback: 완료
비용 없는 단위/API 테스트: 완료
실제 API 키 기반 수동 테스트: 완료
전체 LangGraph 연결: 다른 Agent 완성 후 진행
```

## 2. 왜 LLM을 추가했는가

기존 Response Agent는 Python 코드로 사용자용 `answer`를 결정적으로 생성했다.

이 방식은 테스트하기 쉽고 안전하지만, 문장이 다소 딱딱할 수 있다. LLM을 추가하면 검증된 일정 정보를 바탕으로 더 자연스럽고 사용자 친화적인 한국어 답변을 만들 수 있다.

단, LLM은 사실 생성자가 아니라 표현 계층으로만 사용한다.

LLM이 하면 안 되는 일:

- 장소 추가
- 장소 삭제
- 일정 시간 변경
- 검증 결과 변경
- 확인되지 않은 정책을 가능하다고 추정
- `source_ids`, `notices`, `unverified_fields` 누락

현재 구조는 Python이 검증된 구조화 데이터를 만들고, LLM은 `answer` 문자열만 교체하는 방식이다.

```text
TravelState
→ Response Agent가 days/notices/source_ids 생성
→ 기존 Python _answer()로 fallback 답변 생성
→ LLM이 켜져 있으면 answer만 자연어로 재작성
→ 실패하면 fallback 답변 사용
```

## 3. 추가/수정된 파일

### 3.1 `app/agents/response_llm.py`

새로 추가된 LLM 전용 모듈이다.

주요 역할:

- LLM 사용 여부 확인
- OpenAI Responses API 호출
- LLM 프롬프트 생성
- LLM 입력 JSON 생성
- LLM 응답 텍스트 추출
- 실패 시 fallback 답변 반환

주요 환경변수:

```text
GANGWON_RESPONSE_LLM_ENABLED
GANGWON_RESPONSE_LLM_MODEL
OPENAI_API_KEY
OPENAI_BASE_URL
```

기본 모델은 비용 절감을 위해 `gpt-5.4-nano`로 설정했다.

### 3.2 `app/agents/response.py`

기존 구조화 응답 생성 로직은 유지했다.

변경된 부분은 최종 `answer` 생성 단계다.

기존:

```text
_answer() 결과를 그대로 answer에 사용
```

현재:

```text
_answer()로 fallback 답변 생성
→ render_answer_with_llm() 호출
→ LLM이 꺼져 있거나 실패하면 fallback 사용
→ LLM이 성공하면 answer만 LLM 답변으로 교체
```

`days`, `notices`, `quality_score`, `source_ids` 등 구조화 데이터는 LLM이 수정하지 않는다.

### 3.3 `.env.example`

팀원들이 필요한 환경변수를 확인할 수 있도록 예시 파일을 추가했다.

```env
GANGWON_BE_BASE_URL=http://localhost:8080

GANGWON_RESPONSE_LLM_ENABLED=false
GANGWON_RESPONSE_LLM_MODEL=gpt-5.4-nano
OPENAI_API_KEY=

OPENAI_BASE_URL=https://api.openai.com
```

실제 `.env` 파일은 `.gitignore`에 의해 커밋되지 않는다.

### 3.4 `tests/test_response.py`

Response Agent와 LLM 연동 관련 테스트를 확장했다.

현재 확인하는 내용:

- 검증 통과 일정만 `READY` 응답 생성
- 검증 미완료/실패 상태에서는 `PENDING` 응답 생성
- 날짜와 시간순 정렬
- 주소, 운영시간, 접근성, 반려동물 정책 보존
- 미확인 정보는 `unverified_fields`와 `notices`에 표시
- `source_ids` 보존
- 입력 state 불변성 유지
- LLM OFF 시 LLM client를 호출하지 않음
- LLM ON + 성공 시 `answer`만 교체
- LLM ON + 실패 시 fallback 답변 사용
- LLM 프롬프트에 안전 규칙 포함
- LLM 입력 JSON에 `days`, `notices`, `source_ids` 포함
- Preview API 경로에서도 fake LLM answer 교체 확인

## 4. 테스트 결과

Response Agent 테스트:

```text
python -B -m unittest tests.test_response

Ran 11 tests
OK
```

전체 테스트:

```text
python -B -m unittest

Ran 42 tests
OK
```

테스트 실행 중 FastAPI/Starlette와 LangGraph 관련 deprecation warning이 출력될 수 있으나, 현재 변경 실패는 아니다.

## 5. 실제 LLM 수동 테스트 결과

### 5.1 접근 가능한 모델 확인

전달받은 서비스 키로 OpenAI `/v1/models`를 조회한 결과, 현재 프로젝트에서 접근 가능한 GPT 계열 모델은 `gpt-4.1`만 확인됐다.

처음 설정했던 저비용 모델 `gpt-5.4-nano`는 다음 오류로 실패했다.

```text
HTTP 403 invalid_request_error:
Project ... does not have access to model gpt-5.4-nano
```

따라서 실제 동작 확인은 현재 키로 접근 가능한 `gpt-4.1` 모델로 진행했다.

테스트 당시 환경변수:

```powershell
$env:GANGWON_RESPONSE_LLM_ENABLED="true"
$env:GANGWON_RESPONSE_LLM_MODEL="gpt-4.1"
$env:OPENAI_API_KEY="서비스_API_KEY"
```

### 5.2 실제 생성 결과 요약

`POST /internal/travel/response/preview`에 검증 완료 일정 샘플을 넣어 호출했다.

LLM이 생성한 `answer`는 기존 Python fallback 답변과 다른 자연어 문장으로 교체됐다.

생성 결과 요약:

```text
바다 전망대와 저녁 식당을 방문하는 일정으로 설명
주소, 운영시간, 접근성, 반려동물 정책 포함
source_ids 포함
저녁 식당의 실내 동반 및 허용 크기 미확인 정보를 방문 전 확인하라고 안내
```

확인된 성공 조건:

- 실제 OpenAI API 호출 성공
- `gpt-4.1` 모델 접근 성공
- LLM 답변이 `answer`에 반영됨
- `days`, `notices`, `quality_score`, `source_ids` 구조화 데이터는 유지됨
- 없는 장소를 추가하지 않음
- 주소와 운영시간을 임의로 변경하지 않음
- `null` 정책을 가능하다고 추정하지 않음
- 미확인 정보를 방문 전 확인 대상으로 안내함

### 5.3 테스트 후 비활성화

실제 LLM 호출은 비용이 발생할 수 있으므로, 수동 테스트 완료 후 로컬 환경에서는 LLM을 다시 비활성화한다.

PowerShell:

```powershell
$env:GANGWON_RESPONSE_LLM_ENABLED="false"
Remove-Item Env:OPENAI_API_KEY
```

서버를 실행 중이었다면 `Ctrl + C`로 종료한 뒤 다시 실행해야 변경된 환경변수가 반영된다.

### 5.4 현재 모델 관련 결론

현재 서비스 키로는 저비용 nano/mini 계열 모델을 바로 사용할 수 없었다.

현재 실제 테스트 완료 모델:

```text
gpt-4.1
```

기본 코드와 `.env.example`에는 비용 절감 목적의 기본값으로 `gpt-5.4-nano`를 유지하고 있다. 다만 현재 프로젝트 키로는 권한이 없으므로, 실제 운영 또는 추가 테스트 전 팀에서 모델 접근 권한을 확정해야 한다.

팀 회의 때 확인할 것:

- 현재 서비스 키로 계속 `gpt-4.1`을 사용할지
- 저비용 모델 접근 권한을 요청할지
- 기본 모델명을 현재 접근 가능한 `gpt-4.1`로 바꿀지
- 개발 기본값은 저비용 모델로 유지하고, 실제 배포 환경변수만 별도 지정할지

저비용 후보:

```text
gpt-5-nano
gpt-5-mini
gpt-4.1-nano
gpt-4.1-mini
gpt-4o-mini
```

## 6. 실제 LLM 수동 테스트 방법

실제 비용이 발생할 수 있으므로 팀 회의 후 진행한다.

PowerShell 예시:

```powershell
$env:GANGWON_RESPONSE_LLM_ENABLED="true"
$env:GANGWON_RESPONSE_LLM_MODEL="gpt-5.4-nano"
$env:OPENAI_API_KEY="실제_API_KEY"

uvicorn app.main:app --reload
```

Swagger 접속:

```text
http://127.0.0.1:8000/docs
```

호출 API:

```text
POST /internal/travel/response/preview
```

확인할 것:

- `answer`가 자연스러운 한국어로 생성되는지
- 없는 장소를 만들지 않는지
- 시간, 주소, 장소 ID를 바꾸지 않는지
- 미확인 정보를 가능하다고 표현하지 않는지
- `source_ids`를 보존하는지
- `days`, `notices`, `quality_score` 구조화 데이터가 유지되는지

## 7. 현재 Response Agent 완료 범위

현재까지 Response Agent는 다음 범위까지 완료됐다.

- 구조화된 최종 응답 생성
- 사용자용 기본 Python 답변 생성
- LLM 기반 `answer` 재작성 계층
- LLM 비활성화 기본값
- LLM 실패 fallback
- 저비용 모델 기본값
- 환경변수 예시 문서
- 단위 테스트
- Preview API 경로 테스트

실제 LLM 수동 테스트까지 통과했으므로 Response Agent의 독립 기능은 완료로 볼 수 있다.

## 8. 앞으로 해야 할 일

다른 팀원의 Search Tool과 하위 Agent 작업이 완료된 뒤 다음 순서로 전체 연결을 진행한다.

```text
Search Tool 완성
→ Destination/Restaurant/Lodging Agent 안정화
→ Itinerary Agent 최종 연결
→ Hard Validator 연결
→ Validation Agent 연결
→ Response Agent 연결
→ /internal/travel/plan에서 final_response까지 통합 테스트
```

Response Agent 연결 시 필요한 작업:

- LangGraph에 `response_node` 등록
- Validation Agent `PASS` 이후 Response Agent로 라우팅
- `/internal/travel/plan` 응답에 `final_response` 포함
- Itinerary 결과 시간 모델과 Validation/Response 시간 모델 통합
- 재시도 이후에도 근거 필드와 `source_ids`가 유지되는지 확인

## 9. LLM 답변 개선 후보

실제 `gpt-4.1` 테스트 결과, 기능은 정상 동작했지만 답변 스타일은 더 개선할 수 있다.

현재 아쉬운 점:

- 방문 예정 시간 `10:00-12:00`, `18:00-19:30`이 `answer`에 직접 포함되지 않았다.
- 답변이 한 문단으로 길게 이어졌다.
- 사용자 선호인 `바다`, `한식`과 매칭 이유가 구조화 데이터에는 있지만 `answer`에는 덜 자연스럽게 드러났다.
- 날짜별/시간순 일정표 느낌이 약하다.

프롬프트 개선 방향:

- 방문 예정 시간을 반드시 포함하도록 지시
- 하루 일정은 시간순 bullet 형식으로 작성하도록 지시
- 각 장소마다 추천 이유를 짧게 포함하도록 지시
- 방문 전 확인 사항은 별도 문단으로 분리하도록 지시
- `source_ids`는 마지막에 근거 목록으로 유지하도록 지시

예상 목표 형식:

```text
강릉에서 반려견과 함께 바다 전망과 한식을 즐기는 1일 일정입니다.

1일차
- 10:00-12:00 바다 전망대: 바다 선호와 일치하며, 휠체어 접근과 반려동물 동반이 확인된 장소입니다.
- 18:00-19:30 저녁 식당: 한식 선호와 일치하는 저녁 식사 장소입니다.

방문 전 확인
- 저녁 식당은 실내 반려동물 동반 여부와 허용 크기가 확인되지 않았습니다.

근거
- destination:D1
- restaurant:R2
```

## 10. 주의사항

LLM은 사용자에게 보이는 문장을 자연스럽게 만드는 역할만 한다.

최종 사실 데이터의 기준은 항상 Python이 생성한 구조화 응답이다.

따라서 추후 LLM 프롬프트를 수정하더라도 다음 원칙은 유지해야 한다.

- LLM이 장소/일정/검증 결과를 만들지 않는다.
- LLM 출력은 `answer`에만 반영한다.
- 구조화 데이터는 코드가 만든 값을 그대로 반환한다.
- LLM 실패는 사용자 응답 실패로 이어지지 않고 fallback으로 처리한다.

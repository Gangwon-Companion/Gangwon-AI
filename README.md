# Gangwon-AI

강원도 여행 코스를 생성하기 위한 FastAPI 기반 AI 오케스트레이션 서버입니다.
LangGraph로 여행 요청을 상태로 관리하고, Supervisor Agent가 필요한 전문 Agent의 실행 순서를 결정하는 것을 목표로 합니다.

## 프로젝트 역할

Spring Boot는 사용자 요청을 수신하고 기본 입력을 정규화합니다.
FastAPI는 정규화된 요청을 받아 LangGraph를 실행하고 Agent 실행 계획을 반환합니다.

```text
Client
  ↓
Spring Boot
  - 사용자 요청 수신
  - 인증 및 기본 검증
  - 요청 데이터 정규화
  ↓ POST /internal/travel/plan
FastAPI
  - LangGraph State 생성
  - Preference Extractor
  - Conflict Checker
  - Supervisor Agent
```

## 현재 구현 범위

현재는 `Input Parser`의 일부와 `Supervisor Agent`까지 구현되어 있습니다.

```text
정규화된 요청
  ↓
Preference Extractor
  ↓
Conflict Checker
  ↓
Supervisor Agent
  ├─ Destination Agent
  ├─ Restaurant Agent
  ├─ Lodging Agent
  ├─ Activity Agent
  ├─ Itinerary Agent
  └─ Validator
```

Destination, Restaurant, Lodging Agent의 실제 검색 기능과 Elasticsearch, Hard Validator, Validation Agent, Response Agent는 이후 단계에서 연결할 예정입니다.

## 기술 스택

- Python 3.12+
- FastAPI
- LangGraph
- Uvicorn
- Pydantic

직접 관리하는 의존성은 `requirements.txt`에서 확인할 수 있습니다.

## 가상환경 설정

Windows PowerShell 기준입니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

이미 가상환경이 있다면 다음 명령만 실행하면 됩니다.

```powershell
.\.venv\Scripts\Activate.ps1
```

## FastAPI 서버 실행

프로젝트 루트에서 실행합니다.

```powershell
uvicorn app.main:app --reload
```

기본 서버 주소:

```text
http://127.0.0.1:8000
```

Swagger 문서는 다음 주소에서 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

## Health Check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

응답:

```json
{
  "status": "ok"
}
```

## 여행 계획 API

Spring Boot가 정규화한 요청을 FastAPI로 전달합니다.

```text
POST /internal/travel/plan
Content-Type: application/json
```

요청 예시:

```json
{
  "message": "반려견과 강릉에서 바다와 카페 중심으로 여행하고 싶어요.",
  "region": "강릉",
  "travel_days": 3,
  "nights": 2,
  "pet_allowed": true,
  "pet_size": "SMALL",
  "wheelchair_accessible": false,
  "preferences": ["바다", "카페"]
}
```

PowerShell 호출 예시:

```powershell
$body = @{
  message = "반려견과 강릉에서 바다와 카페 중심으로 여행하고 싶어요."
  region = "강릉"
  travel_days = 3
  nights = 2
  pet_allowed = $true
  pet_size = "SMALL"
  wheelchair_accessible = $false
  preferences = @("바다", "카페")
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/internal/travel/plan `
  -ContentType "application/json" `
  -Body $body
```

정상 요청은 Supervisor의 실행 계획을 반환합니다.

```json
{
  "status": "planned",
  "slots": ["DESTINATION", "LUNCH", "DINNER", "LODGING", "BREAKFAST"],
  "selected_agents": ["destination", "restaurant", "lodging"],
  "execution_plan": [],
  "retry_count": 0,
  "messages": [],
  "missing_fields": [],
  "clarification_questions": [],
  "conflicts": []
}
```

입력 충돌이 있으면 `needs_clarification` 상태와 확인 질문을 반환합니다.

## 디렉터리 구조

```text
app/
├─ agents/
│  ├─ input_parser.py     # Preference Extractor, Conflict Checker
│  └─ supervisor.py       # Supervisor Agent
├─ api/
│  └─ routes.py           # FastAPI API 라우트
├─ core/
│  └─ state.py            # LangGraph State 정의
├─ schemas/
│  └─ travel.py           # 요청/응답 스키마
├─ graph.py               # LangGraph 구성
└─ main.py                # FastAPI 앱 진입점
```

## 관련 문서

- [plan.md](plan.md): 전체 여행 Agent 및 검색 구조 계획

# Gangwon-AI

`plan.md`의 Supervisor Agent 범위를 구현한 초기 FastAPI/LangGraph 구조입니다.

## 실행

직접 의존성은 FastAPI, LangGraph, Uvicorn뿐입니다. Pydantic은 FastAPI의 전이 의존성으로 설치됩니다.

## 가상환경 설정 (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

```powershell
uvicorn app.main:app --reload
```

Spring Boot가 사용자 입력을 처리한 뒤 `POST /internal/travel/plan`으로 정규화된 요청을 전송합니다.

FastAPI는 다음 LangGraph 흐름을 실행합니다.

`PreferenceExtractor → ConflictChecker → Supervisor`

- 입력 충돌이 있으면 `needs_clarification` 상태와 확인 질문을 반환합니다.
- 입력이 정상이면 Supervisor가 슬롯과 Agent 실행 계획을 반환합니다.

현재 Destination, Restaurant, Lodging 등의 실제 검색/실행 노드는 다음 단계에서 연결합니다.

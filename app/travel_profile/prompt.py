"""Travel Type 16 copy and grounded LLM prompt."""

from __future__ import annotations

import json

from app.travel_profile.schema import AxisScores, TravelerType


TYPE_COPY: dict[TravelerType, tuple[str, str, list[str]]] = {
    TravelerType.CAPF: ("도시 정복 플래너", "도시의 대표 명소와 체험을 촘촘한 일정으로 완주하는 여행자예요.", ["도시", "체험", "계획", "대표 명소"]),
    TravelerType.CAPH: ("히든시티 전략가", "숨은 도시 콘텐츠를 미리 조사해 알차게 경험하는 여행자예요.", ["도시", "체험", "계획", "숨은 명소"]),
    TravelerType.CASF: ("랜드마크 액션러", "그날의 기분에 따라 유명한 도심 명소와 체험을 누비는 여행자예요.", ["도시", "체험", "즉흥", "대표 명소"]),
    TravelerType.CASH: ("골목 모험 스카우트", "발길 닿는 대로 골목의 새로운 공간과 활동을 발견하는 여행자예요.", ["도시", "체험", "즉흥", "로컬"]),
    TravelerType.CRPF: ("도심 힐링 가이드", "유명한 도시 공간을 여유로운 동선으로 편안하게 즐기는 여행자예요.", ["도시", "휴식", "계획", "대표 명소"]),
    TravelerType.CRPH: ("골목 감성 큐레이터", "조용한 카페와 숨은 공간을 찾아 자신만의 코스로 엮는 여행자예요.", ["도시", "휴식", "계획", "로컬"]),
    TravelerType.CRSF: ("도심 여유 산책가", "유명한 도시 공간을 일정에 얽매이지 않고 가볍게 즐기는 여행자예요.", ["도시", "휴식", "즉흥", "대표 명소"]),
    TravelerType.CRSH: ("골목 낭만 유랑자", "계획 없이 걷다가 마음에 드는 로컬 공간에 머무는 여행자예요.", ["도시", "휴식", "즉흥", "로컬"]),
    TravelerType.NAPF: ("자연 원정대장", "유명 자연 명소와 액티비티를 철저한 계획으로 공략하는 여행자예요.", ["자연", "체험", "계획", "대표 명소"]),
    TravelerType.NAPH: ("자연 탐험 플래너", "알려지지 않은 자연 명소와 활동을 미리 조사해 찾아가는 여행자예요.", ["자연", "체험", "계획", "숨은 명소"]),
    TravelerType.NASF: ("자연 액티비티 헌터", "즉흥적으로 유명 자연 명소와 레포츠를 즐기는 여행자예요.", ["자연", "체험", "즉흥", "대표 명소"]),
    TravelerType.NASH: ("야생 모험 개척자", "정해진 코스 없이 숨은 자연과 새로운 체험에 뛰어드는 여행자예요.", ["자연", "체험", "즉흥", "숨은 명소"]),
    TravelerType.NRPF: ("절경 힐링 설계자", "대표적인 자연 명소에서 완벽한 휴식을 계획하는 여행자예요.", ["자연", "휴식", "계획", "대표 명소"]),
    TravelerType.NRPH: ("숲속 힐링 설계자", "한적한 자연 속 숨은 휴식처를 계획적으로 찾아가는 여행자예요.", ["자연", "휴식", "계획", "숨은 명소"]),
    TravelerType.NRSF: ("풍경 따라 쉼표 여행자", "유명한 자연 풍경을 따라 자유롭게 쉬어 가는 여행자예요.", ["자연", "휴식", "즉흥", "대표 명소"]),
    TravelerType.NRSH: ("자연 속 은둔 유랑자", "사람 적은 자연을 따라 즉흥적으로 머물 곳을 정하는 여행자예요.", ["자연", "휴식", "즉흥", "숨은 명소"]),
}


def profile_instructions() -> str:
    return (
        "확정된 여행 유형과 실제 활동 근거를 바탕으로 한국어 프로필 문구를 작성하라. "
        "traveler_type과 axis_scores는 이미 규칙 엔진에서 확정되었으므로 변경하거나 재분류하지 마라. "
        "입력에 없는 장소, 행동, 개인정보를 만들지 마라. 장기 성격이 아니라 최근 여행 경향으로 표현하라. "
        "evidences는 evidence_candidates에 있는 문장만 최대 3개 선택하라. "
        "마크다운 없이 title, description, tags, evidences, confidence 키만 가진 JSON 객체를 출력하라."
    )


def profile_input(*, traveler_type: TravelerType, axis_scores: AxisScores, activity_context: dict[str, object], evidence_candidates: list[str]) -> str:
    return json.dumps(
        {
            "traveler_type": traveler_type.value,
            "axis_scores": axis_scores.model_dump(),
            "activity_context": activity_context,
            "evidence_candidates": evidence_candidates,
        },
        ensure_ascii=False,
        indent=2,
    )

from __future__ import annotations

from app.travel_profile.classifier import Classification, classify, place_identity, valid_signal_count
from app.travel_profile.generator import (
    GeneratedProfileCopy,
    LLMProfileCopyGenerator,
    ProfileCopyGenerator,
)
from app.travel_profile.prompt import TYPE_COPY
from app.travel_profile.schema import (
    ProfileStatus,
    TravelProfileRequest,
    TravelProfileResponse,
    TravelerType,
)


ANALYSIS_VERSION = "travel-profile-v1"
MINIMUM_SIGNALS = 3

TYPE_LABELS = {
    TravelerType.NATURE_HEALING: "자연·휴식",
    TravelerType.PET_COMPANION: "반려동물 동반",
    TravelerType.LOCAL_FOOD_EXPLORER: "지역 음식",
    TravelerType.ACTIVITY_ADVENTURE: "체험·액티비티",
    TravelerType.CULTURE_EXPLORER: "문화·역사",
}


class TravelProfileAnalyzer:
    def __init__(self, copy_generator: ProfileCopyGenerator | None = None) -> None:
        self._copy_generator = copy_generator or LLMProfileCopyGenerator()

    def analyze(self, payload: TravelProfileRequest) -> TravelProfileResponse:
        signal_count = valid_signal_count(payload)
        if signal_count < MINIMUM_SIGNALS:
            return TravelProfileResponse(
                status=ProfileStatus.INSUFFICIENT_DATA,
                traveler_type=None,
                title=None,
                description=None,
                tags=[],
                evidences=[],
                confidence=None,
                analysis_version=ANALYSIS_VERSION,
            )

        classification = classify(payload)
        title, description, tags = TYPE_COPY[classification.traveler_type]
        confidence = self._confidence(signal_count, classification)
        evidence_candidates = self._evidences(payload, classification)[:3]
        copy = self._copy_generator.generate(
            payload=payload,
            traveler_type=classification.traveler_type,
            evidence_candidates=evidence_candidates,
            fallback=GeneratedProfileCopy(
                title=title,
                description=description,
                tags=tags[:5],
                evidences=evidence_candidates,
            ),
        )
        return TravelProfileResponse(
            status=ProfileStatus.COMPLETED,
            traveler_type=classification.traveler_type,
            title=copy.title,
            description=copy.description,
            tags=copy.tags,
            evidences=copy.evidences,
            confidence=confidence,
            analysis_version=ANALYSIS_VERSION,
        )

    @staticmethod
    def _confidence(signal_count: int, result: Classification) -> float:
        volume = min(1.0, signal_count / 10)
        if result.traveler_type == TravelerType.BALANCED_TRAVELER:
            consistency = 0.55 if sum(score > 0 for score in result.scores.values()) > 1 else 0.35
        else:
            consistency = result.consistency
        coverage = min(1.0, sum(result.scores.values()) / max(result.total_weight, 0.0001))
        return round(min(0.95, max(0.3, 0.25 + 0.35 * volume + 0.25 * consistency + 0.15 * coverage)), 2)

    @staticmethod
    def _evidences(payload: TravelProfileRequest, result: Classification) -> list[str]:
        evidences: list[str] = []
        if payload.visits:
            evidences.append(f"최근 방문 기록 {len(payload.visits)}건을 분석에 반영했어요.")
        saved_count = len(
            {
                place_identity(place.place_type, place.place_id, place.name)
                for course in payload.saved_courses
                for place in course.places
            }
        )
        if saved_count:
            evidences.append(f"저장한 코스의 서로 다른 장소 {saved_count}건을 분석에 반영했어요.")
        high_reviews = sum(review.rating >= 4 for review in payload.reviews)
        if high_reviews:
            evidences.append(f"평점 4점 이상인 리뷰 {high_reviews}건에서 긍정적인 선택 신호를 확인했어요.")
        if payload.searches and len(evidences) < 3:
            evidences.append(f"최근 검색 기록 {len(payload.searches)}건을 관심 신호로 반영했어요.")

        if result.traveler_type != TravelerType.BALANCED_TRAVELER:
            count = result.matched_counts.get(result.traveler_type, 0)
            if count and len(evidences) < 3:
                label = TYPE_LABELS[result.traveler_type]
                evidences.append(f"입력 활동 중 {count}건에서 {label} 관련 표현을 확인했어요.")
        elif len(evidences) < 3:
            active_types = sum(score > 0 for score in result.scores.values())
            if active_types >= 2:
                evidences.append(f"서로 다른 여행 취향 범주 {active_types}개에서 비슷한 강도의 신호가 나타났어요.")
        return evidences

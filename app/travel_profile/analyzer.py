from __future__ import annotations

from app.travel_profile.classifier import Classification, classify, place_identity, valid_signal_count
from app.travel_profile.generator import GeneratedProfileCopy, LLMProfileCopyGenerator, ProfileCopyGenerator
from app.travel_profile.prompt import TYPE_COPY
from app.travel_profile.schema import ProfileStatus, TravelProfileRequest, TravelProfileResponse


ANALYSIS_VERSION = "travel-type-16-v1"
MINIMUM_SIGNALS = 3


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
                axis_scores=None,
                analysis_version=ANALYSIS_VERSION,
            )

        classification = classify(payload)
        title, description, tags = TYPE_COPY[classification.traveler_type]
        confidence = self._confidence(signal_count, classification)
        evidence_candidates = self._evidences(payload, classification)[:3]
        copy = self._copy_generator.generate(
            payload=payload,
            traveler_type=classification.traveler_type,
            axis_scores=classification.axis_scores,
            evidence_candidates=evidence_candidates,
            fallback=GeneratedProfileCopy(title=title, description=description, tags=tags[:5], evidences=evidence_candidates),
        )
        analyzed_confidence = min(confidence, copy.confidence) if copy.confidence is not None else confidence
        return TravelProfileResponse(
            status=ProfileStatus.COMPLETED,
            traveler_type=classification.traveler_type,
            title=copy.title,
            description=copy.description,
            tags=copy.tags,
            evidences=copy.evidences,
            confidence=analyzed_confidence,
            axis_scores=classification.axis_scores,
            analysis_version=ANALYSIS_VERSION,
        )

    @staticmethod
    def _confidence(signal_count: int, result: Classification) -> float:
        volume = min(1.0, signal_count / 12)
        covered_axes = sum(
            1
            for left, right in (("C", "N"), ("A", "R"), ("P", "S"), ("F", "H"))
            if result.raw_scores[left] + result.raw_scores[right] > 0
        ) / 4
        return round(min(0.95, max(0.3, 0.25 + 0.3 * volume + 0.25 * result.consistency + 0.2 * covered_axes)), 2)

    @staticmethod
    def _evidences(payload: TravelProfileRequest, result: Classification) -> list[str]:
        evidences: list[str] = []
        if payload.visits:
            evidences.append(f"최근 방문 기록 {len(payload.visits)}건을 분석에 반영했어요.")
        saved_count = len({place_identity(place.place_type, place.place_id, place.name) for course in payload.saved_courses for place in course.places})
        if saved_count:
            evidences.append(f"저장한 코스의 서로 다른 장소 {saved_count}건을 분석에 반영했어요.")
        high_reviews = sum(review.rating >= 4 for review in payload.reviews)
        if high_reviews:
            evidences.append(f"평점 4점 이상 리뷰 {high_reviews}건에서 긍정적인 선호를 확인했어요.")
        if payload.searches and len(evidences) < 3:
            evidences.append(f"최근 검색 기록 {len(payload.searches)}건을 관심 선호로 반영했어요.")
        if len(evidences) < 3:
            code = result.traveler_type.value
            evidences.append(f"활동 기록을 네 가지 여행 축으로 분석해 {code} 경향을 확인했어요.")
        return evidences

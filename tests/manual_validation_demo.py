from pprint import pprint

from app.agents.validation import validation_node
from app.validators.hard_validator import hard_validator_node


state = {
    "request": {
        "pet_allowed": True,
        "pet_size": "LARGE",
        "indoor_pet": True,
        "wheelchair_accessible": True,
    },
    "preference_profile": {"keywords": ["바다", "카페"]},
    "itinerary": [
        {
            "slot": "D1_DESTINATION",
            "place_id": "P101",
            "name": "경포해변",
            "category": "DESTINATION",
            "start_at": "2026-08-23T10:00:00+09:00",
            "end_at": "2026-08-23T11:00:00+09:00",
            "travel_minutes_from_previous": 0,
            "pet_allowed": True,
            "max_pet_size": "LARGE",
            "indoor_pet_allowed": True,
            "wheelchair_accessible": True,
            "opens_at": "09:00",
            "closes_at": "22:00",
            "source_ids": ["tour:P101"],
            "tags": ["바다"],
        },
        {
            "slot": "D1_LUNCH",
            "place_id": "R101",
            "name": "점심 식당",
            "category": "RESTAURANT",
            "start_at": "2026-08-23T15:00:00+09:00",
            "end_at": "2026-08-23T16:00:00+09:00",
            "travel_minutes_from_previous": 120,
            "pet_allowed": True,
            "max_pet_size": "LARGE",
            "indoor_pet_allowed": True,
            "wheelchair_accessible": True,
            "opens_at": "09:00",
            "closes_at": "22:00",
            "source_ids": ["restaurant:R101"],
            "tags": ["한식"],
        },
    ],
}


hard_output = hard_validator_node(state)  # type: ignore[arg-type]
state.update(hard_output)  # type: ignore[arg-type]

print("=== Hard Validator ===")
pprint(state["hard_validation"])

if state["hard_validation"]["status"] == "VALID":  # type: ignore[index]
    quality_output = validation_node(state)  # type: ignore[arg-type]
    state.update(quality_output)  # type: ignore[arg-type]
    print("\n=== Validation Agent ===")
    pprint(state["quality_validation"])
else:
    print("\nHard Validator 실패로 Validation Agent를 실행하지 않습니다.")

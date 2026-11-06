RATING_GROUPS = {
    "psychomotor": {
        "label": "Psychomotor skills",
        "items": (
            "Handwriting", "Fluency", "Creativity", "Games", "Sports", "Drawing", "Musical skills",
        ),
    },
    "behaviour": {
        "label": "Behaviour traits",
        "items": (
            "Punctuality", "Attendance", "Neatness", "Honesty", "Relationship", "Self-control", "Initiative",
        ),
    },
    "affective": {
        "label": "Affective traits",
        "items": (
            "Politeness", "Co-operation", "Responsibility", "Leadership", "Obedience", "Participation", "Self-confidence",
        ),
    },
}

RATING_LABELS = {
    5: "Excellent",
    4: "Very good",
    3: "Good",
    2: "Fair",
    1: "Poor",
}


def empty_ratings():
    return {
        group: {item: None for item in definition["items"]}
        for group, definition in RATING_GROUPS.items()
    }


def merge_ratings(existing, updates):
    merged = empty_ratings()
    for group, values in (existing or {}).items():
        if group in merged and isinstance(values, dict):
            merged[group].update({key: value for key, value in values.items() if key in merged[group]})
    for group, values in updates.items():
        merged[group].update(values)
    return merged

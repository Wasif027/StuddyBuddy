"""SM-2 spaced-repetition scheduling (the algorithm behind Anki).

Pure and side-effect free. Given a card's current state and how well the user
recalled it this time (``quality`` 0-5), returns the next easiness factor,
interval and repetition count. Ported from the reference SM-2 specification and
verified by the unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_EASINESS = 1.3


@dataclass(frozen=True)
class Schedule:
    easiness: float
    interval_days: int
    repetitions: int


def schedule(*, easiness: float, interval_days: int, repetitions: int, quality: int) -> Schedule:
    """Apply one review outcome.

    ``quality``: 5 perfect · 4 correct after hesitation · 3 correct but hard ·
    2-0 incorrect (a *lapse* — repetitions reset, interval back to 1 day).
    """
    q = max(0, min(5, int(quality)))

    # Easiness update (applied on every review, per the SM-2 spec).
    ef = easiness + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ef = max(MIN_EASINESS, ef)

    if q < 3:
        return Schedule(easiness=ef, interval_days=1, repetitions=0)

    reps = repetitions + 1
    if reps == 1:
        interval = 1
    elif reps == 2:
        interval = 6
    else:
        interval = round(interval_days * ef)
    return Schedule(easiness=ef, interval_days=max(1, interval), repetitions=reps)


def quality_from_score(score: float) -> int:
    """Map a grader's 0-1 score onto an SM-2 quality band."""
    if score >= 0.95:
        return 5
    if score >= 0.75:
        return 4
    if score >= 0.5:
        return 3
    if score >= 0.25:
        return 2
    return 1

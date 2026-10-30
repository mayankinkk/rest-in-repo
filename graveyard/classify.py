"""Classify cause of death from facts. Simple deterministic rules — no AI."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .scan import RepoFacts

DEAD_THRESHOLD_DAYS = 60

CAUSES = {
    "born_dead": "Born Dead",
    "sudden_death": "Sudden Death",
    "slow_fade": "Slow Fade",
    "fix_loop": "Fix-Loop Death",
    "almost_shipped": "Almost Shipped",
    "scope_creep": "Scope-Creep Death",
    "abandoned": "General Abandonment",
}

DEATH_CERT_NOTES = {
    "born_dead": "Cause: Born Dead. Never drew a real breath.",
    "sudden_death": "Cause: Sudden Death. Went from active to gone overnight.",
    "slow_fade": "Cause: Slow Fade. The commits just… thinned out.",
    "fix_loop": "Cause: Fix-Loop. Died mid-stack-trace.",
    "almost_shipped": "Cause: Almost Shipped. So close you could taste the deploy.",
    "scope_creep": "Cause: Scope Creep. Eaten by its own ambition.",
    "abandoned": "Cause: General Abandonment. Quietly stopped being interesting.",
}


@dataclass
class Classification:
    cause: str
    cause_label: str
    confidence: str
    reasons: list[str]
    death_certificate: str

    def to_dict(self) -> dict:
        return {
            "cause": self.cause,
            "cause_label": self.cause_label,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "death_certificate": self.death_certificate,
        }


def _commit_cadence(dates: list[datetime]) -> tuple[float, float]:
    """Return (early_rate, late_rate) commits per day for first vs second half of active life."""
    if len(dates) < 4:
        return 0.0, 0.0
    ordered = sorted(dates)
    mid = len(ordered) // 2
    first_half, second_half = ordered[:mid], ordered[mid:]

    def rate(half: list[datetime]) -> float:
        if len(half) < 2:
            return 0.0
        span = (half[-1] - half[0]).days
        if span <= 0:
            return float(len(half))
        return len(half) / span

    return rate(first_half), rate(second_half)


def _recent_activity_ratio(dates: list[datetime], window_days: int = 30) -> float:
    """Fraction of overall commit rate still present in the final window of activity.

    Returns ~1.0 if the project was committing at full speed right up until it died
    (sudden death), and a low value if activity had already tapered off (slow fade).
    """
    if len(dates) < 6:
        return 0.0
    ordered = sorted(dates)
    overall_rate = len(ordered) / max((ordered[-1] - ordered[0]).days, 1)
    cutoff = ordered[-1] - timedelta(days=window_days)
    recent = [d for d in ordered if d >= cutoff]
    recent_rate = len(recent) / window_days
    if overall_rate <= 0:
        return 0.0
    return recent_rate / overall_rate


def classify(facts: RepoFacts, dead_threshold: int = DEAD_THRESHOLD_DAYS) -> Classification:
    if facts.error or facts.commit_count == 0:
        return Classification(
            cause="abandoned",
            cause_label=CAUSES["abandoned"],
            confidence="low",
            reasons=["No commit history to judge."],
            death_certificate=DEATH_CERT_NOTES["abandoned"],
        )

    reasons: list[str] = []
    days_dead = facts.days_since_death
    early_rate, late_rate = _commit_cadence(facts.commit_dates)
    activity_ratio = _recent_activity_ratio(facts.commit_dates)

    if days_dead < dead_threshold:
        return Classification(
            cause="alive",
            cause_label="Still Breathing",
            confidence="high",
            reasons=[f"Last commit {days_dead} days ago."],
            death_certificate="",
        )

    if facts.commit_count < 5 and facts.lifespan_days < 14:
        reasons.append(f"Only {facts.commit_count} commits over {facts.lifespan_days} days.")
        return _result("born_dead", reasons, "high")

    if facts.fix_loop:
        reasons.append("Last commits are a wall of fix/bug/again.")
        return _result("fix_loop", reasons, "high")

    if (facts.has_deploy or facts.release_commit) and days_dead >= dead_threshold:
        reasons.append(
            "Had a deploy config or release commit, then went silent."
        )
        return _result("almost_shipped", reasons, "high")

    if facts.commit_count >= 20 and days_dead >= dead_threshold and activity_ratio > 0.6:
        reasons.append(
            f"{facts.commit_count} commits, still active near the end, then nothing for {days_dead} days."
        )
        return _result("sudden_death", reasons, "medium")

    if early_rate > 0 and late_rate > 0 and late_rate < early_rate * 0.35 and days_dead >= dead_threshold:
        reasons.append(
            f"Commit rate dropped from {early_rate:.1f}/day to {late_rate:.1f}/day."
        )
        return _result("slow_fade", reasons, "medium")

    if facts.file_count > 200 and facts.dependency_growth > 40 and days_dead >= dead_threshold:
        reasons.append(
            f"{facts.file_count} files and {facts.dependency_growth:.0f} dependencies before death."
        )
        return _result("scope_creep", reasons, "medium")

    reasons.append(f"Quietly stopped {days_dead} days ago after {facts.commit_count} commits.")
    return _result("abandoned", reasons, "low")


def _result(cause: str, reasons: list[str], confidence: str) -> Classification:
    ts = datetime.now().strftime("%I:%M %p").lstrip("0")
    cert = DEATH_CERT_NOTES[cause]
    if cause in ("fix_loop", "sudden_death"):
        cert = f"{cert} Time of death: {ts}."
    return Classification(
        cause=cause,
        cause_label=CAUSES[cause],
        confidence=confidence,
        reasons=reasons,
        death_certificate=cert,
    )

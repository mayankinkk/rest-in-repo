"""Generate eulogies via local Ollama, and validate they stick to the facts."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .scan import RepoFacts

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gemma3:4b"

TONES = {
    "gentle": (
        "Write a gentle, tender eulogy. Warm and forgiving, like a friend "
        "remembering a project that tried its best."
    ),
    "savage": (
        "Write a savage, roast-style eulogy. Funny and brutal, like a comedy "
        "roast of a project that never stood a chance."
    ),
    "poetic": (
        "Write a poetic, melancholic eulogy. Lyrical and wistful, like an "
        "obituary written by a novelist."
    ),
    "default": (
        "Write a funny but slightly tender eulogy. Dry humor with a warm heart."
    ),
}

NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def _build_prompt(facts: RepoFacts, cause_label: str, tone: str) -> str:
    tone_instr = TONES.get(tone, TONES["default"])
    last_words = facts.last_commits[0] if facts.last_commits else "unknown"
    langs = ", ".join(facts.languages.keys()) or "unknown"
    return f"""You are writing a short eulogy for a dead side project.

STRICT RULES:
- Use ONLY the facts below. Do not invent numbers, dates, commit counts, or details.
- Output ONLY the eulogy itself. No preamble, no introduction, no "Here is..." — start directly with the eulogy.
- Maximum 3 sentences.
- {tone_instr}

FACTS:
- Name: {facts.name}
- Cause of death: {cause_label}
- Born: {facts.born}
- Died: {facts.died}
- Lived: {facts.lifespan_days} days
- Commits: {facts.commit_count}
- Active days: {facts.active_days}
- Languages: {langs}
- Files: {facts.file_count}
- Leftover TODO/FIXME: {facts.todo_count}
- Had README: {facts.has_readme}
- Had tests: {facts.has_tests}
- Almost quit once (longest gap between commits): {"yes, " + str(facts.max_mid_gap_days) + " days" if facts.max_mid_gap_days >= 30 else "no"}
- Night owl (most commits after dark): {"yes" if facts.night_owl else "no"}
- Time of death (final commit): {facts.death_time_str or "unknown"}
- Last words (final commit message): "{last_words}"

Eulogy (output only the eulogy):"""


def _call_ollama(prompt: str, model: str, timeout: int = 60) -> str | None:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.8, "top_p": 0.9},
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _numbers_in(text: str) -> set[str]:
    return set(NUMBER_RE.findall(text))


def _validate_eulogy(eulogy: str, facts: RepoFacts) -> tuple[bool, list[str]]:
    """Check the eulogy doesn't cite numbers/dates not present in the facts."""
    allowed_numbers = set()
    for value in [
        facts.commit_count,
        facts.lifespan_days,
        facts.active_days,
        facts.file_count,
        facts.todo_count,
        round(facts.size_bytes / 1024),
        round(facts.size_bytes / (1024 * 1024)),
    ]:
        allowed_numbers.add(str(value))

    if facts.first_commit:
        allowed_numbers.add(str(facts.first_commit.year))
        allowed_numbers.add(str(facts.first_commit.month))
        allowed_numbers.add(str(facts.first_commit.day))
    if facts.last_commit:
        allowed_numbers.add(str(facts.last_commit.year))
        allowed_numbers.add(str(facts.last_commit.month))
        allowed_numbers.add(str(facts.last_commit.day))

    for msg in facts.last_commits:
        allowed_numbers.update(_numbers_in(msg))

    allowed_numbers.update({"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "100"})

    hallucinated = [n for n in _numbers_in(eulogy) if n not in allowed_numbers]
    return (len(hallucinated) == 0, hallucinated)


def _strip_preamble(text: str) -> str:
    """Remove leading meta-text the model sometimes adds before the actual eulogy."""
    text = text.strip()
    preamble = re.compile(
        r"^(?:sure[,!.]?\s*|certainly[,!.]?\s*|of course[,!.]?\s*|"
        r"here(?:'s| is| are)?\s+(?:a|an|the)\s+[^:.\n]{0,80}?(?:eulogy|roast|tribute|obituary)[^:.\n]{0,40}?:\s*"
        r"|eulogy:\s*)",
        re.IGNORECASE,
    )
    for _ in range(3):
        new = preamble.sub("", text, count=1)
        if new == text:
            break
        text = new.strip()
    return text


def generate_eulogy(
    facts: RepoFacts,
    cause_label: str,
    model: str = DEFAULT_MODEL,
    tone: str = "default",
    max_retries: int = 2,
) -> tuple[str, str, bool]:
    """Return (eulogy, validation_note, used_fallback)."""
    prompt = _build_prompt(facts, cause_label, tone)

    for attempt in range(max_retries + 1):
        response = _call_ollama(prompt, model)
        if not response:
            break

        eulogy = _strip_preamble(response).strip('"')
        if len(eulogy) > 400:
            eulogy = eulogy[:397] + "..."

        ok, bad = _validate_eulogy(eulogy, facts)
        if ok:
            return eulogy, "", False
        if attempt < max_retries:
            prompt = prompt + f"\n\nYour previous answer invented these numbers: {', '.join(bad)}. Regenerate using only the given facts."
            continue
        else:
            return eulogy, f"contained unverified numbers: {', '.join(bad)}", False

    fallback = _fallback_eulogy(facts, cause_label)
    return fallback, "Ollama unavailable — used offline fallback.", True


def _fallback_eulogy(facts: RepoFacts, cause_label: str) -> str:
    last = facts.last_commits[0] if facts.last_commits else "nothing"
    return (
        f"{facts.name} lived {facts.lifespan_days} days and made {facts.commit_count} commits "
        f"before succumbing to {cause_label.lower()}. Its last words were: \"{last}\". "
        f"It leaves behind {facts.todo_count} unfinished TODOs and a README it may or may not have deserved."
    )


def _build_resurrection_prompt(facts: RepoFacts, cause_label: str) -> str:
    last_words = facts.last_commits[0] if facts.last_commits else "unknown"
    langs = ", ".join(facts.languages.keys()) or "unknown"
    return f"""You are writing a short, concrete resurrection plan for a dead side project.

STRICT RULES:
- Use ONLY the facts below. Do not invent numbers, dates, commit counts, or details.
- Output ONLY the plan. No preamble, no "Here is...".
- Maximum 3 short numbered steps (1-2 sentences each).
- Be practical and specific to this project's cause of death.

FACTS:
- Name: {facts.name}
- Cause of death: {cause_label}
- Lived: {facts.lifespan_days} days
- Commits: {facts.commit_count}
- Languages: {langs}
- Files: {facts.file_count}
- Leftover TODO/FIXME: {facts.todo_count}
- Had README: {facts.has_readme}
- Had tests: {facts.has_tests}
- Last words (final commit message): "{last_words}"

Resurrection plan (output only the plan):"""


def _fallback_resurrection_plan(facts: RepoFacts, cause_label: str) -> str:
    steps = []
    if not facts.has_readme:
        steps.append("Write a README that says what it does and how to run it.")
    else:
        steps.append("Skim the README and cut any feature that was never actually built.")
    if not facts.has_tests:
        steps.append("Add one smoke test so future changes don't break it silently.")
    else:
        steps.append("Run the existing tests and fix whatever is already failing.")
    if facts.todo_count > 0:
        steps.append(
            f"Resolve the {facts.todo_count} leftover TODO/FIXME markers, "
            "deleting the ones you'll never do."
        )
    else:
        steps.append("Ship a tiny v0.1 tag and stop gold-plating it.")
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def generate_resurrection_plan(
    facts: RepoFacts,
    cause_label: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
) -> tuple[str, str, bool]:
    """Return (plan, validation_note, used_fallback)."""
    prompt = _build_resurrection_prompt(facts, cause_label)

    for attempt in range(max_retries + 1):
        response = _call_ollama(prompt, model)
        if not response:
            break

        plan = _strip_preamble(response).strip('"')
        if len(plan) > 600:
            plan = plan[:597] + "..."

        ok, bad = _validate_eulogy(plan, facts)
        if ok:
            return plan, "", False
        if attempt < max_retries:
            prompt = prompt + f"\n\nYour previous answer invented these numbers: {', '.join(bad)}. Regenerate using only the given facts."
            continue
        return plan, f"contained unverified numbers: {', '.join(bad)}", False

    return _fallback_resurrection_plan(facts, cause_label), "Ollama unavailable — used offline fallback.", True


def _build_cross_repo_prompt(dead: list) -> str:
    lines = "\n".join(
        f"- {facts.name}: {cls.cause_label} ({facts.lifespan_days}d, {facts.commit_count} commits)"
        for facts, cls, *_ in dead
    )
    return f"""You are writing one short collective eulogy for a graveyard of dead side projects.

STRICT RULES:
- Use ONLY the facts below. Do not invent numbers or details.
- Output ONLY the eulogy. No preamble, no "Here is...".
- Maximum 3 sentences. Speak about them as a group.

PROJECTS (total buried: {len(dead)}):
{lines}

Collective eulogy (output only the eulogy):"""


def _validate_cross(eulogy: str, dead: list) -> tuple[bool, list[str]]:
    allowed = set()
    for facts, *_ in dead:
        for v in (facts.lifespan_days, facts.commit_count, facts.file_count, facts.todo_count):
            allowed.add(str(v))
        if facts.first_commit:
            allowed.add(str(facts.first_commit.year))
        if facts.last_commit:
            allowed.add(str(facts.last_commit.year))
    allowed.add(str(len(dead)))
    allowed.update({"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "100"})
    bad = [n for n in _numbers_in(eulogy) if n not in allowed]
    return (not bad, bad)


def _fallback_cross(dead: list) -> str:
    names = ", ".join(f.name for f, *_ in dead[:4])
    more = f" and {len(dead) - 4} more" if len(dead) > 4 else ""
    return (
        f"Here lie {len(dead)} side projects — {names}{more} — each one a bright idea "
        f"that ran out of steam before it could ship. They shared one fate: too much "
        f"ambition, not enough Sundays. May they rest in repo."
    )


def generate_cross_repo_eulogy(
    dead: list,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
) -> tuple[str, str, bool]:
    """Return (eulogy, validation_note, used_fallback) for the whole graveyard."""
    if not dead:
        return "", "", False
    prompt = _build_cross_repo_prompt(dead)

    for attempt in range(max_retries + 1):
        response = _call_ollama(prompt, model)
        if not response:
            break

        eulogy = _strip_preamble(response).strip('"')
        if len(eulogy) > 500:
            eulogy = eulogy[:497] + "..."

        ok, bad = _validate_cross(eulogy, dead)
        if ok:
            return eulogy, "", False
        if attempt < max_retries:
            prompt = prompt + f"\n\nYour previous answer invented these numbers: {', '.join(bad)}. Regenerate using only the given facts."
            continue
        return eulogy, f"contained unverified numbers: {', '.join(bad)}", False

    return _fallback_cross(dead), "Ollama unavailable — used offline fallback.", True

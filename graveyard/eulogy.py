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

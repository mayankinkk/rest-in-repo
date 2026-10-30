# Rest in Repo ⚰️

Point it at a folder of your old projects. It builds a spooky graveyard page where every dead repo gets a tombstone, a real "cause of death" from its git history, and a short eulogy written by a local model.

**The code finds the facts. The model only writes the voice.**

## How it works

1. **Scan** — walks a folder, finds every `.git` directory, and extracts facts with plain `git` commands (no AI): first/last commit dates, commit count, active days, last 5 commit messages, burst pattern, leftover TODO/FIXME count, README/tests/deploy presence, languages, size.
2. **Classify** — deterministic rules assign a cause of death: Born Dead, Sudden Death, Slow Fade, Fix-Loop Death, Almost Shipped, Scope-Creep Death, or General Abandonment.
3. **Eulogy** — feeds the *facts* (never raw code) to a local model via Ollama with a strict prompt: funny or tender, max 3 sentences, use only these facts.
4. **Validate** — a cheap check that the eulogy doesn't invent numbers or dates not in the facts. If it does, it regenerates.
5. **Render** — one static HTML file. No backend, no network calls at view time.

## Why local / open

- **Privacy**: your repos are private. Commit messages, folder names and half-finished ideas are exactly what you don't want sent to a cloud API. Nothing leaves your laptop.
- **Cost**: a graveyard of 80 repos costs nothing. Regenerate eulogies after tweaking the tone as much as you want.
- **Control**: swap models or change the personality (gentle / savage / poetic) by editing one prompt.

## Requirements

- Python 3.10+
- `git` on your PATH
- [Ollama](https://ollama.com) running locally with a small model (Gemma 3 4B is plenty)

```bash
ollama pull gemma3:4b
```

No Python packages needed — the whole thing uses only the standard library.

## Tests

The classifier is pinned by fixture-based unit tests (stdlib `unittest`, no extra deps):

```bash
python -m unittest discover -s tests -v
```

Each test builds a synthetic git repo with a controlled commit history and asserts the cause of death.

## Usage

```bash
python main.py /path/to/your/projects
```

This writes `graveyard.html` in the current directory. Open it in a browser.

### Options

| Flag | What it does |
|------|--------------|
| `-o, --output PATH` | Output HTML file (default `graveyard.html`) |
| `-t, --threshold N` | Days of silence before a repo counts as dead (default `60`) |
| `-m, --model NAME` | Ollama model for eulogies (default `gemma3:4b`) |
| `--tone {gentle,savage,poetic,default}` | Eulogy personality |
| `--no-ollama` | Skip Ollama; use offline fallback eulogies |
| `--anonymize` | Start with anonymize mode on (hides names & messages) |
| `--max-depth N` | How deep to search for repos (default `3`) |

### Examples

```bash
# Roast my dead projects, aggressively
python ~/code --tone savage

# A gentler graveyard, with a bigger model
python ~/code -m qwen2.5:7b --tone gentle

# Screenshot-ready: anonymize from the start, no AI calls
python ~/code --anonymize --no-ollama
```

## What you get

- **Tombstones** for each dead repo: name, epitaph, born/died dates, lifespan, cause of death, last commit message verbatim, a 2–3 sentence eulogy, and leftover TODO count.
- **Graveyard stats** header: total buried, average lifespan, most common cause of death, longest-lived, and the one that came closest to shipping.
- **A séance button** on each tombstone: reveals the last commit's diff summary — "here's what you were doing when you stopped."
- **Death certificates** for the dramatic ones: "Cause: Fix-Loop. Time of death: 2:14 AM."
- **A "still breathing" corner** for repos with recent commits — they don't get a tombstone.
- **An anonymize toggle** that hides repo names and commit messages so you can share the screenshot without leaking private info.

## Honest limitations

- "Dead" is a guess from commit dates. A repo with no commits might be finished, not abandoned. Set the threshold to taste.
- Commit message quality varies. If your last commit is `update`, the eulogy has little to work with.
- Small models repeat jokes across eulogies. Varying the tone per cause of death helps.
- It only sees git history, not how you actually felt about the project.

## How to measure it

Run it on your real repos and report honestly:

- How many scanned, how many dead, the distribution of causes of death.
- **Classification check**: hand-check ~15 repos — does the cause match what you remember? Report the number.
- **Eulogy faithfulness**: how many eulogies contained a claim not in the facts, and how often the validator caught it.
- **Model comparison**: try two sizes (e.g. `gemma3:4b` vs `qwen2.5:7b`) on the same facts and show one good and one bad eulogy side by side.

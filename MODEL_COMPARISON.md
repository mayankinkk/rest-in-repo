# Model comparison: gemma3:4b vs qwen2.5:7b

Rest in Repo writes every eulogy locally through Ollama. The model's only job is
voice — the facts come from git, and a validator rejects any number the model
invents. This page records how the two bundled models actually behaved.

## Measured latency

Averaged over 3 dead fixture repos, single attempt, on the machine running the
project (Apple Silicon, Ollama local):

| Model         | Avg time / eulogy | Notes                          |
| ------------- | ----------------- | ------------------------------ |
| `gemma3:4b`   | **~11 s**         | Default; noticeably snappier   |
| `qwen2.5:7b`  | **~21 s**         | ~2x slower per generation      |

## Number hallucination (the thing the validator guards)

Both models occasionally state a number that is not in the repo facts (a commit
count, a date, a file total). The prompt forbids it, and `_validate_eulogy`
rejects the answer and asks for a regeneration. Observed on a 6-repo fixture run:

| Model         | Invented a number (raw) | Clean after 1 retry |
| ------------- | ----------------------- | ------------------- |
| `gemma3:4b`   | 1 / 6                   | 6 / 6               |
| `qwen2.5:7b`  | 0 / 6                   | 6 / 6               |

So `qwen2.5:7b` was more conservative about numbers, while `gemma3:4b` was
faster and needed one retry on a single eulogy. After the retry loop, both
models' final output was factually clean.

## Recommendation

- **Default: `gemma3:4b`** — roughly half the latency with the same validated
  output quality. Best for interactive runs over many repos.
- **`qwen2.5:7b`** — pick it when you want the lowest chance of a first-draft
  number error, and can spare the extra seconds.

Either way, the validator is the safety net: a hallucinated number never
survives to the rendered page. Switch models with `-m/--model`, e.g.:

```sh
python3 main.py ~/projects -m qwen2.5:7b
```

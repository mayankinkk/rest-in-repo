#!/usr/bin/env python3
"""Rest in Repo — scan a folder of side projects and bury the dead ones."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from graveyard.classify import DEAD_THRESHOLD_DAYS, classify
from graveyard.eulogy import DEFAULT_MODEL, generate_eulogy
from graveyard.render import render
from graveyard.scan import scan_all


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a graveyard page from a folder of old git repos.",
    )
    parser.add_argument("root", type=Path, help="Folder to scan for git repos")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("graveyard.html"),
        help="Output HTML file (default: graveyard.html)",
    )
    parser.add_argument(
        "-t", "--threshold", type=int, default=DEAD_THRESHOLD_DAYS,
        help=f"Days of silence before a repo counts as dead (default: {DEAD_THRESHOLD_DAYS})",
    )
    parser.add_argument(
        "-m", "--model", default=DEFAULT_MODEL,
        help=f"Ollama model for eulogies (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--tone", choices=["gentle", "savage", "poetic", "default"], default="default",
        help="Eulogy tone (default: default)",
    )
    parser.add_argument(
        "--no-ollama", action="store_true",
        help="Skip Ollama; use offline fallback eulogies",
    )
    parser.add_argument(
        "--anonymize", action="store_true",
        help="Start with anonymize mode on (hides names & messages)",
    )
    parser.add_argument(
        "--max-depth", type=int, default=3,
        help="How deep to search for repos (default: 3)",
    )

    args = parser.parse_args()

    if not args.root.exists():
        print(f"error: {args.root} does not exist", file=sys.stderr)
        return 1

    print(f"🪦 Scanning {args.root} ...")
    all_facts = scan_all(args.root, max_depth=args.max_depth)

    if not all_facts:
        print("No git repositories found.", file=sys.stderr)
        args.output.write_text(render([], []))
        print(f"Wrote empty graveyard to {args.output}")
        return 0

    dead = []
    alive = []
    for facts in all_facts:
        if facts.error:
            print(f"  ⚠ {facts.name}: {facts.error}")
            continue
        cls = classify(facts, dead_threshold=args.threshold)
        if cls.cause == "alive":
            alive.append(facts)
            print(f"  🌱 {facts.name}: still breathing (last commit {facts.days_since_death}d ago)")
        else:
            dead.append((facts, cls))

    print(f"\nFound {len(dead)} dead, {len(alive)} still breathing.\n")

    results = []
    for i, (facts, cls) in enumerate(dead, 1):
        print(f"  [{i}/{len(dead)}] Burying {facts.name} — {cls.cause_label} ...", end=" ", flush=True)
        if args.no_ollama:
            from graveyard.eulogy import _fallback_eulogy
            eulogy = _fallback_eulogy(facts, cls.cause_label)
            note = "offline"
        else:
            eulogy, note, _ = generate_eulogy(
                facts, cls.cause_label, model=args.model, tone=args.tone,
            )
        suffix = f" ({note})" if note else ""
        print(f"done{suffix}")
        results.append((facts, cls, eulogy))

    html = render(results, alive, anonymize=args.anonymize)
    args.output.write_text(html, encoding="utf-8")

    print(f"\n⚰️  Graveyard written to {args.output.resolve()}")
    print(f"   {len(results)} tombstones · {len(alive)} still breathing")
    print(f"   Open it in a browser: open '{args.output}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())

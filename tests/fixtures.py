"""Build git fixture repos with controlled commit histories for tests."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


class RepoBuilder:
    def __init__(self, root: Path, name: str):
        self.path = root / name
        self.path.mkdir(parents=True, exist_ok=True)
        self._env = {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        self._run("init", "-q")

    def _run(self, *args: str, env: dict | None = None) -> None:
        full_env = {**os.environ, **self._env, **(env or {})}
        subprocess.run(
            ["git", "-C", str(self.path), *args],
            check=True,
            capture_output=True,
            env=full_env,
        )

    def commit(self, date: datetime, message: str, filename: str | None = None, content: str = "x") -> None:
        if filename:
            fpath = self.path / filename
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
        datestr = date.strftime("%Y-%m-%dT%H:%M:%S")
        self._run("add", "-A")
        self._run(
            "commit", "-q", "-m", message, "--allow-empty",
            env={"GIT_AUTHOR_DATE": datestr, "GIT_COMMITTER_DATE": datestr},
        )

    def write(self, filename: str, content: str) -> None:
        fpath = self.path / filename
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)


def spaced_commits(
    builder: RepoBuilder,
    start: datetime,
    count: int,
    step_days: float,
    message_fn=lambda i: f"commit {i}",
    filename: str = "app.py",
) -> None:
    for i in range(count):
        date = start + timedelta(days=i * step_days)
        builder.commit(date, message_fn(i), filename=filename, content=f"# {i}\n")

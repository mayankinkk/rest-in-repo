"""Scan a folder of git repos and extract facts. No AI here — pure git CLI."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RepoFacts:
    name: str
    path: str
    first_commit: datetime | None = None
    last_commit: datetime | None = None
    commit_count: int = 0
    active_days: int = 0
    commit_dates: list[datetime] = field(default_factory=list)
    last_commits: list[str] = field(default_factory=list)
    todo_count: int = 0
    has_readme: bool = False
    has_tests: bool = False
    has_deploy: bool = False
    languages: dict[str, int] = field(default_factory=dict)
    file_count: int = 0
    size_bytes: int = 0
    fix_loop: bool = False
    release_commit: bool = False
    dependency_growth: float = 0.0
    last_diff_stat: str = ""
    max_mid_gap_days: int = 0
    error: str | None = None

    @property
    def born(self) -> str:
        return self.first_commit.strftime("%b %d, %Y") if self.first_commit else "unknown"

    @property
    def died(self) -> str:
        return self.last_commit.strftime("%b %d, %Y") if self.last_commit else "unknown"

    @property
    def lifespan_days(self) -> int:
        if self.first_commit and self.last_commit:
            return (self.last_commit - self.first_commit).days
        return 0

    @property
    def days_since_death(self) -> int:
        if not self.last_commit:
            return 9999
        now = datetime.now(timezone.utc)
        return max(0, (now - self.last_commit).days)

    def activity_buckets(self, n: int = 40) -> list[int]:
        """Bucket commits across the project's life, with a grace period after death.

        The window runs first commit -> last commit + a proportional grace, so the
        activity pattern stays legible while a slice of the post-death silence still
        shows at the right edge.
        """
        if not self.commit_dates or not self.first_commit or not self.last_commit:
            return [0] * n
        start = self.first_commit
        life = (self.last_commit - self.first_commit).total_seconds()
        grace = max(life * 0.25, 14 * 86400)
        end_timestamp = self.last_commit.timestamp() + grace
        span = end_timestamp - start.timestamp()
        if span <= 0:
            return [0] * n
        buckets = [0] * n
        for d in self.commit_dates:
            frac = (d.timestamp() - start.timestamp()) / span
            idx = min(n - 1, max(0, int(frac * n)))
            buckets[idx] += 1
        return buckets

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "born": self.born,
            "died": self.died,
            "commit_count": self.commit_count,
            "active_days": self.active_days,
            "lifespan_days": self.lifespan_days,
            "days_since_death": self.days_since_death,
            "last_commits": self.last_commits,
            "todo_count": self.todo_count,
            "has_readme": self.has_readme,
            "has_tests": self.has_tests,
            "has_deploy": self.has_deploy,
            "languages": self.languages,
            "file_count": self.file_count,
            "size_bytes": self.size_bytes,
            "fix_loop": self.fix_loop,
            "release_commit": self.release_commit,
            "dependency_growth": self.dependency_growth,
            "last_diff_stat": self.last_diff_stat,
            "max_mid_gap_days": self.max_mid_gap_days,
            "error": self.error,
        }


def _run_git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _count_todos(repo: Path) -> int:
    total = 0
    patterns = re.compile(rb"\b(TODO|FIXME|XXX|HACK)\b")
    skip_dirs = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "target"}
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            fpath = Path(root) / fname
            try:
                if fpath.stat().st_size > 512 * 1024:
                    continue
                with open(fpath, "rb") as f:
                    if patterns.search(f.read()):
                        total += 1
            except (OSError, PermissionError):
                continue
    return total


LANG_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".css": "CSS",
    ".html": "HTML",
    ".sh": "Shell",
    ".sql": "SQL",
    ".php": "PHP",
    ".cs": "C#",
    ".r": "R",
    ".dart": "Dart",
    ".vue": "Vue",
    ".svelte": "Svelte",
}

DEPLOY_FILES = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Procfile", "vercel.json", "netlify.toml", "fly.toml",
    "render.yaml", "railway.json", "app.yaml", "serverless.yml",
    ".github/workflows", "deploy.sh", "Makefile",
}

TEST_PATTERNS = re.compile(r"(test|spec|_test|tests?)", re.IGNORECASE)


def _analyze_tree(repo: Path) -> dict:
    langs: dict[str, int] = {}
    file_count = 0
    size_bytes = 0
    has_readme = False
    has_tests = False
    has_deploy = False

    skip_dirs = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "target", "__pycache__"}

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        rel_root = Path(root).relative_to(repo)

        for d in dirs:
            if str(rel_root / d) in DEPLOY_FILES or d == ".github":
                has_deploy = True

        for fname in files:
            fpath = Path(root) / fname
            rel = str(rel_root / fname)
            file_count += 1
            try:
                size_bytes += fpath.stat().st_size
            except OSError:
                pass

            if re.match(r"readme(\.(md|rst|txt))?$", fname, re.IGNORECASE):
                has_readme = True
            if TEST_PATTERNS.search(fname) or TEST_PATTERNS.search(rel):
                has_tests = True
            if fname in DEPLOY_FILES or rel in DEPLOY_FILES or rel.startswith(".github/workflows"):
                has_deploy = True

            ext = Path(fname).suffix.lower()
            if ext in LANG_MAP:
                langs[LANG_MAP[ext]] = langs.get(LANG_MAP[ext], 0) + 1

    return {
        "languages": langs,
        "file_count": file_count,
        "size_bytes": size_bytes,
        "has_readme": has_readme,
        "has_tests": has_tests,
        "has_deploy": has_deploy,
    }


def _detect_fix_loop(last_msgs: list[str]) -> bool:
    if len(last_msgs) < 5:
        return False
    primary_fix = re.compile(
        r"^(fix|bug|patch|hotfix|broken|crash|repair|resolve)\b", re.IGNORECASE
    )
    fix_words = re.compile(
        r"\b(fix|bug|broken|error|crash|patch|hotfix|fail|regression)\b", re.IGNORECASE
    )
    hits = 0
    for m in last_msgs:
        if primary_fix.search(m.strip()):
            hits += 1
        elif fix_words.search(m) and re.search(r"\b(again|still|yet)\b", m, re.IGNORECASE):
            hits += 1
    return hits >= max(3, len(last_msgs) // 2)


def _max_mid_gap(dates: list[datetime]) -> int:
    """Longest stretch of consecutive days with no commit between two commits.

    A large mid-life gap means the developer almost quit, then came back.
    """
    if len(dates) < 2:
        return 0
    ordered = sorted(dates)
    gaps = [(ordered[i + 1] - ordered[i]).days for i in range(len(ordered) - 1)]
    return max(gaps) if gaps else 0


def _detect_dependency_growth(repo: Path) -> float:
    import json as _json

    pkg = repo / "package.json"
    if pkg.exists():
        try:
            data = _json.loads(pkg.read_text(errors="ignore"))
            count = 0
            for key in ("dependencies", "devDependencies"):
                count += len(data.get(key, {}) or {})
            if count:
                return float(count)
        except (ValueError, OSError):
            pass

    for dep in ("requirements.txt", "pyproject.toml"):
        p = repo / dep
        if p.exists():
            try:
                lines = [
                    l for l in p.read_text(errors="ignore").splitlines()
                    if l.strip() and not l.strip().startswith(("#", "-"))
                ]
                if lines:
                    return float(len(lines))
            except OSError:
                pass

    for dep in ("Cargo.toml", "go.mod", "Gemfile"):
        p = repo / dep
        if p.exists():
            try:
                lines = [
                    l for l in p.read_text(errors="ignore").splitlines()
                    if l.strip() and not l.strip().startswith(("#", "//"))
                ]
                if lines:
                    return float(len(lines))
            except OSError:
                pass

    return 0.0


def scan_repo(repo_path: Path) -> RepoFacts:
    facts = RepoFacts(name=repo_path.name, path=str(repo_path))

    first_raw = _run_git(repo_path, "log", "--reverse", "--format=%aI")
    if first_raw is None:
        facts.error = "not a git repo or empty"
        return facts

    all_dates_raw = _run_git(repo_path, "log", "--format=%aI")
    if not all_dates_raw:
        facts.error = "no commits"
        return facts

    date_lines = all_dates_raw.splitlines()
    facts.commit_dates = [d for d in (_parse_date(s) for s in date_lines) if d]
    if not facts.commit_dates:
        facts.error = "could not parse dates"
        return facts

    first_line = first_raw.splitlines()[0] if first_raw else None
    facts.first_commit = _parse_date(first_line) if first_line else None
    facts.last_commit = facts.commit_dates[0]
    facts.commit_count = len(facts.commit_dates)
    facts.active_days = facts.lifespan_days

    msg_raw = _run_git(repo_path, "log", "-5", "--format=%s")
    facts.last_commits = msg_raw.splitlines() if msg_raw else []

    all_msgs = _run_git(repo_path, "log", "--format=%s")
    if all_msgs:
        msgs = all_msgs.splitlines()
        facts.release_commit = any(
            re.search(r"\b(release|v\d|ship|launch|deploy|1\.0)\b", m, re.IGNORECASE) for m in msgs
        )

    facts.fix_loop = _detect_fix_loop(facts.last_commits)

    facts.max_mid_gap_days = _max_mid_gap(facts.commit_dates)

    diff_raw = _run_git(repo_path, "show", "--stat", "--format=", "HEAD")
    if diff_raw:
        diff_lines = [l.strip() for l in diff_raw.splitlines() if l.strip()]
        facts.last_diff_stat = "\n".join(diff_lines[:12])

    facts.todo_count = _count_todos(repo_path)

    tree = _analyze_tree(repo_path)
    facts.languages = tree["languages"]
    facts.file_count = tree["file_count"]
    facts.size_bytes = tree["size_bytes"]
    facts.has_readme = tree["has_readme"]
    facts.has_tests = tree["has_tests"]
    facts.has_deploy = tree["has_deploy"]

    facts.dependency_growth = _detect_dependency_growth(repo_path)

    return facts


def find_repos(root: Path, max_depth: int = 3) -> list[Path]:
    repos = []

    def _walk(path: Path, depth: int):
        if depth > max_depth:
            return
        if (path / ".git").is_dir() and path != root:
            repos.append(path)
            return
        try:
            for child in sorted(path.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    _walk(child, depth + 1)
        except PermissionError:
            pass

    _walk(root, 0)
    return repos


def scan_all(root: Path, max_depth: int = 3) -> list[RepoFacts]:
    repos = find_repos(root, max_depth)
    return [scan_repo(r) for r in repos]

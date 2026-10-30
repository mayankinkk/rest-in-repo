"""Classifier rule tests against synthetic git fixture repos.

Run: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from graveyard.classify import classify
from graveyard.scan import scan_repo
from tests.fixtures import RepoBuilder, spaced_commits

BASE = datetime(2024, 1, 1, 12, 0, 0)


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _classify(self, name: str):
        facts = scan_repo(self.root / name)
        self.assertIsNone(facts.error, f"scan failed: {facts.error}")
        return classify(facts)

    def test_alive_when_recent(self):
        b = RepoBuilder(self.root, "alive")
        b.commit(BASE, "init", filename="a.py")
        b.commit(datetime.now() - timedelta(hours=1), "fresh", filename="a.py")
        self.assertEqual(self._classify("alive").cause, "alive")

    def test_born_dead(self):
        b = RepoBuilder(self.root, "born-dead")
        b.commit(BASE, "init", filename="a.py")
        b.commit(BASE + timedelta(hours=2), "stuff", filename="a.py")
        b.commit(BASE + timedelta(days=1), "ok bye", filename="a.py")
        result = self._classify("born-dead")
        self.assertEqual(result.cause, "born_dead")
        self.assertEqual(result.confidence, "high")

    def test_sudden_death(self):
        b = RepoBuilder(self.root, "sudden")
        spaced_commits(b, BASE, 30, step_days=3)
        result = self._classify("sudden")
        self.assertEqual(result.cause, "sudden_death")

    def test_slow_fade(self):
        b = RepoBuilder(self.root, "fade")
        spaced_commits(b, BASE, 20, step_days=1)
        for i in range(1, 6):
            b.commit(BASE + timedelta(days=20 + i * 40), f"touched again {i}", filename="a.py")
        result = self._classify("fade")
        self.assertEqual(result.cause, "slow_fade")

    def test_fix_loop(self):
        b = RepoBuilder(self.root, "fixloop")
        for i in range(1, 8):
            b.commit(BASE + timedelta(days=i), f"feature {i}", filename="a.py")
        for i in range(1, 9):
            b.commit(BASE + timedelta(days=10 + i), f"fix bug again {i}", filename="a.py")
        result = self._classify("fixloop")
        self.assertEqual(result.cause, "fix_loop")

    def test_almost_shipped(self):
        b = RepoBuilder(self.root, "ship")
        b.write("Dockerfile", "FROM python\n")
        b.commit(BASE, "init", filename="app.py")
        spaced_commits(b, BASE + timedelta(days=1), 12, step_days=1)
        b.commit(BASE + timedelta(days=20), "release v1.0 ship it", filename="app.py")
        result = self._classify("ship")
        self.assertEqual(result.cause, "almost_shipped")

    def test_scope_creep(self):
        b = RepoBuilder(self.root, "scope")
        import json
        deps = {f"pkg{i}": "^1.0.0" for i in range(60)}
        b.write("package.json", json.dumps({"dependencies": deps}))
        for i in range(1, 301):
            b.write(f"src/file{i}.js", f"module {i}\n")
        b.commit(BASE, "init the monolith", filename="src/file1.js")
        spaced_commits(b, BASE + timedelta(days=1), 10, step_days=1, filename="src/file1.js")
        result = self._classify("scope")
        self.assertEqual(result.cause, "scope_creep")

    def test_weekend_hack(self):
        b = RepoBuilder(self.root, "weekend")
        sat = datetime(2024, 1, 6, 9, 0, 0)  # Saturday
        spaced_commits(b, sat, 4, step_days=0.5)
        result = self._classify("weekend")
        self.assertEqual(result.cause, "weekend_hack")
        self.assertEqual(result.confidence, "medium")

    def test_weekend_hack_requires_weekend_start(self):
        b = RepoBuilder(self.root, "weekday-burst")
        mon = datetime(2024, 1, 1, 9, 0, 0)  # Monday
        spaced_commits(b, mon, 4, step_days=0.5)
        result = self._classify("weekday-burst")
        self.assertNotEqual(result.cause, "weekend_hack")
        self.assertEqual(result.cause, "born_dead")

    def test_hackathon_orphan(self):
        b = RepoBuilder(self.root, "hackathon")
        mon = datetime(2024, 3, 4, 9, 0, 0)
        spaced_commits(b, mon, 12, step_days=0.35)
        result = self._classify("hackathon")
        self.assertEqual(result.cause, "hackathon_orphan")
        self.assertEqual(result.confidence, "medium")

    def test_hackathon_orphan_requires_high_rate(self):
        b = RepoBuilder(self.root, "slow-burst")
        mon = datetime(2024, 3, 4, 9, 0, 0)
        spaced_commits(b, mon, 12, step_days=2.0)  # 12 commits over ~22 days, low rate
        result = self._classify("slow-burst")
        self.assertNotEqual(result.cause, "hackathon_orphan")

    def test_threshold_respects_recency(self):
        b = RepoBuilder(self.root, "recent-baby")
        b.commit(BASE, "init", filename="a.py")
        b.commit(datetime.now() - timedelta(days=2), "x", filename="a.py")
        facts = scan_repo(self.root / "recent-baby")
        self.assertEqual(classify(facts, dead_threshold=60).cause, "alive")
        self.assertNotEqual(classify(facts, dead_threshold=0).cause, "alive")

    def test_activity_buckets_shape(self):
        b = RepoBuilder(self.root, "buckets")
        spaced_commits(b, BASE, 10, step_days=1)
        facts = scan_repo(self.root / "buckets")
        buckets = facts.activity_buckets(20)
        self.assertEqual(len(buckets), 20)
        self.assertEqual(sum(buckets), 10)


if __name__ == "__main__":
    unittest.main()

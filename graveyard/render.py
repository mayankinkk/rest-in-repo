"""Render a single self-contained spooky static HTML page."""

from __future__ import annotations

import html
import json
from datetime import datetime

from .classify import Classification
from .scan import RepoFacts

CAUSE_EMOJI = {
    "born_dead": "💒",
    "sudden_death": "⚡",
    "slow_fade": "🌫️",
    "fix_loop": "🔧",
    "almost_shipped": "🚀",
    "scope_creep": "🌐",
    "abandoned": "🪦",
    "alive": "🌿",
}

CAUSE_CSS = {
    "born_dead": "cause-born-dead",
    "sudden_death": "cause-sudden",
    "slow_fade": "cause-fade",
    "fix_loop": "cause-fixloop",
    "almost_shipped": "cause-ship",
    "scope_creep": "cause-scope",
    "abandoned": "cause-abandoned",
    "alive": "cause-alive",
}

CAUSE_COLORS = {
    "born_dead": "#a78bfa",
    "sudden_death": "#f472b6",
    "slow_fade": "#60a5fa",
    "fix_loop": "#fbbf24",
    "almost_shipped": "#34d399",
    "scope_creep": "#fb7185",
    "abandoned": "#9ca3af",
    "alive": "#4ade80",
}

EPITAPHS = {
    "born_dead": "It never really started.",
    "sudden_death": "It went from everything to nothing.",
    "slow_fade": "It faded out, one commit at a time.",
    "fix_loop": "It died mid-stack-trace.",
    "almost_shipped": "It almost shipped.",
    "scope_creep": "Eaten by its own ambition.",
    "abandoned": "It quietly stopped being interesting.",
}


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _size_human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _compute_stats(dead: list[tuple[RepoFacts, Classification, str]]) -> dict:
    if not dead:
        return {}
    causes = [c.cause for _, c, _ in dead]
    lifespans = [f.lifespan_days for f, _, _ in dead]
    longest = max(dead, key=lambda t: t[0].lifespan_days)
    closest = None
    for item in dead:
        if item[1].cause == "almost_shipped":
            closest = item
            break
    most_common = causes[0]
    best = 0
    for cause in dict.fromkeys(causes):
        count = causes.count(cause)
        if count > best:
            best = count
            most_common = cause
    cause_counts: dict[str, int] = {}
    for cause in causes:
        cause_counts[cause] = cause_counts.get(cause, 0) + 1
    return {
        "total_buried": len(dead),
        "avg_lifespan": round(sum(lifespans) / len(lifespans)),
        "most_common_cause": most_common,
        "cause_counts": cause_counts,
        "longest_name": longest[0].name,
        "longest_days": longest[0].lifespan_days,
        "closest_name": closest[0].name if closest else None,
    }


def _tombstone(idx: int, facts: RepoFacts, cls: Classification, eulogy: str, anonymize: bool) -> str:
    display_name = f"REPO-{idx:03d}" if anonymize else facts.name
    last_words = facts.last_commits[0] if facts.last_commits else "…"
    display_last = "(hidden)" if anonymize else last_words
    langs = ", ".join(facts.languages.keys()) or "—"
    cause_css = CAUSE_CSS.get(cls.cause, "cause-abandoned")
    emoji = CAUSE_EMOJI.get(cls.cause, "🪦")
    epitaph_line = EPITAPHS.get(cls.cause, "It is gone now.")

    diff_html = ""
    if facts.last_diff_stat:
        diff_lines = "".join(
            f"<div class='diff-line'>{_esc(l)}</div>" for l in facts.last_diff_stat.splitlines()
        )
        diff_html = f"<div class='seance-panel'><div class='seance-title'>🔦 The Séance</div><p class='seance-sub'>Here's what you were doing when you stopped:</p><pre class='diff'>{diff_lines}</pre></div>"

    buckets = facts.activity_buckets(40)
    peak = max(buckets) if buckets else 0
    bars = ""
    for b in buckets:
        if peak > 0 and b > 0:
            h = max(2, round((b / peak) * 22))
            bar_cls = "bar bar-hit"
        else:
            h = 1
            bar_cls = "bar bar-empty"
        bars += f"<span class='{bar_cls}' style='height:{h}px' title='{b} commits'></span>"
    strip = f"<div class='activity-strip' title='Commit activity across the project lifetime'>{bars}</div>"

    todos_badge = (
        f"<span class='badge badge-todos'>🧟 {facts.todo_count} TODO{'' if facts.todo_count == 1 else 's'} left behind</span>"
        if facts.todo_count > 0
        else ""
    )

    return f"""
    <article class="tombstone {cause_css}" data-anon-name="REPO-{idx:03d}" data-real-name="{_esc(facts.name)}"
             data-cause="{_esc(cls.cause)}" data-lifespan="{facts.lifespan_days}" data-commits="{facts.commit_count}">
      <div class="tombstone-top">
        <span class="cause-chip">{emoji} {_esc(cls.cause_label)}</span>
        <span class="confidence conf-{_esc(cls.confidence)}">{_esc(cls.confidence)} confidence</span>
      </div>
      <h2 class="repo-name" data-field="name">{_esc(display_name)}</h2>
      <p class="epitaph">Here lies {_esc(display_name)}. {_esc(epitaph_line)}</p>
      <div class="dates">
        <div><span class="label">Born</span><span class="val" data-field="born">{_esc(facts.born)}</span></div>
        <div class="cross">†</div>
        <div><span class="label">Died</span><span class="val" data-field="died">{_esc(facts.died)}</span></div>
      </div>
      <p class="lifespan" data-field="lifespan">lived {_esc(str(facts.lifespan_days))} days · {_esc(str(facts.commit_count))} commits · {(_esc(langs))}</p>
      {strip}
      <div class="last-words">
        <span class="lw-label">Last words:</span>
        <span class="lw-msg" data-field="lastwords">“{_esc(display_last)}”</span>
      </div>
      <div class="eulogy" data-field="eulogy">{_esc(eulogy)}</div>
      <div class="badges">
        {todos_badge}
        {("<span class='badge badge-good'>✅ README</span>" if facts.has_readme else "<span class='badge badge-miss'>❌ No README</span>")}
        {("<span class='badge badge-good'>✅ Tests</span>" if facts.has_tests else "<span class='badge badge-miss'>❌ No tests</span>")}
        {("<span class='badge badge-good'>🚀 Deploy config</span>" if facts.has_deploy else "")}
      </div>
      <div class="cert" data-field="cert">📜 {_esc(cls.death_certificate)}</div>
      <button class="seance-btn" type="button">🔦 Hold a Séance</button>
      {diff_html}
    </article>
    """


def _alive_card(facts: RepoFacts, anonymize: bool) -> str:
    display = "STILL-BREATHING" if anonymize else facts.name
    return f"""
    <div class="alive-card">
      <span class="alive-dot"></span>
      <span class="alive-name" data-field="name">{_esc(display)}</span>
      <span class="alive-meta">last seen {_esc(str(facts.days_since_death))}d ago</span>
    </div>
    """


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Creepster&family=Special+Elite&display=swap');

:root {
  --bg: #0a0a0f;
  --bg2: #12121a;
  --stone: #1a1a22;
  --stone-edge: #2a2a35;
  --text: #c8c8d0;
  --dim: #7a7a88;
  --accent: #8b5cf6;
  --gold: #d4af37;
  --fog: rgba(120, 120, 160, 0.04);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Special Elite', 'Courier New', monospace;
  min-height: 100vh;
  overflow-x: hidden;
  position: relative;
}

.fog {
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background:
    radial-gradient(ellipse 80% 50% at 20% 100%, var(--fog), transparent),
    radial-gradient(ellipse 60% 40% at 80% 100%, var(--fog), transparent);
  animation: drift 20s ease-in-out infinite alternate;
}
@keyframes drift {
  from { transform: translateX(-3%); opacity: 0.6; }
  to { transform: translateX(3%); opacity: 1; }
}

.container { max-width: 1100px; margin: 0 auto; padding: 40px 20px; position: relative; z-index: 1; }

header { text-align: center; margin-bottom: 50px; }
.title {
  font-family: 'Creepster', cursive;
  font-size: 3.2rem;
  color: var(--accent);
  text-shadow: 0 0 30px rgba(139, 92, 246, 0.5), 0 0 60px rgba(139, 92, 246, 0.2);
  letter-spacing: 3px;
  animation: flicker 4s infinite;
}
@keyframes flicker {
  0%, 100% { opacity: 1; }
  92% { opacity: 1; }
  93% { opacity: 0.8; }
  94% { opacity: 1; }
  96% { opacity: 0.85; }
  97% { opacity: 1; }
}
.subtitle { color: var(--dim); margin-top: 10px; font-size: 0.95rem; }

.controls {
  display: flex; justify-content: center; gap: 20px; align-items: center;
  margin: 30px 0; flex-wrap: wrap;
}
.toggle-wrap {
  display: flex; align-items: center; gap: 10px;
  background: var(--stone); border: 1px solid var(--stone-edge);
  padding: 10px 18px; border-radius: 8px; cursor: pointer;
}
.toggle-wrap input { accent-color: var(--accent); width: 16px; height: 16px; cursor: pointer; }
.toggle-wrap label { cursor: pointer; user-select: none; }

.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 16px; margin: 20px 0 30px; flex-wrap: wrap;
}
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  padding: 6px 14px; border-radius: 16px; cursor: pointer;
  background: var(--stone); border: 1px solid var(--stone-edge);
  color: var(--dim); font-family: inherit; font-size: 0.75rem;
  transition: all 0.2s;
}
.chip:hover { border-color: var(--accent); color: var(--text); }
.chip-active { background: rgba(139,92,246,0.18); border-color: var(--accent); color: var(--accent); }
.sort-select {
  padding: 8px 12px; border-radius: 8px; cursor: pointer;
  background: var(--stone); border: 1px solid var(--stone-edge);
  color: var(--text); font-family: inherit; font-size: 0.78rem;
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px; margin-bottom: 50px;
}
.stat-card {
  background: var(--bg2); border: 1px solid var(--stone-edge);
  padding: 20px; border-radius: 10px; text-align: center;
}
.stat-num {
  font-family: 'Creepster', cursive; font-size: 2rem; color: var(--gold);
  text-shadow: 0 0 15px rgba(212, 175, 55, 0.3);
}
.stat-label { color: var(--dim); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin-top: 6px; }

.dist-wrap { margin: -20px 0 40px; }
.dist-bar {
  display: flex; height: 10px; border-radius: 5px; overflow: hidden;
  background: var(--bg2); border: 1px solid var(--stone-edge);
}
.dist-seg { min-width: 4px; transition: opacity 0.2s; }
.dist-seg:hover { opacity: 0.75; }
.dist-legend {
  display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; margin-top: 10px;
}
.dist-legend-item {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--dim); font-size: 0.7rem;
}
.dist-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px; margin-bottom: 50px;
}

.tombstone {
  background: linear-gradient(180deg, var(--stone) 0%, var(--bg2) 100%);
  border: 1px solid var(--stone-edge);
  border-radius: 16px 16px 8px 8px;
  padding: 28px 24px;
  position: relative;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  cursor: pointer;
}
.tombstone::before {
  content: ''; position: absolute; top: 0; left: 50%; transform: translateX(-50%);
  width: 60px; height: 3px; background: var(--accent); border-radius: 2px;
  box-shadow: 0 0 10px var(--accent);
}
.tombstone:hover {
  transform: translateY(-6px);
  box-shadow: 0 20px 40px rgba(0,0,0,0.5), 0 0 30px rgba(139, 92, 246, 0.15);
}

.tombstone-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.cause-chip {
  font-size: 0.8rem; padding: 4px 12px; border-radius: 20px;
  background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.3);
  color: var(--accent);
}
.confidence { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1px; }
.conf-high { color: #4ade80; } .conf-medium { color: var(--gold); } .conf-low { color: var(--dim); }

.repo-name {
  font-family: 'Creepster', cursive; font-size: 1.6rem; color: #e8e8f0;
  margin-bottom: 8px; word-break: break-word;
}
.epitaph { color: var(--dim); font-style: italic; font-size: 0.85rem; margin-bottom: 16px; line-height: 1.5; }

.dates { display: flex; justify-content: center; align-items: center; gap: 20px; margin-bottom: 10px; }
.dates > div { text-align: center; }
.dates .label { display: block; color: var(--dim); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1px; }
.dates .val { color: var(--text); font-size: 0.9rem; }
.cross { color: var(--accent); font-size: 1.4rem; }

.lifespan { text-align: center; color: var(--gold); font-size: 0.8rem; margin-bottom: 10px; }

.activity-strip {
  display: flex; align-items: flex-end; gap: 2px;
  height: 24px; margin: 0 auto 16px; padding: 0 4px;
  background: rgba(0,0,0,0.25); border-radius: 4px;
  border-bottom: 1px solid var(--stone-edge);
}
.activity-strip .bar { flex: 1; min-width: 1px; border-radius: 1px 1px 0 0; }
.activity-strip .bar-hit { background: var(--accent); box-shadow: 0 0 4px rgba(139,92,246,0.5); }
.activity-strip .bar-empty { background: rgba(122,122,136,0.18); }

.last-words {
  background: rgba(0,0,0,0.3); border-left: 3px solid var(--accent);
  padding: 10px 14px; margin-bottom: 14px; border-radius: 0 6px 6px 0;
}
.lw-label { color: var(--dim); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 4px; }
.lw-msg { color: var(--text); font-size: 0.85rem; font-style: italic; }

.eulogy {
  color: var(--text); font-size: 0.88rem; line-height: 1.6; margin-bottom: 16px;
  padding: 12px; background: rgba(139, 92, 246, 0.05); border-radius: 8px;
  border: 1px dashed rgba(139, 92, 246, 0.2);
}

.badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.badge { font-size: 0.7rem; padding: 3px 10px; border-radius: 12px; }
.badge-good { background: rgba(74, 222, 128, 0.1); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.2); }
.badge-miss { background: rgba(248, 113, 113, 0.1); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.2); }
.badge-todos { background: rgba(251, 191, 36, 0.1); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.2); }

.cert {
  font-size: 0.75rem; color: var(--dim); font-style: italic;
  padding: 8px 12px; background: rgba(0,0,0,0.2); border-radius: 6px; margin-bottom: 14px;
}

.seance-btn {
  width: 100%; padding: 10px; background: transparent;
  border: 1px solid var(--accent); color: var(--accent);
  border-radius: 8px; cursor: pointer; font-family: inherit; font-size: 0.85rem;
  transition: all 0.2s;
}
.seance-btn:hover { background: rgba(139, 92, 246, 0.15); box-shadow: 0 0 15px rgba(139, 92, 246, 0.2); }

.seance-panel { display: none; margin-top: 14px; }
.seance-panel.open { display: block; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
.seance-title { color: var(--gold); font-size: 0.9rem; margin-bottom: 6px; }
.seance-sub { color: var(--dim); font-size: 0.75rem; margin-bottom: 10px; }
.diff {
  background: #000; border-radius: 6px; padding: 12px; font-size: 0.7rem;
  overflow-x: auto; font-family: 'Courier New', monospace; color: #a1a1aa;
}
.diff-line { white-space: pre; }

.alive-section { margin-top: 20px; }
.alive-section h3 {
  font-family: 'Creepster', cursive; color: #4ade80; font-size: 1.4rem;
  text-align: center; margin-bottom: 20px;
  text-shadow: 0 0 15px rgba(74, 222, 128, 0.3);
}
.alive-grid { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; }
.alive-card {
  display: flex; align-items: center; gap: 10px;
  background: rgba(74, 222, 128, 0.05); border: 1px solid rgba(74, 222, 128, 0.2);
  padding: 10px 18px; border-radius: 20px;
}
.alive-dot {
  width: 8px; height: 8px; background: #4ade80; border-radius: 50%;
  animation: pulse 2s infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; box-shadow: 0 0 5px #4ade80; } 50% { opacity: 0.5; box-shadow: 0 0 15px #4ade80; } }
.alive-name { color: #4ade80; font-size: 0.85rem; }
.alive-meta { color: var(--dim); font-size: 0.7rem; }

footer { text-align: center; color: var(--dim); font-size: 0.75rem; margin-top: 60px; padding: 20px; }

.empty-state { text-align: center; padding: 60px 20px; color: var(--dim); }
.empty-state .skull { font-size: 4rem; margin-bottom: 20px; }

@media (max-width: 640px) {
  .title { font-size: 2rem; }
  .grid { grid-template-columns: 1fr; }
  .stats { grid-template-columns: repeat(2, 1fr); }
}
"""

_JS = """
document.querySelectorAll('.seance-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const tomb = btn.closest('.tombstone');
    const panel = tomb.querySelector('.seance-panel');
    if (panel) {
      panel.classList.toggle('open');
      btn.textContent = panel.classList.contains('open') ? '🕯️ Close the Séance' : '🔦 Hold a Séance';
    }
  });
});

const grid = document.querySelector('.grid');
const tombs = () => Array.from(document.querySelectorAll('.tombstone'));

document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('chip-active'));
    chip.classList.add('chip-active');
    const filter = chip.dataset.filter;
    tombs().forEach(t => {
      t.style.display = (filter === 'all' || t.dataset.cause === filter) ? '' : 'none';
    });
  });
});

const sortSelect = document.getElementById('sortSelect');
if (sortSelect && grid) {
  const original = tombs();
  sortSelect.addEventListener('change', () => {
    const mode = sortSelect.value;
    const items = tombs();
    items.sort((a, b) => {
      switch (mode) {
        case 'lifespan-desc': return +b.dataset.lifespan - +a.dataset.lifespan;
        case 'lifespan-asc': return +a.dataset.lifespan - +b.dataset.lifespan;
        case 'commits-desc': return +b.dataset.commits - +a.dataset.commits;
        case 'commits-asc': return +a.dataset.commits - +b.dataset.commits;
        case 'name':
          return (a.dataset.realName || '').localeCompare(b.dataset.realName || '');
        default:
          return original.indexOf(a) - original.indexOf(b);
      }
    });
    items.forEach(el => grid.appendChild(el));
  });
}

const anonToggle = document.getElementById('anonToggle');
if (anonToggle) {
  anonToggle.addEventListener('change', () => {
    const on = anonToggle.checked;
    document.querySelectorAll('[data-field="name"]').forEach(el => {
      const card = el.closest('.tombstone') || el.closest('.alive-card');
      if (!card) return;
      if (on) {
        el.textContent = card.classList.contains('alive-card')
          ? 'STILL-BREATHING'
          : (card.dataset.anonName || 'REPO-???');
      } else {
        el.textContent = card.dataset.realName || el.dataset.real || el.textContent;
      }
    });
    document.querySelectorAll('[data-field="lastwords"]').forEach(el => {
      if (on) { el.dataset.real = el.textContent; el.textContent = '“(hidden for privacy)”'; }
      else if (el.dataset.real) { el.textContent = el.dataset.real; }
    });
    document.querySelectorAll('[data-field="eulogy"]').forEach(el => {
      if (on) { el.dataset.real = el.textContent; el.textContent = '(eulogy hidden while anonymized — repo name and last words are withheld)'; }
      else if (el.dataset.real) { el.textContent = el.dataset.real; }
    });
    document.querySelectorAll('.epitaph').forEach(el => {
      if (on) { el.dataset.real = el.textContent; el.textContent = 'Here lies a nameless project.'; }
      else if (el.dataset.real) { el.textContent = el.dataset.real; }
    });
    document.querySelectorAll('[data-field="stat-name"]').forEach(el => {
      if (on) { el.textContent = el.dataset.anonName || 'REPO-???'; }
      else { el.textContent = el.dataset.realName || el.textContent; }
    });
  });
}
"""


def render(
    dead: list[tuple[RepoFacts, Classification, str]],
    alive: list[RepoFacts],
    anonymize: bool = False,
) -> str:
    stats = _compute_stats(dead)

    cause_labels = {
        "born_dead": "Born Dead",
        "sudden_death": "Sudden Death",
        "slow_fade": "Slow Fade",
        "fix_loop": "Fix-Loop Death",
        "almost_shipped": "Almost Shipped",
        "scope_creep": "Scope-Creep Death",
        "abandoned": "General Abandonment",
    }

    stats_html = ""
    if stats:
        most_common_label = cause_labels.get(stats["most_common_cause"], stats["most_common_cause"])
        longest_name = f"REPO-???" if anonymize else stats["longest_name"]
        closest_anon = "REPO-???"
        closest_attr = ""
        if stats.get("closest_name"):
            closest_attr = (
                f' data-field="stat-name" data-real-name="{_esc(stats["closest_name"])}" '
                f'data-anon-name="{closest_anon}"'
            )
        dist_segments = ""
        dist_legend = ""
        total = stats["total_buried"] or 1
        for cause, count in stats["cause_counts"].items():
            color = CAUSE_COLORS.get(cause, "#9ca3af")
            pct = round((count / total) * 100)
            dist_segments += (
                f"<div class='dist-seg' style='flex:{count};background:{color}' "
                f"title='{_esc(cause_labels.get(cause, cause))}: {count}'></div>"
            )
            dist_legend += (
                f"<span class='dist-legend-item'><span class='dist-dot' style='background:{color}'></span>"
                f"{_esc(cause_labels.get(cause, cause))} ({count})</span>"
            )
        dist_html = f"""
        <div class="dist-wrap">
          <div class="dist-bar">{dist_segments}</div>
          <div class="dist-legend">{dist_legend}</div>
        </div>"""
        stats_html = f"""
        <div class="stats">
          <div class="stat-card"><div class="stat-num">{stats['total_buried']}</div><div class="stat-label">Projects Buried</div></div>
          <div class="stat-card"><div class="stat-num">{stats['avg_lifespan']}</div><div class="stat-label">Avg Lifespan (days)</div></div>
          <div class="stat-card"><div class="stat-num">💀</div><div class="stat-label">Most Common Death</div><div style="color:var(--text);font-size:0.8rem;margin-top:4px;">{_esc(most_common_label)}</div></div>
          <div class="stat-card"><div class="stat-num">{stats['longest_days']}d</div><div class="stat-label">Longest Lived</div><div style="color:var(--text);font-size:0.8rem;margin-top:4px;" data-field="stat-name" data-real-name="{_esc(stats['longest_name'])}" data-anon-name="REPO-???">{_esc(longest_name)}</div></div>
          <div class="stat-card"><div class="stat-num">🚀</div><div class="stat-label">Closest to Shipping</div><div style="color:var(--text);font-size:0.8rem;margin-top:4px;"{closest_attr}>{_esc(f"REPO-???" if anonymize else (stats['closest_name'] or '—'))}</div></div>
        </div>
        {dist_html}"""

    tombstones = "".join(
        _tombstone(i, f, c, e, anonymize) for i, (f, c, e) in enumerate(dead, 1)
    )

    alive_html = ""
    if alive:
        cards = "".join(_alive_card(f, anonymize) for f in alive)
        alive_html = f"""
        <section class="alive-section">
          <h3>🌱 Still Breathing</h3>
          <div class="alive-grid">{cards}</div>
        </section>"""

    empty = ""
    if not dead and not alive:
        empty = """
        <div class="empty-state">
          <div class="skull">💀</div>
          <h2>No graves to dig.</h2>
          <p>No git repositories found in the scanned folder.</p>
        </div>"""

    generated = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    filter_html = ""
    if dead:
        present_causes = list(dict.fromkeys(c.cause for _, c, _ in dead))
        chips = "<button class='chip chip-active' data-filter='all'>All</button>"
        for cause in present_causes:
            label = cause_labels.get(cause, cause)
            chips += f"<button class='chip' data-filter='{_esc(cause)}'>{_esc(label)}</button>"
        filter_html = f"""
    <div class="toolbar">
      <div class="chip-row">{chips}</div>
      <select id="sortSelect" class="sort-select">
        <option value="default">Sort: Default</option>
        <option value="lifespan-desc">Longest lived</option>
        <option value="lifespan-asc">Shortest lived</option>
        <option value="commits-desc">Most commits</option>
        <option value="commits-asc">Fewest commits</option>
        <option value="name">Name (A–Z)</option>
      </select>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rest in Repo — Side Project Graveyard</title>
<style>{_CSS}</style>
</head>
<body>
<div class="fog"></div>
<div class="container">
  <header>
    <h1 class="title">⚰️ Rest in Repo</h1>
    <p class="subtitle">A graveyard for the side projects that didn't make it.</p>
    <div class="controls">
      <div class="toggle-wrap">
        <input type="checkbox" id="anonToggle" {'checked' if anonymize else ''}>
        <label for="anonToggle">🕵️ Anonymize (hide names &amp; messages)</label>
      </div>
    </div>
    {filter_html}
  </header>
  {stats_html}
  {empty}
  <div class="grid">{tombstones}</div>
  {alive_html}
  <footer>
    Generated locally on {generated} · Nothing left your machine · Powered by Ollama + open models
  </footer>
</div>
<script>{_JS}</script>
</body>
</html>"""

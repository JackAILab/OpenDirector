"""Owner feedback for a director plan, kept separate from quality approval.

Feedback is useful for learning which questions and strategies helped, but it
is not a quality label and never grants training or public-release permission.
Only bounded, redacted fields are stored; the immutable plan digest binds the
feedback to the exact revision the owner saw.
"""
import json
import re
import time

from harness.learning.episodes import _hash, _journal_connection

DECISIONS = frozenset(("keep", "revise", "reject"))
DIMENSIONS = frozenset(("claim", "story", "shots", "audio", "product", "model", "reference", "other"))
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
URL = re.compile(r"https?://[^\s)]+", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


def _clean_note(value):
    value = str(value or "").replace("\x00", "").strip()
    value = EMAIL.sub("[REDACTED_EMAIL]", value)
    value = URL.sub("[REDACTED_URL]", value)
    value = PHONE.sub("[REDACTED_PHONE]", value)
    return value[:500]


def connection():
    c = _journal_connection()
    c.execute("""CREATE TABLE IF NOT EXISTS learning_feedback(
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT NOT NULL, owner INTEGER NOT NULL, revision INTEGER NOT NULL,
        plan_sha256 TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL)""")
    return c


def record(project, owner, decision, rating, strategy_indices, changed_dimensions, note=""):
    """Append feedback for the current plan; reject stale or malformed input."""
    if decision not in DECISIONS:
        raise ValueError("反馈结论无效")
    if type(rating) is not int or not 1 <= rating <= 5:
        raise ValueError("反馈评分应为1–5")
    if not isinstance(strategy_indices, list) or len(strategy_indices) > 3 or any(
        type(item) is not int or not 0 <= item < 3 for item in strategy_indices
    ):
        raise ValueError("采用的策略索引无效")
    if not isinstance(changed_dimensions, list) or len(changed_dimensions) > 8 or any(
        item not in DIMENSIONS for item in changed_dimensions
    ):
        raise ValueError("修改项无效")
    note = _clean_note(note)
    if len(note) > 500:
        raise ValueError("反馈说明不超过500字")
    plan = {key: project.get(key) for key in
            ("brief", "shots", "questions", "assumptions", "decisions", "revision")}
    plan_sha = _hash(plan)
    payload = {
        "schema": "visualagent.owner-plan-feedback.v1",
        "decision": decision,
        "rating": rating,
        "strategy_indices": sorted(set(strategy_indices)),
        "changed_dimensions": sorted(set(changed_dimensions)),
        "note": note,
        "plan_sha256": plan_sha,
        "training_eligible": False,
    }
    payload["feedback_sha256"] = _hash(payload)
    c = connection()
    try:
        with c:
            seq = c.execute(
                "INSERT INTO learning_feedback(project,owner,revision,plan_sha256,data,created) VALUES(?,?,?,?,?,?)",
                (project["id"], owner, project["revision"], plan_sha,
                 json.dumps(payload, ensure_ascii=False, sort_keys=True), time.time()),
            ).lastrowid
    finally:
        c.close()
    return dict(payload, feedback_id=seq)


def latest(project, owner):
    c = connection()
    try:
        rows = c.execute(
            "SELECT seq,data FROM learning_feedback WHERE project=? AND owner=? AND revision=? ORDER BY seq DESC",
            (project["id"], owner, project["revision"]),
        ).fetchall()
        output = []
        for seq, raw in rows:
            data = json.loads(raw)
            checked = {key: value for key, value in data.items() if key != "feedback_sha256"}
            if data.get("feedback_sha256") != _hash(checked):
                raise ValueError("反馈记录完整性核对失败")
            output.append(dict(data, feedback_id=seq))
        return output
    finally:
        c.close()


def summary(project, owner):
    rows = latest(project, owner)
    return {
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "training_eligible": False,
        "method": "owner feedback is descriptive preference evidence, not an independent quality label",
    }


def aggregate():
    """Return privacy-safe feedback aggregates for the private operator report."""
    from collections import Counter
    decisions = Counter()
    dimensions = Counter()
    strategies = Counter()
    ratings = []
    count = 0
    c = connection()
    try:
        rows = c.execute("SELECT data FROM learning_feedback ORDER BY seq").fetchall()
        for (raw,) in rows:
            data = json.loads(raw)
            checked = {key: value for key, value in data.items() if key != "feedback_sha256"}
            if data.get("feedback_sha256") != _hash(checked):
                raise ValueError("反馈记录完整性核对失败")
            rating = data.get("rating")
            if type(rating) is not int or not 1 <= rating <= 5:
                raise ValueError("反馈评分无效")
            count += 1
            ratings.append(rating)
            decisions[str(data.get("decision"))] += 1
            dimensions.update(str(item) for item in data.get("changed_dimensions", []) if item in DIMENSIONS)
            strategies.update(str(item) for item in data.get("strategy_indices", []) if type(item) is int and 0 <= item < 3)
    finally:
        c.close()
    return {
        "schema": "visualagent.owner-feedback-aggregate.v1",
        "feedback_count": count,
        "rating_mean": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "decisions": dict(decisions),
        "changed_dimensions": dict(dimensions),
        "strategy_indices": dict(strategies),
        "training_eligible": False,
        "content_exported": False,
        "limitations": ["owner feedback is preference evidence, not independent quality or conversion data"],
    }

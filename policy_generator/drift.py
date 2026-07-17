"""
drift.py — compare the deployed Data Identification methods against the
loaded Classification Registry: the drift-check stage's deterministic core.

The Registry (via author.author) says what SHOULD be deployed — method names,
governed tags, term bindings, regex/signature seeds, dictionary value counts.
The live catalog (pdc.list_methods + pdc.get_method) says what IS. This
module never talks to PDC: it takes both sides as plain dicts and returns a
per-method verdict, so the logic is testable offline and the API layer stays
a thin wire-up.

Verdicts:
  clean    — deployed and every check passes
  drifted  — deployed but at least one governed fact diverged (off-vocabulary
             or missing tags, broken/absent term binding, changed regex or
             signature, changed dictionary row count, method disabled)
  missing  — the Registry authors it, but no method of that name is deployed
  orphaned — a method carries the app's prefix but the Registry no longer
             authors it (a stale deploy, or hand-authored under the prefix)

Dictionary VALUES are not readable over PDC's GraphQL (only the server-side
rowCount survives export), so the value-list check is a row-count check —
an honest proxy, called out as such in the check label.
"""
from __future__ import annotations


def _norm_tags(tags):
    return sorted({str(t).strip().lower() for t in (tags or []) if str(t).strip()})


def _live_actions(method):
    for rule in (method.get("rules") or []):
        for act in (rule.get("actions") or []):
            if isinstance(act, dict):
                yield act


def _live_tags(method):
    tags = []
    for act in _live_actions(method):
        for t in (act.get("applyTags") or []):
            if isinstance(t, dict) and t.get("name"):
                tags.append(t["name"])
    return tags


def _live_terms(method):
    """Every applyBusinessTerms binding in the method -> [{name, id}]."""
    out = []
    for act in _live_actions(method):
        for bt in (act.get("applyBusinessTerms") or []):
            if isinstance(bt, dict):
                out.append(bt)
    return out


def expected_methods(art):
    """Flatten an author() artifact set into one expected row per method."""
    exp = []
    for p in art.get("patterns", []):
        r = p["rule"]
        exp.append({
            "kind": "DataPattern", "name": r["name"],
            "term": p["term"], "term_id": p.get("term_id") or None,
            "tags": _norm_tags(t["name"] for a in r["rules"][0]["actions"]
                               for t in a.get("applyTags", [])),
            "regex": (r.get("regexMatch") or {}).get("regex") or [],
            "signature": r.get("profilePatterns") or [],
        })
    for d in art.get("dictionaries", []):
        r = d["rule"]
        exp.append({
            "kind": "Dictionary", "name": r["name"],
            "term": d["term"], "term_id": d.get("term_id") or None,
            "tags": _norm_tags(t["name"] for a in r["rules"][0]["actions"]
                               for t in a.get("applyTags", [])),
            "row_count": r.get("rowCount"),
        })
    return exp


def _check(name, expected, actual, ok):
    return {"check": name, "expected": expected, "actual": actual, "ok": bool(ok)}


def _checks_for(exp, live, allow):
    """All governed-fact checks for one expected/live method pair."""
    checks = []

    checks.append(_check("enabled", True, bool(live.get("isEnabled", True)),
                         bool(live.get("isEnabled", True))))

    live_tags = _norm_tags(_live_tags(live))
    checks.append(_check("governed tags", exp["tags"], live_tags,
                         live_tags == exp["tags"]))
    if allow:
        off = [t for t in live_tags if t not in allow]
        checks.append(_check("tags on allow-list", [], off, not off))

    terms = _live_terms(live)
    names = {str(bt.get("name") or "").strip().lower() for bt in terms}
    bound = exp["term"].strip().lower() in names
    checks.append(_check("term binding", exp["term"],
                         ", ".join(sorted(n for n in names if n)) or None, bound))
    if exp.get("term_id"):
        ids = {str(bt.get("id") or "") for bt in terms
               if str(bt.get("name") or "").strip().lower() == exp["term"].strip().lower()}
        checks.append(_check("term id", exp["term_id"],
                             ", ".join(sorted(i for i in ids if i)) or None,
                             str(exp["term_id"]) in ids))

    if exp["kind"] == "DataPattern":
        live_rx = (live.get("regexMatch") or {}).get("regex") or []
        checks.append(_check("content regex", exp["regex"], live_rx,
                             list(live_rx) == list(exp["regex"])))
        if exp["signature"]:
            live_sig = live.get("profilePatterns") or []
            checks.append(_check("profile signature", exp["signature"], live_sig,
                                 list(live_sig) == list(exp["signature"])))
    else:
        checks.append(_check("value rows (count proxy)", exp["row_count"],
                             live.get("rowCount"),
                             live.get("rowCount") == exp["row_count"]))
    return checks


def evaluate(art, live_methods, allow=None):
    """Per-method drift verdicts.

    `art`          — author.author(reg, prefix) output (the expected set)
    `live_methods` — full get_method details for every non-built-in method
                     carrying the prefix, each with at least kind+name
    `allow`        — the Registry's governed tag allow-list (lower-case set)

    Returns {'rows': [...], 'counts': {clean, drifted, orphaned, missing}}.
    """
    allow = {str(t).strip().lower() for t in (allow or set())}
    expected = expected_methods(art)
    live_by_key = {(m.get("kind"), m.get("name")): m for m in live_methods}
    seen = set()
    rows = []

    for exp in expected:
        key = (exp["kind"], exp["name"])
        live = live_by_key.get(key)
        if live is None:
            rows.append({"name": exp["name"], "kind": exp["kind"], "term": exp["term"],
                         "verdict": "missing", "checks": [],
                         "findings": ["not deployed — import the authored set"]})
            continue
        seen.add(key)
        checks = _checks_for(exp, live, allow)
        failed = [c for c in checks if not c["ok"]]
        rows.append({
            "name": exp["name"], "kind": exp["kind"], "term": exp["term"],
            "_id": live.get("_id"),
            "verdict": "drifted" if failed else "clean",
            "checks": checks,
            "findings": [f"{c['check']}: expected {c['expected']!r}, live {c['actual']!r}"
                         for c in failed],
        })

    for key, live in live_by_key.items():
        if key in seen:
            continue
        rows.append({
            "name": live.get("name"), "kind": live.get("kind"), "term": None,
            "_id": live.get("_id"),
            "verdict": "orphaned", "checks": [],
            "findings": ["carries the prefix but the Registry no longer authors it"],
        })

    counts = {"clean": 0, "drifted": 0, "orphaned": 0, "missing": 0}
    for r in rows:
        counts[r["verdict"]] += 1
    return {"rows": rows, "counts": counts}

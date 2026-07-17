"""Drift-check engine tests: verdict logic against the fixture Registry,
with live-method dicts shaped exactly like pdc.get_method returns them."""

import copy

from policy_generator import author, drift, registry


def _authored(reg):
    return author.author(reg)


def _live_from(art):
    """A live catalog that echoes the authored set verbatim (the state right
    after a successful deploy — everything should be clean)."""
    live = []
    for p in art["patterns"]:
        live.append({**copy.deepcopy(p["rule"]), "kind": "DataPattern"})
    for d in art["dictionaries"]:
        live.append({**copy.deepcopy(d["rule"]), "kind": "Dictionary"})
    return live


class TestVerdicts:
    def test_freshly_deployed_set_is_clean(self, registry):
        art = _authored(registry)
        out = drift.evaluate(art, _live_from(art), registry_allow(registry))
        assert out["counts"] == {"clean": 2, "drifted": 0, "orphaned": 0, "missing": 0}
        for row in out["rows"]:
            assert row["findings"] == []
            assert all(c["ok"] for c in row["checks"])

    def test_missing_when_nothing_deployed(self, registry):
        art = _authored(registry)
        out = drift.evaluate(art, [], registry_allow(registry))
        assert out["counts"]["missing"] == 2
        assert all(r["verdict"] == "missing" for r in out["rows"])

    def test_orphaned_when_registry_no_longer_authors_it(self, registry):
        art = _authored(registry)
        live = _live_from(art)
        live.append({"kind": "DataPattern", "name": "Claims Retired Concept",
                     "_id": "zz", "isEnabled": True,
                     "rules": [{"actions": [{"applyTags": [{"name": "pii"}]}]}]})
        out = drift.evaluate(art, live, registry_allow(registry))
        assert out["counts"]["orphaned"] == 1
        (orphan,) = [r for r in out["rows"] if r["verdict"] == "orphaned"]
        assert orphan["name"] == "Claims Retired Concept"

    def test_off_vocabulary_tag_drifts(self, registry):
        art = _authored(registry)
        live = _live_from(art)
        live[0]["rules"][0]["actions"][0]["applyTags"] = [{"name": "hand-rolled"}]
        out = drift.evaluate(art, live, registry_allow(registry))
        (row,) = [r for r in out["rows"] if r["name"] == live[0]["name"]]
        assert row["verdict"] == "drifted"
        failed = {c["check"] for c in row["checks"] if not c["ok"]}
        assert "governed tags" in failed
        assert "tags on allow-list" in failed

    def test_broken_term_binding_drifts(self, registry):
        art = _authored(registry)
        live = _live_from(art)
        # the importer rewrote the id to the term name (the exact live
        # behaviour discovered on PDC 11 when the id is unresolved)
        (pat,) = [m for m in live if m["kind"] == "DataPattern"]
        pat["rules"][0]["actions"][0]["applyBusinessTerms"] = [
            {"name": "Member Number", "id": "Member Number"}]
        out = drift.evaluate(art, live, registry_allow(registry))
        (row,) = [r for r in out["rows"] if r["name"] == pat["name"]]
        assert row["verdict"] == "drifted"
        (bad,) = [c for c in row["checks"] if not c["ok"]]
        assert bad["check"] == "term id"
        assert bad["expected"] == "t-100"

    def test_regex_and_rowcount_drift(self, registry):
        art = _authored(registry)
        live = _live_from(art)
        for m in live:
            if m["kind"] == "DataPattern":
                m["regexMatch"] = {"regex": ["^EDITED$"]}
            else:
                m["rowCount"] = 99
        out = drift.evaluate(art, live, registry_allow(registry))
        assert out["counts"]["drifted"] == 2
        findings = " ".join(f for r in out["rows"] for f in r["findings"])
        assert "content regex" in findings
        assert "value rows" in findings

    def test_disabled_method_drifts(self, registry):
        art = _authored(registry)
        live = _live_from(art)
        live[0]["isEnabled"] = False
        out = drift.evaluate(art, live, registry_allow(registry))
        (row,) = [r for r in out["rows"] if r["name"] == live[0]["name"]]
        assert row["verdict"] == "drifted"
        assert any(c["check"] == "enabled" and not c["ok"] for c in row["checks"])


def registry_allow(reg):
    return registry.governed_tags(reg)

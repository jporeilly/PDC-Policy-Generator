"""Engine tests: registry validation + deterministic authoring.
Ports the invariants the old selftest.py checked into pytest."""

import copy
import io
import json
import zipfile

import pytest

from policy_generator import author, registry


class TestRegistry:
    def test_validate_rejects_bad_envelopes(self):
        with pytest.raises(registry.RegistryError):
            registry.validate_registry([1, 2])
        with pytest.raises(registry.RegistryError):
            registry.validate_registry({"schema": "something/else", "concepts": []})
        with pytest.raises(registry.RegistryError):
            registry.validate_registry({"schema": registry.SCHEMA})

    def test_summary_counts(self, registry_file):
        reg = registry.load_registry(str(registry_file))
        s = registry.summary(reg)
        assert s["glossary"] == "Claims"
        assert s["concepts"] == 4
        assert s["seeded"] == 3          # three concepts carry detect seeds
        assert s["resolved_term_ids"] == 1
        assert s["governed_tags"] == 3
        assert len(registry.unresolved_terms(reg)) == 3

    def test_detection_intent_is_optional_and_normalised(self):
        # absent / empty = unknown (pre-1.9 Registries read exactly as before)
        assert registry.detection_intent({}) is None
        assert registry.detection_intent({"detection_intent": ""}) is None
        assert registry.detection_intent({"detection_intent": " Mapping_Only "}) == "mapping_only"
        assert registry.is_mapping_only({"detection_intent": "mapping_only"})
        assert not registry.is_mapping_only({"detection_intent": "seeded"})
        assert not registry.is_mapping_only({})

    def test_mapping_only_is_never_authorable(self):
        from tests.conftest import make_registry
        reg = make_registry()
        # even a concept with lingering seeds drops out of the authorable set
        reg["concepts"][0]["detection_intent"] = "mapping_only"
        assert {c["term_name"] for c in registry.seeded_concepts(reg)} == {"State Code", "Audit Record"}
        assert registry.summary(reg)["seeded"] == 2

    def test_discovery_covers_packaged_glossary_state(self, tmp_path, monkeypatch):
        # The packaged Glossary desktop app writes registries under %APPDATA%
        # (com.pentaho.pdc-glossary\registries); a packaged Policy Generator
        # must find them with nothing configured, or the two Windows installers
        # need hand-wired paths to talk to each other.
        state = tmp_path / "com.pentaho.pdc-glossary" / "registries"
        state.mkdir(parents=True)
        (state / "registry.claims.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.delenv("POLICY_REGISTRY_DIR", raising=False)
        found = registry.discover_registries()
        assert str(state / "registry.claims.json") in found

    def test_write_seed_request_schema(self, tmp_path):
        path = registry.write_seed_request(str(tmp_path), "registry.claims.json",
                                           ["Member Phone", "  ", "Broker Email"])
        import json as _json
        data = _json.loads((tmp_path / "seed-request.json").read_text(encoding="utf-8"))
        assert path.endswith("seed-request.json")
        assert data["registry_file"] == "registry.claims.json"
        assert data["terms"] == [{"name": "Member Phone", "reason": "no_seed"},
                                 {"name": "Broker Email", "reason": "no_seed"}]
        assert data["requested_at"].endswith("Z")


class TestAuthor:
    def test_artifacts_and_skips(self, registry):
        art = author.author(registry)
        assert art["prefix"] == "Claims"  # defaults to the glossary name
        assert len(art["patterns"]) == 1
        assert len(art["dictionaries"]) == 1
        skipped = {s["term"]: s["why"] for s in art["skipped"]}
        assert "Claim Notes" in skipped            # no seeds
        assert "Audit Record" in skipped           # tags fail the allow-list
        assert "governed tags" in skipped["Audit Record"]

    def test_mapping_only_skips_authoring_even_with_seeds(self, registry):
        # the steward's declared intent beats a lingering seed
        registry["concepts"][0]["detection_intent"] = "mapping_only"
        art = author.author(registry)
        assert art["patterns"] == []                       # the pattern seed is ignored
        skipped = {s["term"]: s for s in art["skipped"]}
        assert skipped["Member Number"]["intent"] == "mapping_only"
        assert "steward decision" in skipped["Member Number"]["why"]

    def test_pattern_rule_shape(self, registry):
        (p,) = author.author(registry)["patterns"]
        rule = p["rule"]
        assert rule["name"] == "Claims Member Number"
        assert rule["regexMatch"]["regex"] == ["^MBR-\\d{6}$"]
        assert rule["profilePatterns"] == ["AAA-999999"]
        assert "mbr_?no" in rule["metadataHints"]["aliases"][0]["nameRegex"]
        (action,) = rule["rules"][0]["actions"]
        # governed filter: 'pii' survives, structural 'maskable' does not
        assert action["applyTags"] == [{"name": "pii"}]
        # applyBusinessTerms is PDC 11's LIVE field name (assignBusinessTerm
        # was silently dropped by the importer — fixed in 1.8.0)
        assert action["applyBusinessTerms"] == [{"name": "Member Number", "id": "t-100"}]

    def test_dictionary_rule_shape(self, registry):
        (d,) = author.author(registry)["dictionaries"]
        assert d["csv"] == "Term\nCA\nNY\nTX\n"
        assert d["rule"]["rowCount"] == 3
        # unresolved id: binding is by name only
        assert d["rule"]["rules"][0]["actions"][0]["applyBusinessTerms"] == [{"name": "State Code"}]

    def test_shared_vocabularies_require_the_column_name(self, registry):
        """Field 2026-08-23: four per-context Status dictionaries shared
           Active/Inactive-style values and each bound its term onto every
           status-shaped column — 57 unexpected bindings in one run, because
           the stock blend (similarity 0.9 + metadata 0.1) lets values alone
           clear the 0.7 gate. Dictionaries sharing >= half of the smaller
           vocabulary rebalance to 0.5/0.5 so the column NAME must agree;
           non-overlapping dictionaries keep the loose blend."""
        reg = copy.deepcopy(registry)
        reg["concepts"].append(
            {"term_name": "Ship State", "term_id": "t-200",
             "category": "Geo", "tags": ["pii"],
             "sources": ["claims.shipments.ship_state"],
             "detect": [{"type": "dictionary", "values": ["CA", "NY", "AZ"]}]})
        reg["concepts"].append(
            {"term_name": "Currency", "term_id": "t-300",
             "category": "Finance", "tags": ["finance"],
             "sources": ["claims.billing.currency"],
             "detect": [{"type": "dictionary", "values": ["USD", "EUR", "GBP"]}]})
        arts = {d["term"]: d for d in author.author(reg)["dictionaries"]}
        state, ship, curr = arts["State Code"], arts["Ship State"], arts["Currency"]
        # the colliding pair (2 of 3 values shared) is tightened, both ways…
        for d, partner in ((state, "Ship State"), (ship, "State Code")):
            assert d["shared_vocabulary_with"] == [partner]
            weights = [p["*"][1] for p in d["rule"]["rules"][0]["confidenceScore"]["+"]]
            assert weights == [0.5, 0.5], weights
            assert d["rule"]["metadataHints"]["aliases"][0]["score"] == 0.5
        # …the disjoint dictionary keeps the loose blend
        assert "shared_vocabulary_with" not in curr
        weights = [p["*"][1] for p in curr["rule"]["rules"][0]["confidenceScore"]["+"]]
        assert weights == [0.9, 0.1], weights
        # the temporary value-set key never leaks into the artifact
        assert all("_values" not in d for d in arts.values())

    def test_deterministic_ids(self, registry):
        a = author.author(registry)
        b = author.author(registry)
        assert a["patterns"][0]["rule"]["_id"] == b["patterns"][0]["rule"]["_id"]

    def test_zip_layout_matches_pdc_export(self, registry):
        art = author.author(registry)
        with zipfile.ZipFile(io.BytesIO(author.to_zip_bytes(art))) as z:
            names = set(z.namelist())
            assert {"patterns-import.zip", "dictionaries-import.zip",
                    "INDEX.csv", "README.txt"} <= names
            with zipfile.ZipFile(io.BytesIO(z.read("dictionaries-import.zip"))) as dz:
                (inner_name,) = dz.namelist()
                assert inner_name.endswith(".zip")   # nested per-dictionary zip
                with zipfile.ZipFile(io.BytesIO(dz.read(inner_name))) as iz:
                    kinds = {n.rsplit(".", 1)[1] for n in iz.namelist()}
                    assert kinds == {"json", "csv"}
            with zipfile.ZipFile(io.BytesIO(z.read("patterns-import.zip"))) as pz:
                (pat_name,) = pz.namelist()
                rule = json.loads(pz.read(pat_name))
                assert isinstance(rule, dict)        # PDC Gson-parses per file: object, never array

class TestPBatch:
    """The 2026-08-25 walk's P-log fixes (docs/SPEC-BACKLOG in the Glossary
       repo): P6 hint anchoring, P1 warning split, P2 unresolved split, P7
       nested-source honesty."""

    def test_p6_single_token_hints_anchor(self):
        from policy_generator.author import column_name_regex
        assert column_name_regex(["awc.tiered_rates.status"]) == "(?i)(^status$)"
        assert column_name_regex(["awc.sites.county"]) == "(?i)(^county$)"
        # multi-token names keep the substring claim (prefixed variants exist)
        assert column_name_regex(["awc.customers.account_status"]) \
            == "(?i)(account_?status)"
        # mixed sources: one anchored, one substring, deduped
        rx = column_name_regex(["a.t.status", "a.u.pump_status"])
        assert rx == "(?i)(^status$|pump_?status)"

    def test_p1_all_anchored_shared_shapes_split_from_ambiguous(self):
        from policy_generator import author as A
        reg = {
            "schema": "classification-registry/1", "glossary": "G",
            "tag_vocabulary": {"allow_list": ["pii"]},
            "concepts": [
                {"term_name": "Lead (ppb)", "term_id": "t1", "tags": ["pii"],
                 "sources": ["a.q.lead_ppb"],
                 "detect": [{"type": "pattern", "regex": "^-?[0-9]+$",
                             "source": "name-anchored", "identity": "column_name"}]},
                {"term_name": "Copper (ppm)", "term_id": "t2", "tags": ["pii"],
                 "sources": ["a.q.copper_ppm"],
                 "detect": [{"type": "pattern", "regex": "^-?[0-9]+$",
                             "source": "name-anchored", "identity": "column_name"}]},
                {"term_name": "Billing ZIP", "term_id": "t3", "tags": ["pii"],
                 "sources": ["a.c.billing_zip"],
                 "detect": [{"type": "pattern", "regex": "^\d{5}$"}]},
                {"term_name": "Service ZIP", "term_id": "t4", "tags": ["pii"],
                 "sources": ["a.c.service_zip"],
                 "detect": [{"type": "pattern", "regex": "^\d{5}$"}]},
            ]}
        art = A.author(reg, prefix="T")
        anchored = {a["regex"] for a in art["anchored_shapes"]}
        ambiguous = {a["regex"] for a in art["ambiguous_shapes"]}
        assert "^-?[0-9]+$" in anchored, "all-name-anchored claimants are the neutral line"
        assert "^\d{5}$" in ambiguous, \
            "profiled claimants keep the red warning — their regex weight alone crosses the gate"

    def test_p6_vocabulary_twins_named(self):
        from policy_generator import author as A
        vals = ["Active", "Inactive", "Suspended"]
        reg = {
            "schema": "classification-registry/1", "glossary": "G",
            "tag_vocabulary": {"allow_list": ["pii"]},
            "concepts": [
                {"term_name": "Status (Alerts)", "term_id": "t1", "tags": ["pii"],
                 "sources": ["a.account_alerts.status"],
                 "detect": [{"type": "dictionary", "values": vals}]},
                {"term_name": "Status (Rates)", "term_id": "t2", "tags": ["pii"],
                 "sources": ["a.tiered_rates.status"],
                 "detect": [{"type": "dictionary", "values": vals}]},
            ]}
        art = A.author(reg, prefix="T")
        twins = {t["term"]: t for t in art["vocabulary_twins"]}
        assert set(twins) == {"Status (Alerts)", "Status (Rates)"}, art["vocabulary_twins"]
        assert twins["Status (Alerts)"]["partners"] == ["Status (Rates)"]
        assert twins["Status (Alerts)"]["column"] == "status"

    def test_p2_unresolved_split(self):
        from policy_generator import registry as R
        reg = {"concepts": [
            {"term_name": "Authored NoId", "term_id": None,
             "detect": [{"type": "pattern", "regex": "^x$"}]},
            {"term_name": "MappingOnly NoId", "term_id": None, "detect": [],
             "detection_intent": "mapping_only"},
            {"term_name": "LinkGoverned NoId", "term_id": None, "detect": []},
            {"term_name": "Fine", "term_id": "t-1", "detect": []},
        ]}
        d = R.unresolved_detail(reg)
        assert d["authorable"] == ["Authored NoId"]
        assert set(d["link_governed"]) == {"MappingOnly NoId", "LinkGoverned NoId"}

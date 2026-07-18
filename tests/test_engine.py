"""Engine tests: registry validation + deterministic authoring.
Ports the invariants the old selftest.py checked into pytest."""

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
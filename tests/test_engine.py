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
        assert action["assignBusinessTerm"] == [{"name": "Member Number", "id": "t-100"}]

    def test_dictionary_rule_shape(self, registry):
        (d,) = author.author(registry)["dictionaries"]
        assert d["csv"] == "Term\nCA\nNY\nTX\n"
        assert d["rule"]["rowCount"] == 3
        # unresolved id: binding is by name only
        assert d["rule"]["rules"][0]["actions"][0]["assignBusinessTerm"] == [{"name": "State Code"}]

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
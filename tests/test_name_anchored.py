"""Name-anchored seeds (1.10.1).

The Glossary's Registry now carries the steward's Auto flip on a concept whose
values have no identifying shape — a date, a bounded measure like pH or Lead
ppb — as a pattern seed marked `identity: "column_name"`. Such a rule is a
different claim from a profiled shape: the column NAME identifies, the content
regex only sanity-checks. Authoring it with the stock weights would ship a rule
that either never fires or tags every numeric column in the estate, so the
blend and the condition both change. These tests pin that.
"""
from policy_generator import author


def _reg(seed, term="pH Level", sources=None):
    return {
        "schema": "classification-registry/1",
        "glossary": "Arizona Water",
        "tag_vocabulary": {"allow_list": ["water-quality", "compliance"]},
        "concepts": [{"term_name": term, "term_id": "t-1", "category": "Water",
                      "definition": "d.", "tags": ["water-quality"],
                      "sources": (["aw.samples.ph_level"] if sources is None else sources),
                      "detect": [seed]}],
    }


NAMED = {"type": "pattern", "regex": r"^-?[0-9]+(\.[0-9]+)?$",
         "source": "name-anchored", "identity": "column_name"}
PROFILED = {"type": "pattern", "regex": r"^[A-Z]{3}-[0-9]{6}$",
            "signature": "AAA-nnnnnn", "source": "profiled"}


def _rule(seed):
    art = author.author(_reg(seed), prefix="Arizona")
    assert art["patterns"], art["skipped"]
    return art["patterns"][0]["rule"]["rules"][0], art["patterns"][0]


class TestBlend:
    def test_name_and_shape_weigh_half_each(self):
        rule, _ = _rule(NAMED)
        weights = {list(p["*"][0].values())[0]: p["*"][1]
                   for p in rule["confidenceScore"]["+"]}
        assert weights == {"metadataScore": "0.50", "regexScore": "0.50"}

    def test_neither_half_can_fire_the_rule_alone(self):
        """0.5 name or 0.5 shape both fall short of the 0.7 gate — the rule is
        a conjunction, which is the whole point of the rebalance."""
        rule, _ = _rule(NAMED)
        gate = rule["condition"]["and"][0][">="][1]
        weights = [float(p["*"][1]) for p in rule["confidenceScore"]["+"]]
        assert max(weights) < float(gate) <= sum(weights)

    def test_the_condition_names_no_variable_pdc_rejects(self):
        """Live-caught: PDC's pattern importer refuses a condition mentioning
        columnCardinality — IllegalStateException, one rejected file, and a
        worker that still reports COMPLETED. The clause came from the shipped
        Personal Data Identifier template, which is a dictionary; cardinality is
        legal there and illegal in a DataPattern. 81 of 88 patterns were lost to
        it, because the importer abandons the whole zip at the first bad file."""
        rule, _ = _rule(NAMED)
        assert rule["condition"] == {"and": [{">=": [{"var": "confidenceScore"}, "0.7"]}]}
        assert "columnCardinality" not in str(rule["condition"])

    def test_the_gate_is_higher_than_the_stock_one(self):
        named, _ = _rule(NAMED)
        stock, _ = _rule(PROFILED)
        assert named["condition"]["and"][0][">="][1] == "0.7"
        assert stock["condition"]["and"][0][">="][1] == "0.5"

    def test_the_threshold_is_a_string(self):
        """Not cosmetic: PDC's JsonLogic does not coerce, so a NUMERIC threshold
        makes a rule that imports cleanly, reports drift-clean, and never fires.
        Live-proven — our dictionaries (string thresholds) tagged columns in the
        same run where every pattern (numeric) tagged nothing, and PDC's own
        built-in USA_SSN gates on the string "0.5"."""
        for seed in (NAMED, PROFILED):
            rule, _ = _rule(seed)
            for clause in rule["condition"]["and"]:
                for op in clause.values():
                    assert isinstance(op[1], str), f"threshold must be a string, got {op[1]!r}"

    def test_signature_rides_at_weight_zero(self):
        rule, pat = _rule(dict(NAMED, signature="dddd-dd-dd"))
        sig = [p for p in rule["confidenceScore"]["+"]
               if p["*"][0]["var"] == "profilePatternScore"]
        assert sig and sig[0]["*"][1] == "0.00"
        assert pat["rule"]["profilePatterns"] == ["dddd-dd-dd"], \
            "kept for PDC's own screens — informative, inert"

    def test_alias_score_mirrors_the_name_weight(self):
        _, pat = _rule(NAMED)
        assert pat["rule"]["metadataHints"]["aliases"][0]["score"] == 0.5

    def test_no_column_hint_falls_back_to_the_stock_blend(self):
        """With no sources there is no name to anchor to, so the rule must not
        claim a 0.5 name weight it cannot back."""
        art = author.author(_reg(NAMED, sources=[]), prefix="Arizona")
        rule = art["patterns"][0]["rule"]["rules"][0]
        assert [p["*"][0]["var"] for p in rule["confidenceScore"]["+"]] == ["regexScore"]


class TestProfiledUnchanged:
    def test_profiled_seed_keeps_the_verified_shape(self):
        rule, pat = _rule(PROFILED)
        weights = {p["*"][0]["var"]: p["*"][1] for p in rule["confidenceScore"]["+"]}
        assert weights == {"regexScore": "0.40", "profilePatternScore": "0.30",
                           "metadataScore": "0.30"}
        assert rule["condition"] == {"and": [{">=": [{"var": "confidenceScore"}, "0.5"]}]}
        assert pat["rule"]["metadataHints"]["aliases"][0]["score"] == 0.3


class TestEvidenceTravels:
    def test_artifact_carries_what_each_method_rests_on(self):
        art = author.author(_reg(NAMED), prefix="Arizona")
        assert art["patterns"][0]["evidence"] == "name-anchored"
        art = author.author(_reg(PROFILED), prefix="Arizona")
        assert art["patterns"][0]["evidence"] == "profiled"

    def test_preview_surfaces_it(self, api_client, registry_file):
        api_client.post(f"/api/load?path={registry_file}")
        r = api_client.post("/api/preview", json={"prefix": "Claims"})
        assert r.status_code == 200
        assert all("evidence" in p for p in r.json()["patterns"])


class TestAmbiguousShapesAreFlagged:
    """A content regex shared by several methods identifies none of them.

    Live: one induced shape ^[A-Z]{2}[0-9]{4}$ was the evidence for eight
    concepts, and a free-text `notes` column came back bound to all eight,
    tagged pii/privacy/location. The Registry marks such seeds name-anchored
    from 1.38.34; Author still says so, because an older Registry will not.
    """

    def _reg_two(self, rx_a, rx_b):
        return {
            "schema": "classification-registry/1", "glossary": "AW",
            "tag_vocabulary": {"allow_list": ["water-quality"]},
            "concepts": [
                {"term_name": "Source Type", "term_id": "t-1", "tags": ["water-quality"],
                 "sources": ["aw.s.source_type"],
                 "detect": [{"type": "pattern", "regex": rx_a, "source": "profiled"}]},
                {"term_name": "Water System Type", "term_id": "t-2", "tags": ["water-quality"],
                 "sources": ["aw.s.system_type"],
                 "detect": [{"type": "pattern", "regex": rx_b, "source": "profiled"}]},
            ],
        }

    def test_a_shared_shape_is_reported_with_its_claimants(self):
        art = author.author(self._reg_two(r"^[A-Z]{2}[0-9]{4}$", r"^[A-Z]{2}[0-9]{4}$"),
                            prefix="AW")
        (amb,) = art["ambiguous_shapes"]
        assert amb["terms"] == ["Source Type", "Water System Type"]

    def test_distinct_shapes_raise_nothing(self):
        art = author.author(self._reg_two(r"^[A-Z]{2}[0-9]{4}$", r"^SYS-[0-9]{3}$"), prefix="AW")
        assert art["ambiguous_shapes"] == []


class TestBooleanConceptsAreNotAuthored:
    """Belt to the Registry's braces (1.10.9).

    From 1.38.34 the contract stops seeding boolean columns, but an older
    Registry still can — and a method on a bit column imports, passes drift and
    never fires, which is the most expensive kind of nothing.
    """

    def _reg(self, types):
        return {
            "schema": "classification-registry/1", "glossary": "AW",
            "tag_vocabulary": {"allow_list": ["customer"]},
            "concepts": [{"term_name": "Opted Out Marketing", "term_id": "t-1",
                          "tags": ["customer"], "sources": ["aw.customers.opted_out_marketing"],
                          "source_types": types,
                          "detect": [{"type": "pattern", "regex": r"^-?[0-9]+$",
                                      "source": "name-anchored", "identity": "column_name"}]}],
        }

    def test_a_bit_source_is_skipped_with_a_reason(self):
        art = author.author(self._reg({"aw.customers.opted_out_marketing": "BIT"}), prefix="AW")
        assert art["patterns"] == []
        (skip,) = art["skipped"]
        assert "boolean column" in skip["why"] and "never fire" in skip["why"]

    def test_a_numeric_source_still_authors(self):
        art = author.author(self._reg({"aw.customers.opted_out_marketing": "NUMERIC"}), prefix="AW")
        assert len(art["patterns"]) == 1

    def test_a_registry_without_types_is_unchanged(self):
        art = author.author(self._reg({}), prefix="AW")
        assert len(art["patterns"]) == 1, "pre-1.38.34 contracts must behave as before"

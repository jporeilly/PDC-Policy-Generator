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

    def test_cardinality_guard_rides_along(self):
        rule, _ = _rule(NAMED)
        guard = [c for c in rule["condition"]["and"] if ">" in c]
        assert guard and guard[0][">"][0]["var"] == "columnCardinality"

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
        assert rule["condition"] == {"and": [{">=": [{"var": "confidenceScore"}, 0.5]}]}
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

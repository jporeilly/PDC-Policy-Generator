"""
selftest.py — offline checks for the author pipeline (no PDC, no network).

    python -m policy_generator.selftest
"""
from __future__ import annotations
import io, json, sys, zipfile

from . import author as A, registry as R

PASS = FAIL = 0


def _c(name, ok, detail=""):
    global PASS, FAIL
    print(("  [ok  ] " if ok else "  [FAIL] ") + name + (f" — {detail}" if detail and not ok else ""))
    PASS += ok
    FAIL += not ok


def _registry():
    """A synthetic Registry in the exact shape the Glossary Generator writes."""
    return {
        "schema": "classification-registry/1",
        "glossary": "CSCU Business Glossary",
        "glossary_id": "gid-1",
        "concepts": [
            {"concept": "member_number", "term_name": "Member Number", "term_id": "t-1",
             "sensitivity": "HIGH", "tags": ["pii", "identifier", "sensitive", "maskable"],
             "off_vocabulary_tags": [], "category": "Customer",
             "definition": "The member's unique CSCU number.",
             "detect": [{"type": "pattern", "regex": r"^CSCU-\d{6}$",
                         "signature": "AAAA-nnnnnn", "source": "profiled"}],
             "sources": ["cscu_core.members.mbr_no"],
             "keys": {"cscu_core.members.mbr_no": {"pk": True, "fk": False, "ref": None}},
             "method": None},
            {"concept": "risk_rating", "term_name": "Risk Rating", "term_id": None,
             "sensitivity": "MEDIUM", "tags": ["compliance", "aml"],
             "off_vocabulary_tags": [], "category": "Compliance & Risk",
             "definition": "Three-level AML risk assessment.",
             "detect": [{"type": "dictionary", "values": ["LOW", "MEDIUM", "HIGH"],
                         "source": "profiled"}],
             "sources": ["cscu_core.kyc_reviews.risk_rating_cd"],
             "keys": {}, "method": None},
            {"concept": "memo_text", "term_name": "Memo Text", "term_id": None,
             "sensitivity": "LOW", "tags": ["correspondence"],
             "off_vocabulary_tags": ["rogue-tag"], "category": "Transactions",
             "definition": "Free-text memo.", "detect": [],
             "sources": ["cscu_core.transactions.memo_txt"], "keys": {}, "method": None},
        ],
        "tag_vocabulary": {"allow_list": ["pii", "identifier", "sensitive", "maskable",
                                          "compliance", "aml", "correspondence"],
                           "sensitivity_floors": {"pii": "HIGH"}, "terms": {},
                           "domain": "credit_union", "source": "term_tag_dictionary"},
        "governance_audit": {"count": 0, "recent": []},
        "references": {},
    }


def main():
    print("policy_generator selftest")
    reg = _registry()

    # ---- registry loader ------------------------------------------------------
    s = R.summary(reg)
    _c("summary counts", s["concepts"] == 3 and s["seeded"] == 2 and s["resolved_term_ids"] == 1, s)
    _c("governed tags parsed", "pii" in R.governed_tags(reg))
    _c("unresolved terms listed", set(R.unresolved_terms(reg)) == {"Risk Rating", "Memo Text"})
    try:
        R.load_registry(__file__)
        _c("loader rejects non-registry", False)
    except R.RegistryError:
        _c("loader rejects non-registry", True)

    # ---- author ----------------------------------------------------------------
    art = A.author(reg, prefix="CSCU")
    _c("one pattern authored", len(art["patterns"]) == 1)
    _c("one dictionary authored", len(art["dictionaries"]) == 1)
    _c("seedless concept skipped with reason",
       len(art["skipped"]) == 1 and art["skipped"][0]["term"] == "Memo Text")

    p = art["patterns"][0]["rule"][0]
    _c("patternsRules shape", p["__typename"] == "patternsRules" and p["status"] == "enabled")
    _c("content regex from the seed", p["contentRegex"][0]["regex"] == r"^CSCU-\d{6}$")
    _c("signature becomes the content pattern", p["contentPatterns"][0]["pattern"] == "AAAA-nnnnnn")
    _c("column hint from Registry sources", p["columnNameRegex"][0]["regex"] == "(?i)(mbr_?no)")
    _c("term assigned", p["assignBusinessTerm"][0]["k"] == "Member Number")
    tags = [t["k"] for t in p["actions"][0]["applyTags"]]
    _c("tags governed, structural skipped", tags == ["pii", "sensitive"], tags)

    d = art["dictionaries"][0]
    _c("dictionariesRules shape", d["rule"][0]["__typename"] == "dictionariesRules")
    _c("values CSV", d["csv"] == "term\nLOW\nMEDIUM\nHIGH\n")
    _c("dictionary tags governed", [t["k"] for t in d["rule"][0]["actions"][0]["applyTags"]] == ["compliance", "aml"])

    # off-vocabulary tag from a concept never reaches a rule
    reg2 = _registry()
    reg2["concepts"][0]["tags"] = ["pii", "rogue-tag"]
    art2 = A.author(reg2, prefix="X")
    tags2 = [t["k"] for t in art2["patterns"][0]["rule"][0]["actions"][0]["applyTags"]]
    _c("off-vocabulary tag filtered at authoring", "rogue-tag" not in tags2, tags2)

    # ---- outputs ----------------------------------------------------------------
    z = zipfile.ZipFile(io.BytesIO(A.to_zip_bytes(art)))
    names = z.namelist()
    _c("zip layout", "Patterns/cscu_member_number.json" in names
       and "Dictionaries/cscu_risk_rating.csv" in names and "INDEX.csv" in names, names)
    idx = z.read("INDEX.csv").decode()
    _c("INDEX carries term ids", "t-1" in idx)
    rule = json.loads(z.read("Patterns/cscu_member_number.json"))
    _c("zip rule parses back", rule[0]["name"] == "CSCU Member Number")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

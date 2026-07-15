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

    p = art["patterns"][0]["rule"]
    _c("DataPattern envelope (single object, PDC export shape)",
       isinstance(p, dict) and p["type"] == "DataPattern" and p["isEnabled"] is True and p["builtIn"] is False)
    _c("content regex from the seed", p["regexMatch"]["regex"] == [r"^CSCU-\d{6}$"])
    _c("signature becomes profilePatterns", p["profilePatterns"] == ["AAAA-nnnnnn"])
    _c("column hint becomes metadataHints alias",
       p["metadataHints"]["aliases"][0]["nameRegex"] == "(?i)(mbr_?no)")
    prule = p["rules"][0]
    _c("pattern rule JsonLogic uses regexScore",
       any("regexScore" in json.dumps(x) for x in prule["confidenceScore"]["+"]))
    acts = prule["actions"]
    _c("ONE action object (PDC validator: every action needs a tag)",
       len(acts) == 1 and bool(acts[0].get("applyTags")), acts)
    tags = [t["name"] for t in acts[0]["applyTags"]]
    _c("tags governed (live applyTags {'name'} shape), structural skipped",
       tags == ["pii", "sensitive"], tags)
    bts = acts[0].get("assignBusinessTerm") or []
    _c("term binding rides in the SAME action as the tags",
       bts and bts[0]["name"] == "Member Number" and bts[0].get("id") == "t-1", bts)

    d = art["dictionaries"][0]
    _c("Dictionary envelope (csv paired, rowCount)",
       d["rule"]["type"] == "Dictionary" and d["rule"]["csv"] == d["values_filename"]
       and d["rule"]["rowCount"] == 3)
    _c("values CSV has the live 'Term' header", d["csv"] == "Term\nLOW\nMEDIUM\nHIGH\n")
    _c("dictionary tags governed",
       [t["name"] for a in d["rule"]["rules"][0]["actions"] for t in a.get("applyTags", [])] == ["compliance", "aml"])

    # off-vocabulary tag from a concept never reaches a rule
    reg2 = _registry()
    reg2["concepts"][0]["tags"] = ["pii", "rogue-tag"]
    art2 = A.author(reg2, prefix="X")
    tags2 = [t["name"] for a in art2["patterns"][0]["rule"]["rules"][0]["actions"]
             for t in a.get("applyTags", [])]
    _c("off-vocabulary tag filtered at authoring", "rogue-tag" not in tags2, tags2)

    # a concept whose tags ALL fall to the filter cannot become a method
    reg3 = _registry()
    reg3["concepts"][0]["tags"] = ["rogue-only"]
    art3 = A.author(reg3, prefix="X")
    _c("all-tags-filtered concept is skipped (import validator needs a tag)",
       not art3["patterns"] and any("governed tags" in x["why"] for x in art3["skipped"]),
       art3["skipped"])

    # ---- outputs ----------------------------------------------------------------
    z = zipfile.ZipFile(io.BytesIO(A.to_zip_bytes(art)))
    names = z.namelist()
    _c("download layout: two import zips + manifest",
       set(names) == {"patterns-import.zip", "dictionaries-import.zip", "INDEX.csv", "README.txt"}, names)
    pz = zipfile.ZipFile(io.BytesIO(z.read("patterns-import.zip")))
    _c("patterns zip: flat json per pattern (export layout)",
       pz.namelist() == ["cscu_member_number.json"], pz.namelist())
    rule = json.loads(pz.read("cscu_member_number.json"))
    _c("pattern json is a single object", isinstance(rule, dict) and rule["name"] == "CSCU Member Number")
    dz = zipfile.ZipFile(io.BytesIO(z.read("dictionaries-import.zip")))
    _c("dictionaries zip: nested zip per dictionary (export layout)",
       dz.namelist() == ["cscu_risk_rating.zip"], dz.namelist())
    iz = zipfile.ZipFile(io.BytesIO(dz.read("cscu_risk_rating.zip")))
    _c("nested dictionary zip pairs json + csv",
       set(iz.namelist()) == {"cscu_risk_rating.json", "cscu_risk_rating.csv"}, iz.namelist())
    idx = z.read("INDEX.csv").decode()
    _c("INDEX carries term ids", "t-1" in idx)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

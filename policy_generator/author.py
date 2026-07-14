"""
author.py — Registry concepts -> PDC Data Identification artifacts.

Each concept's detection seeds become importable methods, in exactly the
shapes PDC's Management -> Data Identification -> Import accepts (and the
same shapes the CSCU Technical Track teaches):

  * detect {type: pattern, regex, signature} -> a Data Pattern
        (`patternsRules` JSON: column-name hint + content pattern + regex,
        TT-standard weights and a 0.7 confidence condition)
  * detect {type: dictionary, values}        -> a Dictionary
        (`dictionariesRules` JSON + a values CSV, similarity-weighted)

Every rule assigns the concept's GOVERNED tags (filtered against the
Registry's embedded allow-list — the drift guarantee starts at authoring)
and its business term. Deterministic: the same Registry always produces the
same files. Nothing here talks to PDC — output is files a steward reviews.
"""
from __future__ import annotations
import io, json, re, zipfile

_NON = re.compile(r"[^A-Za-z0-9]+")

# TT-standard blend weights and thresholds
_PATTERN_CONFIDENCE = {"+": [
    {"*": [{"var": "metadataScore"}, 0.3]},
    {"*": [{"var": "patternScore"}, 0.4]},
    {"*": [{"var": "regexScore"}, 0.3]},
]}
_PATTERN_CONDITION = {"and": [{">=": [{"var": "confidenceScore"}, "0.7"]}]}
_DICT_CONFIDENCE = {"+": [
    {"*": [{"var": "similarity"}, 0.8]},
    {"*": [{"var": "metadataScore"}, 0.2]},
]}
_DICT_CONDITION = {"or": [
    {">=": [{"var": "confidenceScore"}, "0.6"]},
    {">=": [{"var": "metadataScore"}, "0.7"]},
]}

# structural vocabulary a policy should not stamp on its own
_SKIP_TAGS = {"maskable", "identifier", "record", "table-level"}


def _slug(s):
    return _NON.sub("_", str(s or "")).strip("_").lower() or "term"


def column_name_regex(sources):
    """Case-insensitive column-name hint from the concept's physical sources
    ('schema.table.column' / 'bucket/folder/file'), e.g. ['x.members.mbr_no']
    -> (?i)(mbr_?no). Returns None when no usable names exist."""
    parts = []
    for src in sources or []:
        name = str(src).replace("/", ".").split(".")[-1].strip()
        toks = [re.escape(t) for t in re.split(r"[^A-Za-z0-9]+", name) if t]
        if toks:
            p = "_?".join(toks)
            if p not in parts:
                parts.append(p)
    return "(?i)(" + "|".join(parts) + ")" if parts else None


def _rule_tags(concept, allow):
    tags = [str(t).strip().lower() for t in (concept.get("tags") or []) if str(t).strip()]
    tags = [t for t in tags if t not in _SKIP_TAGS]
    if allow:
        tags = [t for t in tags if t in allow]
    return tags[:3]


def _pattern_rule(name, category, col_rx, signature, content_rx, tags, term):
    rule = {
        "__typename": "patternsRules",
        "type": "Pattern",
        "name": name,
        "category": category,
        "status": "enabled",
        "columnNameRegex": ([{"regex": col_rx, "score": 1.0}] if col_rx else []),
        "columnNameWeight": 0.3,
        "contentPatterns": ([{"pattern": signature}] if signature else []),
        "contentPatternWeight": 0.4,
        "contentRegex": [{"regex": content_rx}],
        "contentRegexWeight": 0.3,
        "confidenceScore": _PATTERN_CONFIDENCE,
        "condition": _PATTERN_CONDITION,
        "actions": [{"applyTags": [{"k": t} for t in tags]}] if tags else [],
    }
    if term:
        rule["assignBusinessTerm"] = [{"k": term}]
    return [rule]


def _dictionary_rule(name, category, col_rx, tags, term):
    rule = {
        "__typename": "dictionariesRules",
        "type": "Dictionary",
        "name": name,
        "category": category,
        "minSamples": 1,
        "confidenceScore": _DICT_CONFIDENCE,
        "columnNameRegex": ([{"regex": col_rx, "score": 0.9}] if col_rx else []),
        "condition": _DICT_CONDITION,
        "actions": [{"applyTags": [{"k": t} for t in tags]}] if tags else [],
    }
    if term:
        rule["assignBusinessTerm"] = [{"k": term}]
    return [rule]


def author(reg: dict, prefix: str = None) -> dict:
    """Registry -> {'patterns': [...], 'dictionaries': [...], 'skipped': [...]}.

    One artifact per detection seed on each concept; concepts without seeds
    land in `skipped` with the reason (free text / names / amounts have no
    stable shape — identify those with vocabulary dictionaries or rules)."""
    from . import registry as _r
    prefix = (prefix or "").strip() or str(reg.get("glossary") or "Rule").split(" ")[0]
    allow = _r.governed_tags(reg)
    patterns, dictionaries, skipped = [], [], []
    for c in reg.get("concepts", []):
        if not isinstance(c, dict):
            continue
        term = (c.get("term_name") or "").strip()
        seeds = c.get("detect") or []
        if not seeds:
            skipped.append({"term": term,
                            "why": "no detection seed in the Registry (no induced format or reference list)"})
            continue
        col_rx = column_name_regex(c.get("sources"))
        tags = _rule_tags(c, allow)
        name = f"{prefix} {term}"
        category = f"{_slug(prefix).upper()}_{_slug(c.get('category') or 'General').title().replace('_', '')}"
        for seed in seeds:
            kind = (seed or {}).get("type")
            if kind == "pattern" and (seed.get("regex") or "").strip():
                patterns.append({
                    "filename": f"{_slug(prefix)}_{_slug(term)}.json",
                    "term": term, "term_id": c.get("term_id"),
                    "rule": _pattern_rule(name, category, col_rx,
                                          (seed.get("signature") or "").strip() or None,
                                          seed["regex"].strip(), tags, term),
                })
            elif kind == "dictionary" and len(seed.get("values") or []) >= 2:
                dictionaries.append({
                    "filename": f"{_slug(prefix)}_{_slug(term)}_rule.json",
                    "values_filename": f"{_slug(prefix)}_{_slug(term)}.csv",
                    "term": term, "term_id": c.get("term_id"),
                    "rule": _dictionary_rule(name, category, col_rx, tags, term),
                    "csv": "term\n" + "\n".join(str(v) for v in seed["values"]) + "\n",
                })
    return {"patterns": patterns, "dictionaries": dictionaries, "skipped": skipped,
            "glossary": reg.get("glossary"), "prefix": prefix}


def write_out(art: dict, out_dir: str) -> list:
    """Write the authored artifacts as files (Patterns/, Dictionaries/,
    INDEX.csv, README.txt). Returns the relative paths written."""
    import os
    written = []

    def w(rel, content):
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        written.append(rel)

    index = ["kind,name,file,term,term_id"]
    for p in art["patterns"]:
        w("Patterns/" + p["filename"], json.dumps(p["rule"], indent=2) + "\n")
        index.append(f"pattern,{p['rule'][0]['name']},Patterns/{p['filename']},{p['term']},{p.get('term_id') or ''}")
    for d in art["dictionaries"]:
        w("Dictionaries/" + d["filename"], json.dumps(d["rule"], indent=2) + "\n")
        w("Dictionaries/" + d["values_filename"], d["csv"])
        index.append(f"dictionary,{d['rule'][0]['name']},Dictionaries/{d['filename']},{d['term']},{d.get('term_id') or ''}")
    w("INDEX.csv", "\n".join(index) + "\n")
    w("README.txt",
      "Authored by the PDC Policy Generator from the Classification Registry.\n"
      "Import via PDC: Management -> Data Identification -> Patterns / Dictionaries -> Import.\n"
      "Review every rule before importing.\n")
    return written


def to_zip_bytes(art: dict) -> bytes:
    """The same artifact set as one zip (Patterns/, Dictionaries/, INDEX.csv)."""
    buf = io.BytesIO()
    index = ["kind,name,file,term,term_id"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in art["patterns"]:
            z.writestr("Patterns/" + p["filename"], json.dumps(p["rule"], indent=2) + "\n")
            index.append(f"pattern,{p['rule'][0]['name']},Patterns/{p['filename']},{p['term']},{p.get('term_id') or ''}")
        for d in art["dictionaries"]:
            z.writestr("Dictionaries/" + d["filename"], json.dumps(d["rule"], indent=2) + "\n")
            z.writestr("Dictionaries/" + d["values_filename"], d["csv"])
            index.append(f"dictionary,{d['rule'][0]['name']},Dictionaries/{d['filename']},{d['term']},{d.get('term_id') or ''}")
        z.writestr("INDEX.csv", "\n".join(index) + "\n")
    return buf.getvalue()

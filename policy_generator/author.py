"""
author.py — Registry concepts -> PDC Data Identification artifacts.

Each concept's detection seeds become importable methods, in EXACTLY the
envelope format PDC 11's own Export produces (verified against a live
instance's Dictionary_Export/Pattern_Export zips — 95 dictionaries + 42
patterns scanned):

  * detect {type: pattern, regex, signature} -> a DataPattern envelope
        (regexMatch.regex, profilePatterns from the signature,
        metadataHints.aliases from the physical sources, JsonLogic rule)
  * detect {type: dictionary, values}        -> a Dictionary envelope
        (values CSV with header 'Term', similarity-weighted JsonLogic rule)

Import layout mirrors PDC's exports: patterns-import.zip holds one
<name>.json per pattern; dictionaries-import.zip holds one nested
<name>.zip per dictionary (json + csv). Each JSON file is a single
OBJECT — PDC's importer Gson-parses per file and rejects arrays.

Every rule applies the concept's GOVERNED tags (filtered against the
Registry's embedded allow-list — the drift guarantee starts at authoring)
as applyTags {"name": tag}, plus a best-effort assignBusinessTerm action.
Deterministic ids (UUID5 from the rule name); only the lastUpdate/version
timestamps vary between runs. Nothing here talks to PDC — output is files
a steward reviews.
"""
from __future__ import annotations
import io, json, re, time, uuid, zipfile

_NON = re.compile(r"[^A-Za-z0-9]+")
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "pdc-policy-generator")

# structural vocabulary a policy should not stamp on its own
_SKIP_TAGS = {"maskable", "identifier", "record", "table-level"}


def _slug(s):
    return _NON.sub("_", str(s or "")).strip("_").lower() or "term"


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000+0000", time.gmtime())


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


def _actions(tags, term, term_id):
    """applyTags in the live export shape ({'name': tag}); assignBusinessTerm
    is best-effort (no built-in export demonstrates it; unknown JSON fields
    are ignored by PDC's importer, and terms are applied by mapping anyway)."""
    acts = []
    if tags:
        acts.append({"applyTags": [{"name": t} for t in tags]})
    if term:
        bt = {"name": term}
        if term_id:
            bt["id"] = term_id
        acts.append({"assignBusinessTerm": [bt]})
    return acts


def _pattern_def(name, description, category, col_rx, signature, content_rx,
                 tags, term, term_id):
    """A DataPattern envelope, field-for-field like PDC 11's Pattern_Export.
    Confidence weights adapt to the evidence present (regex always; profile
    signature and column hints when the Registry carries them)."""
    parts = []
    if signature:
        parts.append({"*": [{"var": "profilePatternScore"}, "0.30"]})
    if col_rx:
        parts.append({"*": [{"var": "metadataScore"}, "0.30"]})
    regex_w = "%.2f" % (1.0 - 0.3 * len(parts))
    parts.insert(0, {"*": [{"var": "regexScore"}, regex_w]})
    d = {
        "_id": str(uuid.uuid5(_NS, f"pattern:{name}")),
        "name": name,
        "type": "DataPattern",
        "isEnabled": True,
        "rules": [{
            "type": "DataPattern",
            "minSamples": "200",
            "confidenceScore": {"+": parts},
            "condition": {"and": [{">=": [{"var": "confidenceScore"}, 0.5]}]},
            "actions": _actions(tags, term, term_id),
        }],
        "categories": [category],
        "description": description,
        "note": "",
        "lastUpdate": _now_iso(),
        "version": _now_iso(),
        "minSamples": 200,
        "dataEventThreshold": 0.5,
        "regexMatch": {"regex": [content_rx]},
        "builtIn": False,
    }
    if signature:
        d["profilePatterns"] = [signature]
    if col_rx:
        d["metadataHints"] = {"aliases": [{"nameRegex": col_rx, "score": 0.3}]}
    return d


def _dictionary_def(name, description, category, col_rx, tags, term, term_id,
                    csv_name, row_count):
    """A Dictionary envelope, field-for-field like PDC 11's Dictionary_Export
    (server-computed fields — bitset/hll/dictionaryTermId — omitted; PDC
    builds them on import)."""
    d = {
        "_id": str(uuid.uuid5(_NS, f"dictionary:{name}")),
        "name": name,
        "type": "Dictionary",
        "isEnabled": True,
        "rules": [{
            "type": "Dictionary",
            "minSamples": "200",
            "confidenceScore": {"+": [
                {"*": [{"var": "similarity"}, 0.9]},
                {"*": [{"var": "metadataScore"}, 0.1]},
            ]},
            "condition": {"and": [
                {">=": [{"var": "confidenceScore"}, "0.7"]},
                {">=": [{"var": "columnCardinality"}, "1"]},
            ]},
            "actions": _actions(tags, term, term_id),
        }],
        "note": "",
        "description": description,
        "categories": [category],
        "lastUpdate": _now_iso(),
        "version": _now_iso(),
        "rowCount": row_count,
        "csv": csv_name,
        "authoritative": False,
        "language": "en-us",
        "dataEventThreshold": 0.7,
        "builtIn": False,
    }
    if col_rx:
        d["metadataHints"] = {"aliases": [{"nameRegex": col_rx, "score": 0.1}]}
    return d


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
        desc = " ".join(str(c.get("definition") or "").split())[:200] or f"Authored from the {reg.get('glossary')} Registry"
        for seed in seeds:
            kind = (seed or {}).get("type")
            if kind == "pattern" and (seed.get("regex") or "").strip():
                patterns.append({
                    "filename": f"{_slug(prefix)}_{_slug(term)}.json",
                    "term": term, "term_id": c.get("term_id"),
                    "rule": _pattern_def(name, desc, category, col_rx,
                                         (seed.get("signature") or "").strip() or None,
                                         seed["regex"].strip(), tags, term, c.get("term_id")),
                })
            elif kind == "dictionary" and len(seed.get("values") or []) >= 2:
                slug = f"{_slug(prefix)}_{_slug(term)}"
                dictionaries.append({
                    "filename": f"{slug}.json",
                    "values_filename": f"{slug}.csv",
                    "zipname": f"{slug}.zip",
                    "term": term, "term_id": c.get("term_id"),
                    "rule": _dictionary_def(name, desc, category, col_rx, tags, term,
                                            c.get("term_id"), f"{slug}.csv",
                                            len(seed["values"])),
                    "csv": "Term\n" + "\n".join(str(v) for v in seed["values"]) + "\n",
                })
    return {"patterns": patterns, "dictionaries": dictionaries, "skipped": skipped,
            "glossary": reg.get("glossary"), "prefix": prefix}


def patterns_zip_bytes(art: dict) -> bytes:
    """patterns-import.zip — one <name>.json per pattern at the zip root,
    exactly the layout PDC's own Pattern_Export produces (and its Patterns →
    Import accepts)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in art["patterns"]:
            z.writestr(p["filename"], json.dumps(p["rule"], indent=2) + "\n")
    return buf.getvalue()


def dictionaries_zip_bytes(art: dict) -> bytes:
    """dictionaries-import.zip — one nested <name>.zip per dictionary, each
    holding <name>.json + <name>.csv, exactly the layout PDC's own
    Dictionary_Export produces (and its Dictionaries → Import accepts)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in art["dictionaries"]:
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as iz:
                iz.writestr(d["filename"], json.dumps(d["rule"], indent=2) + "\n")
                iz.writestr(d["values_filename"], d["csv"])
            z.writestr(d["zipname"], inner.getvalue())
    return buf.getvalue()


def _index_lines(art: dict) -> list:
    lines = ["kind,name,file,term,term_id"]
    for p in art["patterns"]:
        lines.append(f"pattern,{p['rule']['name']},patterns-import.zip/{p['filename']},{p['term']},{p.get('term_id') or ''}")
    for d in art["dictionaries"]:
        lines.append(f"dictionary,{d['rule']['name']},dictionaries-import.zip/{d['zipname']},{d['term']},{d.get('term_id') or ''}")
    return lines


_README = (
    "Authored by the PDC Policy Generator from the Classification Registry.\n"
    "\n"
    "Import in PDC (Data Operations -> Data Identification Methods):\n"
    "  1. Patterns page      -> Import -> upload patterns-import.zip\n"
    "  2. Dictionaries page  -> Import -> upload dictionaries-import.zip\n"
    "\n"
    "Both zips are in the exact layout PDC's own Export produces. Review\n"
    "every rule before importing (INDEX.csv is the manifest).\n")


def write_out(art: dict, out_dir: str) -> list:
    """Write the import-ready artifacts (patterns-import.zip,
    dictionaries-import.zip, INDEX.csv, README.txt). Returns relative paths."""
    import os
    os.makedirs(out_dir, exist_ok=True)
    written = []

    def wb(rel, data):
        with io.open(os.path.join(out_dir, rel), "wb") as f:
            f.write(data)
        written.append(rel)

    if art["patterns"]:
        wb("patterns-import.zip", patterns_zip_bytes(art))
    if art["dictionaries"]:
        wb("dictionaries-import.zip", dictionaries_zip_bytes(art))
    wb("INDEX.csv", ("\n".join(_index_lines(art)) + "\n").encode("utf-8"))
    wb("README.txt", _README.encode("utf-8"))
    return written


def to_zip_bytes(art: dict) -> bytes:
    """One download: the two import-ready zips + manifest + README."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if art["patterns"]:
            z.writestr("patterns-import.zip", patterns_zip_bytes(art))
        if art["dictionaries"]:
            z.writestr("dictionaries-import.zip", dictionaries_zip_bytes(art))
        z.writestr("INDEX.csv", "\n".join(_index_lines(art)) + "\n")
        z.writestr("README.txt", _README)
    return buf.getvalue()

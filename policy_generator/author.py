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
as applyTags {"name": tag}, plus an applyBusinessTerms term binding.
Deterministic ids (UUID5 from the rule name); only the lastUpdate/version
timestamps vary between runs. Nothing here talks to PDC — output is files
a steward reviews.
"""
from __future__ import annotations
import csv, io, json, re, time, uuid, zipfile

_NON = re.compile(r"[^A-Za-z0-9]+")
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "pdc-policy-generator")

# structural vocabulary a policy should not stamp on its own
_SKIP_TAGS = {"maskable", "identifier", "record", "table-level"}

# Types whose VALUES PDC cannot content-match. It evaluates a pattern's regex
# and a dictionary's vocabulary against a column's values; a bit column has none
# to evaluate. Proven live 2026-08-20 — two BIT columns tagged nothing under a
# regex AND under a hand-built {0,1} dictionary, while every NUMERIC sibling
# tagged correctly. The Registry stops seeding these from 1.38.34; this is the
# belt to that braces, because an older contract will still offer them.
_BOOLEAN_TYPES = {"bit", "bool", "boolean", "tinyint(1)"}


def _is_boolean_concept(concept):
    types = [str(v or "").strip().lower() for v in (concept.get("source_types") or {}).values()]
    types = [t for t in types if t]
    return bool(types) and all(t in _BOOLEAN_TYPES for t in types)


def _slug(s):
    return _NON.sub("_", str(s or "")).strip("_").lower() or "term"


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000+0000", time.gmtime())


def column_name_regex(sources):
    """Case-insensitive column-name hint from the concept's physical sources
    ('schema.table.column' / 'bucket/folder/file'), e.g. ['x.members.mbr_no']
    -> (?i)(mbr_?no). Returns None when no usable names exist.

    P6 (2026-08-25 walk, the cross-fire verdict): a SINGLE-token name
    anchors — (?i)(^status$) — because a substring 'status' hint "agrees"
    with every column CONTAINING the token (account_status, system_status,
    pump_status), which is how the four generic Status dictionaries claimed
    the whole family despite the 0.5/0.5 tightening. Multi-token names keep
    the substring form: account_?status can only ever match its own column,
    and prefixed variants (tbl_account_status) still deserve the claim."""
    parts = []
    for src in sources or []:
        name = str(src).replace("/", ".").split(".")[-1].strip()
        toks = [re.escape(t) for t in re.split(r"[^A-Za-z0-9]+", name) if t]
        if toks:
            p = "_?".join(toks) if len(toks) > 1 else f"^{toks[0]}$"
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
    """ONE action object carrying applyTags (live export shape, {'name': tag})
    plus the term binding. PDC's import validator walks every action object
    and requires a tag in each ('No Tag found in Rule'), so the term binding
    must ride in the SAME object as the tags — never its own.

    The binding field is applyBusinessTerms [{name, id}] — PDC 11's LIVE
    schema name, verified round-trip on 2026-07-17. The assignBusinessTerm
    spelling this app emitted through 1.7.x is NOT in the live schema and the
    importer silently dropped it (the binding never reached PDC). Note the
    importer rewrites an id it cannot resolve to the term name, which is why
    the deploy stage re-stamps Registry ids after import."""
    act = {"applyTags": [{"name": t} for t in tags]}
    if term:
        bt = {"name": term}
        if term_id:
            bt["id"] = term_id
        act["applyBusinessTerms"] = [bt]
    return [act]


def _pattern_def(name, description, category, col_rx, signature, content_rx,
                 tags, term, term_id, identity=None):
    """A DataPattern envelope, field-for-field like PDC 11's Pattern_Export.
    Confidence weights adapt to the evidence present (regex always; profile
    signature and column hints when the Registry carries them).

    `identity="column_name"` marks a NAME-ANCHORED seed: the steward flipped a
    concept whose values carry no identifying shape (a date, a bounded measure
    like pH or Lead ppb) to Auto, declaring the column NAME authoritative. The
    content regex is then only a sanity check, so the blend rebalances to name
    0.5 + regex 0.5 and the rule fires only when BOTH agree — under the stock
    weights the name could never carry a rule past the gate on its own, and
    trusting the shape alone would tag every numeric column in the estate. The
    cardinality guard is PDC's own shipped-template guard: a constant column
    cannot satisfy a sanity shape.

    A profile signature still rides such a rule at weight 0 — informative,
    inert — because a flipped date DOES carry a dddd-dd-dd signature and
    dropping it would lose evidence PDC's own screens show."""
    named = identity == "column_name" and bool(col_rx)
    parts = []
    if named:
        parts = [{"*": [{"var": "metadataScore"}, "0.50"]},
                 {"*": [{"var": "regexScore"}, "0.50"]}]
        if signature:
            parts.append({"*": [{"var": "profilePatternScore"}, "0.00"]})
    else:
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
            "minSamples": "1",
            "confidenceScore": {"+": parts},
            # A name-anchored rule gates HIGHER (0.7, not 0.5) and nothing else
            # changes, because a DataPattern condition may not mention
            # columnCardinality. PDC's importer says so outright —
            #   IllegalStateException: [columnCardinality] variable present in
            #   rule.condition is not valid
            # — and then reports the worker COMPLETED with FAILED 1 / TOTAL 1,
            # so the rejection reads as success unless you open the payload.
            # The clause was borrowed from the shipped "Personal Data
            # Identifier" template, which is a DICTIONARY: cardinality is legal
            # there and illegal here. The constant-column guard it was meant to
            # provide is therefore not available to patterns; the name-AND-shape
            # conjunction in the 0.5/0.5 blend against the 0.7 gate is what
            # keeps such a rule honest.
            # The threshold is a STRING, and that is not cosmetic. PDC's
            # JsonLogic evaluator does not coerce: a rule comparing
            # confidenceScore against the NUMBER 0.5 never becomes true, so the
            # method imports cleanly, reports drift-clean, and silently never
            # fires. Live-proven on 2026-08-20 — our dictionaries (string
            # thresholds) tagged columns in the same identification run where
            # every pattern (numeric) tagged nothing, and PDC's own built-in
            # USA_SSN pattern gates on "0.5". Failing at MATCH time makes this
            # worse than the columnCardinality bug, which at least was rejected
            # at import.
            "condition": {"and": [{">=": [{"var": "confidenceScore"},
                                          "0.7" if named else "0.5"]}]},
            "actions": _actions(tags, term, term_id),
        }],
        "categories": [category],
        "description": description,
        "note": "",
        "lastUpdate": _now_iso(),
        "version": _now_iso(),
        "minSamples": 1,
        "dataEventThreshold": 0.5,
        "regexMatch": {"regex": [content_rx]},
        "builtIn": False,
    }
    if signature:
        d["profilePatterns"] = [signature]
    if col_rx:
        # the alias score mirrors the blend's name weight, so the hint and the
        # confidence formula never tell PDC two different stories
        d["metadataHints"] = {"aliases": [{"nameRegex": col_rx,
                                           "score": 0.5 if named else 0.3}]}
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
            "minSamples": "1",
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
        if _r.is_mapping_only(c):
            # The steward declared no detectable shape exists (the contract's
            # optional detection_intent field) — Apply-based governance is the
            # whole story, so no method is authored even if seeds linger, and
            # drift-check never expects (or reports missing) a method for it.
            skipped.append({"term": term, "intent": _r.INTENT_MAPPING_ONLY,
                            "why": "mapping-only by steward decision — no detectable "
                                   "shape exists; the Glossary app's Apply step stamps "
                                   "term, tags and sensitivity on the mapped columns"})
            continue
        if not seeds:
            skipped.append({"term": term,
                            "why": "no detection seed in the Registry (no induced format or reference list)"})
            continue
        col_rx = column_name_regex(c.get("sources"))
        tags = _rule_tags(c, allow)
        if _is_boolean_concept(c):
            skipped.append({"term": term,
                            "why": "boolean column — PDC matches patterns and dictionaries "
                                   "against column VALUES, and a bit column has none, so any "
                                   "method here would import, pass drift, and never fire; "
                                   "governed by the term↔column link instead"})
            continue
        if not tags:
            # PDC's import validator rejects a rule with no tag — and a method
            # that stamps nothing governs nothing. Fix the tags glossary-side.
            skipped.append({"term": term,
                            "why": "no governed tags survive the allow-list filter "
                                   "(a method must stamp at least one governed tag)"})
            continue
        name = f"{prefix} {term}"
        category = f"{_slug(prefix).upper()}_{_slug(c.get('category') or 'General').title().replace('_', '')}"
        desc = " ".join(str(c.get("definition") or "").split())[:200] or f"Authored from the {reg.get('glossary')} Registry"
        for seed in seeds:
            kind = (seed or {}).get("type")
            if kind == "pattern" and (seed.get("regex") or "").strip():
                patterns.append({
                    "filename": f"{_slug(prefix)}_{_slug(term)}.json",
                    "term": term, "term_id": c.get("term_id"),
                    # what the rule rests on, carried through to the review
                    # manifest: a name-anchored rule is a weaker claim than a
                    # profiled shape and the steward must be able to see which
                    # is which without opening the JSON
                    "evidence": (seed.get("source") or "profiled"),
                    "rule": _pattern_def(name, desc, category, col_rx,
                                         (seed.get("signature") or "").strip() or None,
                                         seed["regex"].strip(), tags, term, c.get("term_id"),
                                         identity=seed.get("identity")),
                })
            elif kind == "dictionary" and len(seed.get("values") or []) >= 2:
                slug = f"{_slug(prefix)}_{_slug(term)}"
                dictionaries.append({
                    "filename": f"{slug}.json",
                    "evidence": (seed.get("source") or "profiled"),
                    "values_filename": f"{slug}.csv",
                    "zipname": f"{slug}.zip",
                    "term": term, "term_id": c.get("term_id"),
                    "rule": _dictionary_def(name, desc, category, col_rx, tags, term,
                                            c.get("term_id"), f"{slug}.csv",
                                            len(seed["values"])),
                    "csv": _csv([("Term",)] + [(str(v),) for v in seed["values"]]),
                    # kept only until the shared-vocabulary pass below, then dropped
                    "_values": frozenset(str(v).strip().lower()
                                         for v in seed["values"] if str(v).strip()),
                })
    # Dictionaries whose VALUE SETS collide cross-fire: PDC's dictionary
    # confidence is similarity x 0.9 + metadataScore x 0.1, so a name anchor
    # can only nudge, never veto — on this estate the four per-context Status
    # vocabularies (Active/Inactive/...) each bound their term onto every
    # status-shaped column, 57 unexpected bindings in one identification run
    # (read-back, 2026-08-23). The Registry knows every value set, so the
    # collision is computable at author time: where two dictionaries share
    # >= half of the smaller vocabulary, the blend rebalances to
    # similarity 0.5 + metadataScore 0.5 against the same "0.7" gate — values
    # alone (0.5) can no longer pass, the column NAME must agree. Same
    # conjunction the name-anchored patterns already use. Non-overlapping
    # dictionaries keep the loose blend: their values alone ARE proof.
    for i, a in enumerate(dictionaries):
        partners = []
        for j, b in enumerate(dictionaries):
            if i == j or not a["_values"] or not b["_values"]:
                continue
            inter = len(a["_values"] & b["_values"])
            if inter and inter / min(len(a["_values"]), len(b["_values"])) >= 0.5:
                partners.append(b["term"])
        hints = (a["rule"].get("metadataHints") or {}).get("aliases")
        if partners and hints:
            a["rule"]["rules"][0]["confidenceScore"] = {"+": [
                {"*": [{"var": "similarity"}, 0.5]},
                {"*": [{"var": "metadataScore"}, 0.5]},
            ]}
            # the alias score mirrors the blend's name weight, so the hint and
            # the confidence formula never tell PDC two different stories
            hints[0]["score"] = 0.5
            a["shared_vocabulary_with"] = sorted(partners)
    for a in dictionaries:
        a.pop("_values", None)
    # A content regex claimed by more than one method identifies none of them:
    # on the Arizona estate one induced shape backed EIGHT concepts, and a
    # free-text column came back bound to all eight. The Registry now marks such
    # seeds name-anchored (1.38.34), but a Registry written before that — or by
    # anything else — still can, so say so where a steward will see it.
    by_regex = {}
    for pat in patterns:
        rx = ((pat["rule"].get("regexMatch") or {}).get("regex") or [None])[0]
        if rx:
            by_regex.setdefault(rx, []).append(pat)
    # P1 (2026-08-25 walk): a shape shared ONLY by name-anchored methods is
    # safe BY CONSTRUCTION — their 0.5/0.5 blend against the gate means the
    # column name must agree, so the shared sanity half identifies nothing on
    # its own. Rendering those red trained the steward to ignore the warning
    # (W13's rule). Profiled claimants stay red: their regexScore weight alone
    # crosses the gate, so the shape really is the claim.
    ambiguous, anchored = [], []
    for rx, pats in by_regex.items():
        if len(pats) < 2:
            continue
        entry = {"regex": rx, "terms": sorted(p["term"] for p in pats)}
        if all(str(p.get("evidence") or "") == "name-anchored" for p in pats):
            anchored.append(entry)
        else:
            ambiguous.append(entry)

    # P6 doctrine: table-qualified twins — dictionaries whose column is the
    # SAME bare generic token — are undetectable distinctly by construction:
    # the name cannot disambiguate them and PDC hints carry no table scope,
    # so whenever their vocabularies overlap in the DATA they claim each
    # other's columns (the walk proved it: account_alerts.status and
    # tiered_rates.status came back wearing both terms). Keyed on the bare
    # token, NOT on seed-value overlap — the seeds can differ while the live
    # columns still overlap, which is exactly what happened. The steward
    # should hear "declare these mapping-only" HERE, not from a read-back
    # probe; their term↔column links already govern the right tables.
    by_token = {}
    for d in dictionaries:
        hint = ((d["rule"].get("metadataHints") or {}).get("aliases")
                or [{}])[0].get("nameRegex") or ""
        bare = re.fullmatch(r"\(\?i\)\((\^[a-z0-9]+\$)\)", hint)
        if bare:
            by_token.setdefault(bare.group(1).strip("^$"), []).append(d["term"])
    twins = [{"term": t, "column": tok,
              "partners": sorted(x for x in terms if x != t)}
             for tok, terms in by_token.items() if len(terms) > 1
             for t in sorted(terms)]

    return {"patterns": patterns, "dictionaries": dictionaries, "skipped": skipped,
            "ambiguous_shapes": ambiguous, "anchored_shapes": anchored,
            "vocabulary_twins": twins,
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


def _csv(rows) -> str:
    """RFC 4180 CSV. Values are DATA, and estate data contains commas.

    The dictionary CSV is one column, and joining the values with newlines
    split a value like "Expanding metro area, new customer acquisition,
    infrastructure growth" into three fields. PDC's importer is stricter than
    the emitter was: it read a 1-column header, hit a 3-field row, threw
    CSVFieldNumDifferentException — and abandoned the REST OF THE ZIP. Deploy
    reported COMPLETED; 13 dictionaries queued before the bad row had landed
    and the 18 after it had not, with nothing on screen saying why
    (field-caught 2026-08-21 on the Arizona estate).
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for r in rows:
        w.writerow(list(r))
    return buf.getvalue()


def _index_lines(art: dict) -> list:
    rows = [("kind", "name", "file", "term", "term_id")]
    for p in art["patterns"]:
        rows.append(("pattern", p["rule"]["name"],
                     f"patterns-import.zip/{p['filename']}", p["term"],
                     p.get("term_id") or ""))
    for d in art["dictionaries"]:
        rows.append(("dictionary", d["rule"]["name"],
                     f"dictionaries-import.zip/{d['zipname']}", d["term"],
                     d.get("term_id") or ""))
    # a term name carrying a comma would break this manifest the same way
    return _csv(rows).rstrip("\n").split("\n")


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

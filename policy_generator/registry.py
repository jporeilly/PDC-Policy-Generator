"""
registry.py — load and validate the Classification Registry the Glossary
Generator writes at export time (`classification-registry/1`).

The Registry is the contract between the two apps: one concept per governed
term, carrying everything this app needs to author, bind and drift-check
PDC Data Identification methods. See docs/CONTRACT.md for the field-by-field
schema. Loading is strict about the envelope (schema id, concepts list) and
tolerant about optional per-concept fields, so older Registries still load.
"""
from __future__ import annotations
import glob
import json
import os
import time

SCHEMA = "classification-registry/1"

# The optional per-concept detection_intent values (1.9.0, backward
# compatible — absent means unknown, exactly how pre-1.9 Registries read):
#   "seeded"       — detection seeds exist (the normal authorable case)
#   "mapping_only" — the steward explicitly decided no detectable shape
#                    exists; the Glossary app's Apply step is the whole
#                    governance story, so no method should ever exist
INTENT_SEEDED = "seeded"
INTENT_MAPPING_ONLY = "mapping_only"


class RegistryError(ValueError):
    """The file is not a usable Classification Registry."""


def validate_registry(reg) -> dict:
    """Validate an already-parsed Registry envelope. Returns the dict; raises
    RegistryError with a plain-language reason when the envelope is wrong."""
    if not isinstance(reg, dict):
        raise RegistryError("top level must be a JSON object")
    if reg.get("schema") != SCHEMA:
        raise RegistryError(
            f"schema is {reg.get('schema')!r}, expected {SCHEMA!r} — is this a "
            "file the Glossary Generator wrote to registries/?")
    if not isinstance(reg.get("concepts"), list):
        raise RegistryError("missing concepts[] — an empty glossary was exported?")
    return reg


def load_registry(path: str) -> dict:
    """Read + validate a Registry file. Returns the dict; raises RegistryError
    with a plain-language reason when the envelope is wrong."""
    try:
        with open(path, encoding="utf-8") as f:
            reg = json.load(f)
    except FileNotFoundError:
        raise RegistryError(f"no such file: {path}")
    except json.JSONDecodeError as e:
        raise RegistryError(f"not valid JSON ({e})")
    return validate_registry(reg)


def discover_registries() -> list:
    """Find Registry files the Glossary Generator wrote, no configuration
    needed. Looks (in order) at POLICY_REGISTRY_DIR, then for a
    glossary_generator/registries/ folder in this repo's parent — the layout
    when this repo is cloned inside the Glossary checkout (~/PDC-Demo) — and
    finally in sibling Glossary checkouts. Newest first."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
    parent = os.path.dirname(root)                # the folder the repo was cloned into
    candidates = []
    env = os.environ.get("POLICY_REGISTRY_DIR")
    if env:
        candidates.append(env)
    candidates += [
        os.path.join(parent, "glossary_generator", "registries"),
        os.path.join(parent, "PDC-Demo", "glossary_generator", "registries"),
        os.path.join(parent, "PDC-Glossary", "glossary_generator", "registries"),
        os.path.join(parent, "PDC-Glossary-Generator", "glossary_generator", "registries"),
    ]
    found = []
    for d in candidates:
        if os.path.isdir(d):
            found += glob.glob(os.path.join(d, "registry.*.json"))
    uniq = sorted({os.path.abspath(p) for p in found}, key=os.path.getmtime, reverse=True)
    return uniq


def governed_tags(reg: dict) -> set:
    """The governed tag allow-list embedded in the Registry (lower-case)."""
    vocab = reg.get("tag_vocabulary") or {}
    return {str(t).strip().lower() for t in (vocab.get("allow_list") or []) if str(t).strip()}


def detection_intent(concept) -> str | None:
    """The steward's declared detection intent for a concept — the OPTIONAL
    contract field added in 1.9.0. Returns 'seeded', 'mapping_only', or None
    when the Registry predates the field / the steward has not decided."""
    v = str(((concept or {}) if isinstance(concept, dict) else {})
            .get("detection_intent") or "").strip().lower()
    return v or None


def is_mapping_only(concept) -> bool:
    """True when the steward declared no detectable shape exists for this
    concept — Apply-based governance only, so no method should ever exist."""
    return detection_intent(concept) == INTENT_MAPPING_ONLY


def seeded_concepts(reg: dict):
    """Concepts that carry at least one detection seed — the authorable set.
    A mapping_only concept is never authorable, even if seeds linger."""
    return [c for c in reg.get("concepts", [])
            if isinstance(c, dict) and (c.get("detect") or []) and not is_mapping_only(c)]


def unresolved_terms(reg: dict) -> list:
    """Concept names whose term_id is still null (glossary not imported /
    Resolve not run) — deploy binds by name only for these, which is weaker."""
    return [c.get("term_name") for c in reg.get("concepts", [])
            if isinstance(c, dict) and not c.get("term_id")]


def write_seed_request(dir_path: str, registry_file: str, terms: list) -> str:
    """Write seed-request.json into the directory the Registry was loaded
    from (the shared registries/ folder in the PDC-Demo layout) so the
    Glossary app can discover which governed terms still need a detection
    seed — the return channel of the no-seed loop. Overwrites any previous
    request (the newest ask is the only one that matters). Returns the path."""
    payload = {
        "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registry_file": registry_file,
        "terms": [{"name": str(t).strip(), "reason": "no_seed"}
                  for t in terms if str(t).strip()],
    }
    path = os.path.join(dir_path, "seed-request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return path


def summary(reg: dict) -> dict:
    """One-line stats for CLI output."""
    concepts = [c for c in reg.get("concepts", []) if isinstance(c, dict)]
    return {
        "glossary": reg.get("glossary"),
        "glossary_id": reg.get("glossary_id"),
        "concepts": len(concepts),
        "seeded": len(seeded_concepts(reg)),
        "resolved_term_ids": sum(1 for c in concepts if c.get("term_id")),
        "governed_tags": len(governed_tags(reg)),
        "off_vocabulary": sum(1 for c in concepts if c.get("off_vocabulary_tags")),
    }

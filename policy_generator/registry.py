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

SCHEMA = "classification-registry/1"


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


def seeded_concepts(reg: dict):
    """Concepts that carry at least one detection seed — the authorable set."""
    return [c for c in reg.get("concepts", [])
            if isinstance(c, dict) and (c.get("detect") or [])]


def unresolved_terms(reg: dict) -> list:
    """Concept names whose term_id is still null (glossary not imported /
    Resolve not run) — deploy binds by name only for these, which is weaker."""
    return [c.get("term_name") for c in reg.get("concepts", [])
            if isinstance(c, dict) and not c.get("term_id")]


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

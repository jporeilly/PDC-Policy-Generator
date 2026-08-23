"""api.py — the Policy Generator's web layer (FastAPI, single user, local-first).

Same shape as before the port: a thin layer over the engine the CLI drives
(registry / author / pdc modules, all unchanged). Run with:

    uvicorn policy_generator.api:app --port 5001

Serves the React UI from frontend/dist at / and auto-generated API docs at
/docs. The /api/* contract matches the original Flask app route-for-route.
"""
import datetime
import io
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from policy_generator import (
    __version__,
    author as author_mod,
    drift as drift_mod,
    pdc as pdc_mod,
    registry as registry_mod,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_DIST = REPO_ROOT / "frontend" / "dist"

app = FastAPI(
    title="Policy Generator",
    version=__version__,
    description=(
        "**[← Back to the Policy Generator](/)**\n\n"
        "Reads the Glossary Generator's Classification Registry and manages PDC's "
        "Data Identification side of the contract: author import-ready Data Patterns "
        "and Dictionaries, reconcile term ids against a live PDC, deploy the authored "
        "set over the import API, drift-check the deployed methods against the "
        "Registry, and retire an authored method set."
    ),
)

# Single-user local app: the last loaded Registry is the working state.
# The PDC token is held in memory for this session only — never saved.
_state = {"reg": None, "name": None,
          "path": None,           # abs path when loaded by path (None = uploaded)
          "pdc": None,            # {base, version, verify_tls, token}
          "reconcile": None}      # last reconcile rows (for apply)


# --------------------------------------------------------------------------- #
#  Models (the Swagger contract)
# --------------------------------------------------------------------------- #
class RegistrySummary(BaseModel):
    glossary: str | None = None
    glossary_id: str | None = None
    concepts: int
    seeded: int
    resolved_term_ids: int
    governed_tags: int
    off_vocabulary: int
    file: str | None = None
    unresolved: int | None = None
    applied: int | None = None


class RegistryListItem(BaseModel):
    path: str
    file: str
    modified: str
    glossary: str | None = None
    concepts: int | None = None


class PdcConnectRequest(BaseModel):
    base_url: str
    version: str = "v3"
    verify_tls: bool = False
    username: str | None = None
    password: str | None = None
    token: str | None = None
    realm: str = "pdc"


class ReconcileRequest(BaseModel):
    offset: int = 0
    limit: int | None = None


class PrefixRequest(BaseModel):
    prefix: str | None = None


class RetireRequest(BaseModel):
    prefix: str
    ids: list[str] | None = None


class DeployRequest(BaseModel):
    prefix: str | None = None
    dry_run: bool = False
    bind: bool = True          # re-stamp Registry term ids after import
    wait_seconds: int = 120    # per import worker
    allow_name_binding: bool = False   # deploy anyway, with weak bindings


class BuiltInsRequest(BaseModel):
    enabled: bool = False       # False disables the built-ins, True restores them
    dry_run: bool = True        # a 137-method write is never the default
    kind: str | None = None     # "Dictionary" | "DataPattern"; both when absent


class EntityLookupRequest(BaseModel):
    q: str                      # a table/file name, or part of one
    limit: int = 25


class EntityDetailRequest(BaseModel):
    id: str | None = None       # an entity id, when you have one
    name: str | None = None     # or a name to look up first
    raw: bool = False           # include the whole payload, not just the summary


class MethodDetailRequest(BaseModel):
    name: str | None = None     # method name, e.g. "USA_SSN"
    id: str | None = None       # or its _id
    kind: str | None = None     # "DataPattern" | "Dictionary"; inferred when absent


class JobStatusRequest(BaseModel):
    id: str | None = None       # a job id from /api/pdc/identify
    recent: int = 0             # or list the N most recent workers instead


class IdentifiedRequest(BaseModel):
    tables: list[str]           # table names, e.g. ["customers"]
    prefix: str | None = None   # the authored set to judge against


class IdentifyRequest(BaseModel):
    prefix: str
    scope: list[str]           # entity ids the bulk job is limited to
    allow_stale_profile: bool = False   # run anyway against an old profile


class DriftRequest(BaseModel):
    prefix: str | None = None


class SeedRequestBody(BaseModel):
    terms: list[str]


# --------------------------------------------------------------------------- #
#  App + registry
# --------------------------------------------------------------------------- #
@app.get("/api/version")
def version() -> dict:
    return {"version": __version__, "service": "policy-generator"}


@app.get("/changelog", response_class=PlainTextResponse, include_in_schema=False)
def changelog() -> str:
    path = REPO_ROOT / "CHANGELOG.md"
    return path.read_text(encoding="utf-8") if path.exists() else "No changelog available."


@app.get("/api/registries", response_model=dict)
def api_registries() -> dict:
    """Registries auto-discovered from a co-located Glossary checkout
    (nested ~/PDC-Demo clone, sibling checkout, or POLICY_REGISTRY_DIR)."""
    out = []
    for p in registry_mod.discover_registries()[:20]:
        # A registries directory is shared ground: the Glossary app writes and
        # rewrites files there, and this app can now delete them, so a path can
        # vanish between the glob and the stat. A listing that raises over a file
        # that is already gone is no use to anyone — skip it and list the rest.
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        item = {"path": p, "file": os.path.basename(p),
                "modified": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                "glossary": None, "concepts": None}
        try:
            with open(p, encoding="utf-8") as f:
                reg = registry_mod.validate_registry(json.load(f))
            item["glossary"] = reg.get("glossary")
            item["concepts"] = len(reg.get("concepts") or [])
        except Exception:
            pass  # unreadable/foreign file: listed, not loadable
        out.append(RegistryListItem(**item))
    return {"registries": [r.model_dump() for r in out]}


@app.delete("/api/registries")
def api_registry_delete(path: str) -> dict:
    """Delete one discovered Registry file. Scoped hard: the path must be a file
    this app's own discovery returned, so a stray path can never make this a
    delete-anything endpoint. The Glossary writes these; a lab machine
    accumulates one per glossary version, and clearing the stale ones is
    housekeeping the steward should not have to do in Explorer.

    The loaded Registry stays loaded when its file goes — the working copy lives
    in memory and may carry reconciled ids that only exist there."""
    target = os.path.abspath(path or "")
    known = {os.path.abspath(p) for p in registry_mod.discover_registries()}
    if target not in known:
        raise HTTPException(
            status_code=400,
            detail="not a discovered Registry file — delete is scoped to the registries "
                   "this app lists, never an arbitrary path")
    try:
        os.remove(target)
    except OSError as e:
        raise HTTPException(status_code=502, detail=f"could not delete the Registry file: {e}")
    remaining = api_registries()
    return {"deleted": os.path.basename(target),
            "was_loaded": _state["name"] == os.path.basename(target),
            **remaining}


def _summary_payload() -> RegistrySummary:
    s = registry_mod.summary(_state["reg"])
    s["file"] = _state["name"]
    s["unresolved"] = len(registry_mod.unresolved_terms(_state["reg"]))
    return RegistrySummary(**s)


@app.post("/api/load", response_model=RegistrySummary)
async def api_load(registry: UploadFile | None = None, path: str | None = None) -> RegistrySummary:
    """Load the working Registry: upload the file, or give a local path
    (e.g. one returned by /api/registries)."""
    try:
        if registry is not None:
            try:
                data = json.load(io.TextIOWrapper(registry.file, encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise registry_mod.RegistryError(f"not valid JSON ({e})")
            reg, name, src = registry_mod.validate_registry(data), registry.filename, None
        elif path:
            reg, name = registry_mod.load_registry(path), os.path.basename(path)
            src = os.path.abspath(path)
        else:
            raise registry_mod.RegistryError("no Registry supplied — upload a file or give a path")
    except registry_mod.RegistryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"could not read Registry: {e}")
    _state["reg"], _state["name"], _state["path"] = reg, name, src
    _state["reconcile"] = None
    return _summary_payload()


@app.get("/api/summary", response_model=RegistrySummary)
def api_summary() -> RegistrySummary:
    _require_registry()
    return _summary_payload()


def _require_registry() -> None:
    if _state["reg"] is None:
        raise HTTPException(status_code=400, detail="load a Registry first")


def _require_pdc() -> dict:
    if not _state["pdc"]:
        raise HTTPException(status_code=400, detail="connect to PDC first")
    return _state["pdc"]


# --------------------------------------------------------------------------- #
#  Author
# --------------------------------------------------------------------------- #
# Why a seedless concept is *correctly* method-less — presentation-side
# classification so the UI can group the skipped list by governance mechanism.
_B_STRUCTURAL = re.compile(r"\b(record|records|report|register|entry|root|documents?|summary)\s*$", re.I)
_B_FREETEXT = re.compile(r"\b(notes?|text|memo|narrative|description|details?|comments?)\b", re.I)
_B_SEEDABLE = re.compile(r"\b(ssn|social security|e-?mail|phone|zip|postal|city|state|address|iban|swift|routing)\b", re.I)


def _bucket(term):
    t = term or ""
    if _B_SEEDABLE.search(t):
        return "seed"
    if _B_STRUCTURAL.search(t):
        return "structural"
    if _B_FREETEXT.search(t):
        return "rule"
    return "mapping"


def _author_or_400(prefix):
    _require_registry()
    try:
        return author_mod.author(_state["reg"], prefix=prefix)
    except registry_mod.RegistryError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _hint(r):
    aliases = (r.get("metadataHints") or {}).get("aliases") or []
    return aliases[0].get("nameRegex") if aliases else None


def _tags(r):
    return [t["name"] for rl in r.get("rules", [])
            for a in rl.get("actions", []) for t in a.get("applyTags", [])]


@app.post("/api/preview")
def api_preview(body: PrefixRequest | None = None) -> dict:
    """What author would emit, without writing anything — the review manifest."""
    art = _author_or_400((body.prefix if body else None) or None)

    def _pat(p):
        r = p["rule"]
        return {"name": r["name"], "term": p["term"], "term_id": p.get("term_id") or None,
                "kind": "pattern", "evidence": p.get("evidence") or "profiled",
                "regex": (r.get("regexMatch") or {}).get("regex", [None])[0],
                "signature": (r.get("profilePatterns") or [None])[0],
                "column_hint": _hint(r), "tags": _tags(r), "rule": r}

    def _dic(d):
        r = d["rule"]
        values = [v for v in d["csv"].splitlines()[1:] if v]
        return {"name": r["name"], "term": d["term"], "term_id": d.get("term_id") or None,
                "kind": "dictionary", "evidence": d.get("evidence") or "profiled",
                "values": values[:200], "values_count": len(values),
                "column_hint": _hint(r), "tags": _tags(r), "rule": r}

    # A steward-declared intent beats the name heuristics: mapping_only
    # concepts land in their own calm bucket, never the amber seed one.
    return {
        "prefix": art["prefix"],
        "ambiguous_shapes": art.get("ambiguous_shapes") or [],
        "patterns": [_pat(p) for p in art["patterns"]],
        "dictionaries": [_dic(d) for d in art["dictionaries"]],
        "skipped": [dict(s, bucket=("mapping_only" if s.get("intent") == "mapping_only"
                                    else _bucket(s["term"])))
                    for s in art["skipped"]],
    }


@app.post("/api/author")
def api_author(body: PrefixRequest | None = None) -> Response:
    """The import-ready artifact set as one zip download."""
    prefix = (body.prefix if body else None) or None
    art = _author_or_400(prefix)
    zbytes = author_mod.to_zip_bytes(art)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (prefix or _state["name"] or "methods")).strip("-").lower()
    return Response(
        content=zbytes, media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="{slug or "methods"}-data-identification.zip"'},
    )


@app.post("/api/seed-request")
def api_seed_request(body: SeedRequestBody) -> dict:
    """Write seed-request.json beside the loaded Registry (the shared
    registries/ folder in the PDC-Demo layout) listing the governed terms
    that still need a detection seed — the return channel of the no-seed
    loop, discoverable by the Glossary app. File schema:
    {requested_at, registry_file, terms: [{name, reason: "no_seed"}]}."""
    _require_registry()
    if not _state.get("path"):
        raise HTTPException(
            status_code=400,
            detail="the Registry was uploaded, not loaded from the shared registries/ "
                   "folder — load it by path (the discovered list on the Load page) so "
                   "the seed request can be written beside it for the Glossary app to find")
    terms = [str(t).strip() for t in body.terms if str(t).strip()]
    if not terms:
        raise HTTPException(status_code=400, detail="no terms to request seeds for")
    try:
        written = registry_mod.write_seed_request(
            os.path.dirname(_state["path"]), os.path.basename(_state["path"]), terms)
    except OSError as e:
        raise HTTPException(status_code=502, detail=f"could not write the seed request: {e}")
    return {"written": written, "file": os.path.basename(written), "terms": len(terms)}


# --------------------------------------------------------------------------- #
#  Reconcile — verify/bind term ids against a live PDC
# --------------------------------------------------------------------------- #
@app.post("/api/pdc/connect")
def api_pdc_connect(body: PdcConnectRequest) -> dict:
    """Authenticate once (Keycloak-first, /auth fallback). The token — and,
    for credential logins, the username/password used to mint it — live in
    process memory for this session only, never on disk: the credentials are
    what lets every later call transparently re-authenticate when the
    short-lived Keycloak token expires (see _with_pdc)."""
    base = body.base_url.strip()
    if not base:
        raise HTTPException(status_code=400, detail="PDC base URL is required (e.g. https://pdc.example.com)")
    token = (body.token or "").strip()
    try:
        if not token:
            if not (body.username and body.password):
                raise HTTPException(status_code=400,
                                    detail="username + password (or a bearer token) required")
            token = pdc_mod.auth(base, body.username, body.password, version=body.version,
                                 verify_tls=body.verify_tls, realm=body.realm)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"authentication failed: {e}")
    _state["pdc"] = {"base": pdc_mod.clean_base(base), "version": body.version,
                     "verify_tls": body.verify_tls, "token": token,
                     # in-memory only, never persisted or echoed back: fuels
                     # the transparent re-auth when the Keycloak token expires
                     "username": (body.username or None) if body.password else None,
                     "password": (body.password or None),
                     "realm": body.realm}
    who = pdc_mod.decode_jwt(token)
    return {"ok": True, "base": _state["pdc"]["base"], "version": body.version,
            "username": who.get("username"), "roles": who.get("roles", [])[:8],
            "expires_in": who.get("expires_in")}


def _expired() -> HTTPException:
    _state["pdc"] = None
    return HTTPException(status_code=401, detail="PDC session expired — connect again")


def _refresh_token(p: dict) -> bool:
    """Mint a fresh token with the in-memory credentials (never persisted).
    False when the session was token-only or the IdP refuses — the caller
    then surfaces the honest 401."""
    if not (p.get("username") and p.get("password")):
        return False
    try:
        p["token"] = pdc_mod.auth(p["base"], p["username"], p["password"],
                                  version=p["version"], verify_tls=p["verify_tls"],
                                  realm=p.get("realm") or "pdc")
        return True
    except Exception:
        return False


def _with_pdc(p: dict, call):
    """Run `call(token)`; on a 401 re-authenticate once with the held
    credentials and retry. Keycloak tokens live minutes, a steward's session
    lives hours — so every PDC-touching endpoint (methods list, retire,
    reconcile, deploy, drift) rides through expiry instead of dying with
    'session expired' while the header still shows connected."""
    try:
        return call(p["token"])
    except pdc_mod.TokenExpired:
        if not _refresh_token(p):
            raise _expired()
        try:
            return call(p["token"])
        except pdc_mod.TokenExpired:
            raise _expired()


def _registry_scope_sources():
    """Distinct governed sources from the loaded Registry: the tables and
    file-side CSVs its concepts actually map, with governed-column counts.
    Bucket-path document sources (awc-documents/...) are not identification
    targets and are skipped."""
    tables, files = {}, {}
    for c in _state["reg"].get("concepts", []):
        if not isinstance(c, dict):
            continue
        for s in c.get("sources") or []:
            if not isinstance(s, str) or "/" in s:
                continue
            parts = s.split(".")
            if len(parts) == 3:
                tables[parts[1]] = tables.get(parts[1], 0) + 1
            elif len(parts) == 4 and parts[2].lower() == "csv":
                fn = parts[1] + ".csv"
                files[fn] = files.get(fn, 0) + 1
    return tables, files


@app.get("/api/scope-sources")
def api_scope_sources() -> dict:
    """The governed estate, from the Registry alone (no PDC needed): what an
    identification scope or read-back SHOULD cover. Exists because a human
    recalling the estate under-scopes it silently — the 2026-08-23 walk ran
    'nine tables' for two days while the catalog held eleven targets."""
    _require_registry()
    tables, files = _registry_scope_sources()
    return {"tables": [{"name": t, "governed": n} for t, n in sorted(tables.items())],
            "files": [{"name": f, "governed": n} for f, n in sorted(files.items())]}


@app.post("/api/pdc/scope-candidates")
def api_pdc_scope_candidates() -> dict:
    """The governed estate resolved to PDC entity ids — a ready-made
    identification scope. The Registry names the sources; PDC supplies the
    ids; nobody has to remember either."""
    _require_registry()
    p = _require_pdc()
    tables, files = _registry_scope_sources()
    rows = []

    def _resolve(names, types, kind, counts):
        if not names:
            return
        try:
            ents = _with_pdc(p, lambda tok: pdc_mod.filter_entities(
                p["base"], tok, {"names": sorted(names), "types": types},
                version=p["version"], verify_tls=p["verify_tls"]))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"entity lookup failed: {e}")
        byname = {}
        for e in ents:
            a = e.get("attributes") or {}
            nm = str(a.get("name") or e.get("name") or "").lower()
            byname.setdefault(nm, e)
        for n in sorted(names):
            e = byname.get(n.lower())
            rows.append({"label": n, "kind": kind, "governed": counts[n],
                         "id": pdc_mod._eid(e) if e else None})

    _resolve(set(tables), ["TABLE", "VIEW"], "table", tables)
    _resolve(set(files), ["FILE"], "file", files)
    return {"rows": rows,
            "resolved": sum(1 for r in rows if r["id"]),
            "unresolved": [r["label"] for r in rows if not r["id"]],
            "total": len(rows)}


@app.post("/api/pdc/methods")
def api_pdc_methods(body: PrefixRequest | None = None) -> dict:
    """List the custom Data Identification methods in PDC, scoped to a name
    prefix (the app's authored set). Read-only — the preview before a retire."""
    p = _require_pdc()
    prefix = ((body.prefix if body else None) or "").strip() or None
    try:
        rows = _with_pdc(p, lambda tok: pdc_mod.list_methods(
            p["base"], tok, prefix=prefix, verify_tls=p["verify_tls"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"method list failed: {e}")
    return {"methods": rows, "count": len(rows), "prefix": prefix}


@app.post("/api/pdc/retire")
def api_pdc_retire(body: RetireRequest) -> dict:
    """Delete Data Identification methods by _id via GraphQL. Built-ins are
    refused outright; a prefix scope is required so this can never sweep the
    whole catalog. Returns a per-method result list."""
    p = _require_pdc()
    prefix = body.prefix.strip()
    if not prefix:
        raise HTTPException(status_code=400,
                            detail="a name prefix is required — retire is always scoped")
    try:
        rows = _with_pdc(p, lambda tok: pdc_mod.list_methods(
            p["base"], tok, prefix=prefix, verify_tls=p["verify_tls"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"method list failed: {e}")

    # An explicit id allow-list from the client is honoured (a subset of the
    # scoped set); absent it, the whole prefixed set is targeted.
    want = set(body.ids or [])
    results = []
    for m in rows:
        if m.get("builtIn"):
            continue  # never delete a built-in, even if one carries the prefix
        if want and m["_id"] not in want:
            continue
        try:
            rid = _with_pdc(p, lambda tok, m=m: pdc_mod.remove_method(
                p["base"], tok, m["kind"], m["_id"], verify_tls=p["verify_tls"]))
            results.append({**m, "removed": bool(rid), "recordId": rid})
        except HTTPException:
            raise
        except Exception as e:
            results.append({**m, "removed": False, "error": str(e)[:300]})
    removed = sum(1 for r in results if r.get("removed"))
    return {"results": results, "removed": removed,
            "attempted": len(results), "prefix": prefix}


# --------------------------------------------------------------------------- #
#  Deploy — import the authored set into PDC over the discovered import API
# --------------------------------------------------------------------------- #
@app.get("/api/pdc/status")
def api_pdc_status() -> dict:
    """Whether this session holds a live PDC connection (the UI's gate for
    the Deploy and Drift steps)."""
    p = _state.get("pdc")
    if not p:
        return {"connected": False}
    who = pdc_mod.decode_jwt(p["token"])
    return {"connected": True, "base": p["base"],
            "username": who.get("username"), "expires_in": who.get("expires_in"),
            # credential sessions self-heal: expiry re-auths transparently
            "renewable": bool(p.get("username") and p.get("password"))}


def _live_index(p, prefix):
    """Non-built-in methods carrying the prefix, keyed by (kind, name)."""
    rows = _with_pdc(p, lambda tok: pdc_mod.list_methods(
        p["base"], tok, prefix=prefix, verify_tls=p["verify_tls"]))
    return {(m["kind"], m["name"]): m for m in rows if not m.get("builtIn")}


def _worker_report(st: dict) -> dict:
    """What the import worker actually said, beyond COMPLETED. PDC finishes a
    worker that rejected every file, so the deploy table must be able to show
    the reason next to the status rather than inferring failure from absence."""
    md = (st or {}).get("metadata") or {}
    keep = {k: v for k, v in md.items() if k != "status"}
    pipe = {k: v for k, v in ((st or {}).get("pipeline") or {}).items() if k != "metadata"}
    return {k: v for k, v in {**pipe, **keep}.items() if v not in (None, "", [], {})}


@app.post("/api/pdc/deploy")
def api_pdc_deploy(body: DeployRequest | None = None) -> dict:
    """Import the authored method set into PDC programmatically — the path
    PDC 11's own UI zip-upload uses (multipart POST /api/importWorkerFiles,
    discovered live; see pdc.upload_import). Per-method results; `dry_run`
    returns the create/update plan without touching PDC.

    Every method name carries the authoring prefix, so the scoped retire on
    the Reconcile page can always clean up exactly what deploy imported.
    After import, the Registry's minted term ids are re-stamped into each
    method's applyBusinessTerms (the importer rewrites ids it cannot
    resolve); pass bind=false to skip."""
    _require_registry()
    p = _require_pdc()
    body = body or DeployRequest()
    art = _author_or_400((body.prefix or "").strip() or None)
    prefix = art["prefix"]
    if not prefix or len(prefix.strip()) < 2:
        raise HTTPException(status_code=400,
                            detail="a name prefix of at least 2 characters is required — "
                                   "deploy is always scoped so retire can clean it up")
    # A method with no term id binds by NAME, and a rename in PDC then detaches
    # it silently. That is not a warning, it is a defect being deployed: on
    # 2026-08-19 a run went out with 40 of 115 bound by name because Reconcile's
    # ids live in memory and a restart had discarded them between the two steps.
    # Nothing downstream would have told anyone. Deploy is the last moment the
    # app can see it, so it stops here unless the caller insists.
    # The dry run is exempt: it writes nothing, and it is precisely how a
    # steward is meant to FIND this before deploying. It reports the count
    # instead (see the plan payload below).
    nameless = [e for e in drift_mod.expected_methods(art) if not e.get("term_id")]
    if nameless and not body.dry_run and not body.allow_name_binding:
        raise HTTPException(
            status_code=409,
            detail=(f"{len(nameless)} of {len(drift_mod.expected_methods(art))} method(s) have no "
                    f"term id and would bind by NAME, which breaks the moment a term is renamed "
                    f"in PDC. Run Reconcile, then Apply, then deploy in the SAME session — the "
                    f"applied ids live in memory, not in the Registry file. "
                    f"First few: {', '.join(e['term'] for e in nameless[:5])}"
                    + (f" (+{len(nameless) - 5} more)" if len(nameless) > 5 else "")
                    + ". To deploy anyway, set allow_name_binding: true."))

    expected = drift_mod.expected_methods(art)

    try:
        live = _live_index(p, prefix)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"method list failed: {e}")

    if body.dry_run:
        rows = [{"kind": e["kind"], "name": e["name"], "term": e["term"],
                 "term_id": e.get("term_id"),
                 "action": "update" if (e["kind"], e["name"]) in live else "create"}
                for e in expected]
        return {"prefix": prefix, "dry_run": True, "rows": rows,
                "counts": {"create": sum(1 for r in rows if r["action"] == "create"),
                           "update": sum(1 for r in rows if r["action"] == "update")},
                # what a real deploy would refuse over, stated up front
                "name_binding": {
                    "count": len(nameless),
                    "terms": [e["term"] for e in nameless[:10]],
                    "blocks_deploy": bool(nameless),
                    "why": ("these method(s) carry no term id and would bind by name, which "
                            "breaks when a term is renamed in PDC — Reconcile, Apply and deploy "
                            "in one session fixes it") if nameless else None,
                }}

    # one importer worker per artifact kind, exactly like the UI's zip upload
    workers = []
    try:
        if art["patterns"]:
            w = _with_pdc(p, lambda tok: pdc_mod.upload_import(
                p["base"], tok, "DataPattern", "patterns-import.zip",
                author_mod.patterns_zip_bytes(art), verify_tls=p["verify_tls"]))
            st = _with_pdc(p, lambda tok: pdc_mod.wait_worker(
                p["base"], tok, w.get("_id"),
                verify_tls=p["verify_tls"], timeout=body.wait_seconds))
            workers.append({"kind": "DataPattern", "worker_id": w.get("_id"),
                            "workerName": w.get("workerName"), "status": st.get("status"),
                            "report": _worker_report(st)})
        if art["dictionaries"]:
            w = _with_pdc(p, lambda tok: pdc_mod.upload_import(
                p["base"], tok, "Dictionary", "dictionaries-import.zip",
                author_mod.dictionaries_zip_bytes(art), verify_tls=p["verify_tls"]))
            st = _with_pdc(p, lambda tok: pdc_mod.wait_worker(
                p["base"], tok, w.get("_id"),
                verify_tls=p["verify_tls"], timeout=body.wait_seconds))
            workers.append({"kind": "Dictionary", "worker_id": w.get("_id"),
                            "workerName": w.get("workerName"), "status": st.get("status"),
                            "report": _worker_report(st)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"import upload failed: {e}")

    try:
        live = _live_index(p, prefix)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"post-import verify failed: {e}")

    rows = []
    for e in expected:
        m = live.get((e["kind"], e["name"]))
        row = {"kind": e["kind"], "name": e["name"], "term": e["term"],
               "term_id": e.get("term_id"), "imported": m is not None,
               "_id": m and m.get("_id"), "bound": None}
        if m and body.bind and e.get("term_id"):
            try:
                row["bound"] = _with_pdc(p, lambda tok, e=e, m=m: pdc_mod.bind_business_term(
                    p["base"], tok, e["kind"], m["_id"],
                    e["term"], e["term_id"], verify_tls=p["verify_tls"]))
            except HTTPException:
                raise
            except Exception as ex:
                row["bound"] = False
                row["error"] = str(ex)[:300]
        rows.append(row)
    counts = {"imported": sum(1 for r in rows if r["imported"]),
              "failed": sum(1 for r in rows if not r["imported"]),
              "bound": sum(1 for r in rows if r["bound"])}

    # NAME THE ONE THAT BROKE IT. PDC's importer works through the zip and
    # abandons the rest at the first member it cannot read — its error says
    # what went wrong ("fields num is 3") but never which file, and the worker
    # still reports COMPLETED. The app knows both halves: the authoring order
    # and which methods came back. The first method of that kind still absent
    # is where the import stopped, and everything after it never got a chance.
    # (Field-caught 2026-08-21: a dictionary value carrying commas took 18 of
    # 31 dictionaries with it, and the deploy table showed only "not found".)
    for w in workers:
        kind = w["kind"]
        absent = [r["name"] for r in rows if r["kind"] == kind and not r["imported"]]
        if not absent:
            continue
        w["stopped_at"] = absent[0]
        w["lost_after"] = len(absent) - 1
        exc = ((w.get("report") or {}).get("ERROR") or {}).get("event", {}).get("exception")
        if exc:
            w["exception"] = str(exc).split("\n")[0][:300]
    return {"prefix": prefix, "dry_run": False, "workers": workers,
            "rows": rows, "counts": counts}


@app.post("/api/pdc/identify")
def api_pdc_identify(body: IdentifyRequest) -> dict:
    """Trigger one DATA_IDENTIFICATION bulk job scoped to the given entity ids
    and to the prefixed method set (POST /api/start-job — the payload PDC's
    own UI sends). An explicit scope is required: this never sweeps the
    whole catalog."""
    p = _require_pdc()
    prefix = body.prefix.strip()
    if not prefix:
        raise HTTPException(status_code=400, detail="a name prefix is required")
    if not body.scope:
        raise HTTPException(status_code=400,
                            detail="an entity-id scope is required — identification "
                                   "jobs are never catalog-wide from here")
    # Patterns match against the PROFILE, not the live table. A scope whose
    # profile predates the data is the difference between 9 tagged columns and
    # 1 — same methods, same job, proven on this estate. Report it before the
    # run rather than leaving a silent no-op to be discovered by reading back.
    profiled, stale = {}, []
    for eid in body.scope:
        try:
            when = _with_pdc(p, lambda tok, e=eid: pdc_mod.profiled_at(
                p["base"], tok, e, verify_tls=p["verify_tls"]))
        except Exception:
            when = None
        profiled[eid] = when
        if not when:
            stale.append({"entity": eid, "profiled_at": None})
    if stale and not body.allow_stale_profile:
        raise HTTPException(
            status_code=409,
            detail=(f"{len(stale)} entity/entities in scope have never been profiled. "
                    f"Identification matches patterns against the stored profile, so "
                    f"they would tag nothing. Profile them in PDC first, or set "
                    f"allow_stale_profile: true."))

    try:
        methods = [m for m in _with_pdc(p, lambda tok: pdc_mod.list_methods(
                       p["base"], tok, prefix=prefix, verify_tls=p["verify_tls"]))
                   if not m.get("builtIn")]
        job_id = _with_pdc(p, lambda tok: pdc_mod.start_identification_job(
            p["base"], tok, body.scope,
            [m["_id"] for m in methods if m["kind"] == "Dictionary"],
            [m["_id"] for m in methods if m["kind"] == "DataPattern"],
            verify_tls=p["verify_tls"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"identification job failed: {e}")
    return {"job_id": job_id, "methods": len(methods), "scope": len(body.scope),
            "profiled": [{"entity": e, "profiled_at": profiled.get(e)}
                         for e in body.scope]}


@app.post("/api/pdc/method")
def api_pdc_method(body: MethodDetailRequest) -> dict:
    """One Data Identification method, whole, by name or id.

    PDC's own objects are the specification: the import envelope was learned by
    reading an export rather than guessing, and the same trick applies to
    matching behaviour. Reading a BUILT-IN pattern beside one of ours is how you
    find the field that makes the difference between a rule that fires and a
    rule that sits there.
    """
    p = _require_pdc()
    kind, mid = (body.kind or "").strip() or None, (body.id or "").strip()
    if not mid:
        nm = (body.name or "").strip()
        if not nm:
            raise HTTPException(status_code=400, detail="give a method name or id")
        try:
            rows = _with_pdc(p, lambda tok: pdc_mod.list_methods(
                p["base"], tok, verify_tls=p["verify_tls"]))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"method list failed: {e}")
        hit = next((m for m in rows if str(m["name"]).lower() == nm.lower()), None)
        if not hit:
            raise HTTPException(status_code=404, detail=f"no method named {nm!r}")
        mid, kind = hit["_id"], hit["kind"]
    if not kind:
        raise HTTPException(status_code=400, detail="kind is required when giving an id")
    try:
        return {"kind": kind, "method": _with_pdc(p, lambda tok: pdc_mod.get_method(
            p["base"], tok, kind, mid, verify_tls=p["verify_tls"]))}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"method read failed: {e}")


@app.post("/api/pdc/job")
def api_pdc_job(body: JobStatusRequest | None = None) -> dict:
    """What became of a job this app started, or what PDC has been doing lately.

    Identification could be fired and then not followed: the outcome lived in
    PDC's Workers page and nowhere this app could reach. `id` reports one job,
    including the per-job lines that say whether the scope was covered
    ("Completed Total 2 of 2"); `recent` lists the last N worker processes for
    when the id is not to hand, which is most of the time.
    """
    p = _require_pdc()
    body = body or JobStatusRequest()
    if body.recent:
        try:
            rows = _with_pdc(p, lambda tok: pdc_mod.recent_workers(
                p["base"], tok, limit=min(max(body.recent, 1), 50),
                verify_tls=p["verify_tls"]))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"worker list failed: {e}")
        return {"recent": rows, "count": len(rows)}

    jid = (body.id or "").strip()
    if not jid:
        raise HTTPException(status_code=400, detail="give a job id, or recent: N to list workers")
    try:
        return _with_pdc(p, lambda tok: pdc_mod.job_status(
            p["base"], tok, jid, verify_tls=p["verify_tls"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"job status failed: {e}")


@app.post("/api/pdc/entity")
def api_pdc_entity(body: EntityDetailRequest) -> dict:
    """Everything PDC holds on one entity — by id, or by name when you only have
    that. Read-only, and deliberately not scoped to this app's own objects: when
    a write looks like it succeeded and the catalog disagrees, the argument is
    settled by reading the entity back, and that should not require leaving the
    app for PDC's UI.

    The summary pulls the fields that carry governance state (rating, quality,
    sensitivity, lineage flags, terms, labels); `raw` returns the payload whole
    for anything the summary does not name.
    """
    p = _require_pdc()
    eid = (body.id or "").strip()
    if not eid:
        nm = (body.name or "").strip()
        if len(nm) < 2:
            raise HTTPException(status_code=400, detail="give an entity id, or a name to look up")
        try:
            hits = _with_pdc(p, lambda tok: pdc_mod.filter_entities(
                p["base"], tok, {"names": [nm]}, verify_tls=p["verify_tls"]))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"entity lookup failed: {e}")
        match = next((h for h in (hits or [])
                      if str(((h.get("attributes") or {}).get("name")) or h.get("name") or "").lower()
                      == nm.lower()), None) or (hits or [None])[0]
        if not match:
            raise HTTPException(status_code=404, detail=f"nothing in the catalog is named {nm!r}")
        eid = pdc_mod._eid(match)

    try:
        ent = _with_pdc(p, lambda tok: pdc_mod.get_entity(
            p["base"], tok, eid, verify_tls=p["verify_tls"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"entity read failed: {e}")

    attrs = ent.get("attributes") or {}
    feats = attrs.get("features") or {}
    out = {
        "id": eid,
        "name": attrs.get("name") or ent.get("name"),
        "type": attrs.get("type") or ent.get("type"),
        "path": attrs.get("qualifiedName") or attrs.get("path"),
        # features verbatim: the point is to see the SHAPE PDC stores, so a
        # rating is not flattened to a number on the way out
        "features": feats,
        "rating": feats.get("rating"),
        "business_terms": [ (b or {}).get("name") for b in (attrs.get("businessTerms") or []) if b ],
        "custom_properties": attrs.get("customProperties") or [],
    }
    if body.raw:
        out["entity"] = ent
    return out


@app.post("/api/pdc/identified")
def api_pdc_identified(body: IdentifiedRequest) -> dict:
    """What identification actually DID, column by column.

    Deploy proves the methods landed; drift proves they still match the
    contract; neither answers "did a rule ever fire against real data". This
    reads the columns back and judges each against the Registry, so the answer
    is a verdict rather than a browse:

      expected_tagged   the contract says this column's term, and PDC agrees
      expected_missing  the contract expected it and PDC has nothing
      unexpected        PDC bound a term the contract does not claim here
      untouched         no term, and none was expected

    `expected_missing` is the interesting one: a rule that deployed cleanly and
    then failed to fire is invisible everywhere else in this app.
    """
    _require_registry()
    p = _require_pdc()
    art = _author_or_400((body.prefix or "").strip() or None)

    # what the contract claims for each physical column, from the authored set —
    # both the TERM and the TAGS the method would stamp. The tags matter: a term
    # on a column proves nothing about identification, because the Glossary's
    # Apply binds terms too. Tags are what a METHOD applies when it matches, so
    # they are the fingerprint of a rule having fired.
    expected, expected_tags = {}, {}
    authored = {e["term"] for e in drift_mod.expected_methods(art)}
    tags_by_term = {}
    for m in (art.get("patterns") or []) + (art.get("dictionaries") or []):
        rule = (m.get("rule") or {}).get("rules") or [{}]
        for act in (rule[0].get("actions") or []):
            for t in (act.get("applyTags") or []):
                nm = (t or {}).get("name")
                if nm:
                    tags_by_term.setdefault(m["term"], set()).add(str(nm).lower())
    for c in (_state["reg"].get("concepts") or []):
        if c.get("term_name") not in authored:
            continue
        for src in (c.get("sources") or []):
            col = str(src).split(".")[-1].strip().lower()
            if col:
                expected.setdefault(col, set()).add(c["term_name"])
                expected_tags.setdefault(col, set()).update(
                    tags_by_term.get(c["term_name"], set()))

    tables, rows = [], []
    for t in body.tables:
        t = (t or "").strip()
        if not t:
            continue
        try:
            cols = _with_pdc(p, lambda tok, t=t: pdc_mod.table_columns(
                p["base"], tok, t, verify_tls=p["verify_tls"]))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"column read failed for {t}: {e}")
        keep = cols          # resolved by parent, so every row belongs to this table
        tables.append({"table": t, "columns": len(keep)})
        for c in keep:
            key = str(c["name"]).strip().lower()
            want = expected.get(key, set())
            want_tags = expected_tags.get(key, set())
            got = set(c["business_terms"])
            got_tags = {str(x).lower() for x in (c["tags"] or [])}
            if want and (want & got) and (not want_tags or (want_tags & got_tags)):
                verdict = "expected_tagged"          # the method matched and stamped
            elif want and (want & got):
                # the term is there but none of the method's tags are: this is a
                # term link from Apply, NOT a rule that fired. Counting it as a
                # match is how today's first read-back flattered the result.
                verdict = "expected_term_only"
            elif want:
                verdict = "expected_missing"
            elif got:
                verdict = "unexpected"
            else:
                verdict = "untouched"
            rows.append({"table": t, "column": c["name"], "verdict": verdict,
                         "expected": sorted(want), "expected_tags": sorted(want_tags),
                         "bound": sorted(got), "tags": c["tags"]})

    counts = {k: sum(1 for r in rows if r["verdict"] == k)
              for k in ("expected_tagged", "expected_term_only", "expected_missing",
                        "unexpected", "untouched")}
    return {"prefix": art["prefix"], "tables": tables, "counts": counts, "rows": rows}


@app.post("/api/pdc/entities")
def api_pdc_entities(body: EntityLookupRequest) -> dict:
    """Find catalog entities by name, so an identification scope can be CHOSEN
    rather than pasted. Deploy asked for raw entity ids, which meant leaving the
    app, finding a table in PDC, and copying a uuid — the kind of step that
    turns a scoped job into an unscoped one because scoping was tedious.

    Read-only. Returns {id, name, type, path} for each hit, newest API first."""
    p = _require_pdc()
    q = (body.q or "").strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="give at least two characters to search for")
    try:
        # `names` + `types`, the shape the Glossary's client has used against
        # this endpoint all along — /filters rejects an unknown `name` property.
        # TABLE first (what a scope usually means), then the file-ish roots the
        # estate also holds, so a CSV or JSON source is findable too.
        rows = []
        for filt in ({"names": [q], "types": ["TABLE", "VIEW"]},
                     {"names": [q], "types": ["FILE", "OBJECT", "RESOURCE"]},
                     {"names": [q]}):
            try:
                rows = _with_pdc(p, lambda tok, f=filt: pdc_mod.filter_entities(
                    p["base"], tok, f, verify_tls=p["verify_tls"]))
            except HTTPException:
                raise
            except Exception:
                rows = []
            if rows:
                break
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"entity lookup failed: {e}")

    out = []
    for it in rows or []:
        if not isinstance(it, dict):
            continue
        attrs = it.get("attributes") or {}
        name = attrs.get("name") or it.get("name") or ""
        if q.lower() not in str(name).lower():
            continue
        out.append({"id": pdc_mod._eid(it), "name": name,
                    "type": attrs.get("type") or it.get("type") or "",
                    "path": attrs.get("qualifiedName") or attrs.get("path") or ""})
        if len(out) >= max(1, min(body.limit, 100)):
            break
    return {"q": q, "count": len(out), "entities": out}


@app.post("/api/pdc/builtins")
def api_pdc_builtins(body: BuiltInsRequest | None = None) -> dict:
    """Disable (or restore) PDC's BUILT-IN patterns and dictionaries.

    PDC ships them enabled, and an identification job started anywhere other
    than this app — PDC's own screen, a schedule, ingest — classifies against
    whatever is enabled. In a custom-only programme that is the drift risk the
    programme exists to remove: a built-in shape induced from somebody else's
    data competing with one induced from this estate.

    Never touches a custom method, so the app can never disable its own
    authored set by this route. `dry_run` (the default) returns the plan.
    Reversible: the same call with enabled=true restores them.
    """
    p = _require_pdc()
    body = body or BuiltInsRequest()
    try:
        rows = _with_pdc(p, lambda tok: pdc_mod.list_methods(
            p["base"], tok, verify_tls=p["verify_tls"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"method list failed: {e}")

    targets = [m for m in rows if m.get("builtIn")]
    if body.kind:
        targets = [m for m in targets if m["kind"] == body.kind]
    plan = {"prefix": None, "enabled": body.enabled, "dry_run": body.dry_run,
            "built_in": len(targets), "custom_untouched": len(rows) - len(targets),
            "by_kind": {k: sum(1 for m in targets if m["kind"] == k)
                        for k in ("Dictionary", "DataPattern")}}
    if body.dry_run:
        plan["rows"] = [{"kind": m["kind"], "name": m["name"], "_id": m["_id"]}
                        for m in targets]
        return plan

    results, failed = [], 0
    for m in targets:
        try:
            ok = _with_pdc(p, lambda tok, m=m: pdc_mod.set_method_enabled(
                p["base"], tok, m["kind"], m["_id"], body.enabled,
                verify_tls=p["verify_tls"]))
        except HTTPException:
            raise
        except Exception as e:
            ok, err = False, str(e)[:200]
            results.append({"kind": m["kind"], "name": m["name"], "ok": False, "error": err})
            failed += 1
            continue
        results.append({"kind": m["kind"], "name": m["name"], "ok": bool(ok)})
        if not ok:
            failed += 1
    plan["rows"] = results
    plan["changed"] = sum(1 for r in results if r.get("ok"))
    plan["failed"] = failed

    # READ BACK. A PATCH that returns 200 is not the same as a method that is
    # off, and this action is the one thing standing between a custom-only
    # programme and 137 built-in shapes competing with it during the next
    # identification run. So the count that gets reported is the count the
    # ESTATE agrees with, not the count of calls that did not raise.
    verified, unverified = 0, []
    for m in targets:
        try:
            d = _with_pdc(p, lambda tok, m=m: pdc_mod.get_method(
                p["base"], tok, m["kind"], m["_id"], verify_tls=p["verify_tls"]))
        except Exception as e:
            unverified.append({"kind": m["kind"], "name": m["name"],
                               "error": str(e)[:120]})
            continue
        if bool(d.get("isEnabled")) == bool(body.enabled):
            verified += 1
        else:
            unverified.append({"kind": m["kind"], "name": m["name"],
                               "isEnabled": bool(d.get("isEnabled"))})
    plan["verified"] = verified
    plan["unverified"] = len(unverified)
    plan["unverified_rows"] = unverified[:20]
    return plan


# --------------------------------------------------------------------------- #
#  Drift-check — deployed methods vs the Registry's governed facts
# --------------------------------------------------------------------------- #
@app.post("/api/pdc/drift")
def api_pdc_drift(body: DriftRequest | None = None) -> dict:
    """Compare every deployed method under the prefix against the loaded
    Registry: governed tags vs the allow-list, term binding (name + id),
    regex/signature vs the seeds, dictionary row counts. Verdict per method:
    clean / drifted / orphaned / missing."""
    _require_registry()
    p = _require_pdc()
    body = body or DriftRequest()
    art = _author_or_400((body.prefix or "").strip() or None)
    prefix = art["prefix"]
    try:
        live = _live_index(p, prefix)
        details = []
        for (kind, _name), m in live.items():
            d = _with_pdc(p, lambda tok, kind=kind, m=m: pdc_mod.get_method(
                p["base"], tok, kind, m["_id"], verify_tls=p["verify_tls"]))
            d["kind"] = kind
            details.append(d)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"drift read failed: {e}")
    out = drift_mod.evaluate(art, details, registry_mod.governed_tags(_state["reg"]))
    out["prefix"] = prefix
    return out


def _reconcile_rows(concepts, found):
    rows = []
    for c in concepts:
        name = c.get("term_name") or ""
        reg_id = c.get("term_id") or None
        hit = found.get(name) or {}
        pdc_id = hit.get("id")
        if pdc_id and reg_id and str(pdc_id) == str(reg_id):
            status = "verified"
        elif pdc_id and reg_id:
            status = "mismatch"
        elif pdc_id:
            status = "resolved"
        else:
            status = "missing"
        row = {"term": name, "registry_id": reg_id, "pdc_id": pdc_id,
               "glossary_id": hit.get("glossaryId"), "status": status,
               "seeded": bool(c.get("detect"))}
        if hit.get("via"):
            row["via"] = hit["via"]   # e.g. column-echo: verified by id, not name
        rows.append(row)
    return rows


def _reconcile_counts(rows):
    counts = {"verified": 0, "mismatch": 0, "resolved": 0, "missing": 0}
    for r in rows:
        counts[r["status"]] += 1
    return counts


@app.post("/api/reconcile")
def api_reconcile(body: ReconcileRequest | None = None) -> dict:
    """Look up concepts' terms in PDC and compare with the Registry's term_id:
    verified / mismatch / resolved / missing. Pass {offset, limit} to run in
    batches — the UI does, so it can draw an exact progress bar; without a
    limit the whole Registry is reconciled in one call."""
    _require_registry()
    p = _require_pdc()
    body = body or ReconcileRequest()
    concepts = [c for c in _state["reg"].get("concepts", []) if isinstance(c, dict)]
    limit = body.limit
    offset = max(0, body.offset)
    chunk = concepts if limit is None else concepts[offset:offset + max(1, min(limit, 50))]
    names = [c.get("term_name") for c in chunk if c.get("term_name")]
    try:
        found = _with_pdc(p, lambda tok: pdc_mod.resolve_terms(
            p["base"], tok, names, version=p["version"], verify_tls=p["verify_tls"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PDC lookup failed: {e}")
    # Name-search misses with a Registry id get one more chance: the
    # column-echo proof (see pdc.confirm_term_by_column_echo). Without it the
    # ampersand terms reconcile MISSING forever while their deployed methods
    # fire happily — a false alarm the steward cannot distinguish from a
    # genuinely absent term.
    for c in chunk:
        nm, rid = c.get("term_name"), c.get("term_id")
        if not nm or not rid or (found.get(nm) or {}).get("id"):
            continue
        try:
            hit = _with_pdc(p, lambda tok, c=c: pdc_mod.confirm_term_by_column_echo(
                p["base"], tok, c.get("term_name"), c.get("term_id"),
                c.get("sources"), version=p["version"], verify_tls=p["verify_tls"]))
        except HTTPException:
            raise
        except Exception:
            hit = None
        if hit:
            found[nm] = hit
    rows = _reconcile_rows(chunk, found)
    if limit is None:
        _state["reconcile"] = rows
        counts = _reconcile_counts(rows)
        return {"rows": rows, "counts": counts,
                "bindable": counts["resolved"] + counts["mismatch"]}
    if offset == 0:
        _state["reconcile"] = []
    _state["reconcile"].extend(rows)
    done = min(offset + len(chunk), len(concepts))
    finished = done >= len(concepts)
    resp = {"rows": rows, "done": done, "total": len(concepts), "finished": finished}
    if finished:
        counts = _reconcile_counts(_state["reconcile"])
        resp["counts"] = counts
        resp["bindable"] = counts["resolved"] + counts["mismatch"]
    return resp


@app.post("/api/reconcile/apply", response_model=RegistrySummary)
def api_reconcile_apply() -> RegistrySummary:
    """Stamp the PDC-found term ids into the loaded Registry (in memory) so
    authoring binds by id. The Registry FILE is owned by the Glossary app —
    export the reconciled copy if you want to keep it."""
    if _state["reg"] is None or not _state["reconcile"]:
        raise HTTPException(status_code=400, detail="run reconcile first")
    by_name = {r["term"]: r for r in _state["reconcile"] if r.get("pdc_id")}
    applied = 0
    gid = None
    for c in _state["reg"].get("concepts", []):
        r = by_name.get((c or {}).get("term_name"))
        if r and str(c.get("term_id") or "") != str(r["pdc_id"]):
            c["term_id"] = r["pdc_id"]
            applied += 1
        if r and r.get("glossary_id"):
            gid = gid or r["glossary_id"]
    if gid and not _state["reg"].get("glossary_id"):
        _state["reg"]["glossary_id"] = gid
    summary = _summary_payload()
    summary.applied = applied
    return summary


@app.get("/api/registry/export")
def api_registry_export() -> Response:
    """The loaded (possibly reconciled) Registry as JSON — keep it beside the
    Glossary app's copy, or diff it."""
    _require_registry()
    return Response(
        content=json.dumps(_state["reg"], indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=registry.reconciled.json"},
    )


# Serve the built React UI for every non-API path (mounted last so API wins).
if UI_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")

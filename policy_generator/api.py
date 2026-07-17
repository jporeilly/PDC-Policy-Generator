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


class IdentifyRequest(BaseModel):
    prefix: str
    scope: list[str]           # entity ids the bulk job is limited to


class DriftRequest(BaseModel):
    prefix: str | None = None


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
        item = {"path": p, "file": os.path.basename(p),
                "modified": datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M"),
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
            reg, name = registry_mod.validate_registry(data), registry.filename
        elif path:
            reg, name = registry_mod.load_registry(path), os.path.basename(path)
        else:
            raise registry_mod.RegistryError("no Registry supplied — upload a file or give a path")
    except registry_mod.RegistryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"could not read Registry: {e}")
    _state["reg"], _state["name"] = reg, name
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
                "kind": "pattern",
                "regex": (r.get("regexMatch") or {}).get("regex", [None])[0],
                "signature": (r.get("profilePatterns") or [None])[0],
                "column_hint": _hint(r), "tags": _tags(r), "rule": r}

    def _dic(d):
        r = d["rule"]
        values = [v for v in d["csv"].splitlines()[1:] if v]
        return {"name": r["name"], "term": d["term"], "term_id": d.get("term_id") or None,
                "kind": "dictionary",
                "values": values[:200], "values_count": len(values),
                "column_hint": _hint(r), "tags": _tags(r), "rule": r}

    return {
        "prefix": art["prefix"],
        "patterns": [_pat(p) for p in art["patterns"]],
        "dictionaries": [_dic(d) for d in art["dictionaries"]],
        "skipped": [dict(s, bucket=_bucket(s["term"])) for s in art["skipped"]],
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


# --------------------------------------------------------------------------- #
#  Reconcile — verify/bind term ids against a live PDC
# --------------------------------------------------------------------------- #
@app.post("/api/pdc/connect")
def api_pdc_connect(body: PdcConnectRequest) -> dict:
    """Authenticate once (Keycloak-first, /auth fallback). The token lives in
    memory for this session only; the password is never stored."""
    base = body.base_url.strip()
    if not base:
        raise HTTPException(status_code=400, detail="PDC base URL is required (e.g. https://192.168.1.200)")
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
                     "verify_tls": body.verify_tls, "token": token}
    who = pdc_mod.decode_jwt(token)
    return {"ok": True, "base": _state["pdc"]["base"], "version": body.version,
            "username": who.get("username"), "roles": who.get("roles", [])[:8],
            "expires_in": who.get("expires_in")}


def _expired() -> HTTPException:
    _state["pdc"] = None
    return HTTPException(status_code=401, detail="PDC session expired — connect again")


@app.post("/api/pdc/methods")
def api_pdc_methods(body: PrefixRequest | None = None) -> dict:
    """List the custom Data Identification methods in PDC, scoped to a name
    prefix (the app's authored set). Read-only — the preview before a retire."""
    p = _require_pdc()
    prefix = ((body.prefix if body else None) or "").strip() or None
    try:
        rows = pdc_mod.list_methods(p["base"], p["token"], prefix=prefix,
                                    verify_tls=p["verify_tls"])
    except pdc_mod.TokenExpired:
        raise _expired()
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
        rows = pdc_mod.list_methods(p["base"], p["token"], prefix=prefix,
                                    verify_tls=p["verify_tls"])
    except pdc_mod.TokenExpired:
        raise _expired()
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
            rid = pdc_mod.remove_method(p["base"], p["token"], m["kind"], m["_id"],
                                        verify_tls=p["verify_tls"])
            results.append({**m, "removed": bool(rid), "recordId": rid})
        except pdc_mod.TokenExpired:
            raise _expired()
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
            "username": who.get("username"), "expires_in": who.get("expires_in")}


def _live_index(p, prefix):
    """Non-built-in methods carrying the prefix, keyed by (kind, name)."""
    rows = pdc_mod.list_methods(p["base"], p["token"], prefix=prefix,
                                verify_tls=p["verify_tls"])
    return {(m["kind"], m["name"]): m for m in rows if not m.get("builtIn")}


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
    expected = drift_mod.expected_methods(art)

    try:
        live = _live_index(p, prefix)
    except pdc_mod.TokenExpired:
        raise _expired()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"method list failed: {e}")

    if body.dry_run:
        rows = [{"kind": e["kind"], "name": e["name"], "term": e["term"],
                 "term_id": e.get("term_id"),
                 "action": "update" if (e["kind"], e["name"]) in live else "create"}
                for e in expected]
        return {"prefix": prefix, "dry_run": True, "rows": rows,
                "counts": {"create": sum(1 for r in rows if r["action"] == "create"),
                           "update": sum(1 for r in rows if r["action"] == "update")}}

    # one importer worker per artifact kind, exactly like the UI's zip upload
    workers = []
    try:
        if art["patterns"]:
            w = pdc_mod.upload_import(p["base"], p["token"], "DataPattern",
                                      "patterns-import.zip",
                                      author_mod.patterns_zip_bytes(art),
                                      verify_tls=p["verify_tls"])
            st = pdc_mod.wait_worker(p["base"], p["token"], w.get("_id"),
                                     verify_tls=p["verify_tls"], timeout=body.wait_seconds)
            workers.append({"kind": "DataPattern", "worker_id": w.get("_id"),
                            "workerName": w.get("workerName"), "status": st.get("status")})
        if art["dictionaries"]:
            w = pdc_mod.upload_import(p["base"], p["token"], "Dictionary",
                                      "dictionaries-import.zip",
                                      author_mod.dictionaries_zip_bytes(art),
                                      verify_tls=p["verify_tls"])
            st = pdc_mod.wait_worker(p["base"], p["token"], w.get("_id"),
                                     verify_tls=p["verify_tls"], timeout=body.wait_seconds)
            workers.append({"kind": "Dictionary", "worker_id": w.get("_id"),
                            "workerName": w.get("workerName"), "status": st.get("status")})
    except pdc_mod.TokenExpired:
        raise _expired()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"import upload failed: {e}")

    try:
        live = _live_index(p, prefix)
    except pdc_mod.TokenExpired:
        raise _expired()
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
                row["bound"] = pdc_mod.bind_business_term(
                    p["base"], p["token"], e["kind"], m["_id"],
                    e["term"], e["term_id"], verify_tls=p["verify_tls"])
            except pdc_mod.TokenExpired:
                raise _expired()
            except Exception as ex:
                row["bound"] = False
                row["error"] = str(ex)[:300]
        rows.append(row)
    counts = {"imported": sum(1 for r in rows if r["imported"]),
              "failed": sum(1 for r in rows if not r["imported"]),
              "bound": sum(1 for r in rows if r["bound"])}
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
    try:
        methods = [m for m in pdc_mod.list_methods(p["base"], p["token"], prefix=prefix,
                                                   verify_tls=p["verify_tls"])
                   if not m.get("builtIn")]
        job_id = pdc_mod.start_identification_job(
            p["base"], p["token"], body.scope,
            [m["_id"] for m in methods if m["kind"] == "Dictionary"],
            [m["_id"] for m in methods if m["kind"] == "DataPattern"],
            verify_tls=p["verify_tls"])
    except pdc_mod.TokenExpired:
        raise _expired()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"identification job failed: {e}")
    return {"job_id": job_id, "methods": len(methods), "scope": len(body.scope)}


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
            d = pdc_mod.get_method(p["base"], p["token"], kind, m["_id"],
                                   verify_tls=p["verify_tls"])
            d["kind"] = kind
            details.append(d)
    except pdc_mod.TokenExpired:
        raise _expired()
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
        rows.append({"term": name, "registry_id": reg_id, "pdc_id": pdc_id,
                     "glossary_id": hit.get("glossaryId"), "status": status,
                     "seeded": bool(c.get("detect"))})
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
        found = pdc_mod.resolve_terms(p["base"], p["token"], names,
                                      version=p["version"], verify_tls=p["verify_tls"])
    except pdc_mod.TokenExpired:
        raise _expired()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PDC lookup failed: {e}")
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

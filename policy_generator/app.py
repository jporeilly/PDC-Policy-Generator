"""
app.py — the Policy Generator's local web UI (Flask, single user, local-first).

Mirrors the Glossary Generator's app shape: run it from this folder
(`./run.sh` / `.\\run.ps1` / `python app.py`), open http://127.0.0.1:5001.

The UI wraps the same engine the CLI drives: load a Classification Registry
(`classification-registry/1`), read the contract summary, author the PDC
Data Identification method set, download it as one zip. Reconcile / deploy /
drift-check land here as those stages ship.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # run as `python app.py` from this folder

from flask import Flask, jsonify, render_template, request, send_file

from policy_generator import __version__, author as author_mod, pdc as pdc_mod, registry as registry_mod

app = Flask(__name__)
APP_VERSION = __version__

# Single-user local app: the last loaded Registry is the working state,
# same model as the Glossary app's in-memory review rows. The PDC token is
# held in memory for this session only — never saved.
_state = {"reg": None, "name": None,
          "pdc": None,            # {base, version, verify_tls, token}
          "reconcile": None}      # last reconcile rows (for apply)


@app.get("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.get("/favicon.svg")
@app.get("/favicon.ico")
def favicon():
    return app.send_static_file("favicon.svg")


@app.get("/api/version")
def version():
    return jsonify({"version": APP_VERSION, "service": "policy-generator"})


@app.get("/api/registries")
def api_registries():
    """Registries auto-discovered from a co-located Glossary checkout
    (nested ~/PDC-Demo clone, sibling checkout, or POLICY_REGISTRY_DIR)."""
    import datetime
    out = []
    for p in registry_mod.discover_registries()[:20]:
        item = {"path": p, "file": os.path.basename(p),
                "modified": datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")}
        try:
            with open(p, encoding="utf-8") as f:
                reg = registry_mod.validate_registry(json.load(f))
            item["glossary"] = reg.get("glossary")
            item["concepts"] = len(reg.get("concepts") or [])
        except Exception:
            item["glossary"] = None  # unreadable/foreign file: listed, not loadable
        out.append(item)
    return jsonify({"registries": out})


def _load_from_request():
    """Accept the Registry as an uploaded file (`registry`) or a local path."""
    if "registry" in request.files:
        f = request.files["registry"]
        try:
            data = json.load(io.TextIOWrapper(f.stream, encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise registry_mod.RegistryError(f"not valid JSON ({e})")
        return registry_mod.validate_registry(data), f.filename
    path = (request.get_json(silent=True) or {}).get("path") or request.form.get("path")
    if path:
        return registry_mod.load_registry(path), os.path.basename(path)
    raise registry_mod.RegistryError("no Registry supplied — upload a file or give a path")


@app.post("/api/load")
def api_load():
    try:
        reg, name = _load_from_request()
    except registry_mod.RegistryError as e:
        return jsonify({"error": str(e)}), 400
    except (OSError, ValueError) as e:
        return jsonify({"error": f"could not read Registry: {e}"}), 400
    _state["reg"], _state["name"] = reg, name
    s = registry_mod.summary(reg)
    s["file"] = name
    s["unresolved"] = len(registry_mod.unresolved_terms(reg))
    return jsonify(s)


@app.post("/api/author")
def api_author():
    if _state["reg"] is None:
        return jsonify({"error": "load a Registry first"}), 400
    prefix = (request.get_json(silent=True) or {}).get("prefix") or None
    try:
        art = author_mod.author(_state["reg"], prefix=prefix)
    except registry_mod.RegistryError as e:
        return jsonify({"error": str(e)}), 400
    zbytes = author_mod.to_zip_bytes(art)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (prefix or _state["name"] or "methods")).strip("-").lower()
    return send_file(io.BytesIO(zbytes), mimetype="application/zip",
                     as_attachment=True,
                     download_name=f"{slug or 'methods'}-data-identification.zip")


@app.post("/api/preview")
def api_preview():
    """What author would emit, without writing anything — the review manifest."""
    if _state["reg"] is None:
        return jsonify({"error": "load a Registry first"}), 400
    prefix = (request.get_json(silent=True) or {}).get("prefix") or None
    try:
        art = author_mod.author(_state["reg"], prefix=prefix)
    except registry_mod.RegistryError as e:
        return jsonify({"error": str(e)}), 400
    def _pat(p):
        r = p["rule"][0]
        return {"name": r["name"], "term": p["term"], "term_id": p.get("term_id") or None,
                "kind": "pattern",
                "regex": (r.get("contentRegex") or [{}])[0].get("regex"),
                "signature": (r.get("contentPatterns") or [{}])[0].get("pattern") if r.get("contentPatterns") else None,
                "column_hint": (r.get("columnNameRegex") or [{}])[0].get("regex") if r.get("columnNameRegex") else None,
                "tags": [t["k"] for a in r.get("actions", []) for t in a.get("applyTags", [])],
                "rule": p["rule"]}

    def _dic(d):
        r = d["rule"][0]
        values = [v for v in d["csv"].splitlines()[1:] if v]
        return {"name": r["name"], "term": d["term"], "term_id": d.get("term_id") or None,
                "kind": "dictionary",
                "values": values[:200], "values_count": len(values),
                "column_hint": (r.get("columnNameRegex") or [{}])[0].get("regex") if r.get("columnNameRegex") else None,
                "tags": [t["k"] for a in r.get("actions", []) for t in a.get("applyTags", [])],
                "rule": d["rule"]}

    return jsonify({
        "patterns": [_pat(p) for p in art["patterns"]],
        "dictionaries": [_dic(d) for d in art["dictionaries"]],
        "skipped": [dict(s, bucket=_bucket(s["term"])) for s in art["skipped"]],
    })


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


# --------------------------------------------------------------------------- #
#  Reconcile — verify/bind term ids against a live PDC
# --------------------------------------------------------------------------- #
@app.post("/api/pdc/connect")
def api_pdc_connect():
    """Authenticate once (Keycloak-first, /auth fallback). The token lives in
    memory for this session only; the password is never stored."""
    b = request.get_json(silent=True) or {}
    base = (b.get("base_url") or "").strip()
    if not base:
        return jsonify({"error": "PDC base URL is required (e.g. https://192.168.1.200)"}), 400
    version = (b.get("version") or "v3").strip()
    verify = bool(b.get("verify_tls"))
    token = (b.get("token") or "").strip()
    try:
        if not token:
            if not (b.get("username") and b.get("password")):
                return jsonify({"error": "username + password (or a bearer token) required"}), 400
            token = pdc_mod.auth(base, b["username"], b["password"], version=version,
                                 verify_tls=verify, realm=(b.get("realm") or "pdc"))
    except Exception as e:
        return jsonify({"error": f"authentication failed: {e}"}), 400
    _state["pdc"] = {"base": pdc_mod.clean_base(base), "version": version,
                     "verify_tls": verify, "token": token}
    who = pdc_mod.decode_jwt(token)
    return jsonify({"ok": True, "base": _state["pdc"]["base"], "version": version,
                    "username": who.get("username"), "roles": who.get("roles", [])[:8],
                    "expires_in": who.get("expires_in")})


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
def api_reconcile():
    """Look up concepts' terms in PDC and compare with the Registry's term_id:
    verified / mismatch / resolved / missing. Pass {offset, limit} to run in
    batches — the UI does, so it can draw an exact progress bar; without a
    limit the whole Registry is reconciled in one call."""
    if _state["reg"] is None:
        return jsonify({"error": "load a Registry first"}), 400
    if not _state["pdc"]:
        return jsonify({"error": "connect to PDC first"}), 400
    p = _state["pdc"]
    b = request.get_json(silent=True) or {}
    concepts = [c for c in _state["reg"].get("concepts", []) if isinstance(c, dict)]
    limit = b.get("limit")
    offset = max(0, int(b.get("offset") or 0))
    chunk = concepts if limit is None else concepts[offset:offset + max(1, min(int(limit), 50))]
    names = [c.get("term_name") for c in chunk if c.get("term_name")]
    try:
        found = pdc_mod.resolve_terms(p["base"], p["token"], names,
                                      version=p["version"], verify_tls=p["verify_tls"])
    except pdc_mod.TokenExpired:
        _state["pdc"] = None
        return jsonify({"error": "PDC session expired — connect again"}), 401
    except Exception as e:
        return jsonify({"error": f"PDC lookup failed: {e}"}), 502
    rows = _reconcile_rows(chunk, found)
    if limit is None:
        _state["reconcile"] = rows
        counts = _reconcile_counts(rows)
        return jsonify({"rows": rows, "counts": counts,
                        "bindable": counts["resolved"] + counts["mismatch"]})
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
    return jsonify(resp)


@app.post("/api/reconcile/apply")
def api_reconcile_apply():
    """Stamp the PDC-found term ids into the loaded Registry (in memory) so
    authoring binds by id. The Registry FILE is owned by the Glossary app —
    export the reconciled copy if you want to keep it."""
    if _state["reg"] is None or not _state["reconcile"]:
        return jsonify({"error": "run reconcile first"}), 400
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
    s = registry_mod.summary(_state["reg"])
    s["applied"] = applied
    return jsonify(s)


@app.get("/api/registry/export")
def api_registry_export():
    """The loaded (possibly reconciled) Registry as JSON — keep it beside the
    Glossary app's copy, or diff it."""
    if _state["reg"] is None:
        return jsonify({"error": "load a Registry first"}), 400
    return app.response_class(json.dumps(_state["reg"], indent=2),
                              mimetype="application/json",
                              headers={"Content-Disposition":
                                       "attachment; filename=registry.reconciled.json"})


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5001")), debug=False)

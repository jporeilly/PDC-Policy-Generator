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

from policy_generator import __version__, author as author_mod, registry as registry_mod

app = Flask(__name__)
APP_VERSION = __version__

# Single-user local app: the last loaded Registry is the working state,
# same model as the Glossary app's in-memory review rows.
_state = {"reg": None, "name": None}


@app.get("/")
def index():
    return render_template("index.html", version=APP_VERSION)


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
    return jsonify({
        "patterns": [{"name": p["rule"][0]["name"], "term": p["term"],
                      "term_id": p.get("term_id") or None} for p in art["patterns"]],
        "dictionaries": [{"name": d["rule"][0]["name"], "term": d["term"],
                          "term_id": d.get("term_id") or None} for d in art["dictionaries"]],
        "skipped": art["skipped"],
    })


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5001")), debug=False)

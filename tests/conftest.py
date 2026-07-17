import copy
import json

import pytest


def make_registry() -> dict:
    """A compact but representative Classification Registry fixture:
    a pattern-seeded concept (id-bound), a dictionary-seeded concept
    (unresolved id), a free-text concept (no seeds), and a concept whose
    tags all fail the governed allow-list."""
    return {
        "schema": "classification-registry/1",
        "glossary": "Claims",
        "tag_vocabulary": {"allow_list": ["pii", "sensitive", "finance"]},
        "concepts": [
            {"term_name": "Member Number", "term_id": "t-100",
             "category": "Identifiers", "definition": "The member's unique id.",
             "tags": ["PII", "maskable"],
             "sources": ["claims.members.mbr_no"],
             "detect": [{"type": "pattern", "regex": "^MBR-\\d{6}$",
                         "signature": "AAA-999999"}]},
            {"term_name": "State Code", "term_id": None,
             "category": "Geo", "tags": ["pii"],
             "sources": ["claims.members.state"],
             "detect": [{"type": "dictionary", "values": ["CA", "NY", "TX"]}]},
            {"term_name": "Claim Notes", "tags": ["sensitive"], "detect": []},
            {"term_name": "Audit Record", "tags": ["internal-only"],
             "detect": [{"type": "pattern", "regex": "^A\\d+$"}]},
        ],
    }


@pytest.fixture
def registry():
    return make_registry()


@pytest.fixture
def registry_file(tmp_path, registry):
    path = tmp_path / "registry.claims.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


@pytest.fixture
def api_client(registry_file):
    """A TestClient with clean per-test app state."""
    from fastapi.testclient import TestClient

    from policy_generator import api as api_mod

    api_mod._state.update({"reg": None, "name": None, "pdc": None, "reconcile": None})
    client = TestClient(api_mod.app)
    yield client
    api_mod._state.update({"reg": None, "name": None, "pdc": None, "reconcile": None})


def loaded_client(api_client, registry_file):
    res = api_client.post(f"/api/load?path={registry_file}")
    assert res.status_code == 200, res.text
    return api_client


@pytest.fixture
def fake_pdc(monkeypatch):
    """Replace every live-PDC call in the api module's pdc binding."""
    from policy_generator import api as api_mod

    class TokenExpired(Exception):
        pass

    calls = {"removed": []}

    def auth(base, user, pw, version="v3", verify_tls=False, realm="pdc"):
        if pw != "good":
            raise RuntimeError("bad credentials")
        return "tok-abc"

    def decode_jwt(token):
        return {"username": "steward", "roles": ["catalog-admin"], "expires_in": 3600}

    def resolve_terms(base, token, names, version="v3", verify_tls=False):
        table = {
            "Member Number": {"id": "t-100", "glossaryId": "g-1"},
            "State Code": {"id": "t-200", "glossaryId": "g-1"},
        }
        return {n: copy.deepcopy(table[n]) for n in names if n in table}

    def list_methods(base, token, prefix=None, verify_tls=False):
        rows = [
            {"_id": "m1", "name": "Claims Member Number", "kind": "pattern", "builtIn": False, "isEnabled": True},
            {"_id": "m2", "name": "Claims State Code", "kind": "dictionary", "builtIn": False, "isEnabled": True},
            {"_id": "m3", "name": "Claims Builtin Clone", "kind": "pattern", "builtIn": True, "isEnabled": True},
        ]
        return [r for r in rows if not prefix or r["name"].startswith(prefix)]

    def remove_method(base, token, kind, _id, verify_tls=False):
        calls["removed"].append(_id)
        return f"rec-{_id}"

    monkeypatch.setattr(api_mod.pdc_mod, "auth", auth)
    monkeypatch.setattr(api_mod.pdc_mod, "decode_jwt", decode_jwt)
    monkeypatch.setattr(api_mod.pdc_mod, "resolve_terms", resolve_terms)
    monkeypatch.setattr(api_mod.pdc_mod, "list_methods", list_methods)
    monkeypatch.setattr(api_mod.pdc_mod, "remove_method", remove_method)
    return calls

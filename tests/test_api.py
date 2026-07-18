"""API tests: the FastAPI layer over the engine, PDC calls mocked."""

import json

from tests.conftest import loaded_client, make_registry


class TestLoadAndSummary:
    def test_version(self, api_client):
        body = api_client.get("/api/version").json()
        assert body["service"] == "policy-generator"

    def test_load_by_path(self, api_client, registry_file):
        res = api_client.post(f"/api/load?path={registry_file}")
        assert res.status_code == 200
        body = res.json()
        assert body["glossary"] == "Claims"
        assert body["concepts"] == 4
        assert body["unresolved"] == 3
        assert body["file"] == "registry.claims.json"

    def test_load_by_upload(self, api_client, registry_file):
        with open(registry_file, "rb") as f:
            res = api_client.post("/api/load", files={"registry": ("r.json", f, "application/json")})
        assert res.status_code == 200
        assert res.json()["seeded"] == 3

    def test_load_rejects_wrong_schema(self, api_client, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"schema": "nope", "concepts": []}')
        res = api_client.post(f"/api/load?path={bad}")
        assert res.status_code == 400
        assert "schema" in res.json()["detail"]

    def test_endpoints_require_registry(self, api_client):
        assert api_client.post("/api/preview").status_code == 400
        assert api_client.get("/api/registry/export").status_code == 400


class TestAuthorEndpoints:
    def test_preview_shape_and_buckets(self, api_client, registry_file):
        client = loaded_client(api_client, registry_file)
        body = client.post("/api/preview", json={}).json()
        assert body["prefix"] == "Claims"
        assert len(body["patterns"]) == 1
        assert body["patterns"][0]["term_id"] == "t-100"
        assert body["dictionaries"][0]["values_count"] == 3
        buckets = {s["term"]: s["bucket"] for s in body["skipped"]}
        assert buckets["Claim Notes"] == "rule"       # free text
        assert buckets["Audit Record"] == "structural"

    def test_mapping_only_gets_its_own_bucket(self, api_client, tmp_path):
        reg = make_registry()
        reg["concepts"] += [
            # would hit the amber seed bucket by name — the steward's declared
            # intent wins and moves it to the calm mapping_only bucket
            {"term_name": "Broker Email", "tags": ["pii"], "detect": [],
             "detection_intent": "mapping_only"},
            {"term_name": "Member Phone", "tags": ["pii"], "detect": []},
        ]
        path = tmp_path / "registry.claims.json"
        path.write_text(json.dumps(reg), encoding="utf-8")
        client = loaded_client(api_client, path)
        buckets = {s["term"]: s["bucket"]
                   for s in client.post("/api/preview", json={}).json()["skipped"]}
        assert buckets["Broker Email"] == "mapping_only"
        assert buckets["Member Phone"] == "seed"          # still a real warner

    def test_seed_request_written_beside_registry(self, api_client, tmp_path):
        reg = make_registry()
        path = tmp_path / "registry.claims.json"
        path.write_text(json.dumps(reg), encoding="utf-8")
        client = loaded_client(api_client, path)
        res = client.post("/api/seed-request", json={"terms": ["Member Phone", " "]})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["file"] == "seed-request.json" and body["terms"] == 1
        data = json.loads((tmp_path / "seed-request.json").read_text(encoding="utf-8"))
        assert data["registry_file"] == "registry.claims.json"
        assert data["terms"] == [{"name": "Member Phone", "reason": "no_seed"}]
        assert "requested_at" in data

    def test_seed_request_needs_a_path_loaded_registry(self, api_client, registry_file):
        # uploaded Registries have no home directory to write back into
        with open(registry_file, "rb") as f:
            api_client.post("/api/load", files={"registry": ("r.json", f, "application/json")})
        res = api_client.post("/api/seed-request", json={"terms": ["Member Phone"]})
        assert res.status_code == 400
        assert "uploaded" in res.json()["detail"]

    def test_seed_request_refuses_an_empty_ask(self, api_client, registry_file):
        client = loaded_client(api_client, registry_file)
        assert client.post("/api/seed-request", json={"terms": ["  "]}).status_code == 400

    def test_author_downloads_zip(self, api_client, registry_file):
        client = loaded_client(api_client, registry_file)
        res = client.post("/api/author", json={"prefix": "Lab 1"})
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"
        assert "lab-1-data-identification.zip" in res.headers["content-disposition"]
        assert res.content[:2] == b"PK"


class TestReconcileFlow:
    def _connect(self, client):
        res = client.post("/api/pdc/connect", json={
            "base_url": "https://pdc.example", "username": "steward", "password": "good",
        })
        assert res.status_code == 200, res.text
        return res.json()

    def test_connect_and_bad_credentials(self, api_client, fake_pdc):
        who = self._connect(api_client)
        assert who["username"] == "steward"
        res = api_client.post("/api/pdc/connect", json={
            "base_url": "https://pdc.example", "username": "steward", "password": "bad",
        })
        assert res.status_code == 400

    def test_batched_reconcile_apply_and_export(self, api_client, registry_file, fake_pdc):
        client = loaded_client(api_client, registry_file)
        self._connect(client)

        offset, batches = 0, 0
        while True:
            body = client.post("/api/reconcile", json={"offset": offset, "limit": 2}).json()
            batches += 1
            if body["finished"]:
                break
            offset = body["done"]
        assert batches == 2
        counts = body["counts"]
        assert counts == {"verified": 1, "mismatch": 0, "resolved": 1, "missing": 2}
        assert body["bindable"] == 1

        applied = client.post("/api/reconcile/apply").json()
        assert applied["applied"] == 1                    # State Code got t-200
        assert applied["resolved_term_ids"] == 2
        assert applied["glossary_id"] == "g-1"

        exported = client.get("/api/registry/export")
        assert exported.status_code == 200
        assert '"t-200"' in exported.text

    def test_methods_and_scoped_retire(self, api_client, fake_pdc):
        self._connect(api_client)
        body = api_client.post("/api/pdc/methods", json={"prefix": "Claims"}).json()
        assert body["count"] == 4

        res = api_client.post("/api/pdc/retire", json={"prefix": "Claims"})
        assert res.status_code == 200
        out = res.json()
        assert out["removed"] == 3                        # built-in never deleted
        assert fake_pdc["removed"] == ["m1", "m2", "m4"]

        res = api_client.post("/api/pdc/retire", json={"prefix": ""})
        assert res.status_code == 400                     # retire is always scoped

    def test_pdc_endpoints_require_connect(self, api_client):
        assert api_client.post("/api/pdc/methods", json={}).status_code == 400


class TestSessionRefresh:
    """Keycloak tokens live minutes; a steward's session lives hours. On a
    401 the backend re-authenticates once with the in-memory credentials and
    retries, so later calls (methods, retire, deploy, drift) just work."""

    def _connect(self, client, **extra):
        body = {"base_url": "https://pdc.example",
                "username": "steward", "password": "good", **extra}
        res = client.post("/api/pdc/connect", json=body)
        assert res.status_code == 200, res.text
        return res.json()

    def _flaky_list(self, monkeypatch, fails=1):
        """list_methods raises a real TokenExpired `fails` times, then works."""
        from policy_generator import api as api_mod
        from policy_generator import pdc as real_pdc
        real_list = api_mod.pdc_mod.list_methods
        state = {"fails": fails, "auths": 0}

        def flaky(base, token, prefix=None, verify_tls=False):
            if state["fails"] > 0:
                state["fails"] -= 1
                raise real_pdc.TokenExpired("401 Unauthorized")
            return real_list(base, token, prefix=prefix, verify_tls=verify_tls)

        def reauth(base, user, pw, version="v3", verify_tls=False, realm="pdc"):
            assert (user, pw) == ("steward", "good")   # the held credentials
            state["auths"] += 1
            return "tok-new"

        monkeypatch.setattr(api_mod.pdc_mod, "list_methods", flaky)
        monkeypatch.setattr(api_mod.pdc_mod, "auth", reauth)
        return state

    def test_transparent_reauth_on_401(self, api_client, fake_pdc, monkeypatch):
        from policy_generator import api as api_mod
        self._connect(api_client)
        state = self._flaky_list(monkeypatch)

        body = api_client.post("/api/pdc/methods", json={}).json()
        assert body["count"] == 4                      # the retry succeeded
        assert state["auths"] == 1                     # exactly one re-auth
        # the refreshed token is the session's token now — every card uses it
        assert api_mod._state["pdc"]["token"] == "tok-new"
        status = api_client.get("/api/pdc/status").json()
        assert status["connected"] is True and status["renewable"] is True

    def test_still_401_when_reauth_also_expires(self, api_client, fake_pdc, monkeypatch):
        self._connect(api_client)
        self._flaky_list(monkeypatch, fails=99)        # expired stays expired
        res = api_client.post("/api/pdc/methods", json={})
        assert res.status_code == 401
        assert api_client.get("/api/pdc/status").json() == {"connected": False}

    def test_token_only_session_cannot_self_heal(self, api_client, fake_pdc, monkeypatch):
        # a pasted bearer token carries no credentials to re-auth with
        res = api_client.post("/api/pdc/connect", json={
            "base_url": "https://pdc.example", "token": "tok-abc"})
        assert res.status_code == 200
        assert api_client.get("/api/pdc/status").json()["renewable"] is False
        state = self._flaky_list(monkeypatch, fails=99)
        res = api_client.post("/api/pdc/methods", json={})
        assert res.status_code == 401
        assert state["auths"] == 0                     # never even tried


class TestDeployFlow:
    def _ready(self, api_client, registry_file):
        client = loaded_client(api_client, registry_file)
        res = client.post("/api/pdc/connect", json={
            "base_url": "https://pdc.example", "username": "steward", "password": "good",
        })
        assert res.status_code == 200, res.text
        return client

    def test_deploy_requires_registry_and_pdc(self, api_client, registry_file, fake_pdc):
        assert api_client.post("/api/pdc/deploy", json={}).status_code == 400  # no registry
        client = loaded_client(api_client, registry_file)
        assert client.post("/api/pdc/deploy", json={}).status_code == 400      # no pdc

    def test_status_endpoint(self, api_client, fake_pdc):
        assert api_client.get("/api/pdc/status").json() == {"connected": False}
        api_client.post("/api/pdc/connect", json={
            "base_url": "https://pdc.example", "username": "steward", "password": "good"})
        body = api_client.get("/api/pdc/status").json()
        assert body["connected"] is True and body["username"] == "steward"

    def test_dry_run_plans_without_uploading(self, api_client, registry_file, fake_pdc):
        client = self._ready(api_client, registry_file)
        body = client.post("/api/pdc/deploy", json={"dry_run": True}).json()
        assert body["dry_run"] is True and body["prefix"] == "Claims"
        # both authored methods already exist in the fake catalog -> updates
        assert body["counts"] == {"create": 0, "update": 2}
        assert fake_pdc["uploads"] == []                  # dry-run never uploads

    def test_deploy_uploads_binds_and_verifies(self, api_client, registry_file, fake_pdc):
        client = self._ready(api_client, registry_file)
        body = client.post("/api/pdc/deploy", json={}).json()

        # payload shape: one zip per kind, in the export layout author produces
        kinds = {u["kind"]: u for u in fake_pdc["uploads"]}
        assert set(kinds) == {"DataPattern", "Dictionary"}
        assert kinds["DataPattern"]["filename"] == "patterns-import.zip"
        assert kinds["DataPattern"]["entries"] == ["claims_member_number.json"]
        assert kinds["Dictionary"]["entries"] == ["claims_state_code.zip"]
        assert fake_pdc["waited"] == ["w-DataPattern", "w-Dictionary"]

        # prefix guard: everything deployed carries the authoring prefix
        assert all(r["name"].startswith("Claims ") for r in body["rows"])

        # verified against the live list; only the id-resolved concept is bound
        assert body["counts"] == {"imported": 2, "failed": 0, "bound": 1}
        assert fake_pdc["binds"] == [
            {"kind": "DataPattern", "_id": "m1", "term": "Member Number", "id": "t-100"}]
        by_name = {r["name"]: r for r in body["rows"]}
        assert by_name["Claims Member Number"]["bound"] is True
        assert by_name["Claims State Code"]["bound"] is None    # no term id yet

    def test_deploy_refuses_a_degenerate_prefix(self, api_client, registry_file, fake_pdc):
        client = self._ready(api_client, registry_file)
        res = client.post("/api/pdc/deploy", json={"prefix": "x"})
        assert res.status_code == 400
        assert "prefix" in res.json()["detail"]

    def test_identify_is_always_scoped(self, api_client, registry_file, fake_pdc):
        client = self._ready(api_client, registry_file)
        res = client.post("/api/pdc/identify", json={"prefix": "Claims", "scope": []})
        assert res.status_code == 400                     # never catalog-wide

        body = client.post("/api/pdc/identify",
                           json={"prefix": "Claims", "scope": ["e-1", "e-2"]}).json()
        assert body["job_id"] == "job-1"
        (job,) = fake_pdc["jobs"]
        assert job["scope"] == ["e-1", "e-2"]
        assert job["dictionaryIds"] == ["m2"]
        assert set(job["dataPatternIds"]) == {"m1", "m4"}   # built-in m3 excluded


class TestDriftEndpoint:
    def test_drift_verdicts(self, api_client, registry_file, fake_pdc):
        client = loaded_client(api_client, registry_file)
        client.post("/api/pdc/connect", json={
            "base_url": "https://pdc.example", "username": "steward", "password": "good"})
        body = client.post("/api/pdc/drift", json={}).json()
        assert body["prefix"] == "Claims"
        assert body["counts"] == {"clean": 1, "drifted": 1, "orphaned": 1, "missing": 0}
        by_name = {r["name"]: r for r in body["rows"]}
        assert by_name["Claims Member Number"]["verdict"] == "clean"
        drifted = by_name["Claims State Code"]
        assert drifted["verdict"] == "drifted"
        joined = " ".join(drifted["findings"])
        assert "governed tags" in joined and "value rows" in joined
        assert by_name["Claims Legacy Thing"]["verdict"] == "orphaned"

    def test_drift_requires_registry_and_pdc(self, api_client, registry_file, fake_pdc):
        assert api_client.post("/api/pdc/drift", json={}).status_code == 400
        client = loaded_client(api_client, registry_file)
        assert client.post("/api/pdc/drift", json={}).status_code == 400
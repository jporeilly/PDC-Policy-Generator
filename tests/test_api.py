"""API tests: the FastAPI layer over the engine, PDC calls mocked."""

from tests.conftest import loaded_client


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
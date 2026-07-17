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
        assert body["count"] == 3

        res = api_client.post("/api/pdc/retire", json={"prefix": "Claims"})
        assert res.status_code == 200
        out = res.json()
        assert out["removed"] == 2                        # built-in never deleted
        assert fake_pdc["removed"] == ["m1", "m2"]

        res = api_client.post("/api/pdc/retire", json={"prefix": ""})
        assert res.status_code == 400                     # retire is always scoped

    def test_pdc_endpoints_require_connect(self, api_client):
        assert api_client.post("/api/pdc/methods", json={}).status_code == 400
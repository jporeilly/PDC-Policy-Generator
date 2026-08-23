"""
pdc.py — lean PDC Public API client for the reconcile, deploy and
drift-check stages.

A verbatim subset of the Glossary Generator's battle-tested pdc_api.py
(auth incl. the Keycloak-first path, and resolve_terms with its three
fallback lookups — including the fix for the /search type-facet bug that
once made Resolve match 0 terms), plus the Data Identification method
lifecycle (list / detail / import / bind / retire) discovered live against
PDC 11.0.0. Stdlib only: no new dependencies.
"""
from __future__ import annotations
import json
import re
import ssl
import time
import uuid
import urllib.request
import urllib.parse
import urllib.error

_REALM_RE = re.compile(r"/(?:auth|keycloak)/realms/([^/]+)", re.I)


def split_base(base_url):
    """Return (clean_base, detected_realm_or_None). Strips a trailing Keycloak
       realm path, token path, /keycloak, or /api/public/vN."""
    b = (base_url or "").strip().rstrip("/")
    m = _REALM_RE.search(b)
    realm = m.group(1) if m else None
    b = re.sub(r"/protocol/openid-connect/token/?$", "", b, flags=re.I)
    b = re.sub(r"/(?:auth|keycloak)/realms/[^/]+.*$", "", b, flags=re.I)
    b = re.sub(r"/api/public/v\d+.*$", "", b, flags=re.I)
    b = re.sub(r"/keycloak/?$", "", b, flags=re.I)
    return b.rstrip("/"), realm


def clean_base(base_url):
    return split_base(base_url)[0]


class TokenExpired(Exception):
    """Raised on a 401 so the caller can re-auth once and retry."""


def _ctx(verify_tls):
    if verify_tls:
        return None
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _req(method, url, token=None, body=None, headers=None, verify_tls=True,
         timeout=30, form=False):
    """Generic request. Returns parsed JSON (or {} on empty body).
       Raises TokenExpired on 401; RuntimeError with the server text otherwise."""
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx(verify_tls)) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:600]
        except Exception:
            pass
        if e.code == 401:
            raise TokenExpired(detail or "401 Unauthorized")
        raise RuntimeError(f"HTTP {e.code} on {method} {url}: {detail}")


# --------------------------------------------------------------------------- #
#  Auth (Keycloak-first, /auth fallback — same as the Glossary app)
# --------------------------------------------------------------------------- #
def keycloak_auth(base_url, username, password, realm="pdc", client_id="pdc-client",
                  verify_tls=True, timeout=20):
    url = clean_base(base_url) + f"/keycloak/realms/{realm}/protocol/openid-connect/token"
    payload = {"client_id": client_id, "grant_type": "password",
               "username": username, "password": password}
    out = _req("POST", url, body=payload, verify_tls=verify_tls, timeout=timeout, form=True)
    tok = out.get("access_token") or (out.get("data") or {}).get("access_token")
    if not tok:
        raise RuntimeError("Keycloak auth returned no access_token")
    return tok


def pdc_api_auth(base_url, username, password, version="v3", verify_tls=True, timeout=20):
    url = clean_base(base_url) + f"/api/public/{version}/auth"
    payload = {"username": username, "password": password, "client_id": "pdc-client",
               "grant_type": "password", "scope": "openid profile email"}
    out = _req("POST", url, body=payload, verify_tls=verify_tls, timeout=timeout, form=True)
    tok = (out.get("data") or {}).get("accessToken") or out.get("accessToken")
    if not tok:
        raise RuntimeError("auth succeeded but no accessToken in response")
    return tok


def auth(base_url, username, password, version="v3", verify_tls=True, timeout=20,
         realm="pdc", client_id="pdc-client"):
    """Keycloak token endpoint first (the real IdP), /api/public/<v>/auth fallback."""
    try:
        return keycloak_auth(base_url, username, password, realm, client_id, verify_tls, timeout)
    except Exception as e_kc:
        try:
            return pdc_api_auth(base_url, username, password, version, verify_tls, timeout)
        except Exception as e_pdc:
            raise RuntimeError(f"Keycloak auth failed: {e_kc}  |  /auth fallback failed: {e_pdc}")


def decode_jwt(token):
    """Display-only decode of a JWT payload (NOT verified). Best-effort."""
    import base64, time as _time
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:
        return {}
    roles = (claims.get("realm_access") or {}).get("roles") or []
    exp = claims.get("exp")
    out = {"username": claims.get("preferred_username") or claims.get("sub") or "",
           "roles": roles, "exp": exp}
    if isinstance(exp, (int, float)):
        out["expires_in"] = max(0, int(exp - _time.time()))
    return out


# --------------------------------------------------------------------------- #
#  GraphQL — Data Identification method lifecycle (list + retire)
#
#  PDC's Data Identification UI is backed by a graphql-compose-mongoose
#  Apollo endpoint at <base>/graphql, NOT the public REST API. Introspection
#  is disabled in production, but the generated CRUD field names are the
#  Mongoose convention and were confirmed live against PDC 11.0.0:
#    query    DictionariesMany / DataPatternsMany   -> [{_id, name, builtIn}]
#    mutation DictionariesRemoveById(_id) {recordId}
#             DataPatternsRemoveById(_id) {recordId}
#  The same Keycloak bearer token that drives the REST API authenticates it.
# --------------------------------------------------------------------------- #
_METHOD_KINDS = {
    "Dictionary": {"many": "DictionariesMany", "remove": "DictionariesRemoveById",
                   "by_id": "DictionariesById", "update": "DictionariesUpdateById",
                   "update_input": "UpdateByIddictionariesInput"},
    "DataPattern": {"many": "DataPatternsMany", "remove": "DataPatternsRemoveById",
                    "by_id": "DataPatternsById", "update": "DataPatternsUpdateById",
                    "update_input": "UpdateByIddatapatternsInput"},
}


def graphql(base_url, token, query, variables=None, verify_tls=True, timeout=30):
    """POST a GraphQL operation to <base>/graphql. Returns the `data` object;
       raises TokenExpired on 401, RuntimeError carrying any GraphQL errors."""
    url = clean_base(base_url) + "/graphql"
    body = {"query": query}
    if variables is not None:
        body["variables"] = variables
    out = _req("POST", url, token=token, body=body, verify_tls=verify_tls, timeout=timeout)
    if out.get("errors"):
        msg = "; ".join(str((e or {}).get("message", e)) for e in out["errors"])[:600]
        raise RuntimeError(f"GraphQL error: {msg}")
    return out.get("data") or {}


_PAGE_SIZE = 200        # what we ask for; PDC may serve less per page
_MAX_PAGES = 200        # runaway guard — 200 pages is far past any real catalog


def _list_all(base_url, token, field, verify_tls=True, timeout=30, page_size=_PAGE_SIZE):
    """Every row of one *Many collection, paged.

    PDC's *Many resolvers apply a SERVER-SIDE default ceiling — observed at
    100 rows — and answer a limitless query with an arbitrary page rather than
    an error. That silence cost a deploy: with 95 built-in dictionaries already
    in the catalog, a 27-method import could only ever surface as 5, and the
    verification, drift and (worst) the scoped retire all read through here.

    Paging stops on an EMPTY page, never on a short one: a server that caps
    `limit` below what we ask returns a short page with more rows waiting. Two
    guards keep a hostile server from spinning us: a page cap, and a repeat
    check for a server that ignores `skip` and re-serves page one forever.
    """
    q = ("query($limit: Int, $skip: Int) { %s(limit: $limit, skip: $skip) "
         "{ _id name builtIn } }" % field)
    out, seen, skip = [], set(), 0
    for _ in range(_MAX_PAGES):
        try:
            page = (graphql(base_url, token, q,
                            variables={"limit": page_size, "skip": skip},
                            verify_tls=verify_tls, timeout=timeout) or {}).get(field) or []
        except RuntimeError as e:
            # An older schema without limit/skip: fall back to the one-shot
            # read rather than failing. It under-reports — that is the bug this
            # function exists to fix — so say so where a caller can see it.
            if "limit" not in str(e) and "skip" not in str(e):
                raise
            data = graphql(base_url, token, "{ %s { _id name builtIn } }" % field,
                           verify_tls=verify_tls, timeout=timeout)
            return list((data or {}).get(field) or [])
        if not page:
            break
        fresh = [m for m in page if (m or {}).get("_id") not in seen]
        if not fresh:
            break                       # skip ignored — stop rather than loop
        seen.update(m.get("_id") for m in fresh)
        out.extend(fresh)
        skip += len(page)
    return out


def list_methods(base_url, token, prefix=None, verify_tls=True, timeout=30):
    """List Data Identification methods (dictionaries + patterns). When
       `prefix` is given, only methods whose name starts with it are returned —
       the guard that keeps a retire scoped to the app's own authored set.
       Each row: {kind, _id, name, builtIn}.

       The prefix filter runs here, over the COMPLETE collection: filtering a
       capped page is how a partial deploy read as a total failure."""
    rows = []
    for kind, fld in (("Dictionary", "DictionariesMany"), ("DataPattern", "DataPatternsMany")):
        for m in _list_all(base_url, token, fld, verify_tls=verify_tls, timeout=timeout):
            name = m.get("name") or ""
            if prefix and not name.startswith(prefix):
                continue
            rows.append({"kind": kind, "_id": m.get("_id"), "name": name,
                         "builtIn": bool(m.get("builtIn"))})
    return rows


def remove_method(base_url, token, kind, _id, verify_tls=True, timeout=30):
    """Delete one method by _id. `kind` is 'Dictionary' or 'DataPattern'.
       Returns the removed recordId (truthy on success)."""
    spec = _METHOD_KINDS.get(kind)
    if not spec:
        raise ValueError(f"unknown method kind: {kind!r}")
    data = graphql(
        base_url, token,
        f"mutation($id: String!) {{ {spec['remove']}(_id: $id) {{ recordId }} }}",
        variables={"id": _id}, verify_tls=verify_tls, timeout=timeout)
    payload = data.get(spec["remove"]) or {}
    return payload.get("recordId")


# --------------------------------------------------------------------------- #
#  Deploy — import the authored method set into PDC (discovered live, 1.8.0)
#
#  PDC 11's UI imports Data Identification methods with a multipart upload to
#  POST <base>/api/importWorkerFiles (fields: type, fileName, file), where
#  `type` is DATA_PATTERNS_IMPORTER (accepts .zip/.json) or DICTIONARY_IMPORTER
#  (accepts .zip in the nested Dictionary_Export layout). Discovered by
#  reading the SPA bundle (/client/App.js) after GraphQL suggestion probing
#  found no import mutation; verified live 2026-07-17: this app's own
#  export-layout zips import as-is, deterministic _ids preserved. The response
#  is a worker record ({_id, workerName: DATA_PATTERN_MANAGER |
#  DICTIONARY_MANAGER}); progress is polled via the WorkersById GraphQL query
#  (pipeline.metadata.status: RUNNING -> COMPLETED/FAILED).
#
#  Term binding: the LIVE schema's action field is applyBusinessTerms
#  [{name, id}] — NOT assignBusinessTerm (silently dropped by the importer).
#  The importer preserves applyBusinessTerms but rewrites an id it cannot
#  resolve to the term name, so deploy re-stamps the exact Registry ids after
#  import via <Kind>UpdateById(_id: String!, record: {rules}) — verified to
#  persist round-trip.
# --------------------------------------------------------------------------- #
_IMPORTERS = {
    "DataPattern": "DATA_PATTERNS_IMPORTER",
    "Dictionary": "DICTIONARY_IMPORTER",
}


def upload_import(base_url, token, kind, filename, blob, verify_tls=True, timeout=120):
    """Upload one import zip to POST /api/importWorkerFiles. `kind` is
    'DataPattern' or 'Dictionary' (mapped to the discovered importer type).
    Returns the worker record ({_id, workerName, ...}) PDC responds with."""
    importer = _IMPORTERS.get(kind)
    if not importer:
        raise ValueError(f"unknown method kind: {kind!r}")
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("type", importer), ("fileName", filename)):
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; "
                      f'name="{name}"\r\n\r\n{value}\r\n').encode())
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; "
                  f'name="file"; filename="{filename}"\r\n'
                  "Content-Type: application/zip\r\n\r\n").encode() + blob + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    url = clean_base(base_url) + "/api/importWorkerFiles"
    req = urllib.request.Request(url, data=b"".join(parts), method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx(verify_tls)) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:600]
        except Exception:
            pass
        if e.code == 401:
            raise TokenExpired(detail or "401 Unauthorized")
        raise RuntimeError(f"HTTP {e.code} on POST {url}: {detail}")


def worker_status(base_url, token, worker_id, verify_tls=True, timeout=30):
    """One WorkersById poll -> {'status': RUNNING|COMPLETED|FAILED|None,
    'label': ...}. The import workers report through pipeline.metadata."""
    data = graphql(
        base_url, token,
        "query($id: MongoID!) { WorkersById(_id: $id) { workerName pipeline } }",
        variables={"id": worker_id}, verify_tls=verify_tls, timeout=timeout)
    w = data.get("WorkersById") or {}
    pipeline = w.get("pipeline") or {}
    md = pipeline.get("metadata") or {}
    # The WHOLE pipeline travels back, not just the status field. A PDC import
    # worker reports COMPLETED after rejecting every file in the zip, so the
    # status alone cannot tell success from silent total failure — the detail
    # that names the rejected file lives in the rest of this payload, and we
    # spent an afternoon guessing at what it would have told us.
    return {"status": md.get("status"), "label": pipeline.get("label"),
            "workerName": w.get("workerName"), "metadata": md, "pipeline": pipeline}


def profiled_at(base_url, token, entity_id, version="v3", verify_tls=True, timeout=20):
    """When PDC last profiled an entity (system.profiledAt), or None.

    Identification matches PATTERNS against the stored profile, not against the
    table as it stands. Rebuild an estate and every pattern quietly stops
    matching until a fresh profile exists — no error, no warning, methods that
    tag nothing. Live-proven 2026-08-20: identical methods tagged 9 columns in a
    freshly profiled table and 1 in a stale one, in the same job.
    """
    ent = get_entity(base_url, token, entity_id, version=version,
                     verify_tls=verify_tls, timeout=timeout)
    sysblk = ent.get("system") if isinstance(ent.get("system"), dict) else {}
    return sysblk.get("profiledAt") or (ent.get("attributes") or {}).get("profiledAt")


def job_status(base_url, token, job_id, verify_tls=True, timeout=30):
    """What became of a job this app started — an identification run, typically.

    The app could fire DATA_IDENTIFICATION and then had no way to ask how it
    went; the answer lived in PDC's Workers page and nowhere else. Two lookups,
    because a job id is not always a worker id: WorkersById first (the shape the
    import workers answer to), then a scan of recent workers for one carrying
    the id. Returns {found, status, label, workerName, jobs[], via} — `jobs`
    carries the per-job lines the Workers page shows ("Completed Total 2 of 2"),
    which is the part that says whether the scope was actually covered.
    """
    def _shape(w, via):
        pipeline = w.get("pipeline") or {}
        md = pipeline.get("metadata") or {}
        jobs = []
        for node in (pipeline.get("nodes") or []):
            nmd = (node or {}).get("metadata") or {}
            jobs.append({"label": (node or {}).get("label"), "status": nmd.get("status"),
                         "statistics": nmd.get("statistics") or {},
                         "message": nmd.get("message")})
        return {"found": True, "via": via, "id": w.get("_id") or job_id,
                "status": md.get("status"), "label": pipeline.get("label"),
                "workerName": w.get("workerName"), "jobs": jobs,
                "metadata": md}

    try:
        data = graphql(base_url, token,
                       "query($id: MongoID!) { WorkersById(_id: $id) "
                       "{ _id workerName pipeline } }",
                       variables={"id": job_id}, verify_tls=verify_tls, timeout=timeout)
        w = data.get("WorkersById")
        if w:
            return _shape(w, "WorkersById")
    except RuntimeError:
        pass                      # not a worker id, or the field rejects it — try the list

    try:
        data = graphql(base_url, token,
                       "query { WorkersMany(limit: 50, sort: _ID_DESC) "
                       "{ _id workerName pipeline } }",
                       verify_tls=verify_tls, timeout=timeout)
        for w in (data.get("WorkersMany") or []):
            blob = json.dumps(w)
            if job_id and job_id in blob:
                return _shape(w, "WorkersMany")
    except RuntimeError as e:
        return {"found": False, "id": job_id, "error": str(e)[:200]}
    return {"found": False, "id": job_id,
            "error": "no worker carries this job id — it may have aged out of the recent list"}


def recent_workers(base_url, token, limit=20, verify_tls=True, timeout=30):
    """The Workers page, as data: the most recent worker processes with their
    status. Useful when a job id is not to hand — which is most of the time."""
    data = graphql(base_url, token,
                   "query($n: Int) { WorkersMany(limit: $n, sort: _ID_DESC) "
                   "{ _id workerName pipeline } }",
                   variables={"n": int(limit)}, verify_tls=verify_tls, timeout=timeout)
    out = []
    for w in (data.get("WorkersMany") or []):
        pipeline = w.get("pipeline") or {}
        md = pipeline.get("metadata") or {}
        out.append({"id": w.get("_id"), "workerName": w.get("workerName"),
                    "label": pipeline.get("label"), "status": md.get("status"),
                    "statistics": md.get("statistics") or {}})
    return out


def wait_worker(base_url, token, worker_id, verify_tls=True, timeout=120, poll=2.0):
    """Poll a worker until COMPLETED/FAILED or `timeout` seconds. Returns the
    final worker_status dict (status may still be RUNNING on timeout)."""
    deadline = time.time() + timeout
    last = {"status": None}
    while time.time() < deadline:
        last = worker_status(base_url, token, worker_id, verify_tls=verify_tls)
        if last.get("status") in ("COMPLETED", "FAILED", "SUCCESS"):
            return last
        time.sleep(poll)
    return last


# Rule sub-selection: actions/confidenceScore/condition/regexMatch/
# metadataHints are JSON scalars on the live schema (no sub-selection).
_RULES_SEL = "rules { type minSamples confidenceScore condition actions }"


def get_method(base_url, token, kind, _id, verify_tls=True, timeout=30):
    """Full method detail by _id — everything drift-check compares: name,
    enabled/builtIn, categories, tags + term bindings (in rules.actions),
    regexMatch/profilePatterns (patterns), rowCount/csv (dictionaries).
    Dictionary VALUES are not readable over GraphQL — rowCount is the proxy."""
    spec = _METHOD_KINDS.get(kind)
    if not spec:
        raise ValueError(f"unknown method kind: {kind!r}")
    extra = ("rowCount csv dictionaryTermId" if kind == "Dictionary"
             else "regexMatch profilePatterns minSamples dataEventThreshold")
    data = graphql(
        base_url, token,
        f"query($id: String!) {{ {spec['by_id']}(_id: $id) {{ "
        f"_id name type isEnabled builtIn categories description {extra} "
        f"{_RULES_SEL} metadataHints }} }}",
        variables={"id": _id}, verify_tls=verify_tls, timeout=timeout)
    return data.get(spec["by_id"]) or {}


def profiling_for_parent(base_url, token, parent_id, version="v3", verify_tls=True,
                         timeout=30, sample_limit=25):
    """The STORED profile for every column under one table/file —
    POST /entities/filter/profiling-info scoped by parentIds (the same route
    the Glossary's harvest reads; identification computes its scores against
    exactly this data). Returns {column_name_lower: {samples: [str], patterns:
    [...]}} — empty samples means PDC retained none, and no pattern can score
    there (the buildSamples lesson, 2026-08-22)."""
    url = (clean_base(base_url)
           + f"/api/public/{version}/entities/filter/profiling-info"
           + f"?sampleLimit={sample_limit}&size=500")
    out = _req("POST", url, token=token,
               body={"filters": {"parentIds": [parent_id]}},
               verify_tls=verify_tls, timeout=timeout)
    res = {}
    for it in _results(out):
        name = str(it.get("name") or (it.get("attributes") or {}).get("name") or "").strip()
        if not name:
            continue
        pinfo = it.get("profilingInfo") or it.get("profiling") or {}
        sampling = pinfo.get("sampling") or pinfo.get("samples") or {}
        raw = sampling.get("sample") if isinstance(sampling, dict) else sampling
        samples = []
        for s in raw or []:
            v = s.get("value") if isinstance(s, dict) else s
            if v is not None and str(v).strip():
                samples.append(str(v))
        res[name.lower()] = {"samples": samples,
                             "patterns": pinfo.get("patternAnalysis") or pinfo.get("patterns") or []}
    return res


def confirm_term_by_column_echo(base_url, token, term_name, term_id, sources,
                                version="v3", verify_tls=True, timeout=20):
    """Prove a term is alive by its id when every NAME lookup misses.

    PDC's search cannot find names containing '&' (field 2026-08-23: both
    'Infrastructure & Assets' terms reconciled as MISSING while their methods
    were deployed and firing), and /entities/{id} does not serve term ids at
    all — so neither name nor id can be asked directly. But a column the
    Glossary mapped to the term carries businessTerms[{termId, name}], and PDC
    echoes the term's NAME against the id it stores — an echo it can only
    produce if the term exists under that id. Returns
    {'id', 'glossaryId', 'via': 'column-echo'} or None."""
    cols = []
    for s in sources or []:
        if not isinstance(s, str):
            continue
        col = s.rsplit(".", 1)[-1].strip()
        if col and col not in cols:
            cols.append(col)
    want_name = (term_name or "").strip().lower()
    for col in cols[:4]:
        try:
            ents = filter_entities(base_url, token, {"names": [col]},
                                   version, verify_tls, timeout)
        except TokenExpired:
            raise
        except Exception:
            continue
        for e in ents:
            a = e.get("attributes") or {}
            for bt in (a.get("businessTerms") or e.get("businessTerms") or []):
                tid = bt.get("termId") or bt.get("id")
                if (tid and str(tid) == str(term_id)
                        and str(bt.get("name", "")).strip().lower() == want_name):
                    return {"id": tid, "glossaryId": bt.get("glossaryId"),
                            "via": "column-echo"}
    return None


def bind_business_term(base_url, token, kind, _id, term_name, term_id,
                       verify_tls=True, timeout=30):
    """Stamp applyBusinessTerms [{name, id}] into every action of the method's
    rules (read-modify-write via <Kind>UpdateById). This is how deploy binds
    the Registry's minted term ids: the importer preserves the field but
    rewrites ids it cannot resolve to the term name. Returns True on success."""
    spec = _METHOD_KINDS.get(kind)
    if not spec:
        raise ValueError(f"unknown method kind: {kind!r}")
    detail = get_method(base_url, token, kind, _id, verify_tls=verify_tls, timeout=timeout)
    rules = detail.get("rules") or []
    if not rules:
        return False
    bt = {"name": term_name}
    if term_id:
        bt["id"] = term_id
    for rule in rules:
        for act in (rule.get("actions") or []):
            # the JSON scalar echoes schema nulls — drop them before writing back
            for k in [k for k, v in list(act.items()) if v is None]:
                act.pop(k)
            act["applyBusinessTerms"] = [dict(bt)]
    data = graphql(
        base_url, token,
        f"mutation($id: String!, $rec: {spec['update_input']}!) "
        f"{{ {spec['update']}(_id: $id, record: $rec) {{ recordId }} }}",
        variables={"id": _id, "rec": {"rules": rules}},
        verify_tls=verify_tls, timeout=timeout)
    return bool((data.get(spec["update"]) or {}).get("recordId"))


def set_method_enabled(base_url, token, kind, _id, enabled, verify_tls=True, timeout=30):
    """Enable or disable ONE method (<Kind>UpdateById, isEnabled) — the same
    mutation deploy uses to re-stamp term ids, so the write path is already
    proven against live PDC.

    Why this exists: PDC ships its built-in patterns and dictionaries ENABLED,
    and an identification job started anywhere other than this app (PDC's own
    screen, a schedule, ingest) classifies against whatever is enabled. In a
    custom-only programme that means shapes induced from somebody else's data
    competing with shapes induced from the estate's own — the inconsistency
    and drift the programme exists to avoid. Reversible by construction: pass
    enabled=True to put a method back exactly as it was.
    """
    spec = _METHOD_KINDS.get(kind)
    if not spec:
        raise ValueError(f"unknown method kind: {kind!r}")
    data = graphql(
        base_url, token,
        f"mutation($id: String!, $rec: {spec['update_input']}!) "
        f"{{ {spec['update']}(_id: $id, record: $rec) {{ recordId }} }}",
        variables={"id": _id, "rec": {"isEnabled": bool(enabled)}},
        verify_tls=verify_tls, timeout=timeout)
    return bool((data.get(spec["update"]) or {}).get("recordId"))


_COL_TYPES = ["COLUMN", "FIELD", "OBJECT", "FILE", "RESOURCE"]


def table_columns(base_url, token, table_name, version="v3", verify_tls=True, timeout=30):
    """Every column under a table, with whatever identification stamped on it:
    {name, id, business_terms[], tags[]}.

    Located by PARENT, not by name. Filtering COLUMN entities by the table's
    name returns nothing at all — a column is not called after its table — which
    is the first version of this function and the reason it reported zero
    columns against two tables that plainly have them. The table is resolved
    first, then its children are listed by `parentIds`, which is unambiguous.

    This is the last mile the app was missing: deploy proves methods LANDED and
    drift proves they still match the contract, but neither says whether a rule
    ever fired against real data. That answer lives on the columns.
    """
    tabs = filter_entities(base_url, token, {"names": [table_name], "types": ["TABLE", "VIEW"]},
                           version=version, verify_tls=verify_tls, timeout=timeout)
    tab = next((t for t in (tabs or [])
                if str(((t.get("attributes") or {}).get("name")) or t.get("name") or "").lower()
                == table_name.lower()), None) or (tabs or [None])[0]
    if not tab:
        return []
    rows = filter_entities(base_url, token,
                           {"parentIds": [_eid(tab)], "types": list(dict.fromkeys(_COL_TYPES))},
                           version=version, verify_tls=verify_tls, timeout=timeout)
    out = []
    for e in rows or []:
        if not isinstance(e, dict):
            continue
        attrs = e.get("attributes") or {}
        bts = attrs.get("businessTerms") if isinstance(attrs.get("businessTerms"), list) else []
        tags = attrs.get("tags") if isinstance(attrs.get("tags"), list) else []
        out.append({
            "id": _eid(e),
            "name": attrs.get("name") or e.get("name") or "",
            "path": attrs.get("qualifiedName") or attrs.get("path") or "",
            "business_terms": [str((b or {}).get("name") or b) for b in bts if b],
            "tags": [str((t or {}).get("name") or t) for t in tags if t],
        })
    return out


def start_identification_job(base_url, token, scope, dictionary_ids, pattern_ids,
                             verify_tls=True, timeout=30):
    """Trigger one DATA_IDENTIFICATION bulk job over POST /api/start-job —
    the exact payload PDC's own UI sends (read from the SPA bundle):
    {name: DATA_IDENTIFICATION, type: START, data: {scope, dictionaryIds,
    dataPatternIds}}. `scope` is a list of entity ids. Returns the job id."""
    url = clean_base(base_url) + "/api/start-job"
    body = {"name": "DATA_IDENTIFICATION", "type": "START",
            "data": {"scope": list(scope or []),
                     "dictionaryIds": list(dictionary_ids or []),
                     "dataPatternIds": list(pattern_ids or [])}}
    out = _req("POST", url, token=token, body=body, verify_tls=verify_tls, timeout=timeout)
    return out.get("_id") or (out.get("data") or {}).get("_id")


# --------------------------------------------------------------------------- #
#  Term resolution (verbatim logic from the Glossary app)
# --------------------------------------------------------------------------- #
def _results(out):
    d = out.get("data", out)
    if isinstance(d, dict):
        for k in ("results", "items", "hits", "data"):
            if isinstance(d.get(k), list):
                return d[k]
        return []
    return d if isinstance(d, list) else []


def _eid(it):
    return it.get("_id") or it.get("id")


def _glossary_id(item):
    """A TERM's glossary is its rootId (NOT parentId, which is the category)."""
    p = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    return (item.get("rootId") or item.get("glossaryId") or item.get("rootID")
            or p.get("rootId") or p.get("glossaryId"))


def _bt_match(item, name):
    for bt in (item.get("businessTerms") or []):
        if str(bt.get("name", "")).strip().lower() == name.strip().lower():
            tid = bt.get("termId") or bt.get("id")
            if tid:
                return tid, bt.get("glossaryId")
    return None, None


def filter_entities(base_url, token, filters, version="v3", verify_tls=True, timeout=20):
    url = clean_base(base_url) + f"/api/public/{version}/entities/filter?extended=true&size=200"
    out = _req("POST", url, token=token, body={"filters": filters},
               verify_tls=verify_tls, timeout=timeout)
    return _results(out)


def get_entity(base_url, token, entity_id, version="v3", verify_tls=True, timeout=20):
    """One entity, whole: GET /entities/{id}. Everything PDC holds on it —
    attributes.features (rating, qualityScore, sensitivity, lineage flags),
    businessTerms, info, customProperties.

    Debugging capability the app lacked. When a write appears to succeed and the
    UI disagrees, the only way to settle it is to read the entity back and look
    at what is actually stored; until now that meant leaving the app. Read-only.
    """
    url = clean_base(base_url) + f"/api/public/{version}/entities/{entity_id}?extended=true"
    out = _req("GET", url, token=token, verify_tls=verify_tls, timeout=timeout)
    d = out.get("data") if isinstance(out.get("data"), dict) else out
    return d if isinstance(d, dict) else {}


def resolve_terms(base_url, token, names, version="v3", verify_tls=True, timeout=20):
    """Look up each term name in PDC -> {name: {id, glossaryId}} for hits.

    Three paths, in order of reliability (do NOT facet /search by type=['term']
    — that facet means ASSET type and returns zero hits for terms):
      A) a /search result that IS the term (its own type contains 'term')
      B) any result whose businessTerms[] carries the name -> {termId, glossaryId}
      C) /entities/filter by name -> term-typed entity -> rootId
    """
    base = clean_base(base_url)
    surl = base + f"/api/public/{version}/search"
    eurl = base + f"/api/public/{version}/entities/"
    out_map = {}

    def _root_of(tid):
        try:
            ent = _req("GET", eurl + str(tid), token=token, verify_tls=verify_tls, timeout=timeout)
            e = ent.get("data", ent)
            if isinstance(e, list):
                e = e[0] if e else {}
            return _glossary_id(e)
        except Exception:
            return None

    for name in sorted(set(n for n in names if n)):
        try:
            res = _req("POST", surl, token=token,
                       body={"searchTerm": name, "perPage": 50},
                       verify_tls=verify_tls, timeout=timeout)
            hits = _results(res)
        except TokenExpired:
            raise
        except Exception:
            hits = []

        tid = gid = None
        for it in hits:  # path A
            if str(it.get("name", "")).strip().lower() != name.strip().lower():
                continue
            if "term" not in str(it.get("type") or it.get("originalType") or "").lower():
                continue
            tid = _eid(it)
            gid = _glossary_id(it)
            if tid and not gid:
                gid = _root_of(tid)
            if tid:
                break
        if not tid or not gid:  # path B
            for it in hits:
                b_tid, b_gid = _bt_match(it, name)
                if b_tid:
                    tid = tid or b_tid
                    gid = gid or b_gid
                    if tid and gid:
                        break
        if not (tid and gid):  # path C
            try:
                ents = filter_entities(base_url, token, {"names": [name]},
                                       version, verify_tls, timeout)
            except TokenExpired:
                raise
            except Exception:
                ents = []
            for e in ents:
                if str(e.get("name", "")).strip().lower() != name.strip().lower():
                    continue
                if "term" not in str(e.get("type") or "").lower():
                    continue
                tid = tid or _eid(e)
                gid = gid or _glossary_id(e)
                if tid and not gid:
                    gid = _root_of(tid)
                if tid:
                    break

        if tid:
            out_map[name] = {"id": tid, "glossaryId": gid}
    return out_map

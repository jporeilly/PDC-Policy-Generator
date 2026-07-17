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


def list_methods(base_url, token, prefix=None, verify_tls=True, timeout=30):
    """List Data Identification methods (dictionaries + patterns). When
       `prefix` is given, only methods whose name starts with it are returned —
       the guard that keeps a retire scoped to the app's own authored set.
       Each row: {kind, _id, name, builtIn}."""
    data = graphql(
        base_url, token,
        "{ DictionariesMany { _id name builtIn } DataPatternsMany { _id name builtIn } }",
        verify_tls=verify_tls, timeout=timeout)
    rows = []
    for kind, fld in (("Dictionary", "DictionariesMany"), ("DataPattern", "DataPatternsMany")):
        for m in (data.get(fld) or []):
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
    md = ((w.get("pipeline") or {}).get("metadata") or {})
    return {"status": md.get("status"), "label": (w.get("pipeline") or {}).get("label"),
            "workerName": w.get("workerName")}


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

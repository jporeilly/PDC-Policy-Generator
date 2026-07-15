"""
pdc.py — lean PDC Public API client for the reconcile stage.

A verbatim subset of the Glossary Generator's battle-tested pdc_api.py
(auth incl. the Keycloak-first path, and resolve_terms with its three
fallback lookups — including the fix for the /search type-facet bug that
once made Resolve match 0 terms). Stdlib only: no new dependencies.
"""
from __future__ import annotations
import json
import re
import ssl
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
    "Dictionary": {"many": "DictionariesMany", "remove": "DictionariesRemoveById"},
    "DataPattern": {"many": "DataPatternsMany", "remove": "DataPatternsRemoveById"},
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

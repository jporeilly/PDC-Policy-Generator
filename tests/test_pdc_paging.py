"""Paged method listing (1.10.2).

PDC's *Many resolvers cap a limitless query at 100 rows and say nothing about
it. Everything that decides what is or is not deployed reads through
list_methods — deploy's verification, drift, and the scoped retire — so a
catalog with 95 built-in dictionaries made a 27-method import look like 5, and
a partial deploy was indistinguishable from a total one.

These tests stand in a fake PDC that behaves the way the real one did.
"""
import pytest

from policy_generator import pdc


def _fake_server(monkeypatch, dictionaries, patterns, cap=100,
                 honour_skip=True, supports_paging=True):
    """A GraphQL stub with PDC's observed manners. Returns the call log."""
    calls = []

    def fake_graphql(base_url, token, query, variables=None, verify_tls=True, timeout=30):
        calls.append({"query": query, "variables": variables})
        if variables and not supports_paging:
            raise RuntimeError('GraphQL error: Unknown argument "limit"')
        field = "DictionariesMany" if "DictionariesMany" in query else "DataPatternsMany"
        rows = dictionaries if field == "DictionariesMany" else patterns
        limit = (variables or {}).get("limit") or cap
        skip = 0 if not honour_skip else ((variables or {}).get("skip") or 0)
        return {field: rows[skip:skip + min(limit, cap)]}

    monkeypatch.setattr(pdc, "graphql", fake_graphql)
    return calls


def _rows(prefix, n, built_in=False, start=0):
    return [{"_id": f"{prefix}-{i}", "name": f"{prefix} {i}", "builtIn": built_in}
            for i in range(start, start + n)]


class TestPagingSeesEverything:
    def test_reads_past_the_hundred_row_ceiling(self, monkeypatch):
        # the shape of the real catalog on deploy day: 95 built-ins already
        # there, 27 freshly imported — 122 dictionaries, of which one unpaged
        # read could only ever show 100
        dicts = _rows("Builtin", 95, built_in=True) + _rows("Arizona", 27)
        _fake_server(monkeypatch, dicts, _rows("Pattern", 42, built_in=True))
        rows = pdc.list_methods("https://pdc", "tok")
        assert len(rows) == 122 + 42

    def test_the_prefix_filter_runs_over_the_whole_catalog(self, monkeypatch):
        dicts = _rows("Builtin", 95, built_in=True) + _rows("Arizona", 27)
        _fake_server(monkeypatch, dicts, _rows("Arizona Pattern", 88))
        rows = pdc.list_methods("https://pdc", "tok", prefix="Arizona")
        assert len(rows) == 27 + 88, "a filter applied to a capped page under-reports"
        assert {r["kind"] for r in rows} == {"Dictionary", "DataPattern"}

    def test_a_short_page_is_not_the_end(self, monkeypatch):
        """We ask for 200 and the server serves 100. Stopping on a short page
        would lose everything after the first hundred."""
        calls = _fake_server(monkeypatch, _rows("D", 250), [], cap=100)
        rows = pdc.list_methods("https://pdc", "tok")
        assert len(rows) == 250
        dict_calls = [c for c in calls if "DictionariesMany" in c["query"]]
        # 100, 100, 50, then an empty page — skip advances by what ARRIVED,
        # not by what was asked for, or the tail row gets skipped
        assert [c["variables"]["skip"] for c in dict_calls] == [0, 100, 200, 250]

    def test_an_empty_page_ends_it(self, monkeypatch):
        calls = _fake_server(monkeypatch, _rows("D", 200), [], cap=100)
        pdc.list_methods("https://pdc", "tok")
        assert len([c for c in calls if "DictionariesMany" in c["query"]]) == 3


class TestHostileServers:
    def test_a_server_that_ignores_skip_does_not_loop_forever(self, monkeypatch):
        _fake_server(monkeypatch, _rows("D", 250), [], cap=100, honour_skip=False)
        rows = pdc.list_methods("https://pdc", "tok")
        assert len(rows) == 100, "same page re-served — take it once and stop"

    def test_falls_back_when_the_schema_has_no_paging(self, monkeypatch):
        _fake_server(monkeypatch, _rows("D", 30), _rows("P", 10), supports_paging=False)
        rows = pdc.list_methods("https://pdc", "tok")
        assert len(rows) == 40, "an older PDC must still list, capped as it is"

    def test_an_unrelated_graphql_error_still_raises(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("GraphQL error: Cannot query field 'builtIn'")
        monkeypatch.setattr(pdc, "graphql", boom)
        with pytest.raises(RuntimeError):
            pdc.list_methods("https://pdc", "tok")

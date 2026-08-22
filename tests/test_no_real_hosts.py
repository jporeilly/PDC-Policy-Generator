"""No real estate hosts or lab credentials in anything that ships.

Ported from the Glossary Generator's test_fresh_install.py, whose 1.38.35
release train FAILED on this exact guard — pentaho.io had been compiled into
a placeholder. Policy never carried the guard, and its Connect card shipped
`https://192.168.1.200` as the Base URL placeholder until 2026-08-22, when the
user read the lab's IP off a screenshot of their own demo app.

A placeholder teaches the field's SHAPE. A real host teaches the audience
where your lab lives.
"""
import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANNED = [
    r"192\.168\.\d+\.\d+",
    r"pentaho\.io",
    r"\bpdc_user\b",
    r"\bcatalog123\b",
    r"minio_secret",
    r"\bazwater\b",
]


def _shipped_sources():
    for pattern in ("policy_generator/**/*.py", "frontend/src/**/*.jsx",
                    "frontend/src/**/*.js"):
        for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
            if ".venv" not in path and "node_modules" not in path:
                yield path


def _bundle():
    return glob.glob(os.path.join(ROOT, "frontend", "dist", "assets", "*.js"))


@pytest.mark.parametrize("pattern", BANNED)
def test_no_real_hosts_or_credentials_in_shipped_code(pattern):
    rx = re.compile(pattern, re.I)
    hits = []
    for path in _shipped_sources():
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if line.lstrip().startswith(("#", "//", "*")):
                    continue           # comments explain history; they ship nothing
                if rx.search(line):
                    hits.append(f"{os.path.relpath(path, ROOT)}:{n}")
    assert not hits, f"{pattern!r} appears in shipped code at {hits}"


@pytest.mark.parametrize("pattern", BANNED)
def test_no_real_hosts_in_the_built_ui(pattern):
    """The bundle is what actually reaches a customer's screen — source can
    lie about it (a stale dist ships whatever it was built from)."""
    files = _bundle()
    if not files:
        pytest.skip("frontend not built")
    rx = re.compile(pattern, re.I)
    hits = [os.path.relpath(p, ROOT) for p in files
            if rx.search(open(p, encoding="utf-8", errors="replace").read())]
    assert not hits, f"{pattern!r} is compiled into the shipped UI: {hits}"

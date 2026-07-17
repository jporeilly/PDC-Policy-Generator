"""Documentation consistency — version markers must never drift again
(this repo shipped with VERSION=1.6.0 while the README said 1.5.4)."""

import re
from pathlib import Path

from policy_generator import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_required_docs_exist():
    for doc in ("README.md", "VERSION.md", "CHANGELOG.md", "docs/INSTALL.md", "docs/CONTRACT.md"):
        assert (ROOT / doc).exists(), f"missing {doc}"


def test_version_markers_agree():
    assert (ROOT / "policy_generator" / "VERSION").read_text(encoding="utf-8").strip() == __version__

    version_md = (ROOT / "VERSION.md").read_text(encoding="utf-8")
    assert f"**{__version__}**" in version_md, "VERSION.md not bumped"

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    entries = re.findall(r"^## \[?v?([0-9][^\]\s]*)\]?", changelog, re.MULTILINE)
    released = [e for e in entries if e.lower() != "unreleased"]
    assert released and released[0] == __version__, (
        f"newest CHANGELOG release is {released[0] if released else 'none'}, "
        f"code says {__version__}"
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stamped = re.search(r"\*\*Version:\*\* ([0-9][^\s]*)", readme)
    assert stamped and stamped.group(1) == __version__, (
        f"README says {stamped.group(1) if stamped else 'nothing'}, code says {__version__}"
    )
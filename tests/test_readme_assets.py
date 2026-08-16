"""Every docs/assets/ path the README references must exist (SPEC-07:
a README screenshot that 404s on the public repo is a silent break)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_asset_references_exist() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    refs = sorted(set(re.findall(r"docs/assets/[A-Za-z0-9._-]+", readme)))
    assert refs, "README references no assets — the evidence sections are gone?"
    missing = [ref for ref in refs if not (REPO_ROOT / ref).is_file()]
    assert not missing, f"README references missing assets: {missing}"

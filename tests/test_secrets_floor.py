"""Pin-pair guard for the secrets floor (phase-7 review ruling 3).

The gitleaks version is pinned twice — GITLEAKS_PIN in
scripts/secrets_audit.sh and the release URL in ci.yml's secrets job —
and drift between them means either spurious local pre-push failures
(the --no-verify pressure) or two layers scanning with different
allowlist-parsing semantics while both report green.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gitleaks_pin_cannot_drift_between_floor_and_ci() -> None:
    floor = (REPO_ROOT / "scripts" / "secrets_audit.sh").read_text()
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    pin = re.search(r'^GITLEAKS_PIN="([0-9.]+)"$', floor, re.MULTILINE)
    assert pin, "GITLEAKS_PIN not found in scripts/secrets_audit.sh"
    version = pin.group(1)

    # the exact pinned version must appear in CI's download URL and
    # archive name (one string in ci.yml carries both)
    assert (
        f"gitleaks/releases/download/v{version}/gitleaks_{version}_linux_x64.tar.gz"
        in ci
    ), f"ci.yml does not download gitleaks {version} (floor pin)"

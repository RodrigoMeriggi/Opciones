#!/usr/bin/env python3
"""Escribe manifiesto de versión semántica + commit."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    sha = sys.argv[1] if len(sys.argv) > 1 else "local"
    try:
        author = subprocess.check_output(["git", "log", "-1", "--pretty=%an"], text=True).strip()
        msg = subprocess.check_output(["git", "log", "-1", "--pretty=%s"], text=True).strip()
    except Exception:  # noqa: BLE001
        author, msg = "unknown", "n/a"
    manifest = {
        "app_version": "0.4.0",
        "commit": sha,
        "date": datetime.utcnow().isoformat() + "Z",
        "author": author,
        "changes": msg,
        "migrations": "alembic (see alembic/versions)",
        "strategies_touched": [],
        "parameters_touched": [],
        "known_risks": [
            "Live trading disabled by default",
            "No official ALyC docs in repo",
            "Paper results are not profitability guarantees",
        ],
    }
    out = ROOT / "reports" / "artifacts" / "version_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()

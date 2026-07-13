#!/usr/bin/env python3
"""Escaneo heurístico de secretos — falla CI si encuentra patrones obvios."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {".venv", "node_modules", ".git", "reports", "__pycache__", ".next"}
PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)password\s*=\s*['\"][^'\"]{8,}['\"]"),
]


def main() -> int:
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(p in path.parts for p in SKIP):
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".yml", ".yaml", ".env", ".json", ".md", ".toml"}:
            continue
        # permitir .env.example
        if path.name.endswith(".example"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in PATTERNS:
            if pat.search(text):
                # excepciones conocidas de demos
                if "admin-change-me" in text or "trader-change-me" in text:
                    continue
                if "dev-only-change-me" in text:
                    continue
                hits.append(f"{path}:{pat.pattern}")
    if hits:
        print("Possible secrets detected:")
        for h in hits[:50]:
            print(" -", h)
        return 1
    print("Secret scan OK (heuristic)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

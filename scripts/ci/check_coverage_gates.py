#!/usr/bin/env python3
"""Quality gates de cobertura por módulo (umbrales mínimos)."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COVERAGE_XML = ROOT / "reports" / "coverage" / "unit.xml"

GATES = {
    "opciones/modules/risk_manager": float(os.environ.get("COVERAGE_MIN_RISK", "40")),
    "opciones/modules/pricing_engine": float(os.environ.get("COVERAGE_MIN_PRICING", "40")),
    "opciones/domain": float(os.environ.get("COVERAGE_MIN_DOMAIN", "30")),
    "opciones/api": float(os.environ.get("COVERAGE_MIN_API", "20")),
}


def package_rates(xml_path: Path) -> dict[str, float]:
    if not xml_path.exists():
        print(f"coverage xml missing: {xml_path} (skip soft in local)")
        return {}
    tree = ET.parse(xml_path)
    rates: dict[str, list[float]] = {}
    for cls in tree.findall(".//class"):
        filename = cls.attrib.get("filename", "")
        line_rate = float(cls.attrib.get("line-rate", 0)) * 100
        for pkg, _ in GATES.items():
            if pkg.replace(".", "/") in filename or pkg in filename:
                rates.setdefault(pkg, []).append(line_rate)
    return {k: (sum(v) / len(v) if v else 0.0) for k, v in rates.items()}


def main() -> int:
    rates = package_rates(COVERAGE_XML)
    if not rates:
        print("No coverage data; gate soft-pass")
        return 0
    failed = []
    for pkg, minimum in GATES.items():
        got = rates.get(pkg, 0.0)
        print(f"{pkg}: {got:.1f}% (min {minimum}%)")
        if got < minimum:
            failed.append(pkg)
    # total
    if COVERAGE_XML.exists():
        root = ET.parse(COVERAGE_XML).getroot()
        total = float(root.attrib.get("line-rate", 0)) * 100
        vmin = float(os.environ.get("COVERAGE_MIN_TOTAL", "35"))
        print(f"TOTAL: {total:.1f}% (min {vmin}%)")
        if total < vmin:
            failed.append("TOTAL")
    if failed:
        print("Coverage gate FAILED:", failed)
        return 1
    print("Coverage gates OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

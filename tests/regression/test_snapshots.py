"""Regresión por snapshots deterministas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opciones.modules.pricing_engine import bsm_price
from opciones.modules.contract_selection import ContractSelector
from tests.fixtures.market import DATA_VERSION, liquid_call_chain, fixture_manifest

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _load_or_update(name: str, payload: dict, *, update: bool = False) -> dict:
    path = SNAPSHOT_DIR / name
    if update or not path.exists():
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return payload
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.regression
def test_bsm_regression_snapshot():
    price = bsm_price(100, 100, 1.0, 0.05, 0.0, 0.2, "CALL")
    payload = {
        "data_version": DATA_VERSION,
        "price": round(price, 6),
        "inputs": {"S": 100, "K": 100, "T": 1, "r": 0.05, "q": 0, "sigma": 0.2},
    }
    expected = _load_or_update("bsm_atm_call.json", payload)
    assert payload["price"] == expected["price"]
    assert payload["data_version"] == expected["data_version"]


@pytest.mark.regression
def test_selector_score_regression():
    chain = liquid_call_chain()
    sel = ContractSelector(
        {
            "min_volume": 1,
            "max_spread_pct": 50,
            "avoid_deep_otm": False,
            "max_quote_age_seconds": 86400,
        }
    )
    result = sel.select(chain, "BULLISH")
    assert result.winner is not None
    payload = {
        "data_version": DATA_VERSION,
        "winner": result.winner.contract.symbol,
        "score": round(result.winner.total_score, 2),
        "components": {c.name: round(c.raw_score, 2) for c in result.winner.components},
    }
    expected = _load_or_update("selector_ggal_call.json", payload)
    if payload != expected:
        pytest.fail(
            "snapshot de regresión cambió sin aceptación explícita.\n"
            f"esperado={expected}\nactual={payload}\n"
            "Actualizar snapshots solo con revisión."
        )


@pytest.mark.regression
def test_fixture_manifest_stable():
    m = fixture_manifest()
    expected = _load_or_update("fixture_manifest.json", m)
    assert m["data_version"] == expected["data_version"]
    assert m["offline"] is True

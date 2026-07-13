"""Observabilidad."""

from opciones.modules.observability.alerts.engine import ALERTS, AlertSeverity
from opciones.modules.observability.health.service import HEALTH
from opciones.modules.observability.logging.structured import StructuredLogger, sanitize
from opciones.modules.observability.metrics.registry import TECH_METRICS
from opciones.modules.observability.tracing.trace import TRACER, get_correlation_id


def test_structured_log_redacts_secrets():
    clean = sanitize({"password": "x", "order_id": "1", "nested": {"api_key": "y"}})
    assert clean["password"] == "***REDACTED***"
    assert clean["nested"]["api_key"] == "***REDACTED***"
    log = StructuredLogger()
    payload = log.log("INFO", "signal discarded", correlation_id="c1", strategy_id="s")
    assert payload["severity"] == "INFO"


def test_health_distinguishes_alive_vs_trading():
    HEALTH.trading_enabled = False
    t = HEALTH.trading()
    assert t["alive"] is True
    assert t["apt_for_trading"] is False
    assert HEALTH.live()["status"] == "alive"


def test_frozen_market_alert_blocks_entries():
    ALERTS.block_entries = False
    ALERTS.alerts.clear()
    alert = ALERTS.evaluate_market_age(999, threshold=10)
    assert alert is not None
    assert alert.severity == AlertSeverity.CRITICAL
    assert ALERTS.block_entries is True


def test_metrics_and_trace():
    TECH_METRICS.inc("api_errors")
    TECH_METRICS.observe("latency_ms", 12.5)
    snap = TECH_METRICS.snapshot()
    assert "api_errors" in snap["counters"]
    cid = get_correlation_id()
    trace, span = TRACER.start("evaluate", correlation_id=cid)
    span.end(ok=True)
    assert trace.root.ended_at is not None

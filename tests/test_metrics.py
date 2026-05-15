"""
Tests para metrics.py — módulo de observabilidad Prometheus.

Cubre:
  - set_service_label: inyecta label service/version
  - timer: context manager que mide latencia y reporta en un Histogram
  - render_metrics: produce exposition format de Prometheus
  - auth_check: bearer token opcional para el endpoint /metrics
  - _safe_compare: comparación constante de strings

Estos tests usan el REGISTRY global del módulo (es un CollectorRegistry propio
de FerreBot, no el default de prometheus_client), así que no hay colisión con
otros módulos que ya lo hayan importado en la misma sesión de pytest.
"""

# -- stdlib --
import re

# -- terceros --
import pytest

# -- propios --
import metrics as _metrics


# ─────────────────────────────────────────────
# set_service_label
# ─────────────────────────────────────────────


def test_set_service_label_api():
    """set_service_label debe registrar el servicio como 'api' con version."""
    _metrics.set_service_label("api", version="test-1.0")
    body, _ct = _metrics.render_metrics()
    text = body.decode()
    assert 'ferrebot_service_info{service="api",version="test-1.0"} 1.0' in text


def test_set_service_label_bot():
    """set_service_label debe poder usarse también con 'bot'."""
    _metrics.set_service_label("bot", version="test-2.0")
    body, _ct = _metrics.render_metrics()
    text = body.decode()
    assert 'service="bot"' in text
    assert 'version="test-2.0"' in text


# ─────────────────────────────────────────────
# timer
# ─────────────────────────────────────────────


def test_timer_observes_latency_in_labeled_histogram():
    """timer debe observar la duración del bloque con labels."""
    before_body, _ = _metrics.render_metrics()
    before = before_body.decode()
    m_before = re.search(
        r'ferrebot_claude_latency_seconds_count\{model="claude-haiku-test"\} (\S+)',
        before,
    )
    count_before = float(m_before.group(1)) if m_before else 0.0

    with _metrics.timer(_metrics.claude_latency_seconds, model="claude-haiku-test"):
        pass

    after_body, _ = _metrics.render_metrics()
    after = after_body.decode()
    m_after = re.search(
        r'ferrebot_claude_latency_seconds_count\{model="claude-haiku-test"\} (\S+)',
        after,
    )
    assert m_after is not None
    count_after = float(m_after.group(1))
    assert count_after == count_before + 1


def test_timer_observes_latency_in_unlabeled_histogram():
    """timer sin labels debe observar sobre el Histogram directamente."""
    before_body, _ = _metrics.render_metrics()
    m_before = re.search(
        r"ferrebot_bypass_latency_seconds_count (\S+)",
        before_body.decode(),
    )
    count_before = float(m_before.group(1)) if m_before else 0.0

    with _metrics.timer(_metrics.bypass_latency_seconds):
        pass

    after_body, _ = _metrics.render_metrics()
    m_after = re.search(
        r"ferrebot_bypass_latency_seconds_count (\S+)",
        after_body.decode(),
    )
    assert m_after is not None
    assert float(m_after.group(1)) == count_before + 1


def test_timer_still_observes_on_exception():
    """timer debe observar la latencia aun si el bloque lanza excepción."""
    before_body, _ = _metrics.render_metrics()
    m_before = re.search(
        r'ferrebot_claude_latency_seconds_count\{model="test-raise"\} (\S+)',
        before_body.decode(),
    )
    count_before = float(m_before.group(1)) if m_before else 0.0

    with pytest.raises(RuntimeError):
        with _metrics.timer(_metrics.claude_latency_seconds, model="test-raise"):
            raise RuntimeError("bang")

    after_body, _ = _metrics.render_metrics()
    m_after = re.search(
        r'ferrebot_claude_latency_seconds_count\{model="test-raise"\} (\S+)',
        after_body.decode(),
    )
    assert m_after is not None
    assert float(m_after.group(1)) == count_before + 1


# ─────────────────────────────────────────────
# render_metrics
# ─────────────────────────────────────────────


def test_render_metrics_returns_prometheus_text():
    """render_metrics debe devolver content_type y bytes parseables como texto."""
    body, content_type = _metrics.render_metrics()
    assert isinstance(body, bytes)
    assert "text/plain" in content_type
    text = body.decode()
    assert "# HELP" in text
    assert "ferrebot_" in text


def test_render_metrics_includes_defined_counters():
    """El exposition debe incluir los Counters que definimos."""
    body, _ = _metrics.render_metrics()
    text = body.decode()
    assert "ferrebot_bypass_hits_total" in text
    assert "ferrebot_claude_calls_total" in text
    assert "ferrebot_compresor_runs_total" in text
    assert "ferrebot_sse_events_broadcast_total" in text


# ─────────────────────────────────────────────
# auth_check
# ─────────────────────────────────────────────


def test_auth_check_public_when_no_token_configured(monkeypatch):
    """Sin METRICS_BEARER_TOKEN, auth_check debe devolver True siempre."""
    monkeypatch.delenv("METRICS_BEARER_TOKEN", raising=False)
    assert _metrics.auth_check(None) is True
    assert _metrics.auth_check("") is True
    assert _metrics.auth_check("Bearer cualquiercosa") is True


def test_auth_check_rejects_missing_header_when_token_configured(monkeypatch):
    """Con token configurado, header faltante → False."""
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "s3cr3t")
    assert _metrics.auth_check(None) is False
    assert _metrics.auth_check("") is False


def test_auth_check_accepts_valid_bearer(monkeypatch):
    """Con token configurado, Authorization: Bearer <token> correcto → True."""
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "s3cr3t")
    assert _metrics.auth_check("Bearer s3cr3t") is True


def test_auth_check_rejects_wrong_bearer(monkeypatch):
    """Con token configurado, bearer con token distinto → False."""
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "s3cr3t")
    assert _metrics.auth_check("Bearer otro-token") is False
    assert _metrics.auth_check("Basic s3cr3t") is False
    assert _metrics.auth_check("s3cr3t") is False


def test_auth_check_trims_whitespace(monkeypatch):
    """El header debe compararse después de strip()."""
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "abc")
    assert _metrics.auth_check("  Bearer abc  ") is True


# ─────────────────────────────────────────────
# _safe_compare (tiempo constante)
# ─────────────────────────────────────────────


def test_safe_compare_equal_strings():
    assert _metrics._safe_compare("abc", "abc") is True


def test_safe_compare_different_strings_same_length():
    assert _metrics._safe_compare("abcd", "abce") is False


def test_safe_compare_different_lengths():
    assert _metrics._safe_compare("abc", "abcd") is False
    assert _metrics._safe_compare("", "x") is False


def test_safe_compare_empty_strings():
    assert _metrics._safe_compare("", "") is True


# ─────────────────────────────────────────────
# Counter increments (smoke tests)
# ─────────────────────────────────────────────


def test_bypass_hits_counter_increments():
    """bypass_hits_total.inc() debe reflejarse en el exposition."""
    before_body, _ = _metrics.render_metrics()
    m_before = re.search(
        r"^ferrebot_bypass_hits_total (\S+)$",
        before_body.decode(),
        re.MULTILINE,
    )
    before = float(m_before.group(1)) if m_before else 0.0

    _metrics.bypass_hits_total.inc()

    after_body, _ = _metrics.render_metrics()
    m_after = re.search(
        r"^ferrebot_bypass_hits_total (\S+)$",
        after_body.decode(),
        re.MULTILINE,
    )
    assert m_after is not None
    assert float(m_after.group(1)) == before + 1


def test_compresor_runs_labeled_counter_increments():
    """compresor_runs_total con label outcome debe contar."""
    _metrics.compresor_runs_total.labels(outcome="ok").inc()
    _metrics.compresor_runs_total.labels(outcome="error").inc()
    body, _ = _metrics.render_metrics()
    text = body.decode()
    assert 'ferrebot_compresor_runs_total{outcome="ok"}' in text
    assert 'ferrebot_compresor_runs_total{outcome="error"}' in text


def test_sse_clients_gauge_inc_dec():
    """sse_clients_active debe soportar .inc() y .dec()."""
    _metrics.sse_clients_active.inc()
    _metrics.sse_clients_active.inc()
    _metrics.sse_clients_active.dec()
    body, _ = _metrics.render_metrics()
    m = re.search(
        r"^ferrebot_sse_clients_active (\S+)$",
        body.decode(),
        re.MULTILINE,
    )
    assert m is not None
    val = float(m.group(1))
    assert val >= 0

"""
metrics.py — Prometheus metrics para FerreBot.

Define counters, histograms y gauges que se pueden importar desde cualquier
módulo para instrumentar puntos críticos del sistema. El endpoint /metrics
(expuesto por api.py y por start-bot.py) genera el scrape text format que
Prometheus / Grafana Cloud consumen.

IMPORTANTE — aislamiento por proceso:
  - Bot y API corren como PROCESOS SEPARADOS en Railway (cada uno con su
    propio CollectorRegistry). Las métricas del bot y de la API no se
    agregan en memoria; Prometheus debe hacer el join via labels (ej:
    `service="bot"` vs `service="api"`) al momento de scrapear.
  - Para que cada proceso exponga una etiqueta 'service' consistente,
    llamar `set_service_label("bot")` o `set_service_label("api")` una
    sola vez al arranque.

DISEÑO:
  - Counter: eventos acumulativos monotónicos (ventas, errores, llamadas)
  - Histogram: latencias y tamaños (buckets sensatos para Claude + bypass)
  - Gauge: estado actual (suscriptores SSE, conexiones de pool)

AUTH del endpoint /metrics:
  - Por defecto el endpoint es PÚBLICO (Railway ya está detrás de HTTPS).
  - Para endurecer, settear METRICS_BEARER_TOKEN en env → el handler valida
    Authorization: Bearer <token> y devuelve 401 sin match.
"""

from __future__ import annotations

# -- stdlib --
import logging
import os
import time
from contextlib import contextmanager
from typing import Iterator

# -- terceros --
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

log = logging.getLogger("ferrebot.metrics")

# ─────────────────────────────────────────────
# REGISTRY + SERVICE LABEL
# ─────────────────────────────────────────────

# Registry propio en vez del default global — evita colisión si alguna
# dependencia (sentry, apscheduler) registra métricas del mismo nombre.
REGISTRY = CollectorRegistry()

# 'service' se inyecta como label constante en todas las métricas via los
# Counters/Histograms/Gauges cuando el servicio llame set_service_label().
# Implementación simple: una Gauge estática con el valor 1 y label service
# — Prometheus la usa para hacer join con otras métricas vía `on(instance)`.
_service_info = Gauge(
    "ferrebot_service_info",
    "Metadata del servicio FerreBot (bot | api)",
    labelnames=["service", "version"],
    registry=REGISTRY,
)


def set_service_label(service: str, version: str = "unknown") -> None:
    """Llamar una sola vez al arranque. Marca el proceso como 'bot' o 'api'."""
    _service_info.labels(service=service, version=version).set(1)
    log.info("metrics: service=%s version=%s", service, version)


# ─────────────────────────────────────────────
# VENTAS
# ─────────────────────────────────────────────

ventas_registradas_total = Counter(
    "ferrebot_ventas_registradas_total",
    "Total de ventas registradas (cada línea de venta cuenta como 1)",
    labelnames=["metodo_pago", "origen"],  # origen: bypass | claude
    registry=REGISTRY,
)

ventas_anuladas_total = Counter(
    "ferrebot_ventas_anuladas_total",
    "Total de ventas anuladas por el vendedor",
    registry=REGISTRY,
)

# ─────────────────────────────────────────────
# BYPASS vs CLAUDE — el ratio 60/40 es un KPI de costo
# ─────────────────────────────────────────────

bypass_hits_total = Counter(
    "ferrebot_bypass_hits_total",
    "Mensajes resueltos en Python sin llamar a Claude",
    registry=REGISTRY,
)

bypass_latency_seconds = Histogram(
    "ferrebot_bypass_latency_seconds",
    "Latencia del bypass Python (objetivo <5ms)",
    buckets=(0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
    registry=REGISTRY,
)

claude_calls_total = Counter(
    "ferrebot_claude_calls_total",
    "Llamadas a Claude API",
    labelnames=["model", "outcome"],  # outcome: ok | error | timeout | budget_exceeded
    registry=REGISTRY,
)

claude_latency_seconds = Histogram(
    "ferrebot_claude_latency_seconds",
    "Latencia de respuestas de Claude API (end-to-end)",
    labelnames=["model"],
    buckets=(0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 120.0),
    registry=REGISTRY,
)

claude_tokens_total = Counter(
    "ferrebot_claude_tokens_total",
    "Tokens consumidos por Claude API",
    labelnames=["model", "kind"],  # kind: input | output | cache_read | cache_created
    registry=REGISTRY,
)

claude_cost_usd_total = Counter(
    "ferrebot_claude_cost_usd_total",
    "Costo acumulado en USD de llamadas a Claude (según budget.py)",
    labelnames=["model"],
    registry=REGISTRY,
)

# ─────────────────────────────────────────────
# COMPRESOR NOCTURNO (Paso 6)
# ─────────────────────────────────────────────

compresor_runs_total = Counter(
    "ferrebot_compresor_runs_total",
    "Ejecuciones del compresor nocturno",
    labelnames=["outcome"],  # ok | error | sin_datos
    registry=REGISTRY,
)

compresor_notas_guardadas_total = Counter(
    "ferrebot_compresor_notas_guardadas_total",
    "Notas de memoria de entidad guardadas por el compresor",
    labelnames=["tipo"],  # producto | alias | vendedor
    registry=REGISTRY,
)

compresor_notas_purgadas_total = Counter(
    "ferrebot_compresor_notas_purgadas_total",
    "Notas viejas purgadas por el compresor (>90 días)",
    registry=REGISTRY,
)

compresor_last_run_timestamp = Gauge(
    "ferrebot_compresor_last_run_timestamp",
    "Unix timestamp del último run del compresor nocturno",
    registry=REGISTRY,
)

# ─────────────────────────────────────────────
# SSE / realtime
# ─────────────────────────────────────────────

sse_clients_active = Gauge(
    "ferrebot_sse_clients_active",
    "Número de clientes suscritos al stream SSE /events",
    registry=REGISTRY,
)

sse_events_broadcast_total = Counter(
    "ferrebot_sse_events_broadcast_total",
    "Eventos SSE emitidos al dashboard",
    labelnames=["event_type"],
    registry=REGISTRY,
)

# ─────────────────────────────────────────────
# DB POOL (psycopg2 ThreadedConnectionPool, maxconn=10)
# ─────────────────────────────────────────────

db_pool_connections_used = Gauge(
    "ferrebot_db_pool_connections_used",
    "Conexiones PostgreSQL actualmente en uso (de maxconn=10)",
    registry=REGISTRY,
)

db_query_errors_total = Counter(
    "ferrebot_db_query_errors_total",
    "Errores de queries a PostgreSQL",
    labelnames=["op"],  # op: query_one | query_all | execute
    registry=REGISTRY,
)

# ─────────────────────────────────────────────
# BOT — mensajes Telegram
# ─────────────────────────────────────────────

bot_mensajes_recibidos_total = Counter(
    "ferrebot_bot_mensajes_recibidos_total",
    "Mensajes recibidos por el bot de Telegram",
    labelnames=["tipo"],  # tipo: texto | audio | foto | documento
    registry=REGISTRY,
)

bot_errores_total = Counter(
    "ferrebot_bot_errores_total",
    "Errores no capturados en handlers del bot",
    labelnames=["handler"],
    registry=REGISTRY,
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────


@contextmanager
def timer(histogram: Histogram, **labels: str) -> Iterator[None]:
    """
    Context manager para medir latencia en segundos y reportarla en un Histogram.

    Uso:
        with timer(claude_latency_seconds, model="sonnet"):
            respuesta = await claude.messages.create(...)
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        if labels:
            histogram.labels(**labels).observe(elapsed)
        else:
            histogram.observe(elapsed)


def render_metrics() -> tuple[bytes, str]:
    """
    Genera el exposition format de Prometheus en bytes.

    Retorna (body, content_type) — para pasar directo a FastAPI Response.
    Si generate_latest falla, retorna un cuerpo vacío y loguea (fail-silent:
    el endpoint /metrics no debe jamás tumbar la app).
    """
    try:
        body = generate_latest(REGISTRY)
        return body, CONTENT_TYPE_LATEST
    except Exception as e:  # noqa: BLE001 — fail-silent intencional
        log.warning("render_metrics falló: %s", e)
        return b"", CONTENT_TYPE_LATEST


def auth_check(authorization_header: str | None) -> bool:
    """
    Valida el Authorization header si METRICS_BEARER_TOKEN está configurado.

    Retorna:
        True  — no hay token configurado (acceso público) O token válido.
        False — token configurado pero header faltante/incorrecto.
    """
    expected = os.getenv("METRICS_BEARER_TOKEN", "").strip()
    if not expected:
        return True  # público
    if not authorization_header:
        return False
    expected_header = f"Bearer {expected}"
    # Comparación constante para no leakear info por timing
    return _safe_compare(authorization_header.strip(), expected_header)


def _safe_compare(a: str, b: str) -> bool:
    """Comparación en tiempo constante de strings."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode(), b.encode()):
        result |= x ^ y
    return result == 0

"""
tests/test_voz_telemetria.py — Telemetría por turno de voz (P0.1).

Cubre ai/voz_telemetria.py:

  * Sink contextvars: no-op fuera de turno, captura de modelo/riel dentro,
    normalización del modelo (haiku/sonnet) y default de riel ("ninguno").
  * registrar_turno_voz: arma el INSERT correcto en audio_logs (texto_original
    y texto_corregido = texto, chat_id/turn_id poblados) y es fail-open si la DB
    falla.

Se mockean config (COLOMBIA_TZ) y db (execute_async) para no tocar red ni disco,
y se carga el módulo de forma aislada para no disparar el ai/__init__.py pesado.
"""
import sys
import os
import types
import asyncio
import importlib.util
from datetime import timezone, timedelta

# Permitir importar desde el root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─────────────────────────────────────────────────────────────────────────
# STUBS de dependencias (config, db) ANTES de cargar el módulo bajo prueba
# ─────────────────────────────────────────────────────────────────────────

_COL_TZ = timezone(timedelta(hours=-5))  # UTC-5, equivalente a COLOMBIA_TZ

if "config" not in sys.modules:
    sys.modules["config"] = types.ModuleType("config")
_cfg = sys.modules["config"]
if getattr(_cfg, "COLOMBIA_TZ", None) is None:
    _cfg.COLOMBIA_TZ = _COL_TZ

# Estado de captura del fake db
_db_calls: list = []
_db_should_raise = {"on": False}


async def _fake_execute_async(sql, params=None):
    if _db_should_raise["on"]:
        raise RuntimeError("db caída (simulada)")
    _db_calls.append((sql, params))
    return 1


if "db" not in sys.modules:
    sys.modules["db"] = types.ModuleType("db")
sys.modules["db"].execute_async = _fake_execute_async


# Cargar ai/voz_telemetria.py de forma aislada (sin ejecutar ai/__init__.py).
_vt_path = os.path.join(_ROOT, "ai", "voz_telemetria.py")
_spec = importlib.util.spec_from_file_location("voz_telemetria_under_test", _vt_path)
vt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vt)


# ─────────────────────────────────────────────────────────────────────────
# SINK contextvars
# ─────────────────────────────────────────────────────────────────────────

def test_sink_noop_fuera_de_contexto():
    """Sin turno activo, set_* no hace nada y capturar() da los defaults."""
    vt.reset()
    vt.set_modelo("claude-haiku-4-5")
    vt.set_riel("R2")
    assert vt.capturar() == {"modelo": None, "riel": "ninguno"}


def test_sink_captura_y_normaliza_modelo():
    """Dentro de un turno se capturan modelo (normalizado) y riel."""
    vt.iniciar()
    try:
        vt.set_modelo("claude-haiku-4-5-20251001")
        assert vt.capturar()["modelo"] == "haiku"

        vt.set_modelo("claude-sonnet-4-6")
        assert vt.capturar()["modelo"] == "sonnet"

        vt.set_riel("R2-precio")
        assert vt.capturar()["riel"] == "R2-precio"
    finally:
        vt.reset()


def test_sink_riel_default_ninguno():
    """Un turno sin riel queda en 'ninguno' y modelo en None."""
    vt.iniciar()
    try:
        tel = vt.capturar()
        assert tel["riel"] == "ninguno"
        assert tel["modelo"] is None
    finally:
        vt.reset()


def test_sink_modelo_id_desconocido_se_conserva():
    """Un ID que no es haiku/sonnet se conserva tal cual; '' → None."""
    vt.iniciar()
    try:
        vt.set_modelo("claude-opus-4-8")
        assert vt.capturar()["modelo"] == "claude-opus-4-8"
        vt.set_modelo("")
        assert vt.capturar()["modelo"] is None
    finally:
        vt.reset()


# ─────────────────────────────────────────────────────────────────────────
# PERSISTENCIA — registrar_turno_voz
# ─────────────────────────────────────────────────────────────────────────

def test_registrar_inserta_fila_con_campos_correctos():
    """El INSERT lleva los campos clave; texto_original == texto_corregido."""
    _db_calls.clear()
    asyncio.run(vt.registrar_turno_voz(
        turn_id="t-123", canal="voz", chat_id=42, vendedor="Andres",
        texto="dos bultos de cemento", session_id="s-1",
        duracion_seg=3.4, no_speech_prob=0.12, descartado_silencio=False,
        modelo="haiku", riel="ninguno", latencia_stt_ms=900,
        latencia_claude_ms=700, pendiente=True, resultado="pendiente_pago",
    ))

    assert len(_db_calls) == 1
    sql, params = _db_calls[0]
    assert "INSERT INTO audio_logs" in sql

    # Orden de columnas del INSERT:
    #   0 chat_id, 1 vendedor, 2 texto_original, 3 texto_corregido,
    #   4 duracion_seg, 5 fecha, 6 canal, 7 turn_id, 8 session_id,
    #   ... 16 resultado
    assert params[0] == 42                       # chat_id (NOT NULL poblado)
    assert params[1] == "Andres"                 # vendedor (NOT NULL)
    assert params[2] == "dos bultos de cemento"  # texto_original (NOT NULL)
    assert params[3] == "dos bultos de cemento"  # texto_corregido (NOT NULL) == texto
    assert params[6] == "voz"                    # canal
    assert params[7] == "t-123"                  # turn_id (correlación)
    assert params[8] == "s-1"                    # session_id
    assert params[-1] == "pendiente_pago"        # resultado


def test_registrar_texto_vacio_no_viola_not_null():
    """Texto vacío se inserta como '' (no None) en texto_original/corregido."""
    _db_calls.clear()
    asyncio.run(vt.registrar_turno_voz(
        turn_id="t-sil", canal="voz", resultado="silencio",
        descartado_silencio=True,
    ))
    assert len(_db_calls) == 1
    _, params = _db_calls[0]
    assert params[2] == ""   # texto_original
    assert params[3] == ""   # texto_corregido


def test_registrar_es_fail_open():
    """Si la DB falla, registrar_turno_voz no propaga la excepción."""
    _db_should_raise["on"] = True
    try:
        # No debe lanzar.
        asyncio.run(vt.registrar_turno_voz(turn_id="t-x", resultado="error"))
    finally:
        _db_should_raise["on"] = False


# ─────────────────────────────────────────────────────────────────────────
# Runner directo (además de pytest)
# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    _fallos = 0
    for _t in _tests:
        try:
            _t()
            print(f"PASS {_t.__name__}")
        except Exception as _e:  # noqa: BLE001
            _fallos += 1
            print(f"FAIL {_t.__name__}: {_e}")
    print(f"\n{len(_tests) - _fallos}/{len(_tests)} OK")
    sys.exit(1 if _fallos else 0)

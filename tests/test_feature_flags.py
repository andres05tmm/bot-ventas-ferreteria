"""tests/test_feature_flags.py — Feature flags de config.py (Sprint 4, fase 3).

Verifica la semántica de _flag(): el valor explícito de la env var manda; si la
var no está, se autodetecta por la credencial del módulo. Garantiza que Punto
Rojo (con credenciales) queda con los módulos activos y una ferretería nueva
(sin credenciales) los tiene apagados.

Cada caso se ejecuta en un SUBPROCESO con su propio entorno: así se importa el
config real (igual que en producción) sin contaminar el sys.modules del runner
de pytest (config es stubbeado por otros tests).
"""
# -- stdlib --
import json
import os
import subprocess
import sys

# -- terceros --
import pytest

_CORE_ENV = {
    "TELEGRAM_TOKEN": "x",
    "ANTHROPIC_API_KEY": "x",
    "OPENAI_API_KEY": "x",
}

_OPCIONALES = [
    "MATIAS_EMAIL", "HONORARIOS_CHAT_ID", "BANCOLOMBIA_GMAIL_CLIENT_ID",
    "BOLD_WEBHOOK_SECRET", "WOMPI_EVENTS_SECRET", "GMAIL_CLIENT_ID",
    "CLOUDINARY_CLOUD_NAME",
    "FE_HABILITADA", "HONORARIOS_HABILITADO", "BANCOLOMBIA_HABILITADO",
    "BOLD_HABILITADO", "WOMPI_HABILITADO", "GMAIL_COMPRAS_HABILITADO",
    "CLOUDINARY_HABILITADO", "IA_MEMORIA_AVANZADA", "INVENTARIO_HABILITADO",
    "CAJA_HABILITADA", "FIADOS_HABILITADO",
]

_FLAGS = [
    "FE_HABILITADA", "HONORARIOS_HABILITADO", "BANCOLOMBIA_HABILITADO",
    "BOLD_HABILITADO", "WOMPI_HABILITADO", "GMAIL_COMPRAS_HABILITADO",
    "CLOUDINARY_HABILITADO", "IA_MEMORIA_AVANZADA", "INVENTARIO_HABILITADO",
    "CAJA_HABILITADA", "FIADOS_HABILITADO",
]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(extra_env: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _OPCIONALES}
    env.update(_CORE_ENV)
    env.update(extra_env)
    code = (
        "import json, config as c; "
        f"print(json.dumps({{f: bool(getattr(c, f)) for f in {_FLAGS!r}}}))"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env, cwd=_ROOT, capture_output=True, text=True,
    )


def _flags(extra_env: dict) -> dict:
    r = _run(extra_env)
    assert r.returncode == 0, f"config abortó: {r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_punto_rojo_con_credenciales_todo_activo():
    f = _flags({
        "MATIAS_EMAIL": "a@b.com", "HONORARIOS_CHAT_ID": "123",
        "BANCOLOMBIA_GMAIL_CLIENT_ID": "cid", "BOLD_WEBHOOK_SECRET": "s",
        "WOMPI_EVENTS_SECRET": "s", "GMAIL_CLIENT_ID": "g",
        "CLOUDINARY_CLOUD_NAME": "cn",
    })
    assert f["FE_HABILITADA"]
    assert f["HONORARIOS_HABILITADO"]
    assert f["BANCOLOMBIA_HABILITADO"]
    assert f["BOLD_HABILITADO"]
    assert f["WOMPI_HABILITADO"]
    assert f["GMAIL_COMPRAS_HABILITADO"]
    assert f["CLOUDINARY_HABILITADO"]


def test_ferreteria_nueva_sin_credenciales_modulos_apagados():
    f = _flags({})
    assert not f["FE_HABILITADA"]
    assert not f["HONORARIOS_HABILITADO"]
    assert not f["BANCOLOMBIA_HABILITADO"]
    assert not f["BOLD_HABILITADO"]
    assert not f["WOMPI_HABILITADO"]
    assert not f["GMAIL_COMPRAS_HABILITADO"]
    # Core "dormidos" activos por defecto (no rompen Punto Rojo).
    assert f["IA_MEMORIA_AVANZADA"]
    assert f["INVENTARIO_HABILITADO"]
    assert f["CAJA_HABILITADA"]


def test_flag_explicito_false_gana_sobre_autodetect():
    f = _flags({"MATIAS_EMAIL": "a@b.com", "FE_HABILITADA": "false"})
    assert not f["FE_HABILITADA"]


def test_flag_explicito_true_sin_credencial_falla_validacion():
    r = _run({"FE_HABILITADA": "true"})
    assert r.returncode != 0  # _validar_flags() aborta con SystemExit

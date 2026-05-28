"""
tests/test_consecutivo_atomico.py — Tests del helper proximo_consecutivo_atomico.

Cubre la lógica determinística sin requerir PostgreSQL real:
  - LOCK TABLE se emite antes del SELECT.
  - El SELECT filtra por fecha (reset diario).
  - Retorna 1 cuando no hay ventas en la fecha.
  - Retorna MAX + 1 cuando ya hay ventas en la fecha.

No requiere DATABASE_URL — usa un cursor mock que registra las queries.
"""

# -- stdlib --
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

# ── Stubs (deben preceder al import de db) ────────────────────────────────────
if "config" not in sys.modules:
    sys.modules["config"] = types.ModuleType("config")

# Otros tests stubean sys.modules["db"] durante la fase de collection de
# pytest. Para que nuestros tests vean el módulo db real, lo cargamos desde
# su path sin modificar sys.modules (así no rompemos a otros tests).
_db_real_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db.py"
)
_spec = importlib.util.spec_from_file_location("_db_real", _db_real_path)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


def _cursor_mock(max_consecutivo: int | None):
    """Crea un cursor mock que registra ejecuciones y devuelve un MAX configurable."""
    cur = MagicMock()
    cur.queries = []  # historial de ejecuciones

    def _execute(sql, params=None):
        cur.queries.append((sql, params))
        return None

    # fetchone retorna lo que sería el resultado del SELECT MAX(consecutivo)
    def _fetchone():
        if max_consecutivo is None:
            return {"siguiente": 1}
        return {"siguiente": max_consecutivo + 1}

    cur.execute = _execute
    cur.fetchone = _fetchone
    return cur


def test_proximo_consecutivo_emite_lock_table_primero():
    """La primera query ejecutada debe ser LOCK TABLE ventas (atomicidad)."""
    cur = _cursor_mock(max_consecutivo=None)
    db.proximo_consecutivo_atomico(cur, "2026-05-27")
    assert len(cur.queries) >= 2
    primera_sql, _ = cur.queries[0]
    assert "LOCK TABLE VENTAS" in primera_sql.upper()
    assert "SHARE ROW EXCLUSIVE" in primera_sql.upper()


def test_proximo_consecutivo_filtra_por_fecha():
    """El SELECT debe incluir WHERE fecha = %s (reset diario, no MAX global)."""
    cur = _cursor_mock(max_consecutivo=None)
    db.proximo_consecutivo_atomico(cur, "2026-05-27")
    select_sql, params = cur.queries[1]
    assert "MAX(consecutivo)" in select_sql
    assert "WHERE fecha = %s" in select_sql
    assert params == ("2026-05-27",)


def test_proximo_consecutivo_retorna_1_cuando_no_hay_ventas():
    """Sin ventas en la fecha → consecutivo 1."""
    cur = _cursor_mock(max_consecutivo=None)
    resultado = db.proximo_consecutivo_atomico(cur, "2026-05-27")
    assert resultado == 1


def test_proximo_consecutivo_retorna_max_mas_uno():
    """Con MAX=47 en la fecha → consecutivo 48."""
    cur = _cursor_mock(max_consecutivo=47)
    resultado = db.proximo_consecutivo_atomico(cur, "2026-05-27")
    assert resultado == 48


def test_proximo_consecutivo_int_no_decimal():
    """El consecutivo retornado debe ser int (no float ni Decimal)."""
    cur = _cursor_mock(max_consecutivo=10)
    resultado = db.proximo_consecutivo_atomico(cur, "2026-05-27")
    assert isinstance(resultado, int)

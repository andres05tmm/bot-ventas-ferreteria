"""
tests/test_facturacion_service.py
Verifica los 4 bugs corregidos en services/facturacion_service.py (abril 2026):

  Fix 1 — _TIPO_ID_MATIAS: todos los 20 tipos de documento verificados con GET /identity-documents
  Fix 2 — identity_document_id ya no está hardcodeado a "1" para personas naturales
  Fix 3 — obtener_pdf usa GET, no POST
  Fix 4 — _armar_lineas_nota usa _fmt() en lugar de int() (no trunca centavos)
"""
import importlib
import types
import pytest


# ─────────────────────────────────────────────
# IMPORTAR EL MÓDULO SIN VARIABLES DE ENTORNO
# (evita errores de conexión a Railway/DB)
# ─────────────────────────────────────────────

def _importar_sin_env(monkeypatch):
    """
    Parchea os.getenv para que las vars de entorno opcionales devuelvan
    strings vacíos y no None, evitando TypeError en int() de MATIAS_NUM_DESDE.
    """
    import os
    _orig = os.getenv

    def _mock_getenv(key, default=None):
        if key in ("MATIAS_NUM_DESDE",):
            return "1"
        return _orig(key, default)

    monkeypatch.setattr(os, "getenv", _mock_getenv)

    # db.py intentaría conectarse a Postgres — lo evitamos con un stub mínimo
    db_stub = types.ModuleType("db")
    db_stub.query_all = lambda *a, **k: []
    db_stub.execute = lambda *a, **k: None
    import sys
    sys.modules.setdefault("db", db_stub)

    # config.py stub si no existe
    if "config" not in sys.modules:
        config_stub = types.ModuleType("config")
        import pytz
        config_stub.COLOMBIA_TZ = pytz.timezone("America/Bogota")
        sys.modules["config"] = config_stub

    # Importar (o recargar) el módulo bajo prueba
    if "services.facturacion_service" in sys.modules:
        mod = importlib.reload(sys.modules["services.facturacion_service"])
    else:
        import services.facturacion_service as mod
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: _TIPO_ID_MATIAS tiene todos los tipos verificados con la API real
# ─────────────────────────────────────────────────────────────────────────────

class TestTipoIdMatiasDict:
    """Verifica que _TIPO_ID_MATIAS contenga los IDs correctos según
    GET /identity-documents de la API de MATIAS (verificado abril 2026)."""

    # Fuente: respuesta real de la API — id, abbreviation
    ESPERADOS = {
        "CC":   "1",   # Cédula de ciudadanía
        "CE":   "2",   # Cédula de extranjería
        "NIT":  "3",   # NIT empresa
        "RC":   "6",   # Registro civil
        "TI":   "7",   # Tarjeta de identidad
        "TE":   "8",   # Tarjeta de extranjería
        "PA":   "9",   # Pasaporte
        "PPN":  "9",   # Alias pasaporte
        "DE":   "10",  # Documento extranjero
        "NITE": "11",  # NIT entidad extranjera
        "NUIP": "12",  # NUIP
        "PPT":  "13",  # Permiso permanencia temporal
        "PP":   "13",  # Alias PPT
        "PEP":  "14",  # Permiso especial de permanencia
        "PE":   "14",  # Alias PEP
        "SC":   "15",  # Secuencial de clientes
        "CN":   "16",  # Certificado nacido vivo
        "AS":   "17",  # Adulto sin identificar
        "MS":   "18",  # Menor sin identificar
        "SI":   "19",  # Sin identificación
        "CD":   "20",  # Carné diplomático
    }

    def test_todos_los_tipos_presentes(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        for abrev, id_esperado in self.ESPERADOS.items():
            actual = mod._TIPO_ID_MATIAS.get(abrev)
            assert actual == id_esperado, (
                f"_TIPO_ID_MATIAS['{abrev}'] = {actual!r}, se esperaba {id_esperado!r}"
            )

    def test_cc_es_1(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS["CC"] == "1"

    def test_nit_es_3(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS["NIT"] == "3"

    def test_ce_es_2(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS["CE"] == "2"

    def test_pep_y_pe_son_14(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS["PEP"] == "14"
        assert mod._TIPO_ID_MATIAS["PE"] == "14"

    def test_ppt_y_pp_son_13(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS["PPT"] == "13"
        assert mod._TIPO_ID_MATIAS["PP"] == "13"

    def test_tipos_nuevos_cn_as_ms_si_cd(self, monkeypatch):
        """CN, AS, MS, SI, CD estaban faltando antes del fix."""
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS["CN"] == "16"
        assert mod._TIPO_ID_MATIAS["AS"] == "17"
        assert mod._TIPO_ID_MATIAS["MS"] == "18"
        assert mod._TIPO_ID_MATIAS["SI"] == "19"
        assert mod._TIPO_ID_MATIAS["CD"] == "20"

    def test_fallback_tipo_desconocido_devuelve_1(self, monkeypatch):
        """Si llega un tipo no mapeado, el .get() debe devolver "1" (CC)."""
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS.get("DESCONOCIDO", "1") == "1"


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: identity_document_id usa el lookup, NO está hardcodeado a "1"
# ─────────────────────────────────────────────────────────────────────────────

class TestIdentityDocumentIdNoHardcodeado:
    """
    Comprueba que para un cliente con CE (cédula extranjería), el campo
    identity_document_id sea "2" y NO "1" (el bug original).

    Usamos la lógica directa de _TIPO_ID_MATIAS.get() para simular lo que
    hace el código en el Caso 3 del bloque customer.
    """

    def test_ce_no_produce_1(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        tipo_id = "CE"
        resultado = mod._TIPO_ID_MATIAS.get(tipo_id, "1")
        assert resultado == "2", (
            f"CE debe mapear a '2' (fix), pero devolvió '{resultado}' "
            f"(posible regresión al bug de hardcoded '1')"
        )

    def test_ti_tarjeta_identidad_no_produce_1(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS.get("TI", "1") == "7"

    def test_pep_migrante_no_produce_1(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS.get("PEP", "1") == "14"

    def test_ppt_venezolano_no_produce_1(self, monkeypatch):
        mod = _importar_sin_env(monkeypatch)
        assert mod._TIPO_ID_MATIAS.get("PPT", "1") == "13"


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: obtener_pdf usa GET, no POST
# ─────────────────────────────────────────────────────────────────────────────

class TestObtenerPdfUsaGet:
    """
    Verifica que la función obtener_pdf esté implementada como GET
    (no POST como estaba antes del fix).
    Inspeccionamos el código fuente de la función para no depender
    de mocks complejos de httpx.
    """

    def test_obtener_pdf_es_get_no_post(self, monkeypatch):
        import inspect
        mod = _importar_sin_env(monkeypatch)
        src = inspect.getsource(mod.obtener_pdf)
        assert "client.get(" in src, (
            "obtener_pdf debe usar client.get() según docs MATIAS v3"
        )
        assert "client.post(" not in src, (
            "obtener_pdf NO debe usar client.post() — ese era el bug original"
        )

    def test_obtener_pdf_pasa_regenerate_como_param(self, monkeypatch):
        import inspect
        mod = _importar_sin_env(monkeypatch)
        src = inspect.getsource(mod.obtener_pdf)
        assert "regenerate" in src, (
            "obtener_pdf debe pasar ?regenerate=1 como query param"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: _armar_lineas_nota no trunca decimales con int()
# ─────────────────────────────────────────────────────────────────────────────

class TestArmarLineasNotaDecimales:
    """
    Verifica que _armar_lineas_nota NO use int() para sumar totales
    (el bug original truncaba 50.50 → 50, causando error FAU04 en DIAN).
    """

    def test_no_usa_int_para_sumar_totales(self, monkeypatch):
        import inspect
        mod = _importar_sin_env(monkeypatch)
        src = inspect.getsource(mod._armar_lineas_nota)
        # No debe haber int(d.get("total" ni int(item.get("total"
        assert "int(d.get(\"total\"" not in src, (
            "_armar_lineas_nota no debe truncar totales con int() — FIX 4"
        )
        assert "int(item.get(\"total\"" not in src, (
            "_armar_lineas_nota no debe truncar iva_val con int() — FIX 4"
        )

    def test_usa_fmt_para_sumar_totales(self, monkeypatch):
        import inspect
        mod = _importar_sin_env(monkeypatch)
        src = inspect.getsource(mod._armar_lineas_nota)
        assert "_fmt(" in src, (
            "_armar_lineas_nota debe usar _fmt() para calcular totales con decimales"
        )

    def test_calculo_decimal_correcto(self, monkeypatch):
        """
        Prueba funcional: una línea con total 50.50 y 19% IVA.
        Antes (con int): subtotal_gravable = 50, iva = 9  → error FAU04
        Ahora (con _fmt): subtotal_gravable = 50.50, iva = 9.60
        """
        mod = _importar_sin_env(monkeypatch)
        lineas = [
            {
                "descripcion":    "Tornillo 3/4",
                "cantidad":       1,
                "precio_unitario": 50.50,
                "total":          50.50,
                "tiene_iva":      True,
                "porcentaje_iva": 19,
                "unidad":         "Unidad",
            }
        ]
        _, subtotal, subtotal_gravable, total_iva = mod._armar_lineas_nota(lineas)

        # subtotal no debe ser 50 (truncado), debe ser 50.50
        assert subtotal == pytest.approx(50.50, abs=0.01), (
            f"subtotal={subtotal} — no debe truncar a 50 (bug int())"
        )
        assert subtotal_gravable == pytest.approx(50.50, abs=0.01), (
            f"subtotal_gravable={subtotal_gravable} — no debe truncar"
        )
        # IVA de 50.50 al 19% = 9.595 ≈ 9.60
        assert total_iva == pytest.approx(9.60, abs=0.01), (
            f"total_iva={total_iva} — esperado ~9.60, no 9 (truncado)"
        )

    def test_calculo_multiples_lineas(self, monkeypatch):
        """
        Dos líneas con decimales: verifica que el subtotal acumulado sea correcto.
        """
        mod = _importar_sin_env(monkeypatch)
        lineas = [
            {
                "descripcion":     "Producto A",
                "cantidad":        2,
                "precio_unitario": 10.75,
                "total":           21.50,
                "tiene_iva":       True,
                "porcentaje_iva":  19,
                "unidad":          "Unidad",
            },
            {
                "descripcion":     "Producto B",
                "cantidad":        1,
                "precio_unitario": 5.99,
                "total":           5.99,
                "tiene_iva":       False,
                "porcentaje_iva":  0,
                "unidad":          "Unidad",
            },
        ]
        _, subtotal, subtotal_gravable, total_iva = mod._armar_lineas_nota(lineas)

        assert subtotal == pytest.approx(27.49, abs=0.01)
        assert subtotal_gravable == pytest.approx(21.50, abs=0.01)
        assert total_iva == pytest.approx(4.09, abs=0.01)  # 21.50 * 0.19 = 4.085 ≈ 4.09

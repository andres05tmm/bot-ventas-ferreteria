"""
tests/test_semantic_catalog.py — Búsqueda semántica del catálogo (fallback fuzzy).

El módulo usa embeddings de OpenAI + cargar_memoria. Acá ambos se reemplazan por
fakes deterministas (vectores controlados) para testear el ranking por coseno, el
umbral, la caché por firma y el comportamiento fail-safe — sin tocar la red.
"""

# -- stdlib --
import os
import types

# Importar el módulo dispara ai/__init__ → config, que aborta sin estas claves.
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")

# -- terceros --
import pytest

# -- propios --
import config
import ai.semantic_catalog as sc


# ─────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────

class _FakeEmbeddings:
    """Imita config.openai_client.embeddings: mapea texto → vector fijo."""
    def __init__(self, mapa, fallar=False):
        self.mapa = mapa
        self.fallar = fallar
        self.llamadas = 0

    def create(self, model, input):
        self.llamadas += 1
        if self.fallar:
            raise RuntimeError("API caída")
        data = [types.SimpleNamespace(embedding=self.mapa.get(t, [0.0, 0.0, 1.0]))
                for t in input]
        return types.SimpleNamespace(data=data)


# Catálogo simulado: el "sentido" de cada producto es un eje del espacio 3D.
_CATALOGO = {
    "1": {"nombre": "Pegante Instantáneo", "nombre_lower": "pegante instantaneo", "precio_unidad": 3000},
    "2": {"nombre": "Martillo",            "nombre_lower": "martillo",            "precio_unidad": 15000},
    "3": {"nombre": "Cemento Gris",        "nombre_lower": "cemento gris",        "precio_unidad": 28000},
}

# Vectores: pegante≈eje X, martillo≈eje Y, cemento≈eje Z.
_VECS = {
    "Pegante Instantáneo": [1.0, 0.0, 0.0],
    "Martillo":            [0.0, 1.0, 0.0],
    "Cemento Gris":        [0.0, 0.0, 1.0],
    # consultas
    "pega loca":           [0.95, 0.05, 0.0],   # cerca de pegante
    "puntilla":            [0.0, 0.9, 0.1],      # cerca de martillo (no exacto)
    "banano maduro":       [0.4, 0.4, 0.4],      # equidistante → coseno ~0.57 a c/u
    "xyzqwerty":           [-1.0, 0.0, 0.0],     # opuesto a todo
}


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    """Resetea el índice y cablea los fakes antes de cada test."""
    sc._indice = []
    sc._firma = None
    monkeypatch.setattr(config, "IA_SEMANTIC_CATALOGO", True, raising=False)
    fake = _FakeEmbeddings(_VECS)
    monkeypatch.setattr(config, "openai_client",
                        types.SimpleNamespace(embeddings=fake))
    monkeypatch.setattr("memoria.cargar_memoria", lambda: {"catalogo": _CATALOGO})
    return fake


# ─────────────────────────────────────────────
# Ranking por coseno
# ─────────────────────────────────────────────

def test_encuentra_el_mas_cercano():
    prod = sc.buscar_semantico("pega loca")
    assert prod is not None and prod["nombre"] == "Pegante Instantáneo"


def test_sugerencia_devuelve_nombre():
    assert sc.sugerencia_semantica("pega loca") == "Pegante Instantáneo"


def test_otro_eje_matchea_su_producto():
    prod = sc.buscar_semantico("puntilla")
    assert prod is not None and prod["nombre"] == "Martillo"


# ─────────────────────────────────────────────
# Umbral
# ─────────────────────────────────────────────

def test_bajo_umbral_no_sugiere():
    # "xyzqwerty" es opuesto (coseno negativo) → ningún match supera el umbral.
    assert sc.buscar_semantico("xyzqwerty") is None
    assert sc.sugerencia_semantica("xyzqwerty") is None


def test_umbral_custom_estricto_descarta_equidistante():
    # "banano maduro" da coseno ~0.577 a cada eje; con umbral 0.8 no alcanza.
    assert sc.buscar_semantico("banano maduro", umbral=0.8) is None
    # Con umbral por defecto (0.45) sí pasa el más cercano (alguno de los ejes).
    assert sc.buscar_semantico("banano maduro") is not None


def test_query_muy_corta_se_ignora():
    assert sc.buscar_semantico("ab") is None


# ─────────────────────────────────────────────
# Caché por firma
# ─────────────────────────────────────────────

def test_indice_se_construye_una_vez(_entorno):
    fake = _entorno
    sc.buscar_semantico("pega loca")
    sc.buscar_semantico("puntilla")
    # 1 build del índice (3 productos) + 1 embedding por cada query = 1 + 2 = 3.
    assert fake.llamadas == 3


def test_indice_se_reconstruye_si_cambia_catalogo(monkeypatch, _entorno):
    fake = _entorno
    sc.buscar_semantico("pega loca")               # construye índice (firma A)
    llamadas_tras_primera = fake.llamadas
    # Catálogo nuevo (un producto más) → firma distinta → reconstruye.
    nuevo = dict(_CATALOGO)
    nuevo["4"] = {"nombre": "Taladro", "nombre_lower": "taladro", "precio_unidad": 90000}
    monkeypatch.setattr("memoria.cargar_memoria", lambda: {"catalogo": nuevo})
    _VECS["Taladro"] = [0.0, 0.0, 0.0]
    sc.buscar_semantico("pega loca")
    # Hubo una reconstrucción extra (build) además del embedding de la query.
    assert fake.llamadas > llamadas_tras_primera + 1


# ─────────────────────────────────────────────
# Fail-safe
# ─────────────────────────────────────────────

def test_falla_de_api_devuelve_none(monkeypatch):
    monkeypatch.setattr(config, "openai_client",
                        types.SimpleNamespace(embeddings=_FakeEmbeddings(_VECS, fallar=True)))
    sc._indice = []
    sc._firma = None
    assert sc.buscar_semantico("pega loca") is None


def test_flag_apagado_devuelve_none(monkeypatch):
    monkeypatch.setattr(config, "IA_SEMANTIC_CATALOGO", False, raising=False)
    assert sc.buscar_semantico("pega loca") is None


def test_catalogo_vacio_devuelve_none(monkeypatch):
    monkeypatch.setattr("memoria.cargar_memoria", lambda: {"catalogo": {}})
    assert sc.buscar_semantico("pega loca") is None


def test_coseno_vector_nulo():
    assert sc._coseno([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == 0.0

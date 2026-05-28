"""
Arnés de pruebas del motor de ventas — READ-ONLY contra la BD de producción.

Mete mensajes en lenguaje natural por el MISMO pipeline que usa el bot
(`procesar_con_claude`), parsea los tags [VENTA] resultantes y los compara
contra un valor esperado, SIN registrar la venta (nunca llama
`procesar_acciones`, que es el único que escribe en la BD).

Objetivo: cazar bugs en productos difíciles — fracciones, fracciones mixtas,
variantes (drywall/lija/tornillos), precio mayorista por umbral, granel por
kilo, puntillas por peso, lija esmeril por cm, y ambigüedad multi-turno.

Uso:
    python pruebas_motor.py            # corre todas las categorías
    python pruebas_motor.py fracciones # corre solo una categoría
"""

# -- stdlib --
import os
import re
import sys
import json
import asyncio
import logging

# -- terceros --
from dotenv import load_dotenv

# ── Configurar entorno ANTES de importar módulos del proyecto ────────────────
load_dotenv()
# Igualar producción: tool-calling nativo activo.
os.environ["IA_TOOL_CALLING"] = "true"
# Placeholders para claves que config.py exige pero que NO se usan al procesar
# ventas de texto (el bot de Telegram y Whisper no intervienen en el arnés).
os.environ.setdefault("TELEGRAM_TOKEN", "harness-dummy")
os.environ.setdefault("OPENAI_API_KEY", "harness-dummy")
# Consola Windows en UTF-8 para los caracteres de formato (═ ▶ ⚠ ⓘ).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
# Silenciar logs ruidosos del bot durante las pruebas.
logging.disable(logging.WARNING)

# -- propios (después de fijar el entorno) --
import db as _db
import memoria
from ai import procesar_con_claude

VENDEDOR = "Andres"
_VENTA_RE = re.compile(r"\[VENTA\](.*?)\[/VENTA\]", re.DOTALL)
_TAG_RE = re.compile(r"\[/?[A-ZÉÍ_]+(?:\][^\[]*\[/[A-ZÉÍ_]+)?\]", re.DOTALL)


# ─────────────────────────────────────────────
# PARSEO DE LA RESPUESTA CRUDA
# ─────────────────────────────────────────────
def _parsear(respuesta_raw: str) -> tuple[str, list[dict]]:
    """Extrae los [VENTA] y el texto visible (pregunta/aviso) de la respuesta cruda."""
    ventas: list[dict] = []
    for m in _VENTA_RE.finditer(respuesta_raw):
        try:
            ventas.append(json.loads(m.group(1)))
        except Exception:
            ventas.append({"_raw_json": m.group(1)})
    # Texto visible = respuesta sin ningún bloque de tag [XXX]...[/XXX] ni tag suelto
    texto = re.sub(r"\[VENTA\].*?\[/VENTA\]", "", respuesta_raw, flags=re.DOTALL)
    texto = re.sub(r"\[[A-ZÉÍ_]+\].*?\[/[A-ZÉÍ_]+\]", "", texto, flags=re.DOTALL)
    texto = re.sub(r"\[/?[A-ZÉÍ_:]+[^\]]*\]", "", texto)
    return texto.strip(), ventas


# ─────────────────────────────────────────────
# SIMULACIÓN DE CONVERSACIÓN (replica mensajes.py)
# ─────────────────────────────────────────────
async def simular(turnos: list[str]) -> list[dict]:
    """
    Simula una conversación multi-turno replicando la reinyección de contexto
    [PEDIDO ORIGINAL:] que hace handlers/mensajes.py.
    Retorna una lista de dicts por turno: {mensaje, texto, ventas, raw}.
    """
    historial: list[dict] = []
    ctx_pendiente: dict | None = None
    salida: list[dict] = []

    for mensaje in turnos:
        msg_para_claude = mensaje
        if ctx_pendiente and ctx_pendiente["mensaje"] != mensaje:
            msg_para_claude = (
                f"[PEDIDO ORIGINAL: {ctx_pendiente['mensaje']}]\n"
                f"[PREGUNTA DEL BOT: {ctx_pendiente['pregunta']}]\n"
                f"[RESPUESTA DEL CLIENTE: {mensaje}]\n"
                "Retoma el pedido original aplicando la respuesta del cliente a la pregunta del bot."
            )

        # historial SIN el mensaje actual (mensajes.py lo pasa así)
        snapshot = list(historial)
        historial.append({"role": "user", "content": f"{VENDEDOR}: {mensaje}"})

        try:
            raw = await procesar_con_claude(
                f"{VENDEDOR}: {msg_para_claude}", VENDEDOR, snapshot, vendedor_id=None
            )
        except Exception as e:  # noqa: BLE001
            raw = f"__ERROR__: {type(e).__name__}: {e}"

        texto, ventas = _parsear(raw)
        historial.append({"role": "assistant", "content": texto or raw})

        # Replica la decisión de mensajes.py de guardar contexto pendiente
        if texto and not ventas and "?" in texto and "__ERROR__" not in raw:
            ctx_pendiente = {"mensaje": mensaje, "pregunta": texto}
        else:
            ctx_pendiente = None

        salida.append({"mensaje": mensaje, "texto": texto, "ventas": ventas, "raw": raw})

    return salida


# ─────────────────────────────────────────────
# CRUCE DE PRECIOS CONTRA CATÁLOGO
# ─────────────────────────────────────────────
def _catalogo_lookup() -> dict[str, int]:
    cat = memoria.cargar_memoria().get("catalogo", {})
    out: dict[str, int] = {}
    for prod in cat.values():
        nombre = (prod.get("nombre") or "").strip().lower()
        if nombre:
            out[nombre] = prod.get("precio_unidad")
    return out


# ─────────────────────────────────────────────
# BATERÍA DE CASOS
# Cada caso: (turnos, esperado_humano)
# turnos: lista de mensajes (multi-turno si len>1)
# ─────────────────────────────────────────────
CASOS: dict[str, list[tuple[list[str], str]]] = {
    "fracciones": [
        (["1/4 de thinner"], "1/4 galón thinner = $8.000"),
        (["litro de thinner"], "litro=1/4 galón = $8.000"),
        (["botella de varsol"], "botella=1/4 galón = $8.000"),
        (["botellita de thinner"], "botellita=1/10 galón = $4.000"),
        (["medio galon thinner"], "1/2 galón = $13.000"),
        (["1 thinner"], "número sin unidad = 1 galón = $26.000 (NO fracción)"),
        (["2 varsol"], "2 galones = $52.000"),
        (["thinner 4000"], "por precio: 4000 = 1/10 galón, total $4.000"),
    ],
    "fracciones_mixtas": [
        (["1-1/2 galon thinner"], "1.5 galones = 26000+13000 = $39.000"),
        (["2 y medio galones varsol"], "2.5 galones = 52000+13000 = $65.000"),
        (["1-1/4 galon thinner"], "1.25 galones = 26000 + (1/4 menudeo=8000) = $34.000"),
    ],
    "lija_esmeril": [
        (["20 cm lija esmeril 36"], "22000/100*20 = $4.400"),
        (["50 cm lija esmeril 60"], "20000/100*50 = $10.000"),
    ],
    "lija_unidad": [
        (["2 lija 100"], "2 x $2.000 = $4.000"),
        (["1 lija"], "AMBIGUO → debe preguntar el número (N°60, N°100, ...)"),
        (["1 lija", "120"], "multi-turno: tras preguntar, '120' → 1 x Lija N°120 = $2.000"),
        (["1 lija", "100"], "multi-turno: '100' → 1 x Lija N°100 = $2.000"),
    ],
    "drywall": [
        (["media docena tornillos drywall 6x2"], "6 x $67 = $402"),
        (["media docena tornillos drywall"], "AMBIGUO → preguntar variante 6x1/6x2/8x3... (BUG conocido: lista rota)"),
        (["media docena tornillos drywall", "6x2"], "multi-turno: → 6 x $67 = $402"),
        (["100 tornillos drywall 6x1"], "100>=50 → mayorista $40 → $4.000"),
        (["1 docena tornillos drywall 8x3"], "12 x $84 = $1.008"),
    ],
    "vinilo": [
        (["1/4 de vinilo t1"], "AMBIGUO: muchos colores T1 → debe preguntar color"),
        (["1 galon vinilo t1 blanco"], "$50.000"),
        (["medio cunete vinilo t1"], "1/2 Cuñete T1 = $120.000, cantidad=1"),
        (["2 cunetes vinilo t1"], "cuñete=4 galones; t1 davinci 220000 -> 2 = $440.000"),
    ],
    "granel": [
        (["2 kilos cemento blanco"], "2 x $2.500 = $5.000"),
        (["medio kilo yeso"], "0.5 x $1.500 = $750"),
        (["kilo y medio talco"], "1.5 x $1.500 = $2.250"),
    ],
}


# ─────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────
def _fmt_venta(v: dict) -> str:
    if "_raw_json" in v:
        return f"[VENTA JSON inválido: {v['_raw_json'][:80]}]"
    prod = v.get("producto", "?")
    cant = v.get("cantidad", "?")
    pu = v.get("precio_unitario", v.get("precio_unidad", "?"))
    tot = v.get("total", "?")
    return f"{cant} × {prod} @ {pu} = ${tot}"


async def correr(categorias: list[str]) -> None:
    print("Inicializando BD (catálogo de producción, read-only)...")
    if not _db.init_db():
        print("ERROR: no se pudo conectar a la BD. ¿DATABASE_URL en .env?")
        sys.exit(1)
    lookup = _catalogo_lookup()
    print(f"Catálogo cargado: {len(lookup)} productos.\n")
    print(f"IA_TOOL_CALLING = {os.environ.get('IA_TOOL_CALLING')}\n")

    total = 0
    for cat in categorias:
        casos = CASOS.get(cat)
        if not casos:
            continue
        print("═" * 78)
        print(f"  CATEGORÍA: {cat}")
        print("═" * 78)
        for turnos, esperado in casos:
            total += 1
            res = await simular(turnos)
            # Encabezado del caso
            entrada = "  →  ".join(turnos)
            print(f"\n▶ ENTRADA : {entrada}")
            print(f"  ESPERADO: {esperado}")
            # Mostrar cada turno
            for i, r in enumerate(res):
                etiqueta = f"  turno {i+1}" if len(res) > 1 else "  bot   "
                if r["ventas"]:
                    for v in r["ventas"]:
                        print(f"{etiqueta} VENTA: {_fmt_venta(v)}")
                        # Cruce de precio contra catálogo (solo informativo)
                        prod_l = str(v.get("producto", "")).strip().lower()
                        if prod_l in lookup:
                            cat_precio = lookup[prod_l]
                            pu = v.get("precio_unitario")
                            if pu is not None and cat_precio is not None and pu != cat_precio:
                                print(f"           ⓘ catálogo precio_unidad={cat_precio} (venta usó {pu})")
                        elif prod_l and not any(prod_l in k or k in prod_l for k in lookup):
                            print(f"           ⚠ producto '{v.get('producto')}' NO existe tal cual en catálogo")
                if r["texto"]:
                    print(f"{etiqueta} TEXTO: {r['texto'][:200]}")
                if "__ERROR__" in r["raw"]:
                    print(f"{etiqueta} {r['raw'][:200]}")
            sys.stdout.flush()

    print("\n" + "═" * 78)
    print(f"  TOTAL CASOS CORRIDOS: {total}")
    print("═" * 78)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a in CASOS]
    cats = args if args else list(CASOS.keys())
    asyncio.run(correr(cats))

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
# Tags de bloque [XXX]...[/XXX] y marcadores de acción sueltos que emite Claude.
_TAGS_BLOQUE = ("VENTA", "GASTO", "FIADO", "INVENTARIO", "BUSCAR_HISTORICO",
                "PRECIO_ACTUALIZADO", "PRECIO_MAYORISTA", "PRECIO_FRACCION")
_ACCIONES_RE = re.compile(
    r"\b(PEDIR_METODO_PAGO|INICIAR_FLUJO_CLIENTE|PAGO_PENDIENTE_AVISO|"
    r"PEDIR_CONFIRMACION|CLIENTE_DESCONOCIDO)\b"
)


def _detectar_tags(raw: str) -> list[str]:
    """Lista de tags de bloque y acciones presentes en la respuesta cruda."""
    tags = [t for t in _TAGS_BLOQUE if f"[{t}]" in raw]
    tags += sorted(set(_ACCIONES_RE.findall(raw)))
    return tags


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
        (["medio kilo yeso"], "0.5 x $2.000 = $1.000 (catálogo $2.000/kg)"),
        (["kilo y medio talco"], "1.5 x $2.000 = $3.000 (catálogo $2.000/kg)"),
    ],
    # Puntilla 2" = caja $5.000 → precio_gramo $10. (con/sin cabeza, mismo precio)
    "puntillas": [
        (["caja puntilla 2"], "caja completa = 500gr, total $5.000"),
        (["media caja puntilla 2"], "250gr, total $2.500"),
        (["1/4 de caja puntilla 2"], "125gr, total $1.250"),
        (["300 gramos puntilla 2"], "300 x $10/gr = $3.000"),
        (["$2000 de puntilla 2 sc"], "por pesos: 2000/10 = 200gr, total $2.000"),
        (["2000 de puntilla 2"], "por pesos: 200gr, total $2.000"),
    ],
    "multiproducto": [
        (["2 tornillos drywall 6x1, 3 lija 100"], "multi: 2x$42=$84 + 3x$2000=$6000"),
        (["2 tornillos drywall 6x1\n3 lija 100"], "multi-línea: igual que arriba"),
        (["5 chazo plastico 1/4, 2 lija 80"], "multi: 5x$42=$210 + 2x$2000=$4000"),
        (["1 galon vinilo t1 blanco, 2 lija 100"], "multi: $50.000 + $4.000"),
    ],
    # Estrés: 7 productos en un mensaje mezclando fracción, gramos, kilos,
    # fracción mixta, mayorista (100 tornillos) y unidad. Total esperado $66.000.
    "estres7": [
        ([
            "1/4 de thinner\n"
            "300 gramos puntilla 2\n"
            "2 kilos cemento blanco\n"
            "1-1/2 galon varsol\n"
            "100 tornillos drywall 6x1\n"
            "3 lija 150\n"
            "medio kilo yeso"
        ],
         "7 prods: thinner 1/4=8000 + puntilla2 300gr=3000 + cemento 2kg=5000 + "
         "varsol 1.5gal=39000 + drywall 6x1 x100 mayorista=4000 + lija150 x3=6000 + "
         "yeso 0.5kg=1000 → TOTAL $66.000"),
    ],
    # Tintes: precio_tarro $26.000 → precio_ml $26. Venta por ml/pesos/tarro.
    "tintes": [
        (["1 tinte caoba"], "tarro completo: 1000ml, $26.000"),
        (["2000 de tinte negro"], "por pesos: 2000/26=76.9ml, total $2.000"),
        (["500ml de tinte miel"], "por ml: 500×26 = $13.000"),
        (["medio tarro de tinte caoba"], "500ml, $13.000"),
    ],
    # Wayper: blanco kg=$10.000, color kg=$7.000, blanco und=$700, color und=$500.
    "wayper": [
        (["2 kilos wayper blanco"], "2×10000 = $20.000 (WAYPER BLANCO por kg)"),
        (["medio kilo wayper color"], "0.5×7000 = $3.500 (WAYPER DE COLOR)"),
        (["3 waypers blancos"], "3×700 = $2.100 (WAYPER BLANCO UNIDAD)"),
        (["2 wayper blanco"], "AMBIGUO → preguntar kilo o unidad"),
        (["2 wayper blanco", "por unidad"], "multi-turno: → 2 × WAYPER BLANCO UNIDAD = $1.600 (800 c/u)"),
        (["2 wayper blanco", "kilo"], "multi-turno: → 2 kg WAYPER BLANCO = $20.000"),
        (["1 wayper color", "unidad"], "multi-turno: → 1 × WAYPER DE COLOR UNIDAD = $700"),
    ],
    # Cinta Pele: S=$8.500, M=$10.000, L=$17.000, XL=$28.000. Número = precio en miles.
    "pele": [
        (["pele de 17"], "~$17.000 → Cinta Pele L"),
        (["pele de 10"], "~$10.000 → Cinta Pele M"),
        (["pele xl"], "talla explícita → Cinta Pele XL $28.000"),
    ],
    # Acronal por kilo = $13.000.
    "acronal": [
        (["2 kilos acronal"], "2×13000 = $26.000"),
        (["medio kilo acronal"], "0.5×13000 = $6.500"),
        (["kilo y medio acronal"], "1.5×13000 = $19.500"),
    ],
    # Pinturas por color: esmalte=$65.000, laca corriente=$80.000, poliuretano=$240.000,
    # anticorrosivo=$65.000. SIEMPRE requieren color.
    "pinturas_color": [
        (["1 galon esmalte rojo"], "Esmalte Rojo = $65.000"),
        (["esmalte"], "AMBIGUO → preguntar color (y tipo)"),
        (["1 galon poliuretano blanco"], "Poliuretano Blanco = $240.000"),
        (["poliuretano"], "AMBIGUO → preguntar color"),
        (["1 galon anticorrosivo negro"], "Anticorrosivo Negro = $65.000"),
        (["1 galon laca corriente azul"], "Laca Corriente Azul = $80.000"),
    ],
    # Carbonato: bolsa 25kg=$26.000, kilo suelto=$2.000.
    "carbonato": [
        (["1 bolsa de carbonato"], "Carbonato X 25 Kg = $26.000"),
        (["3 kilos de carbonato"], "3×2000 = $6.000 (Carbonato x Kg)"),
    ],
    # Rodillo: sin medida → Convencional $8.000 (OJO: skill dice $7.000, desactualizado).
    "rodillo": [
        (["3 rodillos"], "3 × Rodillo Convencional $8.000 = $24.000"),
        (["1 rodillo de 3"], "Rodillo de 3\" = $6.000"),
    ],
    # CONSULTAS: NO deben registrar venta — solo responder info. (sin [VENTA])
    "consultas": [
        (["cuanto vale el galon de thinner"], "info precio, SIN [VENTA]"),
        (["hay lija 100?"], "consulta stock, SIN [VENTA]"),
        (["cuanto cuesta el vinilo t1 blanco"], "info precio, SIN [VENTA]"),
        (["cuanto vendimos hoy"], "reporte, SIN [VENTA]"),
        (["tienes cemento blanco"], "consulta disponibilidad, SIN [VENTA]"),
    ],
    # CLIENTE / FIADO: venta asignada a cliente o crédito (espera [VENTA]+acción cliente/fiado).
    "cliente_fiado": [
        (["2 lija 100 fiado a Pedro"], "venta a crédito → [FIADO] o acción cliente Pedro"),
        (["1 galon vinilo t1 blanco para Juan"], "venta asignada a Juan → acción cliente"),
        (["3 tornillos drywall 6x1 a credito"], "crédito sin nombre → pedir cliente / acción fiado"),
    ],
    # MODIFICACIONES / ANULACIÓN: NUNCA deben crear un [VENTA] nuevo.
    "modificaciones": [
        (["anula la ultima venta"], "anular — SIN [VENTA] nuevo"),
        (["cambia el metodo de pago a transferencia"], "modificar — SIN [VENTA] nuevo"),
        (["borra la ultima venta que registre"], "eliminar — SIN [VENTA] nuevo"),
        (["me equivoque, no era esa cantidad"], "corrección — SIN [VENTA] nuevo"),
    ],
    # MULTIPRODUCTO CON FALLO PARCIAL: un ítem problemático junto a válidos.
    # Observar: ¿registra los buenos y marca el malo? ¿bloquea todo? ¿pregunta?
    "multi_problemas": [
        # (1) producto NO en BD + válido
        (["2 lija 150, 5 destornillador magico marca acme"],
         "lija 150 válido ($4.000) + destornillador inexistente → debe avisar que no existe"),
        # (2) ambiguo (1 lija) + válido
        (["1 lija, 2 tornillos drywall 6x1"],
         "lija ambigua (preguntar número) + tornillos 6x1 válido (2×$42=$84)"),
        # (3) typo NO cubierto (drygual) + válido
        (["12 tornillos drygual 6x2, 2 lija 150"],
         "drygual=typo de drywall → 12×$67=$804 ; lija 150 → 2×$2.000=$4.000"),
        # (4) typo SÍ cubierto por alias (drwall) + válido
        (["12 tornillos drwall 6x2, 2 lija 150"],
         "drwall→drywall (alias) → 12×$67=$804 ; lija150 → $4.000"),
        # (5) varios problemas a la vez: ambiguo + inexistente + typo
        (["1 lija, 5 widget inexistente, 12 tornillos drygual 6x2"],
         "ambiguo + inexistente + typo en un solo mensaje"),
        # (6) producto inexistente solo con otro válido (multi-línea)
        (["3 lija 150\n2 martillo de titanio"],
         "lija150 válido + martillo de titanio inexistente"),
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
    extra = ""
    if v.get("cliente"):
        extra += f"  [cliente: {v['cliente']}]"
    if v.get("metodo_pago"):
        extra += f"  [pago: {v['metodo_pago']}]"
    return f"{cant} × {prod} @ {pu} = ${tot}{extra}"


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
                _tags = _detectar_tags(r["raw"])
                _tags_no_venta = [t for t in _tags if t != "VENTA"]
                if _tags_no_venta:
                    print(f"{etiqueta} TAGS:  {', '.join(_tags_no_venta)}")
                if r["texto"]:
                    print(f"{etiqueta} TEXTO: {r['texto'][:200]}")
                if not r["ventas"] and not r["texto"] and not _tags_no_venta:
                    print(f"{etiqueta} (sin venta, sin texto, sin tags)")
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

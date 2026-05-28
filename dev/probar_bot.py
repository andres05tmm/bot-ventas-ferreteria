#!/usr/bin/env python3
"""
dev/probar_bot.py — Harness para probar el chatbot SIN Telegram y SIN escribir en la BD.

Toma un mensaje de texto, arma el prompt REAL (catálogo de la BD), llama a Claude
de verdad con las tools (M-01), y muestra qué decidió: el texto al vendedor y las
acciones (ventas/gastos/fiados...) que registraría.

SEGURO: solo llama procesar_con_claude() (lectura de catálogo + 1 llamada a Claude).
NO ejecuta procesar_acciones() → no escribe ventas en la BD. Usa vendedor_id=None
→ tampoco registra costo en api_costo_diario. 100% read-only salvo la llamada a Claude.

────────────────────────────────────────────────────────────────────────────────
REQUISITOS — crear un archivo .env en la raíz del repo (ya está en .gitignore):

    ANTHROPIC_API_KEY=sk-ant-...        # obligatorio: para llamar a Claude
    DATABASE_URL=postgresql://...       # obligatorio: usar el DATABASE_PUBLIC_URL
                                        # de Railway (la URL interna .railway.internal
                                        # NO resuelve desde tu PC)

(TELEGRAM_TOKEN y OPENAI_API_KEY se completan con valores dummy automáticamente:
 este harness no los necesita.)
────────────────────────────────────────────────────────────────────────────────
USO:

    python dev/probar_bot.py "2 martillo"
    python dev/probar_bot.py "1/4 laca miel catalizada = 17000"
    python dev/probar_bot.py                         # REPL interactivo (mantiene historial)
    python dev/probar_bot.py --batch dev/casos_prueba.txt
    python dev/probar_bot.py --no-tools "2 martillo"  # fuerza el camino de tags actual
    python dev/probar_bot.py --diff "2 martillo"      # compara tools OFF vs ON lado a lado
"""

# -- stdlib --
import os
import re
import sys
import json
import asyncio
import argparse
import pathlib

# El script vive en dev/ — asegurar que la raíz del repo esté en sys.path para
# poder importar config, ai, db, etc. sin importar desde dónde se invoque.
_RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))


# ─────────────────────────────────────────────
# Carga de .env + dummies (antes de importar config)
# ─────────────────────────────────────────────

def _cargar_env() -> None:
    raiz = pathlib.Path(__file__).resolve().parent.parent
    env = raiz / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            linea = linea.strip()
            if "=" in linea and not linea.startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    # El harness no necesita estas claves — dummies para que config no aborte.
    os.environ.setdefault("TELEGRAM_TOKEN", "dev-harness")
    os.environ.setdefault("OPENAI_API_KEY", "dev-harness")


def _verificar_claves() -> None:
    faltan = [k for k in ("ANTHROPIC_API_KEY", "DATABASE_URL") if not os.environ.get(k)]
    if faltan:
        print("❌ Faltan claves en .env:", ", ".join(faltan))
        print("   Ver el encabezado de dev/probar_bot.py para el formato.")
        sys.exit(1)


# ─────────────────────────────────────────────
# Formato de salida
# ─────────────────────────────────────────────

# Todas las acciones que procesar_acciones reconoce (para mostrar lo que Claude emitió).
_TAGS = [
    "VENTA", "GASTO", "FIADO", "ABONO_FIADO", "INVENTARIO", "CLIENTE_NUEVO",
    "INICIAR_CLIENTE", "BORRAR_CLIENTE", "PRECIO", "PRECIO_FRACCION",
    "PRECIO_MAYORISTA", "CODIGO_PRODUCTO", "NEGOCIO", "CAJA", "MEMORIA",
    "EXCEL", "FACTURA_PROVEEDOR", "ABONO_PROVEEDOR",
    "BUSCAR_HISTORICO", "BUSCAR_MEMORIA",
]

_C = {
    "dim": "\033[2m", "bold": "\033[1m", "reset": "\033[0m",
    "green": "\033[32m", "yellow": "\033[33m", "cyan": "\033[36m", "red": "\033[31m",
}
if (os.name == "nt" and not os.environ.get("WT_SESSION")) or not sys.stdout.isatty():
    # Consolas viejas de Windows / salida a pipe → sin ANSI (evita códigos crudos).
    _C = {k: "" for k in _C}


def _extraer_acciones(texto: str) -> dict[str, list]:
    """Extrae todos los tags de acción → {TAG: [dict|str, ...]}."""
    out: dict[str, list] = {}
    for tag in _TAGS:
        bloques = re.findall(rf"\[{tag}\](.*?)\[/{tag}\]", texto, re.DOTALL)
        if not bloques:
            continue
        parsed = []
        for b in bloques:
            try:
                parsed.append(json.loads(b.strip()))
            except Exception:
                parsed.append(b.strip())
        out[tag] = parsed
    return out


def _texto_sin_tags(texto: str) -> str:
    limpio = texto
    for tag in _TAGS:
        limpio = re.sub(rf"\[{tag}\].*?\[/{tag}\]", "", limpio, flags=re.DOTALL)
    return limpio.strip()


def _fmt_venta(v: dict) -> str:
    if not isinstance(v, dict):
        return f"      (no parseable) {v!r}"
    prod = v.get("producto", "?")
    cant = v.get("cantidad", "?")
    total = v.get("total", "?")
    extra = []
    if v.get("metodo_pago"):
        extra.append(f"pago={v['metodo_pago']}")
    if v.get("cliente"):
        extra.append(f"cliente={v['cliente']}")
    extra_s = ("  " + " ".join(extra)) if extra else ""
    try:
        total_s = f"${float(total):,.0f}"
    except Exception:
        total_s = str(total)
    return f"      • {cant} × {prod} = {total_s}{extra_s}"


def _mostrar_resultado(raw: str) -> None:
    acciones = _extraer_acciones(raw)
    texto = _texto_sin_tags(raw)

    if texto:
        print(f"  {_C['cyan']}TEXTO →{_C['reset']} {texto}")
    else:
        print(f"  {_C['dim']}(sin texto — silencio total){_C['reset']}")

    if not acciones:
        print(f"  {_C['dim']}(sin acciones){_C['reset']}")
        return

    for tag, items in acciones.items():
        if tag == "VENTA":
            print(f"  {_C['green']}VENTA ×{len(items)}{_C['reset']}")
            for v in items:
                print(_fmt_venta(v))
        else:
            print(f"  {_C['yellow']}{tag} ×{len(items)}{_C['reset']}")
            for it in items:
                print(f"      • {json.dumps(it, ensure_ascii=False) if isinstance(it, dict) else it}")


# ─────────────────────────────────────────────
# Llamada al motor
# ─────────────────────────────────────────────

async def _procesar(mensaje: str, historial: list, usar_tools: bool) -> str:
    import config
    from ai import procesar_con_claude
    config.IA_TOOL_CALLING = usar_tools   # se lee en runtime dentro del motor
    # El motor espera el prefijo "Vendedor: " como en producción.
    return await procesar_con_claude(
        f"Test: {mensaje}", "Test", historial, vendedor_id=None,
    )


def _run(mensaje: str, historial: list, usar_tools: bool) -> str:
    return asyncio.run(_procesar(mensaje, historial, usar_tools))


# ─────────────────────────────────────────────
# Modos
# ─────────────────────────────────────────────

def _modo_single(mensaje: str, usar_tools: bool) -> None:
    etiqueta = "TOOLS ON" if usar_tools else "TOOLS OFF (tags)"
    print(f"{_C['bold']}» {mensaje}{_C['reset']}  {_C['dim']}[{etiqueta}]{_C['reset']}")
    raw = _run(mensaje, [], usar_tools)
    _mostrar_resultado(raw)


def _modo_diff(mensaje: str) -> None:
    print(f"{_C['bold']}» {mensaje}{_C['reset']}")
    print(f"{_C['dim']}── TOOLS OFF (camino actual) ──{_C['reset']}")
    _mostrar_resultado(_run(mensaje, [], usar_tools=False))
    print(f"{_C['dim']}── TOOLS ON (M-01) ──{_C['reset']}")
    _mostrar_resultado(_run(mensaje, [], usar_tools=True))


def _modo_batch(ruta: str, usar_tools: bool) -> None:
    p = pathlib.Path(ruta)
    if not p.exists():
        print(f"❌ No existe el archivo de casos: {ruta}")
        sys.exit(1)
    casos = [
        l.strip() for l in p.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    etiqueta = "TOOLS ON" if usar_tools else "TOOLS OFF"
    print(f"{_C['bold']}Batch: {len(casos)} casos [{etiqueta}]{_C['reset']}\n")
    for i, caso in enumerate(casos, 1):
        print(f"{_C['bold']}[{i}/{len(casos)}] » {caso}{_C['reset']}")
        try:
            _mostrar_resultado(_run(caso, [], usar_tools))
        except Exception as e:
            print(f"  {_C['red']}ERROR: {e}{_C['reset']}")
        print()


def _modo_repl(usar_tools: bool) -> None:
    etiqueta = "TOOLS ON" if usar_tools else "TOOLS OFF"
    print(f"{_C['bold']}REPL del bot [{etiqueta}]{_C['reset']} — mantiene historial. "
          f"Ctrl+C o 'salir' para terminar.\n")
    historial: list = []
    while True:
        try:
            msg = input(f"{_C['cyan']}vendedor> {_C['reset']}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg or msg.lower() in ("salir", "exit", "quit"):
            break
        try:
            raw = _run(msg, historial, usar_tools)
        except Exception as e:
            print(f"  {_C['red']}ERROR: {e}{_C['reset']}")
            continue
        _mostrar_resultado(raw)
        # Mantener historial como en producción (texto sin tags como respuesta).
        historial.append({"role": "user", "content": f"Test: {msg}"})
        historial.append({"role": "assistant", "content": _texto_sin_tags(raw)})
        print()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main() -> None:
    # La consola de Windows suele ser cp1252; forzar UTF-8 para acentos/emojis/•/×.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Harness de prueba del chatbot (sin Telegram, sin escribir BD).")
    ap.add_argument("mensaje", nargs="?", help="Mensaje a probar. Sin argumento → REPL interactivo.")
    ap.add_argument("--batch", metavar="ARCHIVO", help="Procesa un archivo de casos (uno por línea).")
    ap.add_argument("--diff", action="store_true", help="Compara TOOLS OFF vs ON para el mensaje.")
    grupo = ap.add_mutually_exclusive_group()
    grupo.add_argument("--tools", action="store_true", help="Forzar tool-calling ON (default).")
    grupo.add_argument("--no-tools", action="store_true", help="Forzar camino de tags actual.")
    args = ap.parse_args()

    # Tras parsear (así --help funciona sin claves): cargar .env y verificar.
    _cargar_env()
    _verificar_claves()

    # Inicializar el pool de la BD (no se auto-inicializa al importar db; en
    # producción lo hace api.py al arrancar). Sin esto el catálogo llega vacío.
    import db as _db
    if not _db.init_db():
        print(f"{_C['red']}⚠️ No conecté a la BD — el catálogo llegará vacío. "
              f"Revisá DATABASE_URL en .env.{_C['reset']}")
        sys.exit(1)

    usar_tools = not args.no_tools  # default ON salvo --no-tools

    if args.diff and args.mensaje:
        _modo_diff(args.mensaje)
    elif args.batch:
        _modo_batch(args.batch, usar_tools)
    elif args.mensaje:
        _modo_single(args.mensaje, usar_tools)
    else:
        _modo_repl(usar_tools)


if __name__ == "__main__":
    main()

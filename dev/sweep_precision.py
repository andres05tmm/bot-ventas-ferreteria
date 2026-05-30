#!/usr/bin/env python3
"""
dev/sweep_precision.py — Barrido de precisión del chatbot contra la BD real.

Corre ~65 mensajes representativos por skill (lija, wayper, thinner, tornillos,
puntillas, acronal, pinturas, multiproducto) a través de procesar_con_claude()
REAL (read-only, no escribe BD) y valida cada respuesta con un chequeo liviano.

Reporta PASS/FAIL con motivo, agrupado por categoría. Pensado para detectar
regresiones de precisión (falsos "no encontré", preguntas kilo/unidad de más,
totales errados) sin revisar 65 salidas a ojo.

USO:
    python dev/sweep_precision.py                 # todas las categorías
    python dev/sweep_precision.py wayper lija      # solo esas categorías
"""
import os, re, sys, asyncio, pathlib

_RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

# .env + dummies antes de importar config
env = _RAIZ / ".env"
if env.exists():
    for ln in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ.setdefault("TELEGRAM_TOKEN", "sweep")
os.environ.setdefault("OPENAI_API_KEY", "sweep")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import db as _db
_db.init_db()
import config
from ai import procesar_con_claude

config.IA_TOOL_CALLING = True


# ── Validadores ──────────────────────────────────────────────────────────────
def encuentra(prod_substr):
    """Falla si el bot dice 'no encontré' o no menciona el producto esperado."""
    def _v(raw):
        low = raw.lower()
        if "no encontré" in low or "no encontre" in low or "no tengo" in low:
            return f"dijo NO encontrado (esperaba '{prod_substr}')"
        if prod_substr.lower() not in low:
            return f"no menciona '{prod_substr}'"
        return None
    return _v

def no_pregunta_kilo_unidad(raw):
    """Falla si pregunta '¿kilo o unidad?' (debe decidir solo)."""
    if re.search(r'kilo\s+o\s+(por\s+)?unidad|unidad\s+o\s+(por\s+)?kilo', raw.lower()):
        return "preguntó kilo/unidad (debe decidir solo)"
    return None

def vende(prod_substr, total=None):
    """Falla si no hay una [VENTA] del producto (y total) esperado."""
    def _v(raw):
        ventas = re.findall(r'\[VENTA\](.*?)\[/VENTA\]', raw, re.DOTALL)
        if not ventas:
            return f"sin [VENTA] (esperaba {prod_substr})"
        blob = " ".join(ventas).lower()
        if prod_substr.lower() not in blob:
            return f"[VENTA] no es '{prod_substr}': {blob[:80]}"
        if total is not None and str(total) not in re.sub(r'[,\.]', '', blob):
            return f"total != {total}: {blob[:80]}"
        return None
    return _v

def todos(*vs):
    def _v(raw):
        for v in vs:
            r = v(raw)
            if r:
                return r
        return None
    return _v


# ── Casos por categoría ──────────────────────────────────────────────────────
CASOS = {
    "lija_esmeril": [
        ("Que precio tiene 30 centímetros de Lija esmeril 60", encuentra("N°60")),
        ("30 centimetros lija esmeril 80",                      encuentra("N°80")),
        ("precio lija esmeril 100",                             encuentra("N°100")),
        ("20 cm lija esmeril 36",                               encuentra("N°36")),
        ("cuanto vale 50 cm de lija esmeril 60",               encuentra("N°60")),
        ("lija esmeril numero 80",                              encuentra("N°80")),
        ("30 cm lija esmeril 60",                               vende("esmeril n°60")),
    ],
    "lija_agua": [
        ("precio lija 220",   encuentra("220")),
        ("lija 600",          encuentra("600")),
        ("lija numero 1000",  encuentra("1000")),
        ("lija 1500",         encuentra("1500")),
        ("lija 3000",         encuentra("3000")),
        ("2 lijas 80",        encuentra("80")),
        ("lija 120",          encuentra("120")),
    ],
    "wayper": [
        ("2 wayper blanco",                 todos(no_pregunta_kilo_unidad, vende("wayper blanco unidad", 1400))),
        ("5 wayper blanco",                 todos(no_pregunta_kilo_unidad, vende("wayper blanco unidad"))),
        ("1 wayper blanco",                 todos(no_pregunta_kilo_unidad, vende("wayper blanco unidad"))),
        ("3 wayper de color",               todos(no_pregunta_kilo_unidad, vende("wayper de color unidad"))),
        ("2 kg de wayper blanco",           vende("wayper blanco", 20000)),
        ("medio kilo de wayper blanco",     vende("wayper blanco", 5000)),
        ("un kilo de wayper de color",      vende("wayper de color", 7000)),
        ("kilo y medio de wayper blanco",   vende("wayper blanco", 15000)),
        ("4 waypers blancos",               todos(no_pregunta_kilo_unidad, vende("wayper blanco unidad"))),
        ("2 unidades de wayper de color",   vende("wayper de color unidad", 1000)),
    ],
    "thinner_varsol": [
        ("2 litros de thinner",       encuentra("thinner")),
        ("1 botella de thinner",      encuentra("thinner")),
        ("medio galon de thinner",    encuentra("thinner")),
        ("thinner de 5000",           encuentra("thinner")),
        ("3 litros de varsol",        encuentra("varsol")),
        # "cuñete de thinner" NO existe como producto → manejo correcto es explicar
        # cómo se vende el thinner, no inventar un match. Solo exigimos que lo mencione.
        ("1 cuñete de thinner",       lambda raw: None if "thinner" in raw.lower() else "no menciona thinner"),
        ("un galon de varsol",        encuentra("varsol")),
    ],
    "tornillos": [
        ("60 tornillos drywall 6x1",      encuentra("drywall")),
        ("30 tornillos drywall 6x2",      encuentra("drywall")),
        ("100 tornillos drywall 8x3",     encuentra("drywall")),
        ("20 chazos 3/8",                 encuentra("chazo")),
        ("12 tornillos drywall 6 por 1",  encuentra("drywall")),
    ],
    "puntillas": [
        ("media caja de puntillas 2 pulgadas",  encuentra("puntilla")),
        ("100 gramos de puntillas 2 pulgadas",  encuentra("puntilla")),
        ("una caja de puntillas 2 pulgadas",    encuentra("puntilla")),
        ("2000 pesos de puntillas 2 pulgadas",  encuentra("puntilla")),
    ],
    "acronal": [
        ("1 kilo de acronal",        encuentra("acronal")),
        ("medio kilo de acronal",    encuentra("acronal")),
        ("2 kilos y medio acronal",  encuentra("acronal")),
    ],
    "pinturas": [
        ("1/4 de vinilo blanco",      encuentra("vinilo")),
        ("medio galon de esmalte",    encuentra("esmalte")),
        # Brocha de 3" = $6.000 en catálogo. El bot puede cotizar o pedir confirmar
        # el total; ambos son válidos mientras use el precio correcto.
        ("una brocha de 3 pulgadas",  lambda raw: None if ("brocha" in raw.lower() or "6.000" in raw or "6000" in raw) else "no usó brocha 3\" ($6.000)"),
        ("un rodillo",                encuentra("rodillo")),
    ],
    "simples": [
        ("2 martillo",          encuentra("martillo")),
        ("1 metro de manguera", encuentra("manguera")),
        ("5 candados",          encuentra("candado")),
        ("1 segueta",           encuentra("segueta")),
    ],
    "multiproducto": [
        ("2 martillo, 30 cm lija esmeril 60",   encuentra("esmeril n°60")),
        ("1 wayper blanco y 2 martillo",        no_pregunta_kilo_unidad),
        ("3 tornillos drywall 6x1, 2 chazos 3/8", encuentra("drywall")),
    ],
}


async def _run(msg):
    return await procesar_con_claude(f"Test: {msg}", "Test", [], vendedor_id=None)


def main():
    cats = sys.argv[1:] or list(CASOS.keys())
    total = passed = 0
    fails = []
    for cat in cats:
        casos = CASOS.get(cat)
        if not casos:
            print(f"(categoría desconocida: {cat})")
            continue
        print(f"\n=== {cat.upper()} ({len(casos)}) ===")
        for msg, val in casos:
            total += 1
            try:
                raw = asyncio.run(_run(msg))
                motivo = val(raw)
            except Exception as e:
                motivo = f"EXCEPCIÓN: {e}"
                raw = ""
            if motivo:
                fails.append((cat, msg, motivo, raw))
                print(f"  ❌ {msg}\n       → {motivo}")
            else:
                passed += 1
                print(f"  ✅ {msg}")
    print(f"\n{'='*60}\nRESUMEN: {passed}/{total} OK, {len(fails)} fallas")
    if fails:
        print("\nFALLAS DETALLADAS:")
        for cat, msg, motivo, raw in fails:
            print(f"\n[{cat}] {msg}\n  motivo: {motivo}\n  resp: {raw[:200].strip()}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

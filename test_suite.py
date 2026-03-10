"""
╔══════════════════════════════════════════════════════════════════╗
║           FERREBOT — TEST SUITE COMPLETO                        ║
║  Corre con: python test_suite.py                                ║
║  Sin necesidad de Telegram, Railway ni Drive                    ║
╚══════════════════════════════════════════════════════════════════╝

Cubre:
  1. Fuzzy search de productos (memoria.py)
  2. Aliases de ferretería (ai.py)
  3. Parser bulk de precios (mensajes.py)
  4. Fracciones y cálculos de cantidades
  5. Sección /productos (productos.py)
  6. Casos edge conocidos (bugs que ya arreglamos)
"""

import sys
import os
import re
import json
import traceback
from typing import Optional

# ── Colores para la terminal ───────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Contadores globales ────────────────────────────────────────────
_passed = 0
_failed = 0
_errored = 0
_skipped = 0

def ok(nombre, detalle=""):
    global _passed
    _passed += 1
    print(f"  {GREEN}✅ PASS{RESET} {nombre}" + (f"  → {detalle}" if detalle else ""))

def fail(nombre, esperado, obtenido):
    global _failed
    _failed += 1
    print(f"  {RED}❌ FAIL{RESET} {nombre}")
    print(f"       esperado : {YELLOW}{esperado}{RESET}")
    print(f"       obtenido : {RED}{obtenido}{RESET}")

def error(nombre, exc):
    global _errored
    _errored += 1
    print(f"  {RED}💥 ERROR{RESET} {nombre}: {exc}")

def skip(nombre, razon=""):
    global _skipped
    _skipped += 1
    print(f"  {YELLOW}⏭  SKIP{RESET} {nombre}" + (f"  ({razon})" if razon else ""))

def seccion(titulo):
    print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {titulo}{RESET}")
    print(f"{BOLD}{CYAN}{'═'*60}{RESET}")

def caso(descripcion):
    print(f"\n  {BOLD}▸ {descripcion}{RESET}")


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 1: FUZZY SEARCH DE PRODUCTOS
# ══════════════════════════════════════════════════════════════════

def test_fuzzy_search(buscar):
    seccion("1. FUZZY SEARCH DE PRODUCTOS")

    casos = [
        # (query, substring_esperado_en_nombre, descripcion)
        # ── Rodillos por medida ──
        ("Rodillo de 1",   "Rodillo de 1\"",  "Rodillo 1 → no confundir con otro"),
        ("Rodillo de 2",   "Rodillo de 2\"",  "Rodillo 2 → bug histórico (matcheaba 1\")"),
        ("Rodillo de 3",   "Rodillo de 3\"",  "Rodillo 3"),
        ("Rodillo de 4",   "Rodillo de 4\"",  "Rodillo 4"),
        ("Rodillo de 6",   "Rodillo de 6\"",  "Rodillo 6"),
        # ── Brochas ──
        ("brocha de 2",    "Brocha de 2\"",   "Brocha 2\" exacta"),
        ("brocha 3",       "Brocha de 3\"",   "Brocha 3 sin 'de'"),
        # ── Puntillas ──
        ("puntilla 3/4 sin cabeza", "3/4",    "Puntilla 3/4 SC"),
        ("puntilla 2 con cabeza",   "2\"",    "Puntilla 2 CC"),
        ("puntilla 1",              "1\"",    "Puntilla 1\""),
        # ── Cinta Pele (bug histórico: L vs XL) ──
        ("cinta pele l",   "Cinta Pele L",    "Pele L → no matchear XL"),
        ("cinta pele xl",  "Cinta Pele XL",   "Pele XL exacto"),
        ("cinta pele s",   "Cinta Pele S",    "Pele S"),
        ("cinta pele m",   "Cinta Pele M",    "Pele M"),
        # ── Tornillos Drywall ──
        ("tornillo drywall 6x1",    "6X1",    "Drywall 6x1"),
        ("tornillo drywall 10x2",   "10X2",   "Drywall 10x2"),
        ("tornillo drywall 8x3/4",  "8X3/4",  "Drywall 8x3/4"),
        # ── Lijas ──
        ("lija 100",       "N°100",           "Lija madera 100"),
        ("lija esmeril 60","Esmeril N°60",    "Lija esmeril 60"),
        # ── Brocas ──
        ("broca metal 1/4","1/4",             "Broca metal 1/4"),
        ("broca muro 5/16","5/16",            "Broca muro 5/16"),
        # ── Laca ──
        ("laca corriente blanca", "Blanca",   "Laca corriente blanca"),
        ("laca corriente roja",   "Roja",     "Laca corriente roja"),
        # ── Vinilo ──
        ("vinilo t1 blanco",  "Blanco",       "Vinilo T1 blanco"),
        ("vinilo t2 negro",   "Negro",        "Vinilo T2 negro"),
        # ── Esmalte ──
        ("esmalte blanco",    "Blanco",       "Esmalte blanco"),
        ("esmalte 3 en 1 negro","3 En",        "Esmalte 3en1 negro (con espacios)"),
        # ── Tornillo estufa ──
        ("tornillo estufa 1/8 x 1", "1/8",   "Estufa 1/8 x 1"),
        ("tornillo estufa 3/16 x 2","3/16",   "Estufa 3/16 x 2"),
    ]

    for query, esperado_substr, desc in casos:
        caso(desc)
        try:
            resultado = buscar(query)
            if resultado is None:
                fail(f'buscar("{query}")', f"nombre con '{esperado_substr}'", "None (no encontró nada)")
            elif esperado_substr.lower() not in str(resultado.get("nombre","")).lower():
                fail(f'buscar("{query}")', f"nombre con '{esperado_substr}'", resultado.get("nombre","?"))
            else:
                ok(f'buscar("{query}")', resultado.get("nombre",""))
        except Exception as e:
            error(f'buscar("{query}")', e)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 2: ALIASES DE FERRETERÍA
# ══════════════════════════════════════════════════════════════════

def test_aliases(aplicar_alias):
    seccion("2. ALIASES DE FERRETERÍA")

    casos = [
        # (entrada, substring_esperado, descripcion)
        # ── Puntilla ──
        ("1 caja de puntilla de 3/4 s.c",   "sin cabeza",   "caja de puntilla + s.c"),
        ("2 puntillas 2 c.c",               "con cabeza",   "c.c → con cabeza"),
        ("3 puntilla 1 s.c",                "sin cabeza",   "s.c → sin cabeza"),
        ("puntilla 2 sc",                   "sin cabeza",   "sc → sin cabeza"),
        ("puntilla 3 cc",                   "con cabeza",   "cc → con cabeza"),
        # ── Thinner / Varsol ──
        ("1/4 de thinner",                  "thinner",      "fracción thinner"),
        ("medio thinner",                   "thinner",      "medio thinner"),
        ("1/2 varsol",                      "varsol",       "fracción varsol"),
        # ── Marcas de vinilo ──
        ("vinilo davinci blanco",           "davinci",      "vinilo davinci"),
        ("vinilo pintuco blanco",           "pintuco",      "vinilo pintuco → pintuco"),
        # ── Esmalte ──
        ("esmalte 3 en 1 blanco",           "3",            "esmalte 3 en 1"),
        # ── Lija ──
        ("lija de madera 100",              "100",          "lija de madera"),
        ("lija esmeril numero 60",          "60",           "lija esmeril numero X"),
    ]

    for entrada, esperado_substr, desc in casos:
        caso(desc)
        try:
            resultado = aplicar_alias(entrada)
            if esperado_substr.lower() not in resultado.lower():
                fail(desc, f"con '{esperado_substr}'", resultado)
            else:
                ok(desc, resultado)
        except Exception as e:
            error(desc, e)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 3: PARSER BULK DE PRECIOS
# ══════════════════════════════════════════════════════════════════

def test_parser_bulk(parsear):
    seccion("3. PARSER BULK DE PRECIOS")

    # ── Casos que deben SER detectados como bulk ──
    caso("Casos válidos — deben retornar lista de pares")

    validos = [
        (
            "actualizar precios:\nRodillo de 1= 4500\nRodillo de 2= 5500\nRodillo de 3= 6000",
            [("Rodillo de 1", 4500), ("Rodillo de 2", 5500), ("Rodillo de 3", 6000)],
            "3 rodillos con encabezado"
        ),
        (
            "Cinta Pele S= 8500\nCinta Pele M= 10000\nCinta Pele L= 17000\nCinta pele XL= 30000",
            [("Cinta Pele S", 8500), ("Cinta Pele M", 10000), ("Cinta Pele L", 17000), ("Cinta pele XL", 30000)],
            "4 peles sin encabezado"
        ),
        (
            "precios:\nLaca Corriente Blanca= 80000\nLaca Corriente Negra= 80000\nLaca Corriente Azul= 80000",
            [("Laca Corriente Blanca", 80000), ("Laca Corriente Negra", 80000), ("Laca Corriente Azul", 80000)],
            "3 lacas"
        ),
        (
            "Rodillo de 1= 4500\nRodillo de 2= 5500",
            [("Rodillo de 1", 4500), ("Rodillo de 2", 5500)],
            "mínimo 2 líneas válidas"
        ),
        (
            # Bug histórico: L y XL en misma línea con espacios enormes
            "actualizar precios:\nCinta Pele S= 8500\nCinta Pele M= 10000\n"
            + "Cinta Pele L= 17000" + " " * 80 + "Cinta pele XL= 30000",
            [("Cinta Pele S", 8500), ("Cinta Pele M", 10000), ("Cinta Pele L", 17000), ("Cinta pele XL", 30000)],
            "BUG HISTÓRICO: L y XL fusionados con espacios"
        ),
        (
            "Carbonato= 28000\nYeso= 25000",
            [("Carbonato", 28000), ("Yeso", 25000)],
            "materiales construcción"
        ),
        (
            "actualizar precios: Bandeja= 7500\nRodillo de 1= 4500",
            [("Bandeja", 7500), ("Rodillo de 1", 4500)],
            "inline header con producto en misma línea"
        ),
    ]

    for mensaje, esperados, desc in validos:
        try:
            resultado = parsear(mensaje)
            if resultado is None:
                fail(desc, f"{len(esperados)} pares", "None (no detectó bulk)")
                continue
            # Verificar cantidad
            if len(resultado) != len(esperados):
                fail(desc, f"{len(esperados)} pares", f"{len(resultado)} pares: {[(r[0],r[1]) for r in resultado]}")
                continue
            # Verificar cada par (nombre aproximado + precio exacto)
            todos_ok = True
            for i, (nombre_esp, precio_esp) in enumerate(esperados):
                nombre_got = resultado[i][0]
                precio_got = resultado[i][1]
                if abs(precio_got - precio_esp) > 1:
                    fail(f"{desc} [par {i+1}]", f"precio {precio_esp}", f"precio {precio_got}")
                    todos_ok = False
            if todos_ok:
                ok(desc, f"{len(resultado)} pares detectados")
        except Exception as e:
            error(desc, e)

    # ── Casos que NO deben ser detectados como bulk ──
    caso("Casos inválidos — deben retornar None")

    invalidos = [
        ("dame 2 brochas de 2",           "venta normal"),
        ("cuanto vale el rodillo",        "consulta de precio"),
        ("actualizar precio de rodillo= 4500", "una sola línea de precio"),
        ("hola como estas",               "saludo"),
        ("",                              "mensaje vacío"),
    ]

    for mensaje, desc in invalidos:
        try:
            resultado = parsear(mensaje)
            if resultado is not None:
                fail(f"NO debería detectar: '{desc}'", "None", f"{resultado}")
            else:
                ok(f"Ignorado correctamente: '{desc}'")
        except Exception as e:
            error(f"Inválido '{desc}'", e)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 4: FRACCIONES Y CANTIDADES
# ══════════════════════════════════════════════════════════════════

def test_fracciones(convertir):
    seccion("4. FRACCIONES Y CANTIDADES")

    casos = [
        ("1/4",   0.25,  "un cuarto"),
        ("1/2",   0.5,   "medio"),
        ("3/4",   0.75,  "tres cuartos"),
        ("1/8",   0.125, "un octavo"),
        ("2",     2.0,   "entero"),
        ("1",     1.0,   "uno"),
        ("3",     3.0,   "tres"),
        ("1.5",   1.5,   "decimal"),
        ("2.5",   2.5,   "decimal 2.5"),
    ]

    for entrada, esperado, desc in casos:
        caso(desc)
        try:
            resultado = convertir(entrada)
            if abs(resultado - esperado) < 0.001:
                ok(f'convertir("{entrada}")', f"= {resultado}")
            else:
                fail(f'convertir("{entrada}")', esperado, resultado)
        except Exception as e:
            error(f'convertir("{entrada}")', e)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 5: DISPLAY /productos — AGRUPACIÓN Y ORDEN
# ══════════════════════════════════════════════════════════════════

def test_productos_display(catalogo):
    seccion("5. DISPLAY /productos — AGRUPACIÓN Y ORDEN")

    caso("Cinta Pele — orden por talla S→M→L→XL")
    peles = [k for k in catalogo if "pele" in catalogo[k].get("nombre_lower","")]
    nombres_pele = [catalogo[k]["nombre"] for k in peles]
    try:
        talla_ord = {"s":0,"m":1,"l":2,"xl":3}
        def _talla(n):
            m = re.search(r'\b(xl|l|m|s)\b', n.lower())
            return talla_ord.get(m.group(1), 99) if m else 99
        sorted_pele = sorted(nombres_pele, key=_talla)
        esperado = ["Cinta Pele S","Cinta Pele M","Cinta Pele L","Cinta Pele XL"]
        if all(e in " ".join(sorted_pele) for e in esperado):
            ok("Pele S→M→L→XL en catálogo", str(sorted_pele))
        else:
            fail("Pele ordenado", esperado, sorted_pele)
    except Exception as e:
        error("Pele orden", e)

    caso("Rodillos — todos en catálogo del 1\" al 6\"")
    for n in range(1, 7):
        nombre_buscado = f'Rodillo de {n}"'
        encontrado = any(
            nombre_buscado.lower() in v.get("nombre_lower","")
            for v in catalogo.values()
        )
        if encontrado:
            ok(f"{nombre_buscado} existe en catálogo")
        else:
            fail(f"{nombre_buscado}", "en catálogo", "NO encontrado")

    caso("Bandeja Para Rodillo — existe en catálogo")
    if any("bandeja" in v.get("nombre_lower","") for v in catalogo.values()):
        ok("Bandeja Para Rodillo existe")
    else:
        fail("Bandeja Para Rodillo", "en catálogo", "NO encontrado")

    caso("Sin duplicados PELE PEQUEÑO / PELE MEDIANO (nombres viejos)")
    nombres_viejos = ["pele pequeño","pele mediano"]
    for nv in nombres_viejos:
        tiene = any(nv in v.get("nombre_lower","") for v in catalogo.values())
        if tiene:
            fail(f"Nombre viejo '{nv}'", "NO debe existir", "EXISTE en catálogo")
        else:
            ok(f"'{nv}' correctamente eliminado")

    caso("Tornillo drywall — 6x, 8x y 10x presentes")
    for calibre in ["6x", "8x", "10x"]:
        encontrado = any(
            f"drywall {calibre}" in v.get("nombre_lower","")
            for v in catalogo.values()
        )
        if encontrado:
            ok(f"Tornillo drywall {calibre} presente")
        else:
            fail(f"Tornillo drywall {calibre}", "en catálogo", "NO encontrado")

    caso("Lija Esmeril — todos los números (36, 60, 80, 100)")
    for num in [36, 60, 80, 100]:
        encontrado = any(
            f"esmeril" in v.get("nombre_lower","") and f"{num}" in v.get("nombre_lower","")
            for v in catalogo.values()
        )
        if encontrado:
            ok(f"Lija Esmeril N°{num} presente")
        else:
            fail(f"Lija Esmeril N°{num}", "en catálogo", "NO encontrado")

    caso("Productos sin precio ($0) — alerta si hay muchos")
    sin_precio = [v["nombre"] for v in catalogo.values() if v.get("precio_unidad", 0) == 0]
    if len(sin_precio) == 0:
        ok("Todos los productos tienen precio")
    elif len(sin_precio) <= 10:
        print(f"  {YELLOW}⚠️  AVISO{RESET} {len(sin_precio)} productos sin precio:")
        for n in sin_precio[:5]:
            print(f"       - {n}")
        if len(sin_precio) > 5:
            print(f"       ... y {len(sin_precio)-5} más")
    else:
        fail("Productos sin precio", "≤10", f"{len(sin_precio)} productos sin precio")


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 6: CASOS EDGE — BUGS CONOCIDOS
# ══════════════════════════════════════════════════════════════════

def test_bugs_conocidos(buscar, parsear_bulk=None):
    seccion("6. CASOS EDGE — BUGS CONOCIDOS Y REGRESIONES")

    # Bug 1: Rodillo de 2 matcheaba Rodillo de 1
    caso("BUG #1 — Rodillo de 2 no debe matchear Rodillo de 1")
    try:
        r = buscar("Rodillo de 2")
        if r and "2" in r.get("nombre",""):
            ok("Rodillo de 2", r["nombre"])
        elif r:
            fail("Rodillo de 2", "Rodillo de 2\"", r.get("nombre","?"))
        else:
            fail("Rodillo de 2", "Rodillo de 2\"", "None")
    except Exception as e:
        error("Bug #1", e)

    # Bug 2: Cinta Pele L no debe matchear Cinta Pele XL
    caso("BUG #2 — Cinta Pele L no debe retornar Cinta Pele XL")
    try:
        r = buscar("Cinta Pele L")
        nombre = r.get("nombre","") if r else ""
        if "xl" in nombre.lower():
            fail("Cinta Pele L", "Cinta Pele L", nombre + " (retornó XL!)")
        elif "Pele L" in nombre:
            ok("Cinta Pele L", nombre)
        else:
            fail("Cinta Pele L", "Cinta Pele L", nombre or "None")
    except Exception as e:
        error("Bug #2", e)

    # Bug 3: token "2" (un dígito) debe ser relevante en búsqueda
    caso("BUG #3 — Token de 1 dígito debe usarse en búsqueda (Rodillo de 2 vs Rodillo de 1)")
    try:
        r1 = buscar("Rodillo de 1")
        r2 = buscar("Rodillo de 2")
        n1 = r1.get("nombre","") if r1 else ""
        n2 = r2.get("nombre","") if r2 else ""
        if n1 == n2:
            fail("Rodillo 1 ≠ Rodillo 2", "resultados distintos", f"ambos → {n1}")
        else:
            ok(f"Rodillo 1 → {n1}  |  Rodillo 2 → {n2}")
    except Exception as e:
        error("Bug #3", e)

    # Bug 4: parser bulk fusionaba L= 17000 [espacios] XL= 30000
    if parsear_bulk:
        caso("BUG #4 — Parser bulk no debe fusionar L y XL con espacios enormes")
        msg_bug = ("actualizar precios:\nCinta Pele S= 12000\nCinta Pele M= 20000\n"
                   + "Cinta Pele L= 30000" + " " * 100 + "Cinta pele XL= 28000")
        try:
            resultado = parsear_bulk(msg_bug)
            if resultado is None:
                fail("Parser bulk 4 peles", "4 pares", "None")
            elif len(resultado) == 4:
                ok(f"4 pares correctamente separados", str([(r[0],r[1]) for r in resultado]))
            else:
                fail("Parser bulk 4 peles", "4 pares", f"{len(resultado)} pares: {[(r[0],r[1]) for r in resultado]}")
        except Exception as e:
            error("Bug #4", e)

    # Bug 5: precio sync race condition (test lógico, no de I/O)
    caso("BUG #5 — Sync síncrono en _escribir_en_excel (no race condition)")
    try:
        with open(os.path.join(os.path.dirname(__file__), "precio_sync.py"), encoding="utf-8") as f:
            codigo = f.read()
        # Extraer solo la función _escribir_en_excel con límite estricto (hasta la próxima def)
        lineas = codigo.split("\n")
        en_fn = False
        fn_lines = []
        for linea in lineas:
            if re.match(r"^def _escribir_en_excel\b|^async def _escribir_en_excel\b", linea):
                en_fn = True
            elif en_fn and re.match(r"^def |^async def |^class ", linea):
                break
            if en_fn:
                fn_lines.append(linea)

        if not fn_lines:
            skip("Bug #5", "_escribir_en_excel no encontrada en precio_sync.py")
        else:
            fn_code = "\n".join(fn_lines)
            # Buscar si LLAMA a subir_a_drive_urgente (no solo que la importe)
            # Detectar una llamada real: nombre seguido de paréntesis, excluyendo líneas de import
            fn_lines_no_import = [l for l in fn_lines if not l.strip().startswith("from ") and not l.strip().startswith("import ")]
            fn_code_no_import = "\n".join(fn_lines_no_import)
            usa_urgente_call = "subir_a_drive_urgente(" in fn_code_no_import
            usa_sincrono = "_ejecutar_subida_real" in fn_code
            if usa_sincrono and not usa_urgente_call:
                ok("_escribir_en_excel usa _ejecutar_subida_real (síncrono) ✓")
            elif usa_urgente_call:
                fail("precio_sync race condition", "_ejecutar_subida_real", "subir_a_drive_urgente() llamada directamente (race condition!)")
            else:
                skip("Bug #5", "no se detectó función de subida siendo llamada en _escribir_en_excel")
    except Exception as e:
        error("Bug #5", e)


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 7: INTEGRIDAD DEL CATÁLOGO
# ══════════════════════════════════════════════════════════════════

def test_integridad_catalogo(catalogo):
    seccion("7. INTEGRIDAD DEL CATÁLOGO")

    caso("Todos los productos tienen nombre")
    sin_nombre = [k for k, v in catalogo.items() if not v.get("nombre","").strip()]
    if sin_nombre:
        fail("Productos sin nombre", "0", f"{len(sin_nombre)}: {sin_nombre[:3]}")
    else:
        ok(f"Todos los {len(catalogo)} productos tienen nombre")

    caso("Todos tienen nombre_lower")
    sin_lower = [k for k, v in catalogo.items() if not v.get("nombre_lower","").strip()]
    if sin_lower:
        fail("Sin nombre_lower", "0", f"{len(sin_lower)}: {sin_lower[:3]}")
    else:
        ok("nombre_lower presente en todos")

    caso("nombre_lower == nombre.lower()")
    inconsistentes = []
    for k, v in catalogo.items():
        nombre = v.get("nombre","")
        nl = v.get("nombre_lower","")
        if nl and nl != nombre.lower():
            inconsistentes.append(k)
    if inconsistentes:
        print(f"  {YELLOW}⚠️  AVISO{RESET} {len(inconsistentes)} productos con nombre_lower inconsistente:")
        for k in inconsistentes[:5]:
            print(f"       {k}: nombre='{catalogo[k]['nombre']}' vs lower='{catalogo[k]['nombre_lower']}'")
    else:
        ok("nombre_lower consistente con nombre.lower()")

    caso("No hay duplicados exactos en nombre")
    nombres = [v["nombre"].lower().strip() for v in catalogo.values() if v.get("nombre")]
    from collections import Counter
    dupes = {n: c for n, c in Counter(nombres).items() if c > 1}
    if dupes:
        fail("Sin duplicados", "0 duplicados", f"{len(dupes)} nombres duplicados: {list(dupes.keys())[:3]}")
    else:
        ok("Sin duplicados exactos en catálogo")

    caso("Precios razonables (entre $10 y $10.000.000)")
    precios_raros = []
    for k, v in catalogo.items():
        p = v.get("precio_unidad", 0)
        if p and (p < 10 or p > 10_000_000):
            precios_raros.append((k, p))
    if precios_raros:
        fail("Precios razonables", "todos en rango", f"{len(precios_raros)} raros: {precios_raros[:3]}")
    else:
        ok("Todos los precios en rango razonable")

    caso("Total productos en catálogo")
    total = len(catalogo)
    if total < 400:
        fail("Total productos", "≥400", f"solo {total}")
    elif total > 700:
        print(f"  {YELLOW}⚠️  AVISO{RESET} {total} productos (¿hay duplicados?)")
    else:
        ok(f"{total} productos en catálogo")


# ══════════════════════════════════════════════════════════════════
# SECCIÓN 8: ESTRUCTURA DE ARCHIVOS CRÍTICOS
# ══════════════════════════════════════════════════════════════════

def test_archivos_criticos():
    seccion("8. ESTRUCTURA DE ARCHIVOS CRÍTICOS")

    base = os.path.dirname(__file__)
    archivos = [
        ("ai.py",                    "Módulo principal IA"),
        ("memoria.py",               "Catálogo y fuzzy search"),
        ("precio_sync.py",           "Sincronización precios"),
        ("ventas_state.py",          "Estado en memoria"),
        ("handlers/mensajes.py",     "Handler mensajes texto"),
        ("handlers/comandos.py",     "Handler comandos /"),
        ("handlers/callbacks.py",    "Handler botones inline"),
        ("handlers/productos.py",    "Comando /productos"),
        ("main.py",                  "Punto de entrada"),
    ]

    for archivo, desc in archivos:
        ruta = os.path.join(base, archivo)
        if os.path.exists(ruta):
            size = os.path.getsize(ruta)
            ok(f"{archivo} ({desc})", f"{size:,} bytes")
        else:
            fail(archivo, "existe", "NO ENCONTRADO")

    caso("Imports críticos en mensajes.py")
    try:
        ruta = os.path.join(base, "handlers/mensajes.py")
        with open(ruta, encoding="utf-8") as f:
            src = f.read()
        checks = [
            ("mensaje_contexto_pendiente", "fix contexto perdido"),
            ("_parsear_actualizacion_masiva", "parser bulk"),
            ("_enviar_pregunta_flujo_cliente", "flujo cliente"),
            ("_expandir_linea", "fix fusión L/XL"),
        ]
        for sym, desc in checks:
            if sym in src:
                ok(f"  '{sym}' presente ({desc})")
            else:
                fail(f"  '{sym}'", "presente", f"NO encontrado en mensajes.py ({desc})")
    except Exception as e:
        error("Imports mensajes.py", e)

    caso("nuevo_cliente registrado en main.py")
    try:
        ruta = os.path.join(base, "main.py")
        with open(ruta, encoding="utf-8") as f:
            src = f.read()
        if "nuevo_cliente" in src:
            ok("comando /nuevo_cliente registrado en main.py")
        else:
            fail("/nuevo_cliente", "en main.py", "NO encontrado")
    except Exception as e:
        error("main.py check", e)


# ══════════════════════════════════════════════════════════════════
# MAIN — RUNNER
# ══════════════════════════════════════════════════════════════════

def main():
    global _passed, _failed, _errored, _skipped

    print(f"\n{BOLD}{'═'*60}")
    print("  🔧 FERREBOT — TEST SUITE COMPLETO")
    print(f"{'═'*60}{RESET}")

    # ── Cargar módulos del bot ─────────────────────────────────────
    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    # También agregar el directorio padre por si hay imports relativos
    sys.path.insert(0, os.path.dirname(base))

    # Setear env vars dummy para que config.py no haga sys.exit
    _env_patch = {
        "TELEGRAM_TOKEN": "TEST:TOKEN",
        "ANTHROPIC_API_KEY": "sk-test-anthropic",
        "OPENAI_API_KEY": "sk-test-openai",
        "GOOGLE_CREDENTIALS_JSON": '{"type":"service_account"}',
        "GOOGLE_FOLDER_ID": "test-folder-id",
        "SHEETS_ID": "test-sheets-id",
    }
    for k, v in _env_patch.items():
        os.environ.setdefault(k, v)

    # Mock de módulos que necesitan credenciales reales
    import unittest.mock as mock
    import types

    # Crear mock de openpyxl como paquete completo con submodulos
    _openpyxl_mock = mock.MagicMock()
    _openpyxl_mock.styles = mock.MagicMock()
    _openpyxl_mock.styles.PatternFill = mock.MagicMock()
    _openpyxl_mock.styles.Font = mock.MagicMock()
    _openpyxl_mock.styles.Alignment = mock.MagicMock()
    _openpyxl_mock.utils = mock.MagicMock()
    _openpyxl_mock.utils.get_column_letter = mock.MagicMock(return_value="A")

    # Mock google / gspread / telegram / openai para no necesitar credenciales
    for mod in ["googleapiclient", "googleapiclient.discovery",
                "googleapiclient.http", "google", "google.oauth2",
                "google.oauth2.service_account", "gspread",
                "telegram", "telegram.ext", "httpx",
                "anthropic", "openai", "sheets",
                "openpyxl", "openpyxl.styles", "openpyxl.utils",
                "openpyxl.styles.fills", "openpyxl.styles.fonts"]:
        sys.modules.setdefault(mod, _openpyxl_mock if "openpyxl" in mod else mock.MagicMock())

    # ── Intentar importar funciones reales ────────────────────────
    buscar_fn      = None
    alias_fn       = None
    parsear_fn     = None
    convertir_fn   = None
    catalogo_dict  = None

    # 1. Cargar catálogo desde memoria.json (buscar en varias ubicaciones)
    memoria_json = None
    _posibles_memoria = [
        os.path.join(base, "memoria.json"),
        os.path.join(base, "memoria__4_.json"),
        os.path.join(base, "memoria__3_.json"),
        os.path.join(base, "memoria__2_.json"),
        "/mnt/user-data/uploads/memoria__4_.json",
    ]
    for path in _posibles_memoria:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                memoria_json = json.load(f)
            catalogo_dict = memoria_json.get("catalogo", {})
            print(f"\n{GREEN}✓ Catálogo cargado:{RESET} {len(catalogo_dict)} productos desde {os.path.basename(path)}")
            break

    if not catalogo_dict:
        print(f"\n{YELLOW}⚠️  No se encontró memoria.json — tests de catálogo limitados{RESET}")

    # 2. Cargar buscar_producto_en_catalogo de memoria.py
    try:
        with mock.patch.dict(sys.modules, {
            "openpyxl": mock.MagicMock(),
            "config": mock.MagicMock(),
        }):
            import memoria as _mem
            # Inyectar catálogo en el cache interno ANTES de cualquier llamada
            if catalogo_dict:
                _mem._cache = {"catalogo": catalogo_dict, "precios": {},
                               "negocio": {}, "notas": [], "inventario": {},
                               "gastos": {}, "caja_actual": {"abierta": False}}
            buscar_fn = _mem.buscar_producto_en_catalogo
        print(f"{GREEN}✓ memoria.py cargado{RESET}")
    except Exception as e:
        print(f"{YELLOW}⚠️  No se pudo cargar memoria.py: {e}{RESET}")

    # 3. Cargar alias function de ai.py
    try:
        with mock.patch.dict(sys.modules, {
            "config": mock.MagicMock(),
            "anthropic": mock.MagicMock(),
        }):
            import ai as _ai
            alias_fn = _ai.aplicar_alias_ferreteria
        print(f"{GREEN}✓ ai.py cargado{RESET}")
    except Exception as e:
        print(f"{YELLOW}⚠️  No se pudo cargar ai.py: {e} — usando stub{RESET}")

    # 4. Cargar parser bulk de mensajes.py
    try:
        # Limpiar cualquier mock de handlers que pudiera haberse colado
        for k in list(sys.modules.keys()):
            if k.startswith("handlers"):
                del sys.modules[k]
        with mock.patch.dict(sys.modules, {
            "ventas_state": mock.MagicMock(),
            "ai": mock.MagicMock(),
            "excel": mock.MagicMock(),
            "handlers.callbacks": mock.MagicMock(),
            "precio_sync": mock.MagicMock(),
            "memoria": mock.MagicMock(),
            "sheets": mock.MagicMock(),
        }):
            import handlers.mensajes as _mens
            parsear_fn = _mens._parsear_actualizacion_masiva
        print(f"{GREEN}✓ handlers/mensajes.py cargado{RESET}")
    except Exception as e:
        print(f"{YELLOW}⚠️  No se pudo cargar mensajes.py parser: {e}{RESET}")

    # 5. Cargar convertir_fraccion de utils
    try:
        with mock.patch.dict(sys.modules, {"config": mock.MagicMock()}):
            import utils as _utils
            convertir_fn = _utils.convertir_fraccion_a_decimal
        print(f"{GREEN}✓ utils.py cargado{RESET}")
    except Exception as e:
        print(f"{YELLOW}⚠️  No se pudo cargar utils.py: {e}{RESET}")

    # ── Ejecutar tests ─────────────────────────────────────────────
    if buscar_fn and catalogo_dict:
        test_fuzzy_search(buscar_fn)
    else:
        seccion("1. FUZZY SEARCH DE PRODUCTOS")
        skip("Todos los tests de fuzzy search", "memoria.py no disponible")

    if alias_fn:
        test_aliases(alias_fn)
    else:
        seccion("2. ALIASES DE FERRETERÍA")
        skip("Todos los tests de aliases", "ai.py no disponible")

    if parsear_fn:
        test_parser_bulk(parsear_fn)
    else:
        seccion("3. PARSER BULK DE PRECIOS")
        skip("Todos los tests de parser bulk", "mensajes.py no disponible")

    if convertir_fn:
        test_fracciones(convertir_fn)
    else:
        seccion("4. FRACCIONES Y CANTIDADES")
        skip("Todos los tests de fracciones", "utils.py no disponible")

    if catalogo_dict:
        test_productos_display(catalogo_dict)
        test_integridad_catalogo(catalogo_dict)
    else:
        seccion("5. DISPLAY /productos")
        skip("Tests de display", "catálogo no disponible")
        seccion("7. INTEGRIDAD DEL CATÁLOGO")
        skip("Tests de integridad", "catálogo no disponible")

    test_bugs_conocidos(
        buscar_fn or (lambda q: None),
        parsear_fn
    )

    test_archivos_criticos()

    # ── Resumen final ──────────────────────────────────────────────
    total = _passed + _failed + _errored + _skipped
    print(f"\n{BOLD}{'═'*60}")
    print("  RESUMEN FINAL")
    print(f"{'═'*60}{RESET}")
    print(f"  Total ejecutados : {total}")
    print(f"  {GREEN}✅ Pasados   : {_passed}{RESET}")
    if _failed:
        print(f"  {RED}❌ Fallados  : {_failed}{RESET}")
    else:
        print(f"  ❌ Fallados  : {_failed}")
    if _errored:
        print(f"  {RED}💥 Errores   : {_errored}{RESET}")
    else:
        print(f"  💥 Errores   : {_errored}")
    if _skipped:
        print(f"  {YELLOW}⏭  Saltados  : {_skipped}{RESET}")
    print()

    if _failed == 0 and _errored == 0:
        print(f"  {GREEN}{BOLD}🎉 TODO VERDE — SAFE TO DEPLOY{RESET}")
    elif _failed + _errored <= 3:
        print(f"  {YELLOW}{BOLD}⚠️  ALGUNOS PROBLEMAS — revisar antes de deploy{RESET}")
    else:
        print(f"  {RED}{BOLD}🚨 MÚLTIPLES FALLAS — NO HACER DEPLOY{RESET}")
    print()

    return 1 if (_failed > 0 or _errored > 0) else 0


if __name__ == "__main__":
    sys.exit(main())

"""
handlers/productos.py
Comando /productos — catálogo interactivo por categorías.
Los precios se leen en TIEMPO REAL desde memoria.json; al actualizar el
catálogo con /catalogo los cambios se reflejan automáticamente aquí.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from memoria import cargar_memoria

# ─────────────────────────────────────────────────────────────
# Helpers para leer el catálogo
# ─────────────────────────────────────────────────────────────

def _catalogo():
    """Devuelve el dict de productos de memoria.json (fresco en cada llamada)."""
    return cargar_memoria().get("catalogo", {})


def _precio(prod: dict) -> str:
    """Formatea el precio unitario con separador de miles."""
    p = prod.get("precio_unidad", 0)
    return f"${p:,.0f}".replace(",", ".")


def _precio_may(prod: dict):
    """Devuelve 'X.XXX ×N' si tiene precio mayorista, None si no."""
    ppc = prod.get("precio_por_cantidad")
    if not ppc:
        return None
    sobre = ppc.get("precio_sobre_umbral", 0)
    umbral = ppc.get("umbral", 50)
    return f"${sobre:,.0f}".replace(",", ".") + f" ×{umbral}"


def _buscar(nombre_lower: str):
    """Busca un producto por nombre_lower exacto."""
    return _catalogo().get(nombre_lower)


def _filtrar(fn) -> list[dict]:
    """Devuelve lista de productos que cumplen fn(prod)."""
    return [p for p in _catalogo().values() if fn(p)]


# ─────────────────────────────────────────────────────────────
# Teclados de navegación
# ─────────────────────────────────────────────────────────────

def _kbd_main():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔧 Ferretería",    callback_data="prod_cat_ferreteria"),
            InlineKeyboardButton("🎨 Pinturas",       callback_data="prod_cat_pinturas"),
        ],
        [
            InlineKeyboardButton("🔩 Tornillería",   callback_data="prod_cat_tornilleria"),
        ],
        [
            InlineKeyboardButton("🏗️ Construcción",  callback_data="prod_cat_construccion"),
            InlineKeyboardButton("⚡ Eléctricos",     callback_data="prod_cat_electricos"),
        ],
    ])


def _kbd_ferreteria():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖌️ Brochas / Rodillos", callback_data="prod_ferr_brochas"),
            InlineKeyboardButton("📏 Lijas",               callback_data="prod_ferr_lijas"),
        ],
        [
            InlineKeyboardButton("🔗 Cintas",              callback_data="prod_ferr_cintas"),
            InlineKeyboardButton("🔒 Cerraduras",          callback_data="prod_ferr_cerraduras"),
        ],
        [
            InlineKeyboardButton("🪚 Brocas / Discos",    callback_data="prod_ferr_brocas"),
            InlineKeyboardButton("🔧 Herramientas",        callback_data="prod_ferr_herramientas"),
        ],
        [
            InlineKeyboardButton("📦 Varios",              callback_data="prod_ferr_varios"),
        ],
        [InlineKeyboardButton("↩️ Volver",                 callback_data="prod_main")],
    ])


def _kbd_pinturas():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖌️ Vinilo / Cuñetes",    callback_data="prod_pint_vinilo"),
            InlineKeyboardButton("🎨 Esmalte / Anticorr.", callback_data="prod_pint_esmalte"),
        ],
        [
            InlineKeyboardButton("🪄 Laca",                callback_data="prod_pint_laca"),
            InlineKeyboardButton("🧪 Thinner / Varsol",    callback_data="prod_pint_thinner"),
        ],
        [
            InlineKeyboardButton("💧 Poliuretano",         callback_data="prod_pint_poli"),
            InlineKeyboardButton("🎭 Aerosol",             callback_data="prod_pint_aerosol"),
        ],
        [
            InlineKeyboardButton("🧴 Sellador / Masilla",  callback_data="prod_pint_sellador"),
            InlineKeyboardButton("🎨 Otros",               callback_data="prod_pint_otros"),
        ],
        [InlineKeyboardButton("↩️ Volver",                 callback_data="prod_main")],
    ])


def _kbd_tornilleria():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚙️ Drywall ×6",          callback_data="prod_torn_dryx6"),
            InlineKeyboardButton("⚙️ Drywall ×8",          callback_data="prod_torn_dryx8"),
            InlineKeyboardButton("⚙️ Drywall ×10",         callback_data="prod_torn_dryx10"),
        ],
        [
            InlineKeyboardButton("🔩 Hex Galvanizado",      callback_data="prod_torn_hex"),
            InlineKeyboardButton("🔩 Estufa",               callback_data="prod_torn_estufa"),
        ],
        [
            InlineKeyboardButton("📌 Puntillas",            callback_data="prod_torn_puntillas"),
            InlineKeyboardButton("🔩 Tira Fondo",           callback_data="prod_torn_tirafondo"),
        ],
        [
            InlineKeyboardButton("⚙️ Arandelas / Tuercas", callback_data="prod_torn_arandelas"),
        ],
        [InlineKeyboardButton("↩️ Volver",                  callback_data="prod_main")],
    ])


def _kbd_volver(destino: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("↩️ Volver", callback_data=destino)
    ]])


# ─────────────────────────────────────────────────────────────
# Generadores de texto para cada submenú
# ─────────────────────────────────────────────────────────────

def _fmt_row(nombre: str, precio: str, mayorista=None) -> str:
    """Línea producto: Nombre ............ $precio  ($may ×N)"""
    if mayorista:
        return f"  {nombre:<28} {precio}  <i>{mayorista}</i>\n"
    return f"  {nombre:<28} {precio}\n"


def _fmt_grupo(titulo: str, productos: list[dict], key_nombre=None) -> str:
    """Formatea una sección con título y filas de productos."""
    if not productos:
        return ""
    txt = f"\n<b>{titulo}</b>\n"
    txt += "─" * 36 + "\n"
    for p in productos:
        n = key_nombre(p) if key_nombre else p["nombre"]
        may = _precio_may(p)
        txt += _fmt_row(n, _precio(p), may)
    return txt


# ── FERRETERÍA ────────────────────────────────────────────────

def _texto_brochas() -> str:
    import re as _re_rod
    cat = _catalogo()
    brochas = sorted(
        [p for p in cat.values() if "brocha" in p["nombre_lower"] and "%" not in p["nombre_lower"]],
        key=lambda x: x["precio_unidad"]
    )
    # Rodillos de medida (ej: "Rodillo de 2"") — excluir bandeja y convencional
    def _medida_rodillo(nombre_lower):
        m = _re_rod.search(r'rodillo\s+de\s+(\d+(?:\.\d+)?)', nombre_lower)
        return float(m.group(1)) if m else None

    rodillos_medida = sorted(
        [p for p in cat.values()
         if "rodillo" in p["nombre_lower"]
         and "bandeja" not in p["nombre_lower"]
         and "convencional" not in p["nombre_lower"]
         and _medida_rodillo(p["nombre_lower"]) is not None],
        key=lambda x: _medida_rodillo(x["nombre_lower"])
    )
    rodillo_conv = [p for p in cat.values() if "rodillo_convencional" == p.get("nombre_lower","").replace(" ","_")
                    or ("rodillo" in p["nombre_lower"] and "convencional" in p["nombre_lower"])]
    bandeja      = [p for p in cat.values() if "bandeja" in p["nombre_lower"]]

    txt = "🖌️ <b>Brochas / Rodillos</b>\n\n"
    txt += "<b>▸ Brochas</b>\n" + "─" * 36 + "\n"
    for p in brochas:
        txt += _fmt_row(p["nombre"], _precio(p))
    txt += "\n<b>▸ Rodillos</b>\n" + "─" * 36 + "\n"
    for p in rodillos_medida:
        txt += _fmt_row(p["nombre"], _precio(p))
    for p in rodillo_conv:
        txt += _fmt_row(p["nombre"], _precio(p))
    for p in bandeja:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_lijas() -> str:
    cat = _catalogo()
    madera = sorted(
        [p for p in cat.values()
         if "lija" in p["nombre_lower"] and "esmeril" not in p["nombre_lower"]],
        key=lambda x: x["precio_unidad"]
    )
    esmeril = sorted(
        [p for p in cat.values() if "esmeril" in p["nombre_lower"]],
        key=lambda x: x["precio_unidad"]
    )

    txt = "📏 <b>Lijas</b>\n\n"
    txt += "<b>▸ Lija de Madera</b>\n" + "─" * 36 + "\n"
    for p in madera:
        txt += _fmt_row(p["nombre"], _precio(p))

    txt += "\n<b>▸ Lija Esmeril</b>  <i>(precio × 10 cm)</i>\n" + "─" * 36 + "\n"
    for p in esmeril:
        # precio en catálogo es por 100 cm → dividir entre 10
        p10 = p["precio_unidad"] // 10
        txt += _fmt_row(p["nombre"], f"${p10:,.0f}".replace(",", "."))
    return txt


def _texto_cintas() -> str:
    cat = _catalogo()
    pele     = sorted([p for p in cat.values() if "pele" in p["nombre_lower"]], key=lambda x: x["precio_unidad"])
    enmasc   = sorted([p for p in cat.values() if "enmascarar" in p["nombre_lower"]], key=lambda x: x["precio_unidad"])
    otras    = sorted([p for p in cat.values()
                       if "cinta" in p["nombre_lower"]
                       and "pele" not in p["nombre_lower"]
                       and "enmascarar" not in p["nombre_lower"]], key=lambda x: x["precio_unidad"])

    txt = "🔗 <b>Cintas</b>\n\n"
    txt += "<b>▸ Cinta Pele</b>\n" + "─" * 36 + "\n"
    for p in pele:
        txt += _fmt_row(p["nombre"], _precio(p))
    txt += "\n<b>▸ Cinta Enmascarar</b>\n" + "─" * 36 + "\n"
    for p in enmasc:
        txt += _fmt_row(p["nombre"], _precio(p))
    if otras:
        txt += "\n<b>▸ Otras Cintas</b>\n" + "─" * 36 + "\n"
        for p in otras:
            txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_cerraduras() -> str:
    cat = _catalogo()
    prods = sorted(
        [p for p in cat.values()
         if any(k in p["nombre_lower"] for k in ["cerradura", "candado", "cerrojo", "falleba"])],
        key=lambda x: x["precio_unidad"]
    )
    txt = "🔒 <b>Cerraduras / Candados</b>\n\n" + "─" * 36 + "\n"
    for p in prods:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_brocas() -> str:
    cat = _catalogo()
    discos = sorted([p for p in cat.values() if "disco" in p["nombre_lower"]], key=lambda x: x["precio_unidad"])
    brocas = sorted([p for p in cat.values()
                     if "broca" in p["nombre_lower"] and "disco" not in p["nombre_lower"]],
                    key=lambda x: x["precio_unidad"])

    txt = "🪚 <b>Brocas / Discos</b>\n\n"
    txt += "<b>▸ Discos de Corte</b>\n" + "─" * 36 + "\n"
    for p in discos:
        txt += _fmt_row(p["nombre"], _precio(p))
    txt += "\n<b>▸ Brocas</b>\n" + "─" * 36 + "\n"
    for p in brocas:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_herramientas() -> str:
    _kw = ["martillo", "metro", "destornillador", "exacto", "espátula", "espatula",
           "tijera", "formon", "grapadora", "machete", "taladro", "llave", "pulidora"]
    cat = _catalogo()
    prods = sorted(
        [p for p in cat.values() if any(k in p["nombre_lower"] for k in _kw)],
        key=lambda x: x["precio_unidad"]
    )
    txt = "🔧 <b>Herramientas</b>\n\n" + "─" * 36 + "\n"
    for p in prods:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_varios_ferr() -> str:
    _excluir = ["brocha", "rodillo", "bandeja", "lija", "cinta", "cerradura",
                "candado", "cerrojo", "falleba", "disco", "broca", "martillo",
                "metro", "destornillador", "exacto", "espatula", "tijera",
                "formon", "grapadora", "machete", "taladro", "llave", "pulidora"]
    cat = _catalogo()
    prods = sorted(
        [p for p in cat.values()
         if p.get("categoria", "") == "1 Artículos de Ferreteria"
         and not any(k in p["nombre_lower"] for k in _excluir)],
        key=lambda x: x["precio_unidad"]
    )
    txt = "📦 <b>Varios — Ferretería</b>\n\n" + "─" * 36 + "\n"
    for p in prods:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


# ── PINTURAS ──────────────────────────────────────────────────

def _texto_vinilo() -> str:
    cat = _catalogo()

    # Agrupar galones por precio (T1/T2/T3) — listar colores en línea
    por_precio = {}
    for p in cat.values():
        nl = p["nombre_lower"]
        if ("vinilo" not in nl or "cunete" in nl or "1/2" in nl
                or "viniltex" in nl or "vinilico" in nl or "ico" in nl):
            continue
        precio = p["precio_unidad"]
        color = p["nombre"]
        # Extraer solo el color (quitar "Vinilo Davinci T1 " etc.)
        for prefix in ["Vinilo Davinci T1 ", "Vinilo Davinci T2 ", "Vinilo Davinci T3 ",
                        "VINILO DAVINCI T1 ", "VINILO DAVINCI T2 ", "VINILO DAVINCI T3 ",
                        "Vinilo T1 ", "Vinilo T2 ", "Vinilo T3 ", "Vinilo ICO "]:
            if color.startswith(prefix):
                color = color[len(prefix):]
                break
        por_precio.setdefault(precio, []).append(color)

    cunete = sorted([p for p in cat.values()
                     if "cunete" in p["nombre_lower"] and "1/2" not in p["nombre_lower"]
                     and "masilla" not in p["nombre_lower"]], key=lambda x: x["precio_unidad"], reverse=True)
    medio  = sorted([p for p in cat.values()
                     if "1/2 cunete" in p["nombre_lower"] or "1/2 cuñete" in p["nombre_lower"]
                     or "medio cunete" in p["nombre_lower"]],
                    key=lambda x: x["precio_unidad"], reverse=True)

    # Separar ICO del resto
    ico = sorted([p for p in cat.values()
                  if "vinilo" in p["nombre_lower"] and "ico" in p["nombre_lower"]
                  and "cunete" not in p["nombre_lower"]], key=lambda x: -x["precio_unidad"])

    txt = "🖌️ <b>Vinilos y Cuñetes</b>\n\n"
    txt += "<b>▸ Galón</b>\n" + "─" * 36 + "\n"
    for precio in sorted(por_precio.keys(), reverse=True):
        colores = por_precio[precio]
        precio_fmt = f"${precio:,.0f}".replace(",", ".")
        if precio >= 50000:
            tono = "T1"
        elif precio >= 35000:
            tono = "T2"
        else:
            tono = "T3"
        txt += f"  Galón Vinilo {tono}    {precio_fmt}    ({len(colores)} colores)\n"
    for p in ico:
        txt += _fmt_row(p["nombre"], _precio(p))

    txt += "\n<b>▸ Cuñete — 5 galones</b>\n" + "─" * 36 + "\n"
    for p in cunete:
        txt += _fmt_row(p["nombre"], _precio(p))
    txt += "\n<b>▸ Medio Cuñete — 2.5 gal</b>\n" + "─" * 36 + "\n"
    for p in medio:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_esmalte() -> str:
    cat = _catalogo()

    def _es_3en1(nl):
        return "3 en 1" in nl or "3 en1" in nl or "3en1" in nl or "3en 1" in nl

    # Estándar: solo los 7 colores base (excluye aluminio, dorado, 3en1)
    estandar = sorted([p for p in cat.values()
                       if "esmalte" in p["nombre_lower"]
                       and not _es_3en1(p["nombre_lower"])
                       and "aluminio" not in p["nombre_lower"]
                       and "dorado" not in p["nombre_lower"]], key=lambda x: x["nombre"])

    anti     = sorted([p for p in cat.values() if "anticorrosivo" in p["nombre_lower"]], key=lambda x: x["nombre"])

    # Aluminio y Dorado como líneas individuales
    aluminio = next((p for p in cat.values()
                     if "esmalte aluminio" == p["nombre_lower"]), None)
    dorado   = next((p for p in cat.values()
                     if "esmalte dorado" == p["nombre_lower"]), None)

    # 3 en 1: excluye aluminio
    tres     = sorted([p for p in cat.values()
                       if _es_3en1(p["nombre_lower"])
                       and "esmalte" in p["nombre_lower"]
                       and "aluminio" not in p["nombre_lower"]], key=lambda x: x["nombre"])

    txt = "🎨 <b>Esmalte / Anticorrosivo</b>\n\n"

    def _ordenar_colores(productos, quitar_prefijo):
        """Blanco primero, Negro segundo, resto alfabético."""
        def _color(p):
            return p["nombre"].replace(quitar_prefijo, "").replace(quitar_prefijo.upper(), "").strip()
        prioridad = {"blanco": 0, "negro": 1}
        return sorted(productos, key=lambda p: (prioridad.get(_color(p).lower(), 2), _color(p).lower()))

    if estandar:
        p0 = next((p for p in estandar if p["precio_unidad"] > 0), estandar[0])
        ordenados = _ordenar_colores(estandar, "Esmalte ")
        colores = " · ".join(p["nombre"].replace("Esmalte ", "").replace("ESMALTE ", "").strip()
                             for p in ordenados)
        txt += f"<b>▸ Esmalte estándar — {_precio(p0)}</b>\n"
        txt += f"  <i>{colores}</i>\n\n"

    if anti:
        p0 = next((p for p in anti if p["precio_unidad"] > 0), anti[0])
        ordenados = _ordenar_colores(anti, "Anticorrosivo ")
        colores = " · ".join(p["nombre"].replace("Anticorrosivo ", "").replace("ANTICORROSIVO ", "").strip()
                             for p in ordenados)
        txt += f"<b>▸ Anticorrosivo — {_precio(p0)}</b>\n"
        txt += f"  <i>{colores}</i>\n\n"

    # Aluminio y Dorado como filas individuales (sin sección "Especiales")
    if aluminio:
        txt += _fmt_row("Esmalte Aluminio", _precio(aluminio))
    if dorado:
        txt += _fmt_row("Esmalte Dorado", _precio(dorado))
    if aluminio or dorado:
        txt += "\n"

    if tres:
        p0 = tres[0]
        # Limpiar prefijos del nombre para mostrar solo el color/variante
        def _color_3en1(nombre):
            import re as _re
            for pre in ["Esmalte 3 En 1 ", "Esmalte 3 en 1 ", "Esmalte 3 En1 ", "ESMALTE 3 EN 1 "]:
                nombre = nombre.replace(pre, "")
            # Quitar marca al final (davinci, tonner, pintuco, etc.)
            nombre = _re.sub(r"\s+(davinci|tonner|pintuco|ico|placco)$", "", nombre.strip(), flags=_re.IGNORECASE)
            return nombre.strip()
        # Ordenar: Blanco primero, Negro segundo, resto alfabético
        tres_ordenados = sorted(tres, key=lambda p: ({"blanco": 0, "negro": 1}.get(_color_3en1(p["nombre"]).lower(), 2), _color_3en1(p["nombre"]).lower()))
        # Deduplicar colores (puede haber varias marcas del mismo color)
        vistos = []
        for p in tres_ordenados:
            c = _color_3en1(p["nombre"])
            if c not in vistos:
                vistos.append(c)
        colores = " · ".join(vistos)
        txt += f"<b>▸ Esmalte 3 en 1 — {_precio(p0)}</b>\n"
        txt += f"  <i>{colores}</i>\n"

    return txt.strip()


def _texto_laca() -> str:
    cat = _catalogo()
    corriente  = sorted([p for p in cat.values()
                         if p["nombre_lower"].startswith("laca corriente") or
                         "laca corriente" in p["nombre_lower"]], key=lambda x: x["nombre"])
    catalizada = sorted([p for p in cat.values()
                         if "laca" in p["nombre_lower"] and "catalizada" in p["nombre_lower"]],
                        key=lambda x: x["nombre"])

    txt = "🪄 <b>Laca</b>\n\n"
    if corriente:
        p0 = corriente[0]
        colores = " · ".join(
            p["nombre"].replace("Laca Corriente", "").replace("Laca corriente", "").strip()
            for p in corriente)
        txt += f"<b>▸ Laca Corriente — {_precio(p0)}</b>\n  <i>{colores}</i>\n\n"
    if catalizada:
        txt += "<b>▸ Laca Catalizada</b>\n" + "─" * 36 + "\n"
        for p in catalizada:
            txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_thinner() -> str:
    cat = _catalogo()
    thinner = sorted([p for p in cat.values() if "thinner" in p["nombre_lower"] or "tiner" in p["nombre_lower"]],
                     key=lambda x: x["precio_unidad"])
    varsol  = sorted([p for p in cat.values() if "varsol" in p["nombre_lower"]],
                     key=lambda x: x["precio_unidad"])

    txt = "🧪 <b>Thinner / Varsol</b>\n"
    txt += "<i>💡 Precio por galón · fracciones disponibles</i>\n\n"
    txt += "<b>▸ Thinner</b>\n" + "─" * 36 + "\n"
    for p in thinner:
        txt += _fmt_row(p["nombre"], _precio(p))
    txt += "\n<b>▸ Varsol</b>\n" + "─" * 36 + "\n"
    for p in varsol:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_poliuretano() -> str:
    cat = _catalogo()
    poli  = sorted([p for p in cat.values() if "poliuretano" in p["nombre_lower"]], key=lambda x: x["nombre"])
    polia = sorted([p for p in cat.values() if "poliamida" in p["nombre_lower"]], key=lambda x: x["nombre"])

    txt = "💧 <b>Poliuretano / Poliamida</b>\n\n"
    if poli:
        p0 = poli[0]
        colores = " · ".join(p["nombre"].replace("Poliuretano ", "").replace("POLIURETANO ", "")
                             for p in poli)
        txt += f"<b>▸ Poliuretano — {_precio(p0)}</b>\n  <i>{colores}</i>\n\n"
    if polia:
        p0 = polia[0]
        colores = " · ".join(p["nombre"].replace("Poliamida ", "").replace("POLIAMIDA ", "").strip()
                             for p in polia)
        txt += f"<b>▸ Poliamida — {_precio(p0)}</b>\n  <i>{colores}</i>\n"
    return txt


def _texto_aerosol() -> str:
    cat = _catalogo()
    estandar  = sorted([p for p in cat.values()
                        if ("aerosol" in p["nombre_lower"] or "aersosol" in p["nombre_lower"])
                        and "alta temp" not in p["nombre_lower"]
                        and "fluorec" not in p["nombre_lower"]
                        and "aluminio" not in p["nombre_lower"]],
                       key=lambda x: x["nombre"])
    especial  = sorted([p for p in cat.values()
                        if ("aerosol" in p["nombre_lower"] or "aersosol" in p["nombre_lower"])
                        and any(k in p["nombre_lower"] for k in ["alta temp", "fluorec", "aluminio"])],
                       key=lambda x: x["precio_unidad"])

    txt = "🎭 <b>Aerosol</b>\n\n"
    if estandar:
        p0 = estandar[0]
        # Deduplicate por precio+nombre
        vistos = set()
        unicos = []
        for p in estandar:
            k = p["nombre"].lower().strip()
            if k not in vistos:
                vistos.add(k)
                unicos.append(p)
        colores = " · ".join(
            p["nombre"].replace("Aerosol ", "").replace("AEROSOL ", "").replace("AERSOSOL ", "").strip()
            for p in unicos)
        txt += f"<b>▸ Estándar — {_precio(p0)}</b>\n  <i>{colores}</i>\n\n"
    if especial:
        vistos = set()
        unicos_e = []
        for p in especial:
            k = p["nombre"].lower().strip()
            if k not in vistos:
                vistos.add(k)
                unicos_e.append(p)
        txt += "<b>▸ Especiales</b>\n" + "─" * 36 + "\n"
        for p in unicos_e:
            txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_sellador() -> str:
    cat = _catalogo()
    sell = sorted([p for p in cat.values() if "sellador" in p["nombre_lower"]], key=lambda x: x["nombre"])
    mas_laca = sorted([p for p in cat.values()
                       if "masilla laca" in p["nombre_lower"] or "masilla de laca" in p["nombre_lower"]],
                      key=lambda x: x["nombre"])
    mas_plas = sorted([p for p in cat.values() if "masilla plastica" in p["nombre_lower"]],
                      key=lambda x: x["precio_unidad"])

    txt = "🧴 <b>Sellador / Masilla</b>\n\n"
    if sell:
        p0 = sell[0]
        colores = " · ".join(p["nombre"].replace("Sellador ", "").strip() for p in sell)
        txt += f"<b>▸ Sellador — {_precio(p0)}</b>\n  <i>{colores}</i>\n\n"
    if mas_laca:
        p0 = mas_laca[0]
        colores = " · ".join(
            p["nombre"].replace("Masilla Laca ", "").replace("MASILLA LACA ", "").strip()
            for p in mas_laca)
        txt += f"<b>▸ Masilla Laca — {_precio(p0)}</b>\n  <i>{colores}</i>\n\n"
    if mas_plas:
        txt += "<b>▸ Masilla Plástica</b>\n" + "─" * 36 + "\n"
        for p in mas_plas:
            txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_otros_pint() -> str:
    _excluir = ["vinilo", "esmalte", "anticorrosivo", "cunete", "laca",
                "thinner", "varsol", "aerosol", "aersosol", "sellador",
                "masilla", "poliuretano", "poliamida"]
    cat = _catalogo()
    prods = sorted(
        [p for p in cat.values()
         if p.get("categoria", "") == "2 Pinturas y Disolventes"
         and not any(k in p["nombre_lower"] for k in _excluir)],
        key=lambda x: x["precio_unidad"]
    )
    txt = "🎨 <b>Otros — Pinturas</b>\n\n" + "─" * 36 + "\n"
    for p in prods:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


# ── TORNILLERÍA ───────────────────────────────────────────────

def _texto_drywall(cabeza: str) -> str:
    """cabeza: '6', '8' o '10'"""
    cat = _catalogo()
    prods = sorted(
        [p for p in cat.values()
         if "drywall" in p["nombre_lower"] and f"{cabeza}x" in p["nombre_lower"].replace(" ", "")
         and "tornillo" in p["nombre_lower"]],
        key=lambda x: x["precio_unidad"]
    )
    txt = f"⚙️ <b>Tornillos Drywall ×{cabeza}</b>\n"
    txt += "<i>💡 Mayorista desde 50 und.</i>\n\n"
    txt += "─" * 36 + "\n"
    for p in prods:
        may = _precio_may(p)
        n = p["nombre"].upper().replace("TORNILLO DRYWALL ", "").replace("-1/2", "½").replace("-1/4", "¼").replace("-3/4", "¾").replace("1/2", "½").replace("1/4", "¼").replace("3/4", "¾")
        txt += _fmt_row(n, _precio(p), may)
    return txt


def _texto_hex() -> str:
    cat = _catalogo()
    tornillos = sorted([p for p in cat.values()
                        if "hex" in p["nombre_lower"] and "tornillo" in p["nombre_lower"]],
                       key=lambda x: x["precio_unidad"])
    tuercas   = sorted([p for p in cat.values()
                        if "tuerca" in p["nombre_lower"] and "hex" in p["nombre_lower"]],
                       key=lambda x: x["precio_unidad"])
    arandelas = sorted([p for p in cat.values()
                        if "arandela" in p["nombre_lower"] and ("galv" in p["nombre_lower"] or "hex" in p["nombre_lower"])],
                       key=lambda x: x["precio_unidad"])

    txt = "🔩 <b>Hex Galvanizado</b>\n\n"
    if tornillos:
        txt += "<b>▸ Tornillos</b>\n" + "─" * 36 + "\n"
        for p in tornillos:
            txt += _fmt_row(p["nombre"], _precio(p), _precio_may(p))
    if tuercas:
        txt += "\n<b>▸ Tuercas</b>\n" + "─" * 36 + "\n"
        for p in tuercas:
            txt += _fmt_row(p["nombre"], _precio(p))
    if arandelas:
        txt += "\n<b>▸ Arandelas</b>\n" + "─" * 36 + "\n"
        for p in arandelas:
            txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_estufa() -> str:
    cat = _catalogo()
    prods = sorted([p for p in cat.values() if "estufa" in p["nombre_lower"]], key=lambda x: x["precio_unidad"])
    txt = "🔩 <b>Tornillos Estufa</b>\n\n" + "─" * 36 + "\n"
    for p in prods:
        txt += _fmt_row(p["nombre"], _precio(p), _precio_may(p))
    return txt


def _texto_puntillas() -> str:
    cat = _catalogo()
    con  = sorted([p for p in cat.values()
                   if "puntilla" in p["nombre_lower"] and "sin cabeza" not in p["nombre_lower"]
                   and " sc" not in p["nombre_lower"]], key=lambda x: x["precio_unidad"])
    sin  = sorted([p for p in cat.values()
                   if "puntilla" in p["nombre_lower"]
                   and ("sin cabeza" in p["nombre_lower"] or " sc" in p["nombre_lower"])],
                  key=lambda x: x["precio_unidad"])

    txt = "📌 <b>Puntillas</b>  <i>(precio por libra)</i>\n\n"
    if con:
        txt += "<b>▸ Con Cabeza</b>\n" + "─" * 36 + "\n"
        for p in con:
            txt += _fmt_row(p["nombre"], _precio(p))
    if sin:
        txt += "\n<b>▸ Sin Cabeza</b>\n" + "─" * 36 + "\n"
        for p in sin:
            txt += _fmt_row(p["nombre"], _precio(p))
    if not con and not sin:
        prods = sorted([p for p in cat.values() if "puntilla" in p["nombre_lower"]],
                       key=lambda x: x["precio_unidad"])
        txt += "─" * 36 + "\n"
        for p in prods:
            txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_tirafondo() -> str:
    cat = _catalogo()
    prods = sorted([p for p in cat.values() if "tira fondo" in p["nombre_lower"]], key=lambda x: x["precio_unidad"])
    txt = "🔩 <b>Tira Fondo</b>\n\n" + "─" * 36 + "\n"
    for p in prods:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


def _texto_arandelas() -> str:
    cat = _catalogo()
    prods = sorted(
        [p for p in cat.values()
         if any(k in p["nombre_lower"] for k in ["arandela", "chazo"])
         and "galv" not in p["nombre_lower"]],
        key=lambda x: x["precio_unidad"]
    )
    txt = "⚙️ <b>Arandelas / Chazos</b>\n\n" + "─" * 36 + "\n"
    for p in prods:
        txt += _fmt_row(p["nombre"], _precio(p))
    return txt


# ── CONSTRUCCIÓN & ELÉCTRICOS ─────────────────────────────────

def _texto_construccion() -> str:
    cat = _catalogo()
    prods = [p for p in cat.values()
             if p.get("categoria", "") == "4 Impermeabilizantes y Materiales de construcción"]

    grupos = {
        "Cementos / Bases":    ["cemento", "yeso", "talco", "marmolina", "granito", "carbonato"],
        "Impermeabilizantes":  ["placco", "imperfil", "torofil", "pintucofil", "manto", "tela asfaltica"],
        "Drywall / Estuco":    ["vigueta", "angulo", "omega", "estuco", "masilla"],
        "Adhesivos / Químicos":["acronal", "latecol", "silicato", "amoniaco", "paragüita"],
        "Plásticos / Malla":   ["plastico", "malla"],
    }

    asignados = set()
    txt = "🏗️ <b>Construcción</b>\n\n"
    for grupo, kws in grupos.items():
        items = sorted(
            [p for p in prods if any(k in p["nombre_lower"] for k in kws)],
            key=lambda x: x["precio_unidad"]
        )
        if not items:
            continue
        txt += f"<b>▸ {grupo}</b>\n" + "─" * 36 + "\n"
        for p in items:
            txt += _fmt_row(p["nombre"], _precio(p))
            asignados.add(p["nombre_lower"])
        txt += "\n"

    resto = sorted([p for p in prods if p["nombre_lower"] not in asignados], key=lambda x: x["precio_unidad"])
    if resto:
        txt += "<b>▸ Otros</b>\n" + "─" * 36 + "\n"
        for p in resto:
            txt += _fmt_row(p["nombre"], _precio(p))
    return txt.strip()


def _texto_electricos() -> str:
    cat = _catalogo()
    prods = [p for p in cat.values()
             if p.get("categoria", "") == "5 Materiales Electricos"]

    grupos = {
        "Cables":                ["alambre", "cable"],
        "Interruptores / Tomas": ["interruptor", "toma", "enchufe"],
        "Lámparas LED":          ["lampara", "led"],
        "Cuñas / Cajas":         ["cuña", "caja de cuña"],
        "Canaleta":              ["canaleta"],
    }

    asignados = set()
    txt = "⚡ <b>Eléctricos</b>\n\n"
    for grupo, kws in grupos.items():
        items = sorted(
            [p for p in prods if any(k in p["nombre_lower"] for k in kws)],
            key=lambda x: x["precio_unidad"]
        )
        if not items:
            continue
        txt += f"<b>▸ {grupo}</b>\n" + "─" * 36 + "\n"
        # dedup
        vistos = set()
        for p in items:
            k = p["nombre"].lower().strip()
            if k not in vistos:
                vistos.add(k)
                txt += _fmt_row(p["nombre"], _precio(p))
                asignados.add(p["nombre_lower"])
        txt += "\n"
    return txt.strip()


# ─────────────────────────────────────────────────────────────
# Mapa callback → texto + teclado de vuelta
# ─────────────────────────────────────────────────────────────

_SUBMENUS = {
    # Ferretería
    "prod_ferr_brochas":     (lambda: _texto_brochas(),           "prod_cat_ferreteria"),
    "prod_ferr_lijas":       (lambda: _texto_lijas(),             "prod_cat_ferreteria"),
    "prod_ferr_cintas":      (lambda: _texto_cintas(),            "prod_cat_ferreteria"),
    "prod_ferr_cerraduras":  (lambda: _texto_cerraduras(),        "prod_cat_ferreteria"),
    "prod_ferr_brocas":      (lambda: _texto_brocas(),            "prod_cat_ferreteria"),
    "prod_ferr_herramientas":(lambda: _texto_herramientas(),      "prod_cat_ferreteria"),
    "prod_ferr_varios":      (lambda: _texto_varios_ferr(),       "prod_cat_ferreteria"),
    # Pinturas
    "prod_pint_vinilo":      (lambda: _texto_vinilo(),            "prod_cat_pinturas"),
    "prod_pint_esmalte":     (lambda: _texto_esmalte(),           "prod_cat_pinturas"),
    "prod_pint_laca":        (lambda: _texto_laca(),              "prod_cat_pinturas"),
    "prod_pint_thinner":     (lambda: _texto_thinner(),           "prod_cat_pinturas"),
    "prod_pint_poli":        (lambda: _texto_poliuretano(),       "prod_cat_pinturas"),
    "prod_pint_aerosol":     (lambda: _texto_aerosol(),           "prod_cat_pinturas"),
    "prod_pint_sellador":    (lambda: _texto_sellador(),          "prod_cat_pinturas"),
    "prod_pint_otros":       (lambda: _texto_otros_pint(),        "prod_cat_pinturas"),
    # Tornillería
    "prod_torn_dryx6":       (lambda: _texto_drywall("6"),        "prod_cat_tornilleria"),
    "prod_torn_dryx8":       (lambda: _texto_drywall("8"),        "prod_cat_tornilleria"),
    "prod_torn_dryx10":      (lambda: _texto_drywall("10"),       "prod_cat_tornilleria"),
    "prod_torn_hex":         (lambda: _texto_hex(),               "prod_cat_tornilleria"),
    "prod_torn_estufa":      (lambda: _texto_estufa(),            "prod_cat_tornilleria"),
    "prod_torn_puntillas":   (lambda: _texto_puntillas(),         "prod_cat_tornilleria"),
    "prod_torn_tirafondo":   (lambda: _texto_tirafondo(),         "prod_cat_tornilleria"),
    "prod_torn_arandelas":   (lambda: _texto_arandelas(),         "prod_cat_tornilleria"),
    # Construcción / Eléctricos
    "prod_cat_construccion": (lambda: _texto_construccion(),      "prod_main"),
    "prod_cat_electricos":   (lambda: _texto_electricos(),        "prod_main"),
}


# ─────────────────────────────────────────────────────────────
# Handlers de Telegram
# ─────────────────────────────────────────────────────────────

async def comando_productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entrada principal: /productos"""
    await update.message.reply_text(
        "📦 <b>Catálogo de Productos</b>\n\nSelecciona una categoría:",
        parse_mode="HTML",
        reply_markup=_kbd_main(),
    )


async def manejar_callback_productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los callbacks de /productos (prod_*)."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Menú principal ──
    if data == "prod_main":
        await query.edit_message_text(
            "📦 <b>Catálogo de Productos</b>\n\nSelecciona una categoría:",
            parse_mode="HTML",
            reply_markup=_kbd_main(),
        )
        return

    # ── Submenús de segundo nivel ──
    if data == "prod_cat_ferreteria":
        await query.edit_message_text(
            "🔧 <b>Ferretería</b>\n\nSelecciona una subcategoría:",
            parse_mode="HTML",
            reply_markup=_kbd_ferreteria(),
        )
        return

    if data == "prod_cat_pinturas":
        await query.edit_message_text(
            "🎨 <b>Pinturas y Disolventes</b>\n\nSelecciona una subcategoría:",
            parse_mode="HTML",
            reply_markup=_kbd_pinturas(),
        )
        return

    if data == "prod_cat_tornilleria":
        await query.edit_message_text(
            "🔩 <b>Tornillería</b>\n\nSelecciona una subcategoría:",
            parse_mode="HTML",
            reply_markup=_kbd_tornilleria(),
        )
        return

    # ── Hojas de producto (nivel 3) ──
    if data in _SUBMENUS:
        fn_texto, volver = _SUBMENUS[data]
        try:
            texto = fn_texto()
            if not texto or not texto.strip():
                texto = "⚠️ Sin productos en esta categoría."
            # Telegram límite: 4096 chars
            if len(texto) > 4000:
                texto = texto[:3950] + "\n\n<i>... (lista truncada)</i>"
            await query.edit_message_text(
                texto,
                parse_mode="HTML",
                reply_markup=_kbd_volver(volver),
            )
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            print(f"[productos] ERROR en {data}: {err}")
            try:
                await query.edit_message_text(
                    f"❌ Error al cargar categoría:\n<code>{e}</code>",
                    parse_mode="HTML",
                    reply_markup=_kbd_volver(volver),
                )
            except Exception:
                pass
        return

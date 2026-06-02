"""
Integración con Claude AI (modelo: claude-haiku-4-5-20251001):
- Construcción del system prompt con contexto del negocio
- Llamada a la API de Claude con PROMPT CACHING (ahorro ~60% en tokens de input)
- Parseo y ejecución de acciones embebidas en la respuesta ([VENTA]...[/VENTA], etc.)

OPTIMIZACIONES DE COSTO ACTIVAS:
  1. Prompt caching  — la parte estática del prompt (reglas + catálogo) se cachea 5 min.
                       Costo de tokens cacheados = 10% del precio normal.
  2. Historial corto — se envían solo los últimos 1-4 mensajes (adaptativo).
  3. max_tokens cap  — techo adaptativo de respuesta.
  4. Catálogo simplificado — parte estática solo precio base, fracciones vía MATCH dinámico (~26% menos tokens cacheados).

CORRECCIONES v4:
  - Bug precedencia and/or en filtro tornillos drywall corregido
  - _quitar_tildes (redefinida en loop) eliminada, reemplazada por _normalizar
  - Todos los `import re as _re*` dentro de funciones eliminados (re ya importado al top)
"""

import logging
import os
import asyncio
import json
import re
import traceback
from datetime import datetime

import config
import bypass
import skill_loader
import alias_manager

# Métricas Prometheus — fail-silent si el módulo no está disponible
try:
    import metrics as _metrics
except Exception:  # noqa: BLE001
    _metrics = None
from ai.price_cache import registrar as _registrar_precio_reciente, get_activos as _get_precios_recientes_activos


from memoria import (
    cargar_memoria, guardar_memoria, invalidar_cache_memoria,
    buscar_producto_en_catalogo, buscar_multiples_en_catalogo,
    buscar_multiples_con_alias,
    obtener_precios_como_texto, obtener_info_fraccion_producto,
    obtener_precio_para_cantidad,
    cargar_inventario, cargar_caja, cargar_gastos_hoy,
    obtener_resumen_caja, guardar_gasto,
    guardar_fiado_movimiento, abonar_fiado,
    actualizar_precio_en_catalogo,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, _normalizar
import db as _db  # noqa: E402 — necesario para helpers PG (_pg_resumen_ventas, etc.)
from ai.excel_gen import generar_excel_personalizado, editar_excel_con_claude, ejecutar_operacion_excel
from ai.prompts import (
    aplicar_alias_ferreteria, _construir_parte_estatica,
    _construir_catalogo_imagen, _construir_parte_dinamica,
    _calcular_historial, MODELO_HAIKU, MODELO_SONNET, _elegir_modelo,
    VOZ_INSTRUCCIONES,
)
# Control de budget / costo real por vendedor/día
from ai import budget as _budget
# Tool-calling nativo (M-01) — schemas + puente tool_use→tags
from ai import tools as tools_mod
# Búsqueda semántica del catálogo (fallback del fuzzy) — solo voz, fail-safe
from ai import semantic_catalog as _semantic

def _cantidad_legible_voz(cantidad) -> str:
    """Cantidad apta para leer en voz: '3', '1/4', '1 y 1/2'. Fail-safe a str."""
    try:
        return decimal_a_fraccion_legible(float(cantidad))
    except (TypeError, ValueError):
        return str(cantidad)


# Palabras que, solas o casi, cuentan como un "sí" del vendedor al confirmar una
# mutación por voz (gasto/fiado/abono). Normalizadas (sin tildes). Conservador
# para no leer un "sí" dentro de un mensaje sustantivo como confirmación.
_AFIRMACIONES_VOZ = {
    "si", "sip", "claro", "dale", "listo", "ok", "oka", "okay", "okey",
    "hagale", "hazlo", "registralo", "registra", "confirmo", "confirma",
    "confirmado", "correcto", "exacto", "eso", "aja", "sisas", "obvio",
    "seguro", "perfecto", "afirmativo", "va", "vale", "hecho", "una", "once",
}
# Conectores que no aportan significado (no incluir "si": es afirmación por sí solo).
_CONECTORES_VOZ = {"de", "pues", "ya", "esta", "bien", "por", "favor", "todo"}


def es_afirmacion_voz(mensaje: str) -> bool:
    """
    True si el mensaje de voz es esencialmente una afirmación corta ('sí', 'dale',
    'de una', 'hágale pues', 'sí confirmo') — señal de que el vendedor confirma la
    mutación propuesta el turno anterior. Estricto a propósito: mensaje corto y
    TODAS sus palabras significativas afirmativas, para no confundir un 'sí' suelto
    dentro de un pedido sustantivo ('sí dame un martillo') con una confirmación.
    """
    t = mensaje or ""
    for flag in ("##VOZ##", "##DASHBOARD##", "##BOT##"):
        t = t.replace(flag, "")
    if ":" in t:                       # quitar prefijo "Nombre: ..."
        t = t.split(":", 1)[1]
    t = re.sub(r"[^a-z0-9 ]", " ", _normalizar(t)).strip()
    if not t:
        return False
    palabras = t.split()
    if len(palabras) > 4:              # una afirmación es corta
        return False
    significativas = [w for w in palabras if w not in _CONECTORES_VOZ]
    return bool(significativas) and all(w in _AFIRMACIONES_VOZ for w in significativas)


# Palabras que indican que el vendedor NO confirma (corrige, cancela o pospone).
_NEGACIONES_VOZ = {
    "no", "nones", "negativo", "cancela", "cancelar", "espera", "espere",
    "para", "pará", "todavia", "aun", "mejor", "cambia", "cambiar", "corrige",
    "corregir", "esta", "mal", "equivocado", "asi",
}


def es_negacion_voz(mensaje: str) -> bool:
    """True si el mensaje parece una negación/corrección ('no', 'mejor no',
    'espera', 'así no', 'está mal'): bloquea que un re-emit cuente como confirmación."""
    t = mensaje or ""
    for flag in ("##VOZ##", "##DASHBOARD##", "##BOT##"):
        t = t.replace(flag, "")
    if ":" in t:
        t = t.split(":", 1)[1]
    t = re.sub(r"[^a-z0-9 ]", " ", _normalizar(t)).strip()
    if not t:
        return False
    return any(w in _NEGACIONES_VOZ for w in t.split())


def _norm_cmp_voz(texto: str) -> str:
    """Normaliza un texto para comparar dos respuestas habladas (propuestas)."""
    return re.sub(r"[^a-z0-9]+", " ", _normalizar(texto or "")).strip()


def _ultima_respuesta_asistente(historial_chat: list) -> str:
    """Último mensaje del asistente en el historial (para detectar re-propuesta)."""
    for _h in reversed(historial_chat or []):
        try:
            if _h.get("role") == "assistant":
                return str(_h.get("content") or "")
        except AttributeError:
            continue
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS PG — reemplazan funciones de excel.py
# ─────────────────────────────────────────────────────────────────────────────

def _pg_fila_a_cliente(row: dict) -> dict:
    """Adapta fila PG al formato dict que espera el código existente (claves estilo Excel)."""
    return {
        "Nombre tercero":         row.get("nombre", ""),
        "Tipo de identificacion": row.get("tipo_id", ""),
        "Identificacion":         row.get("identificacion", ""),
        "Fecha registro":         row.get("fecha_registro", ""),
    }


def _pg_resumen_ventas() -> dict | None:
    """Total y conteo de ventas del mes actual. Reemplaza obtener_resumen_ventas()."""
    if not _db.DB_DISPONIBLE:
        return None
    row = _db.query_one(
        """SELECT COUNT(*) AS num_ventas, COALESCE(SUM(total), 0) AS total
           FROM ventas
           WHERE DATE_TRUNC('month', fecha) = DATE_TRUNC('month', CURRENT_DATE)"""
    )
    return {"total": float(row["total"]), "num_ventas": int(row["num_ventas"])} if row else None


def _pg_todos_los_datos(limite: int = 300) -> list:
    """Historial de ventas con detalle. Reemplaza obtener_todos_los_datos()."""
    if not _db.DB_DISPONIBLE:
        return []
    rows = _db.query_all(
        """SELECT v.fecha::text, v.hora::text, v.cliente_nombre, v.vendedor,
                  v.metodo_pago, v.total,
                  vd.producto_nombre, vd.cantidad, vd.precio_unitario,
                  vd.total AS subtotal
           FROM ventas v
           LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
           ORDER BY v.fecha DESC, v.id DESC
           LIMIT %s""",
        (limite,),
    )
    return [dict(r) for r in rows]


def _pg_buscar_cliente(termino: str) -> tuple[dict | None, list]:
    """Busca clientes en PG por nombre o cédula. Reemplaza buscar_cliente_con_resultado()."""
    if not _db.DB_DISPONIBLE:
        return None, []
    termino_norm = _normalizar(termino)
    palabras     = [p for p in termino_norm.split() if len(p) > 2]

    # Búsqueda exacta por identificación
    row = _db.query_one(
        """SELECT nombre, tipo_id, identificacion,
                  created_at::text AS fecha_registro
           FROM clientes WHERE identificacion = %s""",
        (termino.strip(),),
    )
    if row:
        c = _pg_fila_a_cliente(row)
        return c, [c]

    if not palabras:
        return None, []

    todos = _db.query_all(
        "SELECT nombre, tipo_id, identificacion, created_at::text AS fecha_registro FROM clientes"
    )
    candidatos = []
    for r in todos:
        nombre_n = _normalizar(r["nombre"])
        if any(p in nombre_n for p in palabras):
            candidatos.append(_pg_fila_a_cliente(r))
    candidatos.sort(key=lambda x: len(x.get("Nombre tercero", "")))
    return (candidatos[0] if len(candidatos) == 1 else None), candidatos


def _pg_clientes_recientes(limite: int = 5) -> list:
    """Últimos N clientes registrados. Reemplaza obtener_clientes_recientes()."""
    if not _db.DB_DISPONIBLE:
        return []
    rows = _db.query_all(
        """SELECT nombre, tipo_id, identificacion, created_at::text AS fecha_registro
           FROM clientes ORDER BY created_at DESC LIMIT %s""",
        (limite,),
    )
    return [_pg_fila_a_cliente(r) for r in rows]


def _pg_guardar_cliente(nombre, tipo_id, identificacion,
                        tipo_persona="Natural", correo="", telefono="") -> bool:
    """INSERT de cliente en PG. Reemplaza guardar_cliente_nuevo()."""
    if not _db.DB_DISPONIBLE:
        return False
    try:
        _db.execute(
            """INSERT INTO clientes
                   (nombre, tipo_id, identificacion, tipo_persona, correo, telefono)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (
                nombre.upper().strip(),
                tipo_id,
                identificacion.strip() or None,
                tipo_persona,
                correo.strip()   or None,
                telefono.strip() or None,
            ),
        )
        return True
    except Exception as e:
        logging.getLogger("ferrebot.ai").error(f"Error guardando cliente en PG: {e}")
        return False


def _pg_borrar_cliente(termino: str) -> tuple[bool, str]:
    """DELETE de cliente en PG. Reemplaza borrar_cliente()."""
    if not _db.DB_DISPONIBLE:
        return False, "Base de datos no disponible."
    termino_norm = _normalizar(termino)
    row = _db.query_one(
        "SELECT id, nombre FROM clientes WHERE identificacion = %s", (termino.strip(),)
    )
    if not row:
        todos    = _db.query_all("SELECT id, nombre FROM clientes")
        palabras = [p for p in termino_norm.split() if len(p) > 2]
        for r in todos:
            nombre_n = _normalizar(r["nombre"])
            if nombre_n == termino_norm or (palabras and all(p in nombre_n for p in palabras)):
                row = r
                break
    if not row:
        return False, f"No encontré un cliente que coincida con '{termino}'."
    _db.execute("DELETE FROM clientes WHERE id = %s", (row["id"],))
    return True, f"✅ Cliente '{row['nombre']}' borrado del sistema."


# ─────────────────────────────────────────────
# LLAMADA A CLAUDE CON PROMPT CACHING
# ─────────────────────────────────────────────

async def _llamar_claude_con_reintentos(cliente, max_tokens, system, messages, max_reintentos=3, model: str = None, tools: list | None = None):
    """
    Wrapper para llamar a Claude con reintentos: máximo 2 reintentos (3 intentos total),
    espera fija de 2s entre ellos. Si se agota, lanza RuntimeError con mensaje amigable.

    `tools` (opcional): lista de tool schemas. Si se pasa, la llamada habilita
    tool-calling nativo (M-01). tool_choice queda en "auto" — Claude decide si
    registrar (llamando la herramienta) o preguntar (devolviendo texto).
    """
    _model = model or MODELO_HAIKU   # default haiku si no se especifica

    _MSG_NO_DISPONIBLE = (
        "⚠️ El asistente IA no está disponible ahora. "
        "Puedes registrar la venta manualmente con /ventas."
    )

    ultimo_error = None
    for intento in range(max_reintentos):
        try:
            loop = asyncio.get_event_loop()
            _m = _model   # capturar en closure
            import time as _time
            _t0 = _time.perf_counter()
            _kwargs = {
                "model":      _m,
                "max_tokens": max_tokens,
                "system":     system,
                "messages":   messages,
            }
            if tools:
                _kwargs["tools"] = tools
            respuesta = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: cliente.messages.create(**_kwargs)),
                timeout=45.0,
            )
            # Métricas Prometheus — fail-silent
            if _metrics is not None:
                try:
                    _elapsed = _time.perf_counter() - _t0
                    _metrics.claude_latency_seconds.labels(model=_m).observe(_elapsed)
                    _metrics.claude_calls_total.labels(model=_m, outcome="ok").inc()
                    _usage = getattr(respuesta, "usage", None)
                    if _usage is not None:
                        _input_tok = getattr(_usage, "input_tokens", 0) or 0
                        _output_tok = getattr(_usage, "output_tokens", 0) or 0
                        _cache_read = getattr(_usage, "cache_read_input_tokens", 0) or 0
                        _cache_create = getattr(_usage, "cache_creation_input_tokens", 0) or 0
                        if _input_tok:
                            _metrics.claude_tokens_total.labels(model=_m, kind="input").inc(_input_tok)
                        if _output_tok:
                            _metrics.claude_tokens_total.labels(model=_m, kind="output").inc(_output_tok)
                        if _cache_read:
                            _metrics.claude_tokens_total.labels(model=_m, kind="cache_read").inc(_cache_read)
                        if _cache_create:
                            _metrics.claude_tokens_total.labels(model=_m, kind="cache_creation").inc(_cache_create)
                except Exception:
                    pass
            return respuesta
        except asyncio.TimeoutError:
            ultimo_error = asyncio.TimeoutError("La IA tardó demasiado en responder (>45s).")
        except Exception as e:
            ultimo_error = e
            error_str = str(e).lower()
            # Saldo agotado — error no recuperable, lanzar mensaje amigable inmediatamente
            if "credit balance" in error_str or "too low" in error_str or "billing" in error_str:
                logging.getLogger("ferrebot.ai").error("[CLAUDE] ❌ Saldo de API agotado")
                raise RuntimeError(
                    "⚠️ La IA no está disponible por falta de saldo en la API. "
                    "Puedes registrar ventas manualmente con el formato: "
                    "'anadir N producto = total'"
                )
            # Errores de autenticación — no recuperable
            if "401" in str(e) or "unauthorized" in error_str:
                raise
            # Errores no reintentables (ej. bad request, invalid param)
            _reintentable = (
                "529" in str(e) or "overload" in error_str
                or "503" in str(e) or "unavailable" in error_str
                or "429" in str(e) or "rate" in error_str
                or "connection" in error_str or "timeout" in error_str
                or "500" in str(e)
            )
            if not _reintentable:
                raise

        # Reintentar si quedan intentos
        if intento < max_reintentos - 1:
            logging.getLogger("ferrebot.ai").warning(
                f"[CLAUDE] Reintento {intento + 1}/{max_reintentos - 1} en 2s "
                f"(error: {type(ultimo_error).__name__})..."
            )
            await asyncio.sleep(2)

    # Agotamos los reintentos
    logging.getLogger("ferrebot.ai").error(
        f"[CLAUDE] ❌ Sin respuesta tras {max_reintentos} intentos: {ultimo_error}"
    )
    if _metrics is not None:
        try:
            _metrics.claude_calls_total.labels(model=_model, outcome="error").inc()
        except Exception:
            pass
    raise RuntimeError(_MSG_NO_DISPONIBLE)


async def procesar_con_claude(
    mensaje_usuario: str,
    nombre_usuario: str,
    historial_chat: list,
    contexto_extra: str = "",
    modelo_preferido: str = None,
    imagen_b64: str = None,
    imagen_media_type: str = None,
    vendedor_id: int | None = None,
) -> str:
    """
    Procesa un mensaje con Claude.  Si se pasa imagen_b64, se incluye la imagen
    en el mensaje (visión) y se omite el bypass Python (que no puede procesar imágenes).

    `vendedor_id` (opcional) habilita el control de budget diario por vendedor:
    si el vendedor ya agotó su cupo de Sonnet/Haiku del día, retorna un mensaje
    amistoso sin llamar a la API.  Si es None, no hay tracking por vendedor
    (modo legacy, ej. chat del dashboard sin JWT).
    """
    # BYPASS PYTHON — ANTES de alias_ferreteria (que transforma fracciones y rompería el match)
    # Solo se aplican aliases DINÁMICOS (simples word-substitutions: tiner→thinner, etc.)
    # El mensaje llega como "{vendedor}: {texto}" — stripear prefijo antes del bypass
    _dashboard_mode = "##DASHBOARD##" in mensaje_usuario
    # Canal de voz (app Android): estilo hablado + confirmación antes de registrar.
    # Se salta el bypass Python (igual que se hará abajo) para que Claude confirme.
    _voz_mode = "##VOZ##" in mensaje_usuario
    if _voz_mode:
        mensaje_usuario = mensaje_usuario.replace("##VOZ## ", "").replace("##VOZ##", "").strip()
    _tiene_imagen   = imagen_b64 is not None  # True cuando viene una foto del cuaderno
    _msg_bypass = re.sub(r'^[^:]+:\s*', '', mensaje_usuario).strip()
    # Mensaje crudo SIN aliases dinámicos — necesario para el resolutor de wayper:
    # un alias en BD reescribe "wayper blanco" → "WAYPER BLANCO UNIDAD" (default a
    # unidad), lo que ocultaría la ambigüedad kilo/unidad que el resolutor detecta.
    _msg_pre_alias = _msg_bypass
    _msg_bypass = alias_manager.aplicar_aliases_dinamicos(_msg_bypass)
    # ── FIX [PEDIDO ORIGINAL:] — sintetizar query limpia para MATCH ─────────
    # mensajes.py inyecta [PEDIDO ORIGINAL: X]\n[PREGUNTA DEL BOT:...]\n
    # [RESPUESTA DEL CLIENTE: Y] cuando guarda contexto pendiente (ej. tras
    # bypass-ambigüedad). Los corchetes y tokens basura ("[PEDIDO", "lija]", etc.)
    # rompen buscar_multiples_con_alias y producen un MATCH incorrecto o vacío.
    # Solución: extraer X e Y y sintetizar "_msg_bypass = X Y" para búsqueda limpia.
    # mensaje_usuario que Claude recibe queda intacto (contexto completo).
    _pfx_po_m = re.match(r'^[^:]+:\s*', mensaje_usuario)
    _pfx_po_s = _pfx_po_m.group(0) if _pfx_po_m else ""
    _po_m2    = re.search(r'\[PEDIDO ORIGINAL:\s*([^\]]+)\]', _msg_bypass, re.IGNORECASE)
    _rc_m2    = re.search(r'\[RESPUESTA DEL CLIENTE[^\]]*:\s*([^\]]+)\]', _msg_bypass, re.IGNORECASE)
    _override_msg_para_match: str | None = None
    if _po_m2 and _rc_m2:
        _msg_bypass = f"{_po_m2.group(1).strip()} {_rc_m2.group(1).strip()}"
        _msg_bypass = alias_manager.aplicar_aliases_dinamicos(_msg_bypass)
        _override_msg_para_match = f"{_pfx_po_s}{_msg_bypass}"
        # Versión limpia (pre-alias) del pedido sintetizado, para el resolutor de
        # wayper en multi-turno ("2 wayper blanco" + "por unidad" → "2 wayper blanco por unidad").
        _po_raw = re.search(r'\[PEDIDO ORIGINAL:\s*([^\]]+)\]', _msg_pre_alias, re.IGNORECASE)
        _rc_raw = re.search(r'\[RESPUESTA DEL CLIENTE[^\]]*:\s*([^\]]+)\]', _msg_pre_alias, re.IGNORECASE)
        if _po_raw and _rc_raw:
            _msg_pre_alias = f"{_po_raw.group(1).strip()} {_rc_raw.group(1).strip()}"
        logging.getLogger("ferrebot.ai").info(
            "[PEDIDO-ORIG] sintetizando para MATCH: '%s'", _msg_bypass[:80]
        )
    memoria = cargar_memoria()
    # ── Resolutor determinista de wayper (MEDIUM-7) ──────────────────────────
    # El wayper se vende por kilo/medio kilo/unidad, en blanco o color. Se decide
    # determinísticamente: con palabra de peso (kg/kilo/...) → kilo; un número
    # pelado sin peso → unidad (regla del negocio, NO se pregunta).
    if not _tiene_imagen and not _dashboard_mode and not _voz_mode:
        _way = bypass.resolver_wayper(_msg_pre_alias, memoria.get("catalogo", {}))
        if _way:
            import json as _jw
            # resolver_wayper solo devuelve ("venta", dict) o None (ver su docstring).
            _wkind, _wval = _way
            _wtxt = f"{_wval['cantidad']:g} {_wval['producto']} — ${_wval['total']:,.0f}"
            return f"{_wtxt}\n[VENTA]{_jw.dumps(_wval, ensure_ascii=False)}[/VENTA]"
    # Las fotos con imagen no pueden pasar por el bypass Python (no hay texto estructurado).
    # En voz tampoco: siempre pasa a Claude para confirmar hablando antes de registrar.
    # Solo intentar bypass cuando NO hay imagen y NO es voz.
    if _tiene_imagen or _voz_mode:
        _bypass = None
    else:
        if _metrics is not None:
            with _metrics.timer(_metrics.bypass_latency_seconds):
                _bypass = bypass.intentar_bypass_python(_msg_bypass, memoria.get("catalogo", {}))
        else:
            _bypass = bypass.intentar_bypass_python(_msg_bypass, memoria.get("catalogo", {}))
        if _bypass is not None and _metrics is not None:
            try:
                _metrics.bypass_hits_total.inc()
            except Exception:  # noqa: BLE001
                pass
    # Con IA_TOOL_CALLING activo: anular bypass si el producto es ambiguo (hay
    # múltiples variantes del mismo producto base sin que el vendedor especificara cuál).
    # Esto permite que el BYPASS AMBIGÜEDAD más abajo genere la pregunta determinista.
    if _bypass and config.IA_TOOL_CALLING and not _tiene_imagen:
        from memoria import buscar_multiples_con_alias
        from ai.prompt_products import _detectar_ambiguedad_variante, _detectar_ambiguedad_segmentos
        _cands_q = buscar_multiples_con_alias(_msg_bypass, limite=20)
        # Whole-message + per-segment (MP-1): en multiproducto la búsqueda global
        # se llena de variantes de un solo producto y oculta la ambigüedad de otro
        # (ej "1 lija, 2 tornillos 6x1" → el bypass resolvía lija→N°60 callado).
        if (_detectar_ambiguedad_variante(_cands_q, _msg_bypass)
                or _detectar_ambiguedad_segmentos(_msg_bypass)):
            logging.getLogger("ferrebot.ai").info(
                "[AMBIGUO] bypass anulado por ambigüedad: '%s'", _msg_bypass[:60]
            )
            _bypass = None

    if _bypass:
        import json as _jbp
        _txt, _venta = _bypass
        # Multi-producto: expandir a múltiples tags [VENTA]
        if _venta.get("multi"):
            _tags = ""
            for _item in _venta.get("items", []):
                _v = {
                    "producto":        _item["producto"],
                    "cantidad":        _item["cantidad"],
                    "total":           _item["total"],
                    "precio_unitario": _item["precio_unitario"],
                    "metodo_pago":     "",
                }
                _tags += f"[VENTA]{_jbp.dumps(_v, ensure_ascii=False)}[/VENTA]"
            return f"{_txt}\n{_tags}"
        # Single producto
        return f"{_txt}\n[VENTA]{_jbp.dumps(_venta, ensure_ascii=False)}[/VENTA]"

    logging.getLogger("ferrebot.ai").info(f"[→ CLAUDE] '{_msg_bypass[:60]}'")

    # Alias solo para Claude — después de que bypass descartó el mensaje
    mensaje_usuario = aplicar_alias_ferreteria(mensaje_usuario)

    parte_estatica = _construir_parte_estatica(memoria, solo_voz=_voz_mode)

    # ── FIX MULTI-TURNO: si el mensaje actual es una clarificación corta ──────
    # Cuando el bot pregunta "¿qué tamaño?" y el usuario responde solo con
    # "Segmentado de 4", construir_seccion_match() solo ve esa respuesta y no
    # encuentra candidatos para brocha/rodillo/teflón del turno anterior.
    # Solución: detectar clarificaciones y augmentar el mensaje usado para
    # candidatos con el contenido del último turno del usuario en el historial.
    # IMPORTANTE: solo se usa para construir candidatos — el mensaje real que
    # va a Claude sigue siendo mensaje_usuario sin modificar.
    #
    # V-11 (Sprint 3): tres guards adicionales para evitar falsos positivos
    # del estilo "Hola" → bot intentando registrar venta de cerraduras de
    # hace una hora. Sin estos guards, cualquier mensaje corto sin coma se
    # interpretaba como continuación del último turno del usuario, aunque
    # ese turno fuera de horas atrás o de otro vendedor en el mismo grupo.
    _msg_para_match = mensaje_usuario
    _msg_para_match_augmented = False
    if historial_chat:
        _palabras_match = [w for w in _msg_bypass.lower().split() if len(w) > 2]
        _es_clarificacion = len(_palabras_match) <= 6 and "," not in _msg_bypass

        # Guard 1: lista de "no-clarificaciones" obvias (saludos, agradecimientos,
        # respuestas afirmativas/negativas, muletillas). Si el mensaje (en su
        # forma normalizada, sin el prefijo "Vendedor: ") es exactamente uno
        # de estos términos o empieza por uno, NO es continuación de nada.
        if _es_clarificacion:
            # Quitar prefijo "Vendedor: " si está presente para el chequeo.
            _msg_limpio = _msg_bypass.lower().strip()
            if ":" in _msg_limpio:
                _msg_limpio = _msg_limpio.split(":", 1)[1].strip()
            _NO_CLARIFICACIONES = {
                "hola", "buenas", "buenas tardes", "buenos dias", "buenos días",
                "buenas noches", "saludos", "ola", "hey",
                "gracias", "muchas gracias", "ok", "vale", "listo", "dale",
                "perfecto", "si", "sí", "no", "ya", "claro",
                "jaja", "jeje", "jajaja", "mmm", "mm",
                "chao", "adios", "adiós", "hasta luego", "bye",
                "?", "??", "???",
            }
            if _msg_limpio in _NO_CLARIFICACIONES:
                _es_clarificacion = False
                logging.getLogger("ferrebot.ai").info(
                    "[multi-turno] descartado — saludo/muletilla: '%s'", mensaje_usuario[:60]
                )

        # Guard 2: solo augmentar si el ÚLTIMO turno del assistant terminó en
        # pregunta. Si el bot no preguntó nada, no hay razón para asumir que
        # el usuario está aclarando algo.
        if _es_clarificacion:
            _ultimo_assistant = None
            for _hmsg in reversed(historial_chat):
                if _hmsg.get("role") == "assistant":
                    _ultimo_assistant = _hmsg.get("content", "") or ""
                    break
            if not _ultimo_assistant or "?" not in _ultimo_assistant:
                _es_clarificacion = False
                if _ultimo_assistant is not None:
                    logging.getLogger("ferrebot.ai").info(
                        "[multi-turno] descartado — bot no preguntó nada en el turno anterior"
                    )

        if _es_clarificacion:
            for _hmsg in reversed(historial_chat):
                if _hmsg.get("role") == "user":
                    _prev_content = _hmsg.get("content", "")
                    # Solo augmentar si el mensaje previo tiene más contexto de productos
                    if isinstance(_prev_content, str) and len(_prev_content) > len(mensaje_usuario):
                        _msg_para_match = _prev_content + ", " + mensaje_usuario
                        _msg_para_match_augmented = True
                        # Sintetizar el mensaje completo para Claude: pedido original + aclaración
                        # "Test: 1 lija" + "Test: 120" → "Test: 1 lija 120"
                        # Así Claude recibe toda la info en un turno y puede registrar directo.
                        _bare_prev = re.sub(r'^[^:]+:\s*', '', _prev_content).strip()
                        _bare_curr = re.sub(r'^[^:]+:\s*', '', mensaje_usuario).strip()
                        _pfx_m     = re.match(r'^[^:]+:\s*', mensaje_usuario)
                        _pfx       = _pfx_m.group(0) if _pfx_m else ""
                        mensaje_usuario = f"{_pfx}{_bare_prev} {_bare_curr}"
                        logging.getLogger("ferrebot.ai").info(
                            "[multi-turno] clarificación — augmentando match y mensaje: "
                            "'%s' → '%s'", _msg_para_match[:80], mensaje_usuario[:80]
                        )
                    break

    # Aplicar override de [PEDIDO ORIGINAL:] si multi-turno no augmentó el mensaje.
    if not _msg_para_match_augmented and _override_msg_para_match is not None:
        _msg_para_match = _override_msg_para_match

    parte_dinamica = _construir_parte_dinamica(_msg_para_match, nombre_usuario, memoria, solo_voz=_voz_mode)

    # Fix 2+3: cuando hay imagen, inyectar catalogo completo con fracciones
    # + skill foto_cuaderno al frente de la parte dinamica.
    # El MATCH normal llega vacio porque el texto es 'foto de ventas',
    # asi Claude tiene todo el catalogo disponible para identificar productos.
    if _tiene_imagen:
        _cat_img    = _construir_catalogo_imagen(memoria)
        _skill_foto = skill_loader.obtener_skill("foto_cuaderno")
        _extra      = "\n\n".join(p for p in [_skill_foto, _cat_img] if p)
        if _extra:
            parte_dinamica = _extra + "\n\n" + parte_dinamica

    # Clasificadores de intención — usados por BYPASS AMBIGÜEDAD y MATCH dinámico.
    _kw_no_venta = {"cuanto","vendimos","reporte","analiz","resumen","estadistica",
                    "top","mas vendido","gasto","caja","inventario","cliente",
                    "precio","vale","cuesta","cuanto vale","hay","stock","quedan"}
    _es_consulta = any(p in mensaje_usuario.lower() for p in _kw_no_venta)
    _kw_venta_varia = {"venta varia", "ventas varia", "venta general",
                       "ventas del dia", "ventas del día", "cuadre de caja",
                       "cuadre caja", "no alcance a anotar", "no alcancé a anotar"}
    _es_venta_varia = any(kw in mensaje_usuario.lower() for kw in _kw_venta_varia)

    # BYPASS AMBIGÜEDAD DETERMINISTA (M-01): si el MATCH ya detectó múltiples
    # variantes del mismo producto sin que el vendedor especificara cuál, preguntar
    # en Python sin gastar una llamada a Claude. Solo con IA_TOOL_CALLING activo.
    _SEÑAL_AMBIGUO = "⚠️ AMBIGUO"
    if ((config.IA_TOOL_CALLING or _voz_mode)
            and _SEÑAL_AMBIGUO in parte_dinamica
            and not _es_consulta
            and not _dashboard_mode
            and not _es_venta_varia
            and not _tiene_imagen
            and "=" not in mensaje_usuario
            and "$" not in mensaje_usuario):
        from ai.prompt_products import _etiquetas_ambiguedad
        _idx_amb = parte_dinamica.find(_SEÑAL_AMBIGUO)
        _lineas_amb = [l.strip() for l in parte_dinamica[_idx_amb:_idx_amb + 400].split('\n') if l.strip()]
        _opciones_linea = _lineas_amb[1] if len(_lineas_amb) > 1 else ""
        if _opciones_linea:
            _ops = [o.strip() for o in _opciones_linea.split(',') if o.strip()]
            _prefijo, _etqs, _son_num = _etiquetas_ambiguedad(_ops)
            # Solo resolvemos en Python el caso NUMÉRICO (lija N°, tornillo 6x2…).
            # El caso por palabra/color (vinilo T1 Lila/Ocre…) lo deja a Claude,
            # que ve los nombres completos en el nudge y pregunta con naturalidad.
            if _son_num and len(_etqs) >= 2:
                try:
                    _etqs.sort(key=lambda x: [int(n) for n in re.findall(r'\d+', x)] or [0])
                except ValueError:
                    pass
                _pref_disp = (_prefijo[0].upper() + _prefijo[1:]) if _prefijo else _ops[0]
                _ops_str = ', '.join(_etqs[:10])
                logging.getLogger("ferrebot.ai").info(
                    "[AMBIGUO-BYPASS] '%s' → pregunta determinista: %s", mensaje_usuario[:60], _ops_str
                )
                return f"¿{_pref_disp} de qué número? Tengo: {_ops_str}."

    _modo = "MATCH+SIMPLE-CAT 💡"  # fracciones en MATCH, precio_unidad en estático

    # Historial adaptativo: usa _calcular_historial para determinar cuántos mensajes
    _n_hist = _calcular_historial(mensaje_usuario)

    messages = []
    for msg in historial_chat[-_n_hist:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({"role": str(msg["role"]), "content": str(msg["content"])})

    # Construir contenido del mensaje de usuario.
    # Con imagen: lista [image_block, text_block] — visión de Claude activa.
    # Sin imagen: string simple (comportamiento original).
    if _tiene_imagen:
        _user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": imagen_media_type or "image/jpeg",
                    "data": imagen_b64,
                },
            },
            {
                "type": "text",
                "text": mensaje_usuario or "Transcribe las ventas anotadas en esta foto.",
            },
        ]
    else:
        _user_content = str(mensaje_usuario)

    messages.append({"role": "user", "content": _user_content})

    # max_tokens adaptativo por tipo de mensaje:
    # - Venta simple (1 producto, sin comas ni saltos): solo JSON → 400 tok
    # - Venta multi-producto: JSON × N productos + posible texto → 250 × lineas
    # - Consulta/reporte/modificacion: respuesta larga → 2000 mínimo
    _kw_reporte = {"cuanto","vendimos","reporte","analiz","resumen","estadistica",
                   "grafica","top","mas vendido","gasto","caja","inventario"}
    _kw_edicion = {"modificar","corregir","cambia","quita","agrega","error",
                   "equivoque","fiado","debe","abono","borrar","eliminar"}
    num_lineas = mensaje_usuario.count("\n") + mensaje_usuario.count(",") + 1
    _msg_low   = mensaje_usuario.lower()
    if _tiene_imagen:
        max_tokens = 3000          # imagen: puede tener varios productos
    elif any(p in _msg_low for p in _kw_reporte):
        max_tokens = 2000          # reportes necesitan espacio
    elif any(p in _msg_low for p in _kw_edicion):
        max_tokens = 1200          # ediciones: algo de texto + JSON
    elif num_lineas == 1 and "," not in mensaje_usuario:
        max_tokens = 450           # venta simple: solo JSON, ~150 tok reales
    else:
        max_tokens = min(3000, max(800, num_lineas * 220))  # multi-producto

    # ── MEJORA B: Separar contexto en bloques cacheables ────────────────────
    # Bloque 1: parte estática del prompt (reglas, catálogo comprimido) — muy estable
    # Bloque 2: parte dinámica (MATCH, candidatos del mensaje) — cambia por mensaje
    # Bloque 3 (dashboard): catálogo completo — estable, cacheable
    # Bloque 4 (dashboard): datos del día — cambia cada hora
    #
    # TTL "1h": el beta `extended-cache-ttl-2025-04-11` permite guardar el cache
    # por 1 hora en lugar de los 5 min default. Escribir con TTL 1h cuesta 2× el
    # precio base (vs. 1.25× de 5min), pero amortiza mucho mejor porque el
    # catálogo no cambia durante el día de trabajo del vendedor.
    _cache_1h = {"type": "ephemeral", "ttl": "1h"}
    system = [
        {
            "type": "text",
            "text": parte_estatica,
            "cache_control": _cache_1h,
        },
        {
            "type": "text",
            "text": parte_dinamica,
        },
    ]

    # En voz: anteponer instrucciones de estilo hablado (sin caché — bloque corto).
    if _voz_mode:
        system.append({"type": "text", "text": VOZ_INSTRUCCIONES})

    if contexto_extra:
        # Separar catálogo (estático) de datos del día (dinámico)
        _sep = "## ESTADO DEL NEGOCIO"
        if _sep in contexto_extra:
            _partes_ctx = contexto_extra.split(_sep, 1)
            _ctx_estatico = _partes_ctx[0].strip()   # identidad + catálogo
            _ctx_dinamico = (_sep + _partes_ctx[1]).strip()  # datos del día
            # Bloque estático (catálogo): se cachea de forma independiente
            system.append({
                "type": "text",
                "text": _ctx_estatico,
                "cache_control": _cache_1h,
            })
            # Bloque dinámico (datos del día): sin caché, cambia constantemente
            system.append({
                "type": "text",
                "text": _ctx_dinamico,
            })
        else:
            system.append({
                "type": "text",
                "text": contexto_extra,
                "cache_control": _cache_1h,
            })

    # ── MEJORA A: Extended Thinking para análisis complejos ──────────────────
    _kw_thinking = {
        "analiz", "analís", "por qué", "porqué", "recomienda", "suger",
        "proyecc", "estrateg", "diagnos", "evalua", "evalúa",
        "debería", "deberia", "conviene", "vale la pena",
        "cuánto me queda", "cuanto me queda", "ganancia", "utilidad",
        "compara", "tendencia", "predic", "próximo mes", "proximo mes",
    }
    _usar_thinking = (
        _dashboard_mode
        and modelo_preferido != "haiku"
        and any(kw in mensaje_usuario.lower() for kw in _kw_thinking)
    )

    # Elegir modelo según preferencia o auto-selección
    if modelo_preferido == "sonnet":
        _modelo_no_stream = MODELO_SONNET
    elif modelo_preferido == "haiku":
        _modelo_no_stream = MODELO_HAIKU
    else:
        # Voz incluida: auto-router (Sonnet solo si el mensaje es complejo/ambiguo).
        # El costo por turno de voz es ínfimo igual; la precisión la da la
        # confirmación hablada, no forzar Sonnet.
        _modelo_no_stream = _elegir_modelo(mensaje_usuario)

    # Telemetría de voz (P0.1): registra el modelo elegido. No-op fuera de voz.
    from ai import voz_telemetria as _voz_tel
    _voz_tel.set_modelo(_modelo_no_stream)

    # ── BUDGET CHECK ─────────────────────────────────────────────────────────
    # Antes de gastar una llamada, verificar que el vendedor aún tenga cupo
    # diario para el modelo elegido. Si agotó, devolver un mensaje amistoso
    # sin llamar a la API (fail-open si DB está caída o no hay vendedor_id).
    _ok, _mensaje_budget = _budget.puede_llamar(vendedor_id, _modelo_no_stream)
    if not _ok:
        return _mensaje_budget

    if _usar_thinking:
        # Extended Thinking: Claude razona antes de responder
        # budget_tokens = tokens de pensamiento (no visibles al usuario)
        # max_tokens debe ser > budget_tokens
        # NOTA: usar _thinking_budget_tokens (NO _budget) para no tapar el módulo ai.budget
        _thinking_budget_tokens = 8000
        _max_thinking = max(max_tokens, _thinking_budget_tokens + 2000)
        try:
            loop = asyncio.get_event_loop()
            respuesta = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: config.claude_client.messages.create(
                        model=MODELO_SONNET,
                        max_tokens=_max_thinking,
                        thinking={"type": "enabled", "budget_tokens": _thinking_budget_tokens},
                        system=system,
                        messages=messages,
                    )
                ),
                timeout=90.0,  # thinking necesita más tiempo
            )
            logging.getLogger("ferrebot.ai").info(
                f"[THINKING] ✅ Análisis con extended thinking activado"
            )
        except Exception as _e_think:
            logging.getLogger("ferrebot.ai").warning(
                f"[THINKING] Falló, usando Sonnet normal: {_e_think}"
            )
            respuesta = await _llamar_claude_con_reintentos(
                config.claude_client, max_tokens, system, messages,
                model=_modelo_no_stream
            )
    else:
        # M-01: tool-calling nativo cuando el flag está activo. tool_choice="auto"
        # (default) deja que Claude decida entre llamar la herramienta o preguntar.
        # En VOZ siempre se usa (más robusto para clasificar intención: venta vs
        # gasto vs fiado), sin depender del flag global que rige bot/dashboard.
        # Voz suma crear_cliente (Fase 4.5); bot/dashboard usan su propio wizard.
        if _voz_mode:
            _tools = tools_mod.TOOLS_VOZ
        elif config.IA_TOOL_CALLING:
            _tools = tools_mod.TOOLS
        else:
            _tools = None
        respuesta = await _llamar_claude_con_reintentos(
            config.claude_client, max_tokens, system, messages,
            model=_modelo_no_stream, tools=_tools,
        )

    # ── Registro de uso + log de cache ─────────────────────────────────────────
    # Todo el cálculo de costo lo hace ai.budget.registrar_uso con los precios
    # actualizados (Sonnet 4.6 y Haiku 4.5) y los persiste en api_costo_diario.
    # Retorna el costo USD de esta llamada específica para incluirlo en el log.
    uso           = respuesta.usage
    cache_read    = getattr(uso, "cache_read_input_tokens",     0) or 0
    cache_created = getattr(uso, "cache_creation_input_tokens", 0) or 0
    input_normal  = getattr(uso, "input_tokens",                0) or 0
    output_tokens = getattr(uso, "output_tokens",               0) or 0

    _costo_llamada = _budget.registrar_uso(
        vendedor_id, _modelo_no_stream, uso, cache_ttl="1h"
    )

    if cache_read > 0 or cache_created > 0:
        logging.getLogger("ferrebot.cache").info(
            f"[CACHE] ✅ hit={cache_read} tok | created={cache_created} tok | "
            f"input={input_normal} tok | output={output_tokens} tok | "
            f"costo≈${_costo_llamada:.5f}"
        )
    else:
        logging.getLogger("ferrebot.cache").warning(
            f"[CACHE] ⚠️ SIN CACHE — input={input_normal} tok | "
            f"output={output_tokens} tok | costo≈${_costo_llamada:.5f}"
        )

    # M-01: con tool-calling, la respuesta puede traer bloques tool_use además
    # de texto. El puente los convierte a tags [VENTA] que procesar_acciones ya
    # consume. El thinking path no usa tools → conserva el return clásico.
    if (config.IA_TOOL_CALLING or _voz_mode) and not _usar_thinking:
        # ── RIEL R2 (solo voz): no registrar productos que no existen ─────────
        # El prompt ya prohíbe inventar productos, pero eso es a nivel modelo y
        # puede fallar (alucinación, transcripción dudosa). Como riel de CÓDIGO,
        # si registrar_venta trae un producto que ni el fuzzy match resuelve en
        # el catálogo, NO se registra: se pide aclaración hablada. Scoped a voz
        # para no alterar bot/dashboard (que usan IA_TOOL_CALLING).
        if _voz_mode:
            _existe = lambda n: buscar_producto_en_catalogo(n) is not None
            _desconocidos = tools_mod.ventas_con_producto_desconocido(
                respuesta.content, _existe
            )
            if _desconocidos:
                _voz_tel.set_riel("R2")
                logging.getLogger("ferrebot.ai").info(
                    "[R2-VOZ] producto(s) fuera de catálogo, no registro: %s", _desconocidos
                )
                _lista = (_desconocidos[0] if len(_desconocidos) == 1
                          else ", ".join(_desconocidos))
                # Conservar el contexto del pedido: si OTROS productos del mismo
                # turno sí existen, recordarlos en la pregunta. Quedan explícitos
                # en el historial → el turno de aclaración retoma la venta completa.
                _conocidas = tools_mod.ventas_conocidas(respuesta.content, _existe)
                _prefijo = ""
                if _conocidas:
                    _resumen = ", ".join(
                        f"{_cantidad_legible_voz(c.get('cantidad', 1))} "
                        f"{c.get('producto', '')}".strip()
                        for c in _conocidas
                    )
                    _prefijo = f"Entendí {_resumen}, pero "
                _cola = "no encontré" if _prefijo else "No encontré"
                # Fallback semántico: si el nombre no resuelve léxico ni con fuzzy
                # pero hay un producto cercano en SENTIDO, ofrecerlo para confirmar
                # (sin registrar aún). Fail-safe: si no hay match, pregunta genérica.
                if len(_desconocidos) == 1:
                    _sug = _semantic.sugerencia_semantica(_desconocidos[0])
                    if _sug:
                        return f"{_prefijo}{_cola} {_lista} en el catálogo. ¿Quisiste decir {_sug}?"
                return (f"{_prefijo}{_cola} {_lista} en el catálogo. "
                        f"¿Me lo repetís o es otro producto?")

            # ── RIEL R2-precio (solo voz): total dicho vs catálogo ────────────
            # Llega acá solo con productos CONOCIDOS (la existencia ya pasó). Si
            # el vendedor NO declaró precio y el total que puso Claude no cuadra
            # con el del catálogo (precio×cantidad), es alucinación de precio: no
            # se registra, se confirma hablado con el precio real. No se auto-
            # corrige porque la prosa hablada de Claude ya dijo el monto.
            _dudosas = tools_mod.ventas_con_precio_dudoso(
                respuesta.content, obtener_precio_para_cantidad
            )
            if _dudosas:
                _voz_tel.set_riel("R2-precio")
                logging.getLogger("ferrebot.ai").info(
                    "[R2-PRECIO-VOZ] total no cuadra con catálogo, no registro: %s",
                    _dudosas,
                )
                _d = _dudosas[0]
                _cant_voz = _cantidad_legible_voz(_d["cantidad"])
                return (f"Para {_cant_voz} {_d['producto']} el precio es "
                        f"{_d['total_catalogo']}. ¿Lo registro así o el precio es otro?")

            # ── Confirmar-antes-de-registrar gasto/fiado/abono/cliente (voz) ──
            # Estas mutaciones se registraban de una. Se proponen habladas y se
            # registran al confirmar. La confirmación se detecta de forma ROBUSTA:
            #   (a) el vendedor afirma ("sí", "dale", "confirmo"), o
            #   (b) re-propongo EXACTAMENTE lo mismo que el turno anterior y el
            #       vendedor no niega → está confirmando (aguanta typos de Whisper
            #       como "regítralo" o "confirma reistraduración" que (a) no capta).
            # Si cambió algún dato, la propuesta cambia → se re-propone con lo nuevo.
            _conf_mut = tools_mod.confirmacion_mutaciones_voz(respuesta.content)
            if _conf_mut:
                _afirma = es_afirmacion_voz(mensaje_usuario)
                _prev   = _ultima_respuesta_asistente(historial_chat)
                _repite = bool(_prev) and _norm_cmp_voz(_prev) == _norm_cmp_voz(_conf_mut)
                _confirmado = _afirma or (_repite and not es_negacion_voz(mensaje_usuario))
                if not _confirmado:
                    _voz_tel.set_riel("CONFIRM-VOZ")
                    logging.getLogger("ferrebot.ai").info(
                        "[CONFIRM-VOZ] propongo y espero confirmación: %s", _conf_mut
                    )
                    return _conf_mut
                logging.getLogger("ferrebot.ai").info(
                    "[CONFIRM-VOZ] confirmado (afirma=%s repite=%s) → registro", _afirma, _repite
                )
        return tools_mod.tool_uses_a_tags(respuesta.content)
    return respuesta.content[0].text

async def _stream_claude_chunks(system: list, messages: list, max_tokens: int, model: str = MODELO_SONNET, tools: list | None = None):
    """
    Async generator que hace streaming de Claude usando un thread + asyncio.Queue.
    Yields: ("chunk", text_piece) durante el stream
            ("usage", usage_obj)  justo antes de "done" (para tracking de costo)
            ("done",  full_text)  al finalizar
            ("error", error_str)  en caso de fallo

    M-01: si `tools` viene, los text deltas se streamean igual (la prosa que
    Claude emita), pero el payload de "done" se arma desde get_final_message()
    con el puente tool_uses_a_tags — así los bloques tool_use (que NO salen por
    text_stream) se convierten a tags [VENTA] para procesar_acciones.
    """
    import threading
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _sync_worker():
        try:
            _kwargs = {
                "model":      model,
                "max_tokens": max_tokens,
                "system":     system,
                "messages":   messages,
            }
            if tools:
                _kwargs["tools"] = tools
            with config.claude_client.messages.stream(**_kwargs) as stream:
                full = ""
                for text in stream.text_stream:
                    full += text
                    loop.call_soon_threadsafe(q.put_nowait, ("chunk", text))
                # Extraer usage + content final para tracking de costo y tools
                _usage = None
                _final = None
                try:
                    _final = stream.get_final_message()
                    _usage = getattr(_final, "usage", None)
                except Exception:
                    _usage = None
                loop.call_soon_threadsafe(q.put_nowait, ("usage", _usage))
                if tools and _final is not None:
                    _done_payload = tools_mod.tool_uses_a_tags(_final.content)
                else:
                    _done_payload = full
                loop.call_soon_threadsafe(q.put_nowait, ("done", _done_payload))
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, ("error", str(exc)))

    threading.Thread(target=_sync_worker, daemon=True).start()

    while True:
        kind, data = await q.get()
        yield kind, data
        if kind in ("done", "error"):
            break


async def procesar_con_claude_stream(
    mensaje_usuario: str,
    nombre_usuario: str,
    historial_chat: list,
    contexto_extra: str = "",
    modelo_preferido: str = None,
    vendedor_id: int | None = None,
):
    """
    Versión streaming de procesar_con_claude.
    Yields: ("chunk", text)   — fragmento de texto mientras Claude responde
            ("done",  text)   — texto completo final
            ("error", msg)    — error
    Si el bypass Python intercepta, devuelve ("done", respuesta) de inmediato.

    `vendedor_id` (opcional) habilita el control de budget diario: si el vendedor
    ya agotó su cupo del modelo elegido, se devuelve un mensaje amistoso sin
    llamar a la API (fail-open si no hay DB o vendedor).
    """
    import re as _re_s
    import json as _json_s

    # ── Detectar modo dashboard y limpiar flag ────────────────────────────────
    _dashboard_mode = "##DASHBOARD##" in mensaje_usuario
    if _dashboard_mode:
        mensaje_usuario = mensaje_usuario.replace("##DASHBOARD## ", "").replace("##DASHBOARD##", "").strip()

    # ── Detectar canal de VOZ y limpiar flag ──────────────────────────────────
    # El asistente de voz (app Android) antepone ##VOZ##. Cambia el ESTILO de la
    # respuesta (hablada, sin símbolos) y exige confirmación antes de registrar,
    # por eso se SALTA el bypass Python (que auto-registra sin confirmar en voz).
    _voz_mode = "##VOZ##" in mensaje_usuario
    if _voz_mode:
        mensaje_usuario = mensaje_usuario.replace("##VOZ## ", "").replace("##VOZ##", "").strip()

    # ── Bypass Python ─────────────────────────────────────────────────────────
    _msg_bypass = _re_s.sub(r'^[^:]+:\s*', '', mensaje_usuario).strip()
    _msg_bypass = alias_manager.aplicar_aliases_dinamicos(_msg_bypass)
    memoria = cargar_memoria()
    # En voz: no usar bypass — siempre pasa a Claude para confirmar hablando.
    _bp = None if _voz_mode else bypass.intentar_bypass_python(_msg_bypass, memoria.get("catalogo", {}))

    # Con IA_TOOL_CALLING activo: anular bypass si el producto es ambiguo
    if _bp and config.IA_TOOL_CALLING:
        from memoria import buscar_multiples_con_alias
        from ai.prompt_products import _detectar_ambiguedad_variante, _detectar_ambiguedad_segmentos
        _cands_qs = buscar_multiples_con_alias(_msg_bypass, limite=20)
        if (_detectar_ambiguedad_variante(_cands_qs, _msg_bypass)
                or _detectar_ambiguedad_segmentos(_msg_bypass)):
            logging.getLogger("ferrebot.ai").info(
                "[AMBIGUO] bypass-stream anulado por ambigüedad: '%s'", _msg_bypass[:60]
            )
            _bp = None

    if _bp:
        _txt, _venta = _bp
        if _venta.get("multi"):
            _tags = ""
            for _item in _venta.get("items", []):
                _v = {
                    "producto":        _item["producto"],
                    "cantidad":        _item["cantidad"],
                    "total":           _item["total"],
                    "precio_unitario": _item["precio_unitario"],
                    "metodo_pago":     "",
                }
                _tags += f"[VENTA]{_json_s.dumps(_v, ensure_ascii=False)}[/VENTA]"
            yield ("done", f"{_txt}\n{_tags}")
        else:
            yield ("done", f"{_txt}\n[VENTA]{_json_s.dumps(_venta, ensure_ascii=False)}[/VENTA]")
        return

    # ── Construir prompt ──────────────────────────────────────────────────────
    mensaje_usuario = aplicar_alias_ferreteria(mensaje_usuario)
    parte_estatica  = _construir_parte_estatica(memoria, solo_voz=_voz_mode)
    parte_dinamica  = _construir_parte_dinamica(
        mensaje_usuario, nombre_usuario, memoria, dashboard_mode=_dashboard_mode, solo_voz=_voz_mode
    )

    # ── MATCH vacío: solo en Telegram, no en dashboard ────────────────────────
    _MATCH_VACIO = "MATCH: (sin resultados — producto no encontrado en catalogo)"
    _kw_consulta = {"cuanto","vendimos","reporte","analiz","resumen","estadistica",
                    "top","mas vendido","gasto","caja","inventario","cliente",
                    "precio","vale","cuesta","cuanto vale","hay","stock","quedan"}
    _es_consulta = any(p in mensaje_usuario.lower() for p in _kw_consulta)
    # EXCEPCIÓN: venta varia siempre pasa a Claude aunque no esté en catálogo
    _kw_venta_varia2 = {"venta varia", "ventas varia", "venta general",
                        "ventas del dia", "ventas del día", "cuadre de caja",
                        "cuadre caja", "no alcance a anotar", "no alcancé a anotar"}
    _es_venta_varia2 = any(kw in mensaje_usuario.lower() for kw in _kw_venta_varia2)
    # Sin dígitos → no puede ser venta (no hay cantidad/precio) → dejar pasar a Claude
    _tiene_numeros2 = bool(re.search(r'\d', _msg_bypass))
    if _MATCH_VACIO in parte_dinamica and not _es_consulta and not _dashboard_mode and not _es_venta_varia2 and _tiene_numeros2:
        _msg_lp = re.sub(r'^[\d\s/\.]+', '', mensaje_usuario.strip().lower()).strip()
        _msg_lp = re.sub(r'^(kilo|kilos|galon|galones|metro|metros|unidad|unidades|litro|litros)\s*', '', _msg_lp).strip()
        yield ("done", f"No tengo {_msg_lp} en el catálogo.")
        return

    # BYPASS AMBIGÜEDAD DETERMINISTA (M-01) — versión stream
    _SEÑAL_AMBIGUO2 = "⚠️ AMBIGUO"
    if ((config.IA_TOOL_CALLING or _voz_mode)
            and _SEÑAL_AMBIGUO2 in parte_dinamica
            and not _es_consulta
            and not _dashboard_mode
            and not _es_venta_varia2
            and "=" not in mensaje_usuario
            and "$" not in mensaje_usuario):
        from ai.prompt_products import _etiquetas_ambiguedad
        _idx_amb2 = parte_dinamica.find(_SEÑAL_AMBIGUO2)
        _lineas_amb2 = [l.strip() for l in parte_dinamica[_idx_amb2:_idx_amb2 + 400].split('\n') if l.strip()]
        _opciones_linea2 = _lineas_amb2[1] if len(_lineas_amb2) > 1 else ""
        if _opciones_linea2:
            _ops2 = [o.strip() for o in _opciones_linea2.split(',') if o.strip()]
            _prefijo2, _etqs2, _son_num2 = _etiquetas_ambiguedad(_ops2)
            if _son_num2 and len(_etqs2) >= 2:
                try:
                    _etqs2.sort(key=lambda x: [int(n) for n in re.findall(r'\d+', x)] or [0])
                except ValueError:
                    pass
                _pref_disp2 = (_prefijo2[0].upper() + _prefijo2[1:]) if _prefijo2 else _ops2[0]
                _ops_str2 = ', '.join(_etqs2[:10])
                logging.getLogger("ferrebot.ai").info(
                    "[AMBIGUO-BYPASS] stream '%s' → pregunta determinista: %s",
                    mensaje_usuario[:60], _ops_str2
                )
                yield ("done", f"¿{_pref_disp2} de qué número? Tengo: {_ops_str2}.")
                return

    # ── Historial ─────────────────────────────────────────────────────────────
    _n_hist = _calcular_historial(mensaje_usuario)
    messages = []
    for msg in historial_chat[-_n_hist:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
    messages.append({"role": "user", "content": str(mensaje_usuario)})

    # ── max_tokens ────────────────────────────────────────────────────────────
    _kw_rep = {"cuanto","vendimos","reporte","analiz","resumen","estadistica",
               "grafica","top","mas vendido","gasto","caja","inventario"}
    _kw_edi = {"modificar","corregir","cambia","quita","agrega","error",
               "equivoque","fiado","debe","abono","borrar","eliminar"}
    _nl  = mensaje_usuario.count("\n") + mensaje_usuario.count(",") + 1
    _ml  = mensaje_usuario.lower()
    if _dashboard_mode:
        max_tokens = 4000
    elif any(p in _ml for p in _kw_rep):
        max_tokens = 2000
    elif any(p in _ml for p in _kw_edi):
        max_tokens = 1200
    elif _nl == 1 and "," not in mensaje_usuario:
        max_tokens = 450
    else:
        max_tokens = min(3000, max(800, _nl * 220))

    # ── System prompt con cache separado (Mejora B) + TTL 1h ────────────────
    _cache_1h = {"type": "ephemeral", "ttl": "1h"}
    system = [
        {"type": "text", "text": parte_estatica, "cache_control": _cache_1h},
        {"type": "text", "text": parte_dinamica},
    ]
    # En voz: anteponer instrucciones de estilo hablado (sin caché — bloque corto).
    if _voz_mode:
        system.append({"type": "text", "text": VOZ_INSTRUCCIONES})
    if contexto_extra:
        _sep2 = "## ESTADO DEL NEGOCIO"
        if _sep2 in contexto_extra:
            _p2 = contexto_extra.split(_sep2, 1)
            system.append({"type": "text", "text": _p2[0].strip(),
                            "cache_control": _cache_1h})
            system.append({"type": "text", "text": (_sep2 + _p2[1]).strip()})
        else:
            system.append({"type": "text", "text": contexto_extra,
                            "cache_control": _cache_1h})

    # ── Elegir modelo (híbrido o forzado por usuario) ───────────────────────
    if modelo_preferido == "sonnet":
        _modelo = MODELO_SONNET
    elif modelo_preferido == "haiku":
        _modelo = MODELO_HAIKU
    else:
        # Voz incluida: auto-router (Sonnet solo si el mensaje es complejo/ambiguo).
        # El costo por turno de voz es ínfimo igual; la precisión la da la
        # confirmación hablada, no forzar Sonnet.
        _modelo = _elegir_modelo(mensaje_usuario)
    _tag = "sonnet" if "sonnet" in _modelo else "haiku"
    _forced = " (forzado)" if modelo_preferido in ("sonnet", "haiku") else ""
    logging.getLogger("ferrebot.ai").info(f"[MODELO] {_tag.upper()}{_forced} para: {mensaje_usuario[:60]}...")

    # ── BUDGET CHECK ─────────────────────────────────────────────────────────
    # Si el vendedor ya agotó su cupo, emitir el mensaje como un único "done"
    # y salir — el caller (ChatWidget, handler bot) lo muestra como respuesta.
    _ok, _mensaje_budget = _budget.puede_llamar(vendedor_id, _modelo)
    if not _ok:
        yield ("done", _mensaje_budget)
        return

    yield ("model", _modelo)

    # ── Stream ────────────────────────────────────────────────────────────────
    # M-01: habilita tool-calling cuando el flag está activo. El payload de
    # "done" trae texto+tags armados desde get_final_message (ver _stream_claude_chunks).
    _tools_stream = tools_mod.TOOLS if config.IA_TOOL_CALLING else None
    async for kind, data in _stream_claude_chunks(system, messages, max_tokens, model=_modelo, tools=_tools_stream):
        # Interceptar el evento "usage" para registrar costo sin propagarlo
        # al caller (que solo espera chunk/done/error/model).
        if kind == "usage":
            try:
                _budget.registrar_uso(vendedor_id, _modelo, data, cache_ttl="1h")
            except Exception as _e_bud:
                logging.getLogger("ferrebot.ai").debug(
                    f"[BUDGET] registro falló (stream): {_e_bud}"
                )
            continue
        yield kind, data



# ─────────────────────────────────────────────
# Re-exports de compatibilidad — los callers que importen desde ai siguen funcionando
# ─────────────────────────────────────────────
from ai.response_builder import procesar_acciones, procesar_acciones_async  # noqa: E402

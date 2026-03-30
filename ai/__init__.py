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
from ai.price_cache import registrar as _registrar_precio_reciente, get_activos as _get_precios_recientes_activos


from memoria import (
    cargar_memoria, guardar_memoria, invalidar_cache_memoria,
    buscar_producto_en_catalogo, buscar_multiples_en_catalogo,
    buscar_multiples_con_alias,
    obtener_precios_como_texto, obtener_info_fraccion_producto,
    cargar_inventario, cargar_caja, cargar_gastos_hoy,
    obtener_resumen_caja, guardar_gasto,
    guardar_fiado_movimiento, abonar_fiado,
    actualizar_precio_en_catalogo,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, _normalizar
import db as _db  # noqa: E402 — necesario para helpers PG (_pg_resumen_ventas, etc.)
from ai.excel_gen import generar_excel_personalizado, editar_excel_con_claude
from ai.prompts import (
    aplicar_alias_ferreteria, _construir_parte_estatica,
    _construir_catalogo_imagen, _construir_parte_dinamica,
    _calcular_historial, MODELO_HAIKU, MODELO_SONNET, _elegir_modelo,
)

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

async def _llamar_claude_con_reintentos(cliente, max_tokens, system, messages, max_reintentos=5, model: str = None):
    """
    Wrapper para llamar a Claude con reintentos adicionales para error 529 (overloaded).
    El SDK ya hace 3 reintentos internos, pero agregamos una capa extra con backoff.
    """
    import random
    from anthropic import APIError

    _model = model or MODELO_HAIKU   # default haiku si no se especifica

    ultimo_error = None
    for intento in range(max_reintentos):
        try:
            loop = asyncio.get_event_loop()
            _m = _model   # capturar en closure
            respuesta = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: cliente.messages.create(
                        model=_m,
                        max_tokens=max_tokens,
                        system=system,
                        messages=messages,
                    )
                ),
                timeout=45.0,  # timeout más generoso
            )
            return respuesta
        except asyncio.TimeoutError:
            ultimo_error = RuntimeError("La IA tardó demasiado en responder (>45s).")
            if intento >= 2:
                raise ultimo_error
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
            # Solo reintentar en errores 529 (overloaded) o 503 (service unavailable)
            if "529" in str(e) or "overload" in error_str or "503" in str(e) or "unavailable" in error_str:
                if intento < max_reintentos - 1:
                    espera = (2 ** intento) + random.uniform(0, 1)
                    logging.getLogger("ferrebot.ai").warning(
                        f"[CLAUDE] Error 529/503, reintento {intento+1}/{max_reintentos} en {espera:.1f}s..."
                    )
                    await asyncio.sleep(espera)
                    continue
            # Otros errores: no reintentar
            raise
    
    # Si llegamos aquí, agotamos los reintentos
    raise ultimo_error or RuntimeError("Error desconocido al llamar a Claude")


async def procesar_con_claude(
    mensaje_usuario: str,
    nombre_usuario: str,
    historial_chat: list,
    contexto_extra: str = "",
    modelo_preferido: str = None,
    imagen_b64: str = None,
    imagen_media_type: str = None,
) -> str:
    """
    Procesa un mensaje con Claude.  Si se pasa imagen_b64, se incluye la imagen
    en el mensaje (visión) y se omite el bypass Python (que no puede procesar imágenes).
    """
    # BYPASS PYTHON — ANTES de alias_ferreteria (que transforma fracciones y rompería el match)
    # Solo se aplican aliases DINÁMICOS (simples word-substitutions: tiner→thinner, etc.)
    # El mensaje llega como "{vendedor}: {texto}" — stripear prefijo antes del bypass
    _dashboard_mode = "##DASHBOARD##" in mensaje_usuario
    _tiene_imagen   = imagen_b64 is not None  # True cuando viene una foto del cuaderno
    _msg_bypass = re.sub(r'^[^:]+:\s*', '', mensaje_usuario).strip()
    _msg_bypass = alias_manager.aplicar_aliases_dinamicos(_msg_bypass)
    memoria = cargar_memoria()
    # Las fotos con imagen no pueden pasar por el bypass Python (no hay texto estructurado).
    # Solo intentar bypass cuando NO hay imagen.
    _bypass = None if _tiene_imagen else bypass.intentar_bypass_python(_msg_bypass, memoria.get("catalogo", {}))
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

    parte_estatica = _construir_parte_estatica(memoria)
    parte_dinamica = _construir_parte_dinamica(mensaje_usuario, nombre_usuario, memoria)

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

    # BLOQUEO PYTHON: si el MATCH está vacío y el mensaje parece una venta
    # (no es consulta, no es reporte), responder directamente sin llamar a Claude.
    # Esto evita que el bot registre productos inexistentes con total:0.
    # EXCEPCIÓN: si viene con contexto_extra (ej: dashboard), siempre pasa a Claude
    # para permitir conversación libre sin que saludos/preguntas se traten como ventas.
    _SEÑAL_MATCH_VACIO = "MATCH: (sin resultados — producto no encontrado en catalogo)"
    _kw_no_venta = {"cuanto","vendimos","reporte","analiz","resumen","estadistica",
                    "top","mas vendido","gasto","caja","inventario","cliente",
                    "precio","vale","cuesta","cuanto vale","hay","stock","quedan"}
    _es_consulta = any(p in mensaje_usuario.lower() for p in _kw_no_venta)

    # EXCEPCIÓN: venta varia siempre pasa a Claude aunque no esté en catálogo
    _kw_venta_varia = {"venta varia", "ventas varia", "venta general",
                       "ventas del dia", "ventas del día", "cuadre de caja",
                       "cuadre caja", "no alcance a anotar", "no alcancé a anotar"}
    _es_venta_varia = any(kw in mensaje_usuario.lower() for kw in _kw_venta_varia)

    # BLOQUEO MATCH-VACÍO: omitir cuando hay imagen (el texto puede venir vacío/genérico)
    if _SEÑAL_MATCH_VACIO in parte_dinamica and not _es_consulta and not _dashboard_mode and not _tiene_imagen and not _es_venta_varia:
        # Extraer nombre del producto del mensaje para respuesta clara
        _msg_limpio = mensaje_usuario.strip().lower()
        # Quitar cantidades y unidades del inicio para aislar el nombre
        _msg_limpio = re.sub(r'^[\d\s/\.]+', '', _msg_limpio).strip()
        _msg_limpio = re.sub(r'^(kilo|kilos|galon|galones|metro|metros|unidad|unidades|litro|litros)\s*', '', _msg_limpio).strip()
        return f"No tengo {_msg_limpio} en el catálogo."

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
    system = [
        {
            "type": "text",
            "text": parte_estatica,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": parte_dinamica,
        },
    ]

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
                "cache_control": {"type": "ephemeral"},
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
                "cache_control": {"type": "ephemeral"},
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
        _modelo_no_stream = _elegir_modelo(mensaje_usuario)

    if _usar_thinking:
        # Extended Thinking: Claude razona antes de responder
        # budget_tokens = tokens de pensamiento (no visibles al usuario)
        # max_tokens debe ser > budget_tokens
        _budget = 8000
        _max_thinking = max(max_tokens, _budget + 2000)
        try:
            loop = asyncio.get_event_loop()
            respuesta = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: config.claude_client.messages.create(
                        model=MODELO_SONNET,
                        max_tokens=_max_thinking,
                        thinking={"type": "enabled", "budget_tokens": _budget},
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
        respuesta = await _llamar_claude_con_reintentos(
            config.claude_client, max_tokens, system, messages, model=_modelo_no_stream
        )

    # ── Log de uso de tokens y cache ──
    uso = respuesta.usage
    cache_read    = getattr(uso, "cache_read_input_tokens",    0) or 0
    cache_created = getattr(uso, "cache_creation_input_tokens", 0) or 0
    input_normal  = getattr(uso, "input_tokens",               0) or 0
    output_tokens = getattr(uso, "output_tokens",              0) or 0

    if cache_read > 0 or cache_created > 0:
        costo_input   = (input_normal  / 1_000_000) * 1.00
        costo_cached  = (cache_read    / 1_000_000) * 0.10
        costo_created = (cache_created / 1_000_000) * 1.25
        costo_output  = (output_tokens / 1_000_000) * 5.00
        costo_total   = costo_input + costo_cached + costo_created + costo_output
        logging.getLogger("ferrebot.cache").info(
            f"[CACHE] ✅ hit={cache_read} tok | created={cache_created} tok | "
            f"input={input_normal} tok | output={output_tokens} tok | "
            f"costo≈${costo_total:.5f}"
        )
    else:
        logging.getLogger("ferrebot.cache").warning(
            f"[CACHE] ⚠️ SIN CACHE — input={input_normal} tok | output={output_tokens} tok"
        )

    return respuesta.content[0].text

async def _stream_claude_chunks(system: list, messages: list, max_tokens: int, model: str = MODELO_SONNET):
    """
    Async generator que hace streaming de Claude usando un thread + asyncio.Queue.
    Yields: ("chunk", text_piece) durante el stream
            ("done",  full_text)  al finalizar
            ("error", error_str)  en caso de fallo
    """
    import threading
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _sync_worker():
        try:
            with config.claude_client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                full = ""
                for text in stream.text_stream:
                    full += text
                    loop.call_soon_threadsafe(q.put_nowait, ("chunk", text))
                loop.call_soon_threadsafe(q.put_nowait, ("done", full))
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
):
    """
    Versión streaming de procesar_con_claude.
    Yields: ("chunk", text)   — fragmento de texto mientras Claude responde
            ("done",  text)   — texto completo final
            ("error", msg)    — error
    Si el bypass Python intercepta, devuelve ("done", respuesta) de inmediato.
    """
    import re as _re_s
    import json as _json_s

    # ── Detectar modo dashboard y limpiar flag ────────────────────────────────
    _dashboard_mode = "##DASHBOARD##" in mensaje_usuario
    if _dashboard_mode:
        mensaje_usuario = mensaje_usuario.replace("##DASHBOARD## ", "").replace("##DASHBOARD##", "").strip()

    # ── Bypass Python ─────────────────────────────────────────────────────────
    _msg_bypass = _re_s.sub(r'^[^:]+:\s*', '', mensaje_usuario).strip()
    _msg_bypass = alias_manager.aplicar_aliases_dinamicos(_msg_bypass)
    memoria = cargar_memoria()
    _bp = bypass.intentar_bypass_python(_msg_bypass, memoria.get("catalogo", {}))
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
    parte_estatica  = _construir_parte_estatica(memoria)
    parte_dinamica  = _construir_parte_dinamica(
        mensaje_usuario, nombre_usuario, memoria, dashboard_mode=_dashboard_mode
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
    if _MATCH_VACIO in parte_dinamica and not _es_consulta and not _dashboard_mode and not _es_venta_varia2:
        _msg_lp = re.sub(r'^[\d\s/\.]+', '', mensaje_usuario.strip().lower()).strip()
        _msg_lp = re.sub(r'^(kilo|kilos|galon|galones|metro|metros|unidad|unidades|litro|litros)\s*', '', _msg_lp).strip()
        yield ("done", f"No tengo {_msg_lp} en el catálogo.")
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

    # ── System prompt con cache separado (Mejora B) ──────────────────────────
    system = [
        {"type": "text", "text": parte_estatica, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": parte_dinamica},
    ]
    if contexto_extra:
        _sep2 = "## ESTADO DEL NEGOCIO"
        if _sep2 in contexto_extra:
            _p2 = contexto_extra.split(_sep2, 1)
            system.append({"type": "text", "text": _p2[0].strip(),
                            "cache_control": {"type": "ephemeral"}})
            system.append({"type": "text", "text": (_sep2 + _p2[1]).strip()})
        else:
            system.append({"type": "text", "text": contexto_extra,
                            "cache_control": {"type": "ephemeral"}})

    # ── Elegir modelo (híbrido o forzado por usuario) ───────────────────────
    if modelo_preferido == "sonnet":
        _modelo = MODELO_SONNET
    elif modelo_preferido == "haiku":
        _modelo = MODELO_HAIKU
    else:
        _modelo = _elegir_modelo(mensaje_usuario)
    _tag = "sonnet" if "sonnet" in _modelo else "haiku"
    _forced = " (forzado)" if modelo_preferido in ("sonnet", "haiku") else ""
    logging.getLogger("ferrebot.ai").info(f"[MODELO] {_tag.upper()}{_forced} para: {mensaje_usuario[:60]}...")
    yield ("model", _modelo)

    # ── Stream ────────────────────────────────────────────────────────────────
    async for kind, data in _stream_claude_chunks(system, messages, max_tokens, model=_modelo):
        yield kind, data


# ─────────────────────────────────────────────
# PARSEO Y EJECUCIÓN DE ACCIONES
# ─────────────────────────────────────────────

def procesar_acciones(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    from ventas_state import (ventas_pendientes, registrar_ventas_con_metodo,
        _estado_lock, mensajes_standby, limpiar_pendientes_expirados, _guardar_pendiente)

    acciones:       list[str] = []
    archivos_excel: list[str] = []
    texto_limpio = texto_respuesta

    # ── Ventas ──
    ventas_con_metodo = []
    ventas_sin_metodo = []

    with _estado_lock:
        esperando_pago = bool(ventas_pendientes.get(chat_id))

    # ── Helper: conversión para productos vendidos por mililitro (MLT) ──────
    def _convertir_venta_mlt(venta: dict) -> dict:
        """
        Para productos con unidad_medida='MLT' (tintes):
          precio_unidad en catálogo = precio del TARRO COMPLETO (1000 ml)
          precio_por_ml = precio_unidad / 1000
          Ej: Tinte Caoba precio_unidad=26000 → precio_por_ml=26

        CASO 1 — cliente pide tarro(s) completo(s):
          Claude envía cantidad=1 (o N) y total=26000 (o N×26000)
          Detectado: total ≈ cantidad × precio_unidad → convertir a ml
          Ej: {cantidad:1, total:26000} → cantidad=1000 ml

        CASO 2 — cliente pide por pesos (menudeo):
          Claude envía cantidad=pesos y total=pesos (mismo número)
          Ej: {cantidad:2000, total:2000} → ml = 2000/26 = 76.9
          → cantidad=76.9, total=2000 (total NO se toca)

        CASO 3 — cliente pide ml explícitamente:
          Claude ya envía cantidad en ml correctamente → no tocar
          Ej: {cantidad:500, total:13000} → 500×26=13000 ✅
        """
        try:
            prod = buscar_producto_en_catalogo(venta.get("producto", ""))
            if not prod:
                return venta
            if prod.get("unidad_medida") != "MLT":
                return venta

            precio_tarro = prod.get("precio_unidad", 0)  # precio de 1000 ml
            if not precio_tarro:
                return venta

            # precio_por_ml REAL: tarro / 1000
            precio_por_ml = precio_tarro / 1000.0

            cantidad = float(venta.get("cantidad", 1))
            total    = float(venta.get("total", 0))

            if total <= 0:
                return venta

            # ── CASO 1: cantidad en tarros (entero pequeño, total ≈ N × precio_tarro) ──
            if (cantidad <= 20
                    and cantidad == int(cantidad)
                    and abs(total - cantidad * precio_tarro) / max(total, 1) < 0.05):
                ml = int(cantidad * 1000)
                venta = dict(venta)
                venta["cantidad"] = ml
                logging.getLogger("ferrebot.ai").info(
                    "[MLT] Tarros→ml: %s | %d tarro(s) → %d ml | $%.0f",
                    prod.get("nombre"), int(cantidad), ml, total
                )
                return venta

            # ── CASO 2: cantidad == total → cliente pidió por pesos ──
            # También aplica si cantidad es un múltiplo redondo de 500/1000 mucho mayor que precio_por_ml
            cantidad_parece_pesos = (
                abs(cantidad - total) < 1          # cantidad y total son iguales
                or (cantidad >= 500
                    and cantidad % 500 == 0
                    and abs(total - cantidad) < 1)  # doble chequeo
            )
            if cantidad_parece_pesos:
                ml = round(total / precio_por_ml, 1)
                venta = dict(venta)
                venta["cantidad"] = ml
                # total NO se modifica — es lo que el cliente pagó
                logging.getLogger("ferrebot.ai").info(
                    "[MLT] Pesos→ml: %s | $%.0f ÷ $%.4f/ml = %.1f ml",
                    prod.get("nombre"), total, precio_por_ml, ml
                )
                return venta

            # ── CASO 3: cantidad ya en ml → verificar coherencia y no tocar ──
            # Si total ≈ cantidad × precio_por_ml ya está bien
            logging.getLogger("ferrebot.ai").debug(
                "[MLT] Sin conversión (ya en ml): %s | %.1f ml | $%.0f",
                prod.get("nombre"), cantidad, total
            )

        except Exception as e:
            logging.getLogger("ferrebot.ai").warning("[MLT] Error conversión: %s", e)
        return venta

    for venta_json in re.findall(r'\[VENTA\](.*?)\[/VENTA\]', texto_respuesta, re.DOTALL):
        try:
            if esperando_pago:
                print(f"[VENTA] ignorado — esperando selección de pago para chat {chat_id}")
            else:
                venta = json.loads(venta_json.strip())
                logging.getLogger("ferrebot.ai").debug(f"[VENTA] JSON recibido: {venta}")
                # Aplicar conversión ml si aplica
                venta = _convertir_venta_mlt(venta)
                if venta.get("metodo_pago"):
                    ventas_con_metodo.append(venta)
                else:
                    ventas_sin_metodo.append(venta)
        except Exception as e:
            logging.getLogger("ferrebot.ai").error(f"Error parseando venta: {e} | JSON raw: {repr(venta_json.strip())}")
        texto_limpio = texto_limpio.replace(f'[VENTA]{venta_json}[/VENTA]', '')

    if esperando_pago and ventas_con_metodo:
        ventas_con_metodo.clear()

    def _tiene_cliente_desconocido(ventas: list) -> str | None:
        for v in ventas:
            nombre_cliente = v.get("cliente", "").strip()
            if not nombre_cliente or nombre_cliente.lower() in ("consumidor final", "cf", ""):
                continue
            try:
                _, candidatos = _pg_buscar_cliente(nombre_cliente)
                if not candidatos:
                    return nombre_cliente
                # Verificar que algún candidato coincida con al menos 2 palabras
                palabras_buscadas = set(_normalizar(nombre_cliente).split())
                match_exacto = False
                for c in candidatos:
                    palabras_encontradas = set(_normalizar(c.get("Nombre tercero", "")).split())
                    coincidencias = palabras_buscadas & palabras_encontradas
                    if len(coincidencias) >= 2 or (len(palabras_buscadas) == 1 and coincidencias):
                        match_exacto = True
                        break
                if not match_exacto:
                    return nombre_cliente
            except Exception:
                pass
        return None

    todas_las_ventas_nuevas = ventas_con_metodo + ventas_sin_metodo
    cliente_desconocido     = _tiene_cliente_desconocido(todas_las_ventas_nuevas) if todas_las_ventas_nuevas else None

    if cliente_desconocido and not esperando_pago:
        with _estado_lock:
            _guardar_pendiente(chat_id, todas_las_ventas_nuevas)
        acciones.append(f"CLIENTE_DESCONOCIDO:{cliente_desconocido}")
        ventas_con_metodo.clear()
        ventas_sin_metodo.clear()

    if ventas_con_metodo:
        metodo_conocido = ventas_con_metodo[0].get("metodo_pago", "efectivo").lower()
        with _estado_lock:
            _guardar_pendiente(chat_id, ventas_con_metodo)
        acciones.append(f"PEDIR_CONFIRMACION:{metodo_conocido}")

    ventas_ignoradas = esperando_pago and bool(
        re.findall(r'\[VENTA\](.*?)\[/VENTA\]', texto_respuesta, re.DOTALL)
    )
    if ventas_ignoradas or (ventas_sin_metodo and esperando_pago):
        acciones.append("PAGO_PENDIENTE_AVISO")
    elif ventas_sin_metodo:
        with _estado_lock:
            _guardar_pendiente(chat_id, ventas_sin_metodo)
        acciones.append("PEDIR_METODO_PAGO")

    # ── Cliente nuevo (datos completos) ──
    for cli_json in re.findall(r'\[CLIENTE_NUEVO\](.*?)\[/CLIENTE_NUEVO\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(cli_json.strip())
            nombre = datos.get("nombre", "").strip()
            id_num = str(datos.get("identificacion", "")).strip()
            if nombre and id_num:
                ok = _pg_guardar_cliente(
                    nombre, datos.get("tipo_id", "Cedula de ciudadania"), id_num,
                    datos.get("tipo_persona", "Natural"),
                    datos.get("correo", ""), datos.get("telefono", ""),
                )
                acciones.append(
                    f"Cliente creado: {nombre.upper()} — {datos.get('tipo_id','')}: {id_num}"
                    if ok else f"No pude guardar el cliente {nombre}."
                )
        except Exception as e:
            logging.getLogger("ferrebot.ai").error(f"Error cliente nuevo: {e}")
        texto_limpio = texto_limpio.replace(f'[CLIENTE_NUEVO]{cli_json}[/CLIENTE_NUEVO]', '')

    # ── Iniciar flujo paso a paso de cliente ──
    for ini_json in re.findall(r'\[INICIAR_CLIENTE\](.*?)\[/INICIAR_CLIENTE\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(ini_json.strip())
            nombre = datos.get("nombre", "").strip()
            from ventas_state import clientes_en_proceso, ventas_esperando_cliente, _estado_lock as _lock
            with _lock:
                clientes_en_proceso[chat_id] = {
                    "nombre":         nombre,
                    "tipo_id":        None,
                    "identificacion": None,
                    "tipo_persona":   None,
                    "correo":         None,
                    "paso":           "nombre" if not nombre else "tipo_id",
                    "vendedor":       vendedor,
                }
                if chat_id in ventas_pendientes and ventas_pendientes[chat_id]:
                    ventas_esperando_cliente[chat_id] = {
                        "ventas":   ventas_pendientes.pop(chat_id),
                        "metodo":   None,
                        "vendedor": vendedor,
                    }
                elif ventas_sin_metodo:
                    ventas_esperando_cliente[chat_id] = {
                        "ventas":   list(ventas_sin_metodo),
                        "metodo":   None,
                        "vendedor": vendedor,
                    }
                    ventas_sin_metodo.clear()
            acciones.append("INICIAR_FLUJO_CLIENTE")
        except Exception as e:
            print(f"Error iniciando flujo cliente: {e}")
        texto_limpio = texto_limpio.replace(f'[INICIAR_CLIENTE]{ini_json}[/INICIAR_CLIENTE]', '')

    # ── Borrar cliente ──
    for bc_json in re.findall(r'\[BORRAR_CLIENTE\](.*?)\[/BORRAR_CLIENTE\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(bc_json.strip())
            nombre = datos.get("nombre", "").strip()
            if nombre:
                exito, msg = _pg_borrar_cliente(nombre)
                acciones.append(msg)
        except Exception as e:
            print(f"Error borrando cliente: {e}")
        texto_limpio = texto_limpio.replace(f'[BORRAR_CLIENTE]{bc_json}[/BORRAR_CLIENTE]', '')

    # ── Precio fraccion ──
    for pf_json in re.findall(r'\[PRECIO_FRACCION\](.*?)\[/PRECIO_FRACCION\]', texto_respuesta, re.DOTALL):
        try:
            datos    = json.loads(pf_json.strip())
            producto = datos.get("producto", "").strip()
            fraccion = datos.get("fraccion", "").strip()
            precio   = float(datos.get("precio", 0))
            if producto and fraccion and precio:
                # Intentar actualizar en catálogo (fuente única de verdad)
                en_cat = actualizar_precio_en_catalogo(producto, precio, fraccion)
                if en_cat:
                    # Override RAM 5 min
                    _pf_prod = buscar_producto_en_catalogo(producto)
                    _pf_key  = _pf_prod.get("nombre_lower", producto.lower()) if _pf_prod else producto.lower()
                    _registrar_precio_reciente(_pf_key, precio, fraccion)
                    invalidar_cache_memoria()
                else:
                    # Producto no en catálogo: nada que hacer, PG es la fuente de verdad
                    pass
                acciones.append(f"Precio de fracción guardado: {producto} {fraccion} = ${precio:,.0f}")
        except Exception as e:
            print(f"Error precio fraccion: {e}")
        texto_limpio = texto_limpio.replace(f'[PRECIO_FRACCION]{pf_json}[/PRECIO_FRACCION]', '')

    # ── Precio ──
    for precio_json in re.findall(r'\[PRECIO\](.*?)\[/PRECIO\]', texto_respuesta, re.DOTALL):
        try:
            datos    = json.loads(precio_json.strip())
            producto = datos["producto"]
            precio   = float(datos["precio"])
            fraccion = datos.get("fraccion")  # opcional: "1/4", "1/2", etc.

            # Actualizar directo en PG (fuente única de verdad)
            en_catalogo = actualizar_precio_en_catalogo(producto, precio, fraccion)

            # Override RAM 5 min
            prod_encontrado = buscar_producto_en_catalogo(producto)
            nombre_lower_pc = prod_encontrado.get("nombre_lower", producto.lower()) if prod_encontrado else producto.lower()
            _registrar_precio_reciente(nombre_lower_pc, precio, fraccion)
            invalidar_cache_memoria()

            if fraccion:
                acciones.append(f"🧠 Precio actualizado: {producto} {fraccion} = ${precio:,.0f}")
            else:
                acciones.append(f"🧠 Precio actualizado: {producto} = ${precio:,.0f}")
        except Exception as e:
            print(f"Error precio: {e}")
        texto_limpio = texto_limpio.replace(f'[PRECIO]{precio_json}[/PRECIO]', '')

    # ── Precio mayorista (tornillería) ──
    for pm_json in re.findall(r'\[PRECIO_MAYORISTA\](.*?)\[/PRECIO_MAYORISTA\]', texto_respuesta, re.DOTALL):
        try:
            datos       = json.loads(pm_json.strip())
            producto    = datos["producto"]
            p_unidad    = float(datos.get("precio_unidad", 0) or 0)
            p_mayorista = float(datos.get("precio_mayorista", 0) or 0)
            umbral      = int(datos.get("umbral", 50))

            prod = buscar_producto_en_catalogo(producto)
            if not prod:
                acciones.append(f"⚠️ Producto no encontrado: {producto}")
            else:
                import db as _db_pm
                from memoria import invalidar_cache_memoria as _inv
                prod_row_pm = _db_pm.query_one(
                    "SELECT id, nombre, precio_unidad FROM productos "
                    "WHERE nombre_lower = %s AND activo = TRUE",
                    [prod.get("nombre_lower", producto.lower())],
                )
                if prod_row_pm:
                    prod_id_pm     = prod_row_pm["id"]
                    nombre_display = prod_row_pm["nombre"]
                    if p_unidad > 0:
                        _db_pm.execute(
                            "UPDATE productos SET precio_unidad = %s, updated_at = NOW() WHERE id = %s",
                            [round(p_unidad), prod_id_pm],
                        )
                    # Usar precio_unidad existente en BD como fallback para precio_bajo
                    precio_bajo = round(p_unidad) if p_unidad > 0 else (prod_row_pm["precio_unidad"] or 0)
                    if p_mayorista > 0 or p_unidad > 0:
                        _db_pm.execute(
                            """
                            INSERT INTO productos_precio_cantidad
                                (producto_id, umbral, precio_bajo_umbral, precio_sobre_umbral)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (producto_id) DO UPDATE
                            SET umbral              = EXCLUDED.umbral,
                                precio_bajo_umbral  = EXCLUDED.precio_bajo_umbral,
                                precio_sobre_umbral = EXCLUDED.precio_sobre_umbral
                            """,
                            (prod_id_pm, umbral, precio_bajo,
                             round(p_mayorista) if p_mayorista > 0 else precio_bajo),
                        )
                    _inv()
                    msg = f"🧠 {nombre_display}: unidad=${p_unidad:,.0f}" if p_unidad else f"🧠 {nombre_display}"
                    if p_mayorista > 0:
                        msg += f" | mayorista ×{umbral}=${p_mayorista:,.0f}"
                    acciones.append(msg)
        except Exception as e:
            print(f"Error precio_mayorista: {e}")
        texto_limpio = texto_limpio.replace(f'[PRECIO_MAYORISTA]{pm_json}[/PRECIO_MAYORISTA]', '')

    # ── Código producto ──
    for cp_json in re.findall(r'\[CODIGO_PRODUCTO\](.*?)\[/CODIGO_PRODUCTO\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(cp_json.strip())
            nombre = datos.get("producto", "").strip()
            codigo = datos.get("codigo", "").strip()
            if nombre and codigo:
                import db as _db_cp
                prod = buscar_producto_en_catalogo(nombre)
                if prod:
                    filas = _db_cp.execute(
                        "UPDATE productos SET codigo = %s, updated_at = NOW() WHERE nombre_lower = %s",
                        [codigo, prod.get("nombre_lower")],
                    )
                    if filas:
                        invalidar_cache_memoria()
                        acciones.append(f"Código guardado: {nombre} = {codigo}")
        except Exception as e:
            print(f"Error código producto: {e}")
        texto_limpio = texto_limpio.replace(f'[CODIGO_PRODUCTO]{cp_json}[/CODIGO_PRODUCTO]', '')

    # ── Negocio ──
    for neg_json in re.findall(r'\[NEGOCIO\](.*?)\[/NEGOCIO\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(neg_json.strip())
            mem   = cargar_memoria()
            mem["negocio"].update(datos)
            guardar_memoria(mem)
        except Exception as e:
            print(f"Error negocio: {e}")
        texto_limpio = texto_limpio.replace(f'[NEGOCIO]{neg_json}[/NEGOCIO]', '')

    # ── Caja ──
    for caja_json in re.findall(r'\[CAJA\](.*?)\[/CAJA\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(caja_json.strip())
            caja  = cargar_caja()
            if datos.get("accion") == "apertura":
                caja.update({
                    "abierta": True,
                    "fecha":   datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
                    "monto_apertura": float(datos.get("monto", 0)),
                    "efectivo": 0, "transferencias": 0, "datafono": 0,
                })
                from memoria import guardar_caja
                guardar_caja(caja)
                acciones.append(f"Caja abierta con ${float(datos.get('monto', 0)):,.0f}")
            elif datos.get("accion") == "cierre":
                acciones.append(f"Caja cerrada.\n{obtener_resumen_caja()}")
                caja["abierta"] = False
                from memoria import guardar_caja
                guardar_caja(caja)
        except Exception as e:
            print(f"Error caja: {e}")
        texto_limpio = texto_limpio.replace(f'[CAJA]{caja_json}[/CAJA]', '')

    # ── Gastos ──
    for gasto_json in re.findall(r'\[GASTO\](.*?)\[/GASTO\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(gasto_json.strip())
            gasto = {
                "concepto":  datos.get("concepto", ""),
                "monto":     float(datos.get("monto", 0)),
                "categoria": datos.get("categoria", "varios"),
                "origen":    datos.get("origen", "externo"),
                "hora":      datetime.now(config.COLOMBIA_TZ).strftime("%H:%M"),
            }
            guardar_gasto(gasto)
            acciones.append(f"Gasto registrado: {gasto['concepto']} — ${gasto['monto']:,.0f} ({gasto['origen']})")
        except Exception as e:
            print(f"Error gasto: {e}")
        texto_limpio = texto_limpio.replace(f'[GASTO]{gasto_json}[/GASTO]', '')

    # ── Memoria del negocio (dashboard) ──────────────────────────────────────
    for mem_json in re.findall(r'\[MEMORIA\](.*?)\[/MEMORIA\]', texto_respuesta, re.DOTALL):
        try:
            datos     = json.loads(mem_json.strip())
            tipo      = datos.get("tipo", "observacion")
            contenido = datos.get("contenido", "").strip()
            if contenido:
                from memoria import cargar_memoria, guardar_memoria as _gm_mem
                import time as _t_mem
                import config as _cfg_mem
                from datetime import datetime as _dt_mem
                _mem = cargar_memoria()
                _notas = _mem.get("notas", {})
                if isinstance(_notas, list):
                    _notas = {"observaciones": _notas} if _notas else {}
                _fecha = _dt_mem.now(_cfg_mem.COLOMBIA_TZ).strftime("%Y-%m-%d")
                if tipo == "contexto_negocio":
                    _notas["contexto_negocio"] = contenido
                elif tipo == "decision":
                    _notas.setdefault("decisiones", []).append(f"[{_fecha}] {contenido}")
                    _notas["decisiones"] = _notas["decisiones"][-30:]
                else:
                    _notas.setdefault("observaciones", []).append(f"[{_fecha}] {contenido}")
                    _notas["observaciones"] = _notas["observaciones"][-30:]
                _mem["notas"] = _notas
                _gm_mem(_mem, urgente=True)
                acciones.append(f"Memoria guardada: {contenido[:60]}")
        except Exception as e:
            logging.getLogger("ferrebot.ai").warning(f"Error guardando memoria: {e}")
        texto_limpio = texto_limpio.replace(f'[MEMORIA]{mem_json}[/MEMORIA]', '')

    # ── Fiado ──
    for fiado_json in re.findall(r'\[FIADO\](.*?)\[/FIADO\]', texto_respuesta, re.DOTALL):
        try:
            datos    = json.loads(fiado_json.strip())
            cliente  = datos.get("cliente", "").strip()
            concepto = datos.get("concepto", "")
            cargo    = float(datos.get("cargo", 0))
            abono    = float(datos.get("abono", 0))
            if cliente and cargo > 0:
                saldo = guardar_fiado_movimiento(cliente, concepto, cargo, abono)
                acciones.append(f"Fiado registrado: {cliente} debe ${saldo:,.0f}")
        except Exception as e:
            print(f"Error fiado: {e}")
        texto_limpio = texto_limpio.replace(f'[FIADO]{fiado_json}[/FIADO]', '')

    # ── Abono fiado ──
    for abono_json in re.findall(r'\[ABONO_FIADO\](.*?)\[/ABONO_FIADO\]', texto_respuesta, re.DOTALL):
        try:
            datos   = json.loads(abono_json.strip())
            cliente = datos.get("cliente", "").strip()
            monto   = float(datos.get("monto", 0))
            if cliente and monto > 0:
                ok, msg = abonar_fiado(cliente, monto)
                if ok:
                    from memoria import cargar_fiados
                    fiados      = cargar_fiados()
                    cliente_key = next((k for k in fiados if k.lower() in cliente.lower() or cliente.lower() in k.lower()), cliente)
                acciones.append(msg)
        except Exception as e:
            print(f"Error abono fiado: {e}")
        texto_limpio = texto_limpio.replace(f'[ABONO_FIADO]{abono_json}[/ABONO_FIADO]', '')

    # ── Inventario ──
    for inv_json in re.findall(r'\[INVENTARIO\](.*?)\[/INVENTARIO\]', texto_respuesta, re.DOTALL):
        try:
            datos      = json.loads(inv_json.strip())
            inventario = cargar_inventario()
            producto   = datos.get("producto", "").lower()
            accion     = datos.get("accion", "actualizar")
            if accion == "actualizar":
                cantidad = convertir_fraccion_a_decimal(datos.get("cantidad", 0))
                minimo   = convertir_fraccion_a_decimal(datos.get("minimo", 0.5))
                unidad   = datos.get("unidad", "unidades")
                datos_inv = {
                    "cantidad": cantidad, "minimo": minimo, "unidad": unidad,
                    "nombre_original": datos.get("producto", producto),
                }
                from memoria import guardar_inventario as _guardar_inv
                _guardar_inv(producto, datos_inv)
                acciones.append(f"Inventario: {datos['producto']} — {decimal_a_fraccion_legible(cantidad)} {unidad}")
            elif accion == "descontar" and producto in inventario:
                descuento = convertir_fraccion_a_decimal(datos.get("cantidad", 0))
                inventario[producto]["cantidad"] = max(0, inventario[producto]["cantidad"] - descuento)
                from memoria import guardar_inventario as _guardar_inv
                _guardar_inv(producto, inventario[producto])
            from memoria import verificar_alertas_inventario
            acciones.extend(verificar_alertas_inventario())
        except Exception as e:
            print(f"Error inventario: {e}")
        texto_limpio = texto_limpio.replace(f'[INVENTARIO]{inv_json}[/INVENTARIO]', '')

    # ── Excel personalizado ──
    for excel_json in re.findall(r'\[EXCEL\](.*?)\[/EXCEL\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(excel_json.strip())
            nombre = f"reporte_{datetime.now(config.COLOMBIA_TZ).strftime('%Y%m%d_%H%M%S')}.xlsx"
            generar_excel_personalizado(
                datos.get("titulo", "Reporte"),
                datos.get("encabezados", []),
                datos.get("filas", []),
                nombre,
            )
            archivos_excel.append(nombre)
        except Exception as e:
            print(f"Error generando Excel: {e}")
        texto_limpio = texto_limpio.replace(f'[EXCEL]{excel_json}[/EXCEL]', '')

    # ── Factura de proveedor ──
    for fac_json in re.findall(r'\[FACTURA_PROVEEDOR\](.*?)\[/FACTURA_PROVEEDOR\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(fac_json.strip())
            proveedor   = datos.get("proveedor", "").strip()
            total       = float(datos.get("total", 0))
            descripcion = datos.get("descripcion", "Sin descripción").strip()
            if proveedor and total > 0:
                from memoria import registrar_factura_proveedor
                factura = registrar_factura_proveedor(
                    proveedor   = proveedor,
                    descripcion = descripcion,
                    total       = total,
                )
                acciones.append(
                    f"✅ {factura['id']} registrada · {proveedor} · ${total:,.0f} pendiente"
                )
        except Exception as e:
            print(f"Error factura proveedor: {e}")
        texto_limpio = texto_limpio.replace(f'[FACTURA_PROVEEDOR]{fac_json}[/FACTURA_PROVEEDOR]', '')

    # ── Abono a proveedor ──
    for abo_json in re.findall(r'\[ABONO_PROVEEDOR\](.*?)\[/ABONO_PROVEEDOR\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(abo_json.strip())
            fac_id = datos.get("fac_id", "").strip().upper()
            monto  = float(datos.get("monto", 0))
            if fac_id and monto > 0:
                from memoria import registrar_abono_factura
                result = registrar_abono_factura(fac_id=fac_id, monto=monto)
                if result["ok"]:
                    fac = result["factura"]
                    estado_icon = {"pagada": "✅", "parcial": "🔶", "pendiente": "🔴"}.get(fac["estado"], "📄")
                    acciones.append(
                        f"{estado_icon} Abono ${monto:,.0f} a {fac_id} · "
                        f"Pendiente: ${fac['pendiente']:,.0f}"
                    )
                else:
                    acciones.append(f"⚠️ {result['error']}")
        except Exception as e:
            print(f"Error abono proveedor: {e}")
        texto_limpio = texto_limpio.replace(f'[ABONO_PROVEEDOR]{abo_json}[/ABONO_PROVEEDOR]', '')

    return texto_limpio.strip(), acciones, archivos_excel

# ─────────────────────────────────────────────
# VERSIÓN ASYNC DE PROCESAR_ACCIONES
# ─────────────────────────────────────────────

async def procesar_acciones_async(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    """
    Wrapper async de procesar_acciones para compatibilidad con handlers async.
    Ejecuta procesar_acciones en un executor para no bloquear el event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: procesar_acciones(texto_respuesta, vendedor, chat_id)
    )

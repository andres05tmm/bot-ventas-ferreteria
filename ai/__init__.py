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
from ai.excel_gen import generar_excel_personalizado, editar_excel_con_claude, ejecutar_operacion_excel
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
# Re-exports de compatibilidad — los callers que importen desde ai siguen funcionando
# ─────────────────────────────────────────────
from ai.response_builder import procesar_acciones, procesar_acciones_async  # noqa: E402

"""
Router: Chat IA — /chat/*, /api/health
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Union

import config
from sheets import sheets_leer_ventas_del_dia
from routers.shared import (
    _hoy, _hace_n_dias, _leer_excel_rango, _leer_excel_compras,
    _to_float, _cantidad_a_float, _stock_wayper,
)

logger = logging.getLogger("ferrebot.api")

router = APIRouter()

# ── Chat IA desde el Dashboard ────────────────────────────────────────────────

# Convierte session_id (string) en un chat_id negativo único.
# Los chat_id de Telegram son positivos, los del dashboard son negativos → sin colisión.
def _session_chat_id(session_id: str) -> int:
    return -(abs(hash(session_id)) % (10 ** 9))


def _construir_contexto_dashboard(mensaje: str, tab_activo: str = "") -> str:
    """
    Construye el bloque de contexto enriquecido para el asistente del dashboard.
    Incluye: ventas del día, catálogo completo, top productos, histórico, compras,
    caja, gastos, fiados, inventario crítico, márgenes y memoria persistente.
    """
    from memoria import cargar_memoria, cargar_caja, cargar_gastos_hoy
    from datetime import datetime
    import config

    mem   = cargar_memoria()
    ahora = datetime.now(config.COLOMBIA_TZ)
    fecha_hoy = ahora.strftime("%A %d de %B de %Y, %H:%M")
    hoy_str   = ahora.strftime("%Y-%m-%d")

    # ── Memoria persistente ───────────────────────────────────────────────────
    notas_raw = mem.get("notas", {})
    if isinstance(notas_raw, list):
        notas_raw = {"observaciones": notas_raw} if notas_raw else {}
    contexto_negocio = notas_raw.get("contexto_negocio", "")
    decisiones       = notas_raw.get("decisiones", [])
    observaciones    = notas_raw.get("observaciones", [])

    memoria_partes = []
    if contexto_negocio:
        memoria_partes.append("CONTEXTO DEL NEGOCIO:\n" + contexto_negocio)
    if decisiones:
        memoria_partes.append("DECISIONES GUARDADAS:\n" + "\n".join("- " + d for d in decisiones[-10:]))
    if observaciones:
        memoria_partes.append("OBSERVACIONES:\n" + "\n".join("- " + o for o in observaciones[-10:]))
    memoria_texto = "\n\n".join(memoria_partes) + "\n\n" if memoria_partes else ""

    # ── Caja actual ──────────────────────────────────────────────────────────
    try:
        caja = cargar_caja()
        if caja.get("abierta"):
            ef  = caja.get("efectivo", 0)
            tr  = caja.get("transferencias", 0)
            dat = caja.get("datafono", 0)
            ap  = caja.get("monto_apertura", 0)
            total_caja = ef + tr + dat
            caja_texto = (
                "CAJA (abierta desde " + str(caja.get("fecha", "?")) + "):\n"
                "  Apertura: $" + f"{ap:,.0f}" + " | Efectivo: $" + f"{ef:,.0f}" +
                " | Transferencias: $" + f"{tr:,.0f}" + " | Datafono: $" + f"{dat:,.0f}" + "\n"
                "  Total en caja: $" + f"{total_caja:,.0f}"
            )
        else:
            caja_texto = "CAJA: Cerrada (última fecha: " + str(caja.get("fecha", "sin datos")) + ")"
    except Exception:
        caja_texto = "CAJA: Sin datos"

    # ── Gastos del día ───────────────────────────────────────────────────────
    try:
        gastos_hoy = cargar_gastos_hoy()
        if gastos_hoy:
            total_gastos = sum(float(g.get("monto", 0)) for g in gastos_hoy)
            items_gasto  = "\n".join(
                "  " + str(g.get("hora", "?")) + " " + str(g.get("concepto", "?")) +
                " $" + f"{float(g.get('monto', 0)):,.0f}"
                for g in gastos_hoy
            )
            gastos_texto = "GASTOS HOY (total $" + f"{total_gastos:,.0f}" + "):\n" + items_gasto
        else:
            gastos_texto = "GASTOS HOY: ninguno registrado"
    except Exception:
        gastos_texto = "GASTOS: Sin datos"

    # ── Ventas del día (detalle completo) ────────────────────────────────────
    try:
        from sheets import sheets_leer_ventas_del_dia
        ventas_hoy_list = []
        try:
            ventas_hoy_list = [v for v in sheets_leer_ventas_del_dia()
                               if str(v.get("fecha", ""))[:10] == hoy_str]
        except Exception:
            pass
        if not ventas_hoy_list:
            ventas_hoy_list = [v for v in _leer_excel_rango(dias=1)
                               if str(v.get("fecha", ""))[:10] == hoy_str]

        if ventas_hoy_list:
            total_ventas_hoy = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list)
            por_prod: dict = {}
            for v in ventas_hoy_list:
                prod = str(v.get("producto", "")).strip()
                if not prod:
                    continue
                if prod not in por_prod:
                    por_prod[prod] = {"uds": 0.0, "total": 0.0}
                por_prod[prod]["uds"]   += _cantidad_a_float(v.get("cantidad", 1))
                por_prod[prod]["total"] += _to_float(v.get("total", 0))
            lineas_ventas = "\n".join(
                f"  {p}: {d['uds']:.2g} uds — ${d['total']:,.0f}"
                for p, d in sorted(por_prod.items(), key=lambda x: -x[1]["total"])
            )
            ef_hoy  = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list if "efect"  in str(v.get("metodo_pago", "")).lower())
            tr_hoy  = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list if "transf" in str(v.get("metodo_pago", "")).lower())
            dat_hoy = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list if "data"   in str(v.get("metodo_pago", "")).lower())
            ventas_texto = (
                f"VENTAS HOY ({len(ventas_hoy_list)} transacciones, total ${total_ventas_hoy:,.0f}):\n"
                + lineas_ventas
                + f"\n  Pago — Efectivo: ${ef_hoy:,.0f} | Transferencia: ${tr_hoy:,.0f} | Datáfono: ${dat_hoy:,.0f}"
            )
        else:
            ventas_texto = "VENTAS HOY: ninguna registrada aún"
    except Exception:
        ventas_texto = "VENTAS HOY: Sin datos"

    # ── Resumen semanal y mensual ─────────────────────────────────────────────
    try:
        ventas_sem = _leer_excel_rango(dias=7)
        total_sem  = sum(_to_float(v.get("total", 0)) for v in ventas_sem)
        dias_con_ventas = len({str(v.get("fecha", ""))[:10] for v in ventas_sem if _to_float(v.get("total", 0)) > 0})
        promedio_dia = total_sem / max(dias_con_ventas, 1)

        ventas_mes = _leer_excel_rango(mes_actual=True)
        total_mes  = sum(_to_float(v.get("total", 0)) for v in ventas_mes)

        por_dia: dict = {}
        for v in ventas_sem:
            dia = str(v.get("fecha", ""))[:10]
            if dia:
                por_dia[dia] = por_dia.get(dia, 0) + _to_float(v.get("total", 0))
        historico_sem = "\n".join(
            f"  {dia}: ${monto:,.0f}" for dia, monto in sorted(por_dia.items())
        )
        resumen_texto = (
            f"RESUMEN SEMANAL (últimos 7 días):\n"
            f"  Total: ${total_sem:,.0f} | Promedio/día: ${promedio_dia:,.0f} | Días activos: {dias_con_ventas}/7\n"
            + historico_sem + "\n"
            f"RESUMEN MENSUAL (mes actual): ${total_mes:,.0f}"
        )
    except Exception:
        resumen_texto = "RESUMEN SEMANAL/MENSUAL: Sin datos"

    # ── Top 10 productos de la semana ─────────────────────────────────────────
    try:
        por_producto: dict = {}
        for v in ventas_sem:
            prod = str(v.get("producto", "")).strip()
            if not prod:
                continue
            if prod not in por_producto:
                por_producto[prod] = {"uds": 0.0, "total": 0.0}
            por_producto[prod]["uds"]   += _cantidad_a_float(v.get("cantidad", 1))
            por_producto[prod]["total"] += _to_float(v.get("total", 0))
        top10 = sorted(por_producto.items(), key=lambda x: -x[1]["total"])[:10]
        if top10:
            top_lineas = "\n".join(
                f"  {i+1}. {p}: {d['uds']:.2g} uds — ${d['total']:,.0f}"
                for i, (p, d) in enumerate(top10)
            )
            top_texto = "TOP 10 PRODUCTOS (semana):\n" + top_lineas
        else:
            top_texto = "TOP PRODUCTOS: Sin ventas esta semana"
    except Exception:
        top_texto = "TOP PRODUCTOS: Sin datos"

    # ── Compras recientes (últimos 30 días) ───────────────────────────────────
    try:
        compras_rec = _leer_excel_compras(dias=30)
        if compras_rec:
            total_compras = sum(_to_float(c.get("total", 0)) for c in compras_rec)
            items_compras = "\n".join(
                "  " + str(c.get("fecha", "?"))[:10] + " " + str(c.get("proveedor", "?")) +
                " — " + str(c.get("producto", "?")) + " $" + f"{_to_float(c.get('total', 0)):,.0f}"
                for c in compras_rec[-10:]
            )
            compras_texto = (
                f"COMPRAS RECIENTES (30 días, total ${total_compras:,.0f}):\n" + items_compras
            )
        else:
            compras_texto = "COMPRAS: Ninguna registrada en los últimos 30 días"
    except Exception:
        compras_texto = "COMPRAS: Sin datos"

    # ── Fiados activos ───────────────────────────────────────────────────────
    try:
        fiados = mem.get("fiados", {})
        fiados_activos = {
            nombre: datos for nombre, datos in fiados.items()
            if float(datos.get("saldo", 0)) > 0
        }
        if fiados_activos:
            total_fiado = sum(float(d.get("saldo", 0)) for d in fiados_activos.values())
            items_fiado = "\n".join(
                "  " + n + ": $" + f"{float(d.get('saldo', 0)):,.0f}"
                for n, d in sorted(fiados_activos.items(), key=lambda x: -float(x[1].get("saldo", 0)))[:15]
            )
            fiados_texto = (
                "FIADOS ACTIVOS (" + str(len(fiados_activos)) +
                " clientes, total $" + f"{total_fiado:,.0f}" + "):\n" + items_fiado
            )
        else:
            fiados_texto = "FIADOS: Sin saldos pendientes"
    except Exception:
        fiados_texto = "FIADOS: Sin datos"

    # ── Catálogo completo (precios, stock, fracciones) ───────────────────────
    try:
        catalogo  = mem.get("catalogo", {})
        inv_mem   = mem.get("inventario", {})
        lineas_cat = []
        for k, p in catalogo.items():
            precio  = p.get("precio_unidad", 0)
            nombre  = p.get("nombre", k)
            cat     = p.get("categoria", "")
            unidad  = p.get("unidad_medida", "Unidad")
            st_raw  = inv_mem.get(k)
            st_val  = st_raw.get("cantidad") if isinstance(st_raw, dict) else st_raw
            st_str  = f" [stock: {st_val}]" if st_val is not None else ""
            fracs   = p.get("precios_fraccion", {})
            fracs_str = ""
            if fracs:
                partes = []
                for fk, fv in fracs.items():
                    fp = fv.get("precio", fv) if isinstance(fv, dict) else fv
                    partes.append(f"{fk}=${fp:,}")
                fracs_str = " [fracs: " + " | ".join(partes) + "]"
            lineas_cat.append(f"  {nombre} ({cat}) — ${precio:,}/{unidad}{st_str}{fracs_str}")
        catalogo_texto = (
            f"CATALOGO COMPLETO ({len(lineas_cat)} productos):\n" +
            "\n".join(lineas_cat)
        )
    except Exception:
        catalogo_texto = "CATALOGO: Sin datos"

    # ── Inventario crítico ───────────────────────────────────────────────────
    try:
        inventario = mem.get("inventario", {})
        if inventario:
            criticos = [
                "  " + k + ": " + str(v.get("cantidad", 0)) + " " + str(v.get("unidad", "u")) +
                " (min: " + str(v.get("minimo", 0)) + ")"
                for k, v in inventario.items()
                if float(v.get("cantidad", 0)) <= float(v.get("minimo", 0)) * 1.2
                and float(v.get("minimo", 0)) > 0
            ]
            if criticos:
                inv_texto = (
                    "INVENTARIO CRITICO (" + str(len(criticos)) + " productos bajo mínimo):\n" +
                    "\n".join(criticos[:15])
                )
            else:
                inv_texto = "INVENTARIO: " + str(len(inventario)) + " productos registrados, todos sobre mínimo"
        else:
            inv_texto = "INVENTARIO: Pendiente de configurar (aún no hay stock registrado)"
    except Exception:
        inv_texto = "INVENTARIO: Sin datos"

    # ── Márgenes ─────────────────────────────────────────────────────────────
    try:
        catalogo_m = mem.get("catalogo", {})
        prods_con_costo = [p for p in catalogo_m.values() if p.get("precio_compra") or p.get("costo")]
        if prods_con_costo:
            margenes_lineas = []
            for p in prods_con_costo[:15]:
                costo = float(p.get("precio_compra") or p.get("costo", 0))
                venta = float(p.get("precio_unidad", 0))
                if costo > 0 and venta > 0:
                    margen = ((venta - costo) / venta) * 100
                    margenes_lineas.append(
                        "  " + str(p["nombre"]) + ": costo $" + f"{costo:,.0f}" +
                        " -> venta $" + f"{venta:,.0f}" + " (margen " + f"{margen:.0f}" + "%)"
                    )
            margenes_texto = (
                "MARGENES (muestra):\n" + "\n".join(margenes_lineas)
            ) if margenes_lineas else "MARGENES: Pendiente (agrega precio_compra al catálogo)"
        else:
            margenes_texto = "MARGENES: Pendiente de configurar (agrega el precio de compra de cada producto)"
    except Exception:
        margenes_texto = "MARGENES: Sin datos"

    # ── Tab activo ───────────────────────────────────────────────────────────
    tab_ctx = (
        "\nTAB ACTIVO EN DASHBOARD: El usuario está mirando '" + tab_activo +
        "'. Ten esto en cuenta para dar contexto relevante."
    ) if tab_activo else ""

    return (
        "CANAL: Dashboard web — modo gerente/asistente avanzado.\n"
        "FECHA Y HORA ACTUAL: " + fecha_hoy + "\n"
        "\n"
        "## PERSONALIDAD Y MODO DE OPERACION\n"
        "Eres el asistente inteligente de Ferretería Punto Rojo. En este canal tienes un rol dual:\n"
        "1. REGISTRAR con precisión (ventas, gastos, compras, fiados) — igual que en Telegram\n"
        "2. SER GERENTE: analizar, opinar, recomendar, advertir, recordar decisiones pasadas\n"
        "\n"
        "TONO: Directo, claro, con criterio. No eres un bot genérico — conoces este negocio.\n"
        "Si ves algo raro en los datos, lo dices. Si hay una oportunidad, la señalas.\n"
        "Si te preguntan tu opinión, la das con base en los datos reales.\n"
        "\n"
        "FORMATO: Responde con la extensión que el tema requiera. Para análisis, sé detallado.\n"
        "Para registros (ventas/gastos), usa el mismo formato compacto con [VENTA]/[GASTO].\n"
        "No uses markdown (asteriscos, #). Usa texto plano limpio.\n"
        "\n"
        "## ESTADO ACTUAL DEL NEGOCIO\n"
        + caja_texto + "\n\n"
        + ventas_texto + "\n\n"
        + gastos_texto + "\n\n"
        + resumen_texto + "\n\n"
        + top_texto + "\n\n"
        + compras_texto + "\n\n"
        + fiados_texto + "\n\n"
        + inv_texto + "\n\n"
        + margenes_texto + "\n\n"
        + catalogo_texto + "\n\n"
        + memoria_texto
        + "## MEMORIA PERSISTENTE\n"
        "Puedes guardar información importante del negocio usando la acción:\n"
        '[MEMORIA]{"tipo":"decision"|"observacion"|"contexto","contenido":"texto"}[/MEMORIA]\n'
        "Úsala cuando el usuario mencione algo que debe recordarse: cambios de estrategia,\n"
        "observaciones sobre clientes, decisiones de precio, metas, etc.\n"
        "\n"
        "## CAPACIDADES COMPLETAS EN ESTE CANAL\n"
        "- Registrar ventas, gastos, compras, fiados, abonos\n"
        "- Consultar precio de cualquier producto del catálogo (los tienes todos arriba)\n"
        "- Analizar ventas por día, semana, mes, producto, vendedor\n"
        "- Identificar tendencias: qué vende más, qué días son mejores, ticket promedio\n"
        "- Ver márgenes y rentabilidad (cuando estén configurados los costos)\n"
        "- Gestionar inventario y alertas de stock\n"
        "- Revisar compras recientes y proveedores\n"
        "- Recordar y recuperar decisiones pasadas del negocio\n"
        "- Dar opinión y recomendaciones basadas en datos reales"
        + tab_ctx
    )


# ── Endpoint para guardar memoria del negocio ─────────────────────────────────
class MemoriaRequest(BaseModel):
    tipo: str        # "decision" | "observacion" | "contexto_negocio"
    contenido: str


# ── Endpoint para guardar memoria del negocio ─────────────────────────────────
class MemoriaRequest(BaseModel):
    tipo: str        # "decision" | "observacion" | "contexto_negocio"
    contenido: str


@router.post("/chat/memoria")
def guardar_memoria_negocio(req: MemoriaRequest):
    """Guarda una nota/decisión/observación persistente del negocio."""
    from memoria import cargar_memoria, guardar_memoria as _guardar

    if not req.contenido.strip():
        raise HTTPException(status_code=400, detail="Contenido vacío")

    mem   = cargar_memoria()
    notas = mem.get("notas", {})
    if isinstance(notas, list):
        notas = {"observaciones": notas} if notas else {}

    if req.tipo == "contexto_negocio":
        notas["contexto_negocio"] = req.contenido.strip()
    elif req.tipo == "decision":
        from datetime import datetime
        import config
        fecha = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        notas.setdefault("decisiones", []).append(f"[{fecha}] {req.contenido.strip()}")
        notas["decisiones"] = notas["decisiones"][-30:]  # máx 30 decisiones
    else:
        from datetime import datetime
        import config
        fecha = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        notas.setdefault("observaciones", []).append(f"[{fecha}] {req.contenido.strip()}")
        notas["observaciones"] = notas["observaciones"][-30:]

    mem["notas"] = notas
    _guardar(mem, urgente=True)
    return {"ok": True, "tipo": req.tipo}


class ChatRequest(BaseModel):
    mensaje: str
    nombre: str = "Dashboard"
    historial: list = []
    # Si viene con confirmar_pago, se salta Claude y registra directamente
    confirmar_pago: Optional[str] = None   # "efectivo" | "transferencia" | "datafono"
    # ID de sesión único por pestaña del navegador (evita race condition multi-usuario)
    session_id: str = "default"
    # Tab activo en el dashboard (contexto extra para el asistente)
    tab_activo: str = ""
    # Forzar modelo: null=auto, "haiku", "sonnet"
    modelo_preferido: Optional[str] = None


@router.post("/chat")
async def chat_ia(req: ChatRequest):
    """
    Endpoint de chat IA para el dashboard.

    Flujo normal:
      1. procesar_con_claude()      → respuesta con tags [VENTA]
      2. procesar_acciones_async()  → guarda ventas en ventas_pendientes[0]
      3. Si hay ventas pendientes   → devuelve pendiente=True + botones de pago
      4. El frontend muestra botones; el usuario hace clic
      5. Segunda llamada con confirmar_pago="efectivo"|"transferencia"|"datafono"
      6. registrar_ventas_con_metodo_async() → Excel + Sheets + confirmación

    Flujo con método explícito en el mensaje (ej: "venta 3 tornillos efectivo"):
      - Si Claude detecta el método, devuelve PEDIR_CONFIRMACION:efectivo
      - Se registra directamente sin pedir botones
    """
    from ai import procesar_con_claude, procesar_acciones_async
    from ventas_state import ventas_pendientes, registrar_ventas_con_metodo_async, _estado_lock

    log = logging.getLogger("ferrebot.api")

    # ── RAMA B: Confirmación de pago desde botón ─────────────────────────────
    if req.confirmar_pago:
        metodo = req.confirmar_pago.strip().lower()
        if metodo not in ("efectivo", "transferencia", "datafono"):
            raise HTTPException(status_code=400, detail=f"Método de pago inválido: {metodo}")

        _chat_id = _session_chat_id(req.session_id)
        with _estado_lock:
            ventas_pend = list(ventas_pendientes.get(_chat_id, []))

        if not ventas_pend:
            return {
                "ok": True,
                "respuesta": "⚠️ No hay ventas pendientes de confirmar.",
                "acciones": {"ventas": 0, "gastos": 0},
                "pendiente": False,
            }

        confirmacion = await registrar_ventas_con_metodo_async(
            ventas_pend, metodo, req.nombre, _chat_id
        )
        log.info(f"[/chat] ✅ {len(ventas_pend)} venta(s) confirmadas | método: {metodo}")

        return {
            "ok": True,
            "respuesta": "✅ Venta registrada\n" + "\n".join(confirmacion),
            "acciones": {"ventas": len(ventas_pend), "gastos": 0},
            "pendiente": False,
        }

    # ── RAMA A: Mensaje normal ────────────────────────────────────────────────
    if not req.mensaje or not req.mensaje.strip():
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    try:
        mensaje_formateado = f"{req.nombre}: {req.mensaje.strip()}"

        _chat_id = _session_chat_id(req.session_id)

        # ── Contexto dinámico del dashboard (datos reales en cada llamada) ──
        contexto_dash = _construir_contexto_dashboard(req.mensaje, tab_activo=req.tab_activo)

        # Inyectar flag ##DASHBOARD## para que ai.py active modo dashboard
        mensaje_con_flag = f"##DASHBOARD## {mensaje_formateado}"

        # 1. Claude con contexto enriquecido del dashboard
        respuesta_raw = await procesar_con_claude(
            mensaje_usuario=mensaje_con_flag,
            nombre_usuario=req.nombre,
            historial_chat=req.historial,
            contexto_extra=contexto_dash,
        )

        # 2. Parsear acciones
        texto_limpio, acciones, _ = await procesar_acciones_async(
            respuesta_raw, req.nombre, _chat_id
        )

        pedir_pago   = "PEDIR_METODO_PAGO" in acciones
        confirmacion_accion = next(
            (a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None
        )
        gastos_registrados = sum(
            1 for a in acciones if a.startswith("Gasto registrado:")
        )

        # 3a. Método de pago ya viene en la acción (Claude lo detectó) → registrar directo
        if confirmacion_accion:
            metodo = confirmacion_accion.split(":", 1)[1].strip()
            if metodo not in ("efectivo", "transferencia", "datafono"):
                metodo = "efectivo"

            with _estado_lock:
                ventas_pend = list(ventas_pendientes.get(_chat_id, []))

            if ventas_pend:
                conf = await registrar_ventas_con_metodo_async(
                    ventas_pend, metodo, req.nombre, _chat_id
                )
                return {
                    "ok": True,
                    "respuesta": "✅ Venta registrada\n" + "\n".join(conf),
                    "acciones": {"ventas": len(ventas_pend), "gastos": gastos_registrados},
                    "pendiente": False,
                }

        # 3b. Hay ventas esperando método → devolver botones al frontend
        if pedir_pago:
            with _estado_lock:
                ventas_pend = list(ventas_pendientes.get(_chat_id, []))

            if ventas_pend:
                resumen = "\n".join(
                    f"• {v.get('cantidad',1)} {v.get('producto','?')}  ${float(v.get('total',0)):,.0f}"
                    for v in ventas_pend
                )
                texto_previo = texto_limpio.strip() if texto_limpio and texto_limpio.strip() else ""
                texto_botones = (f"{texto_previo}\n\n" if texto_previo else "") + \
                                f"🧾 {resumen}\n\n¿Cómo pagó?"
                return {
                    "ok": True,
                    "respuesta": texto_botones,
                    "acciones": {"ventas": 0, "gastos": gastos_registrados},
                    "pendiente": True,
                    "opciones_pago": [
                        {"label": "💵 Efectivo",      "valor": "efectivo"},
                        {"label": "📲 Transferencia", "valor": "transferencia"},
                        {"label": "💳 Datafono",      "valor": "datafono"},
                    ],
                }

        # 4. Sin ventas pendientes → respuesta normal
        if texto_limpio and texto_limpio.strip():
            texto_final = texto_limpio.strip()
        elif gastos_registrados:
            gasto_msgs = [a for a in acciones if a.startswith("Gasto registrado:")]
            texto_final = "✅ " + "\n".join(gasto_msgs)
        else:
            otras = [a for a in acciones if a not in (
                "PEDIR_METODO_PAGO", "PAGO_PENDIENTE_AVISO", "INICIAR_FLUJO_CLIENTE",
            ) and not a.startswith("PEDIR_CONFIRMACION:")
              and not a.startswith("CLIENTE_DESCONOCIDO:")]
            texto_final = "\n".join(otras) if otras else "(Sin respuesta)"

        return {
            "ok": True,
            "respuesta": texto_final,
            "acciones": {"ventas": 0, "gastos": gastos_registrados},
            "pendiente": False,
        }

    except Exception as e:
        log.error(f"[/chat] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Endpoint SSE para el dashboard con streaming token-a-token.
    Emite eventos:
      data: {"type":"chunk","text":"..."}
      data: {"type":"done","respuesta":"...","acciones":{...},"pendiente":bool}
      data: {"type":"error","message":"..."}
    """
    from ai import procesar_con_claude_stream, procesar_acciones_async
    from ventas_state import ventas_pendientes, registrar_ventas_con_metodo_async, _estado_lock

    log = logging.getLogger("ferrebot.api")

    if not req.mensaje or not req.mensaje.strip():
        async def _err():
            yield f"data: {json.dumps({'type':'error','message':'Mensaje vacío'})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    _chat_id = _session_chat_id(req.session_id)

    async def generate():
        try:
            mensaje_formateado = f"{req.nombre}: {req.mensaje.strip()}"
            contexto_dash = _construir_contexto_dashboard(req.mensaje, tab_activo=req.tab_activo)
            mensaje_con_flag = f"##DASHBOARD## {mensaje_formateado}"
            full_text = ""
            modelo_usado = None  # capturar qué modelo se usó

            async for kind, data in procesar_con_claude_stream(
                mensaje_usuario=mensaje_con_flag,
                nombre_usuario=req.nombre,
                historial_chat=req.historial,
                contexto_extra=contexto_dash,
                modelo_preferido=req.modelo_preferido,
            ):
                if kind == "model":
                    modelo_usado = "sonnet" if "sonnet" in data else "haiku"
                elif kind == "chunk":
                    full_text += data
                    yield f"data: {json.dumps({'type':'chunk','text':data}, ensure_ascii=False)}\n\n"
                elif kind == "done":
                    full_text = data
                    break
                elif kind == "error":
                    yield f"data: {json.dumps({'type':'error','message':data})}\n\n"
                    return

            texto_limpio, acciones, _ = await procesar_acciones_async(
                full_text, req.nombre, _chat_id
            )

            pedir_pago          = "PEDIR_METODO_PAGO" in acciones
            confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
            gastos_reg          = sum(1 for a in acciones if a.startswith("Gasto registrado:"))
            ventas_reg          = 0
            pendiente           = False
            opciones_pago       = None

            if confirmacion_accion:
                metodo = confirmacion_accion.split(":", 1)[1].strip()
                if metodo not in ("efectivo", "transferencia", "datafono"):
                    metodo = "efectivo"
                with _estado_lock:
                    vp = list(ventas_pendientes.get(_chat_id, []))
                if vp:
                    conf = await registrar_ventas_con_metodo_async(vp, metodo, req.nombre, _chat_id)
                    texto_limpio = "✅ Venta registrada\n" + "\n".join(conf)
                    ventas_reg = len(vp)

            elif pedir_pago:
                with _estado_lock:
                    vp = list(ventas_pendientes.get(_chat_id, []))
                if vp:
                    resumen = "\n".join(
                        f"• {v.get('cantidad',1)} {v.get('producto','?')}  ${float(v.get('total',0)):,.0f}"
                        for v in vp
                    )
                    tp = texto_limpio.strip() if texto_limpio and texto_limpio.strip() else ""
                    texto_limpio = (f"{tp}\n\n" if tp else "") + f"🧾 {resumen}\n\n¿Cómo pagó?"
                    pendiente = True
                    opciones_pago = [
                        {"label": "💵 Efectivo",      "valor": "efectivo"},
                        {"label": "📲 Transferencia", "valor": "transferencia"},
                        {"label": "💳 Datafono",      "valor": "datafono"},
                    ]

            if not texto_limpio or not texto_limpio.strip():
                if gastos_reg:
                    texto_limpio = "✅ " + "\n".join(a for a in acciones if a.startswith("Gasto registrado:"))
                else:
                    otras = [a for a in acciones if a not in (
                        "PEDIR_METODO_PAGO","PAGO_PENDIENTE_AVISO","INICIAR_FLUJO_CLIENTE"
                    ) and not a.startswith("PEDIR_CONFIRMACION:") and not a.startswith("CLIENTE_DESCONOCIDO:")]
                    texto_limpio = "\n".join(otras) if otras else "(Sin respuesta)"

            payload = {
                "type": "done",
                "respuesta": texto_limpio.strip(),
                "acciones": {"ventas": ventas_reg, "gastos": gastos_reg},
                "pendiente": pendiente,
                "opciones_pago": opciones_pago,
                "modelo": modelo_usado,
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        except Exception as exc:
            log.error(f"[/chat/stream] {exc}", exc_info=True)
            yield f"data: {json.dumps({'type':'error','message':str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )



# ── Transcripción de audio desde el Dashboard ─────────────────────────────────

@router.post("/chat/transcribir")
async def transcribir_audio(audio: UploadFile = File(...)):
    """
    Recibe un archivo de audio desde el dashboard, lo transcribe con Whisper
    y devuelve el texto. El frontend luego envía ese texto al /chat/stream.
    """
    import tempfile, os

    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Transcripción no disponible (sin clave OpenAI)")

    # Validar que sea audio
    content_type = audio.content_type or ""
    if not (content_type.startswith("audio/") or audio.filename.endswith((".ogg", ".webm", ".mp3", ".wav", ".m4a"))):
        raise HTTPException(status_code=400, detail="Formato de audio no soportado")

    # Leer y validar tamaño (~90s de audio webm/opus ≈ 1.5-2 MB, margen hasta 3 MB)
    MAX_AUDIO_BYTES = 3 * 1024 * 1024  # 3 MB
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio demasiado largo (máx ~90 segundos). Tamaño: {len(audio_bytes) / 1024 / 1024:.1f} MB"
        )
    suffix = "." + (audio.filename.rsplit(".", 1)[-1] if "." in audio.filename else "webm")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        ruta_tmp = tmp.name

    try:
        def _transcribir():
            with open(ruta_tmp, "rb") as f:
                return config.openai_client.audio.transcriptions.create(
                    model="whisper-1", file=f, language="es"
                )

        import asyncio
        resultado = await asyncio.to_thread(_transcribir)
        texto = resultado.text.strip()

        if not texto:
            return {"ok": False, "texto": ""}

        return {"ok": True, "texto": texto}

    except Exception as e:
        logging.getLogger("ferrebot.api").error(f"[/chat/transcribir] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(ruta_tmp)
        except Exception:
            pass

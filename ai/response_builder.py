"""
ai/response_builder.py — Parsing y ejecución de acciones embebidas en respuestas de Claude.

Parsea los tags estructurados que Claude incluye en sus respuestas:
  [VENTA]...[/VENTA]
  [GASTO]...[/GASTO]
  [EXCEL]...[/EXCEL]
  etc.

Y los convierte en efectos: registrar ventas, guardar gastos, generar Excel.

DEPENDENCIAS DE ESTADO (importadas lazy para evitar ciclo con ventas_state):
  - ventas_state.ventas_pendientes
  - ventas_state.registrar_ventas_con_metodo
  - ventas_state._estado_lock

DEPENDENCIAS PG (importadas lazy para evitar ciclo con ai.__init__):
  - ai._pg_buscar_cliente
  - ai._pg_guardar_cliente
  - ai._pg_borrar_cliente

No importar estos al nivel de módulo — mantener los imports dentro de las funciones.
"""

# -- stdlib --
import asyncio
import json
import logging
import re
from datetime import datetime

# -- propios --
import config
import db as _db
from memoria import (
    buscar_producto_en_catalogo,
    actualizar_precio_en_catalogo,
    invalidar_cache_memoria,
    cargar_caja,
    obtener_resumen_caja,
    guardar_gasto,
    guardar_fiado_movimiento,
    abonar_fiado,
    cargar_inventario,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, _normalizar
from ai.price_cache import registrar as _registrar_precio_reciente
from ai.excel_gen import generar_excel_personalizado

logger = logging.getLogger("ferrebot.ai.response_builder")


def procesar_acciones(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    from ventas_state import (ventas_pendientes, registrar_ventas_con_metodo,
        _estado_lock, mensajes_standby, limpiar_pendientes_expirados, _guardar_pendiente)
    from ai import _pg_buscar_cliente, _pg_guardar_cliente, _pg_borrar_cliente

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
            from memoria import cargar_memoria, guardar_memoria as _gm_neg
            mem   = cargar_memoria()
            mem["negocio"].update(datos)
            _gm_neg(mem)
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

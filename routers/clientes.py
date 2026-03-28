"""
Router: Clientes — /clientes/*
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
from routers.shared import (
    _hoy, _hace_n_dias, _leer_excel_rango, _leer_excel_compras,
    _to_float, _cantidad_a_float, _stock_wayper,
)

logger = logging.getLogger("ferrebot.api")

router = APIRouter()


# ── Clientes ──────────────────────────────────────────────────────────────────
@router.get("/clientes/buscar")
def buscar_clientes_endpoint(q: str = Query(default="")):
    """
    Busca clientes en la hoja 'Clientes' del Excel por nombre o identificación.
    Devuelve lista de coincidencias para el autocompletado del dashboard.
    """
    try:
        from excel import cargar_clientes
        from utils import _normalizar
        clientes = cargar_clientes()
        if not q.strip():
            return {"clientes": clientes[:10], "total": len(clientes)}

        q_norm = _normalizar(q.strip())
        resultado = []
        for c in clientes:
            nombre_norm = _normalizar(c.get("Nombre tercero", "") or "")
            id_norm     = _normalizar(str(c.get("Identificacion", "") or ""))
            # Buscar la query completa como substring (para "rene acosta" → encuentra "rene acosta medina")
            # O buscar cada palabra individualmente
            if q_norm in nombre_norm or q_norm in id_norm:
                resultado.append(c)
            else:
                palabras = [p for p in q_norm.split() if p]
                if palabras and all(p in nombre_norm or p in id_norm for p in palabras):
                    resultado.append(c)
        resultado.sort(key=lambda x: len(str(x.get("Nombre tercero", ""))))
        return {"clientes": resultado[:10], "total": len(resultado)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class NuevoCliente(BaseModel):
    nombre:         str
    tipo_id:        str  = "CC"   # CC | NIT | CE | PAS
    identificacion: str  = ""
    tipo_persona:   str  = "Natural"
    correo:         str  = ""
    telefono:       str  = ""
    direccion:      str  = ""

class NuevoCliente(BaseModel):
    nombre:         str
    tipo_id:        str  = "CC"   # CC | NIT | CE | PAS
    identificacion: str  = ""
    tipo_persona:   str  = "Natural"
    correo:         str  = ""
    telefono:       str  = ""
    direccion:      str  = ""

@router.post("/clientes")
def crear_cliente_endpoint(body: NuevoCliente):
    """Crea un cliente nuevo en la hoja Clientes del Excel."""
    try:
        from excel import guardar_cliente_nuevo, buscar_cliente, buscar_clientes_multiples
        from utils import _normalizar

        if not body.nombre.strip():
            raise HTTPException(status_code=400, detail="El nombre es obligatorio")

        # ── Verificar duplicados ──────────────────────────────────────────────
        # 1. Por identificación (exacto) si viene informada
        if body.identificacion.strip():
            existente = buscar_cliente(body.identificacion.strip())
            if existente:
                return {
                    "ok":      True,
                    "existia": True,
                    "cliente": existente,
                    "mensaje": "El cliente ya estaba registrado (misma identificación)",
                }

        # 2. Por nombre (flexible) — evita duplicados cuando no hay cédula
        candidatos_nombre = buscar_clientes_multiples(body.nombre.strip(), limite=3)
        for candidato in candidatos_nombre:
            nombre_existente = _normalizar(candidato.get("Nombre tercero", "") or "")
            nombre_nuevo     = _normalizar(body.nombre.strip())
            # Coincidencia de ≥80 % de palabras → considerar duplicado
            palabras_ex  = set(nombre_existente.split())
            palabras_nu  = set(nombre_nuevo.split())
            if palabras_ex and palabras_nu:
                interseccion = palabras_ex & palabras_nu
                similitud    = len(interseccion) / max(len(palabras_ex), len(palabras_nu))
                if similitud >= 0.6:
                    return {
                        "ok":      True,
                        "existia": True,
                        "cliente": candidato,
                        "mensaje": f"Ya existe un cliente con nombre similar: '{candidato.get('Nombre tercero')}'",
                    }

        ok = guardar_cliente_nuevo(
            nombre         = body.nombre.strip(),
            tipo_id        = body.tipo_id,
            identificacion = body.identificacion.strip(),
            tipo_persona   = body.tipo_persona,
            correo         = body.correo.strip(),
            telefono       = body.telefono.strip(),
            direccion      = body.direccion.strip(),
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Error guardando cliente en Excel")
        return {"ok": True, "existia": False, "mensaje": f"Cliente '{body.nombre.strip().upper()}' creado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Editar / Eliminar Ventas ──────────────────────────────────────────────────

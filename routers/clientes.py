"""
Router: Clientes — /clientes/*
Fuente de datos: PostgreSQL (tabla `clientes`).
Sin dependencias de excel.py, openpyxl ni Drive.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import config
import db
from utils import _normalizar

logger = logging.getLogger("ferrebot.api")

router = APIRouter()


# ── Helpers internos ──────────────────────────────────────────────────────────

def _row_to_cliente(r: dict) -> dict:
    """
    Mapea una fila de la tabla `clientes` al formato canónico que esperan
    el dashboard y la lógica de deduplicación (claves en español, igual que
    antes con Excel).
    """
    return {
        "id":             r.get("id"),
        "Nombre tercero": r.get("nombre", "") or "",
        "Identificacion": r.get("identificacion", "") or "",
        "Tipo ID":        r.get("tipo_id", "") or "",
        "Tipo persona":   r.get("tipo_persona", "") or "",
        "Correo":         r.get("correo", "") or "",
        "Telefono":       r.get("telefono", "") or "",
        "Direccion":      r.get("direccion", "") or "",
        "created_at":     str(r["created_at"]) if r.get("created_at") else "",
    }


# ── GET /clientes/buscar ──────────────────────────────────────────────────────

@router.get("/clientes/buscar")
def buscar_clientes_endpoint(q: str = Query(default="")):
    """
    Busca clientes en la tabla `clientes` por nombre o identificación.
    Devuelve lista de coincidencias (máx. 10) para el autocompletado del dashboard.
    """
    try:
        q_strip = q.strip()

        if not q_strip:
            # Sin filtro → primeros 10 ordenados por nombre + conteo total
            filas = db.query_all(
                "SELECT * FROM clientes ORDER BY nombre LIMIT 10"
            )
            total_row = db.query_one("SELECT COUNT(*) AS n FROM clientes")
            total = int(total_row["n"]) if total_row else 0
            return {
                "clientes": [_row_to_cliente(r) for r in filas],
                "total":    total,
            }

        # Con filtro: búsqueda flexible por nombre (ILIKE) o identificación exacta
        # La búsqueda multi-palabra funciona: "rene acosta" → ILIKE '%rene acosta%'
        patron = f"%{q_strip}%"
        filas = db.query_all(
            """
            SELECT *
            FROM   clientes
            WHERE  nombre        ILIKE %s
               OR  identificacion ILIKE %s
            ORDER  BY LENGTH(nombre)
            LIMIT  10
            """,
            (patron, patron),
        )

        # Fallback multi-palabra si no hay resultados directos
        if not filas:
            palabras = [p for p in _normalizar(q_strip).split() if p]
            if palabras:
                # Construye condición AND sobre cada palabra
                condiciones = " AND ".join(
                    ["(LOWER(nombre) LIKE %s OR LOWER(identificacion) LIKE %s)"] * len(palabras)
                )
                params = []
                for p in palabras:
                    params += [f"%{p}%", f"%{p}%"]
                filas = db.query_all(
                    f"SELECT * FROM clientes WHERE {condiciones} ORDER BY LENGTH(nombre) LIMIT 10",
                    params,
                )

        clientes = [_row_to_cliente(r) for r in filas]
        return {"clientes": clientes, "total": len(clientes)}

    except Exception as e:
        logger.exception("buscar_clientes_endpoint")
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /clientes ────────────────────────────────────────────────────────────

class NuevoCliente(BaseModel):
    nombre:         str
    tipo_id:        str = "CC"        # CC | NIT | CE | PAS
    identificacion: str = ""
    tipo_persona:   str = "Natural"
    correo:         str = ""
    telefono:       str = ""
    direccion:      str = ""


@router.post("/clientes")
def crear_cliente_endpoint(body: NuevoCliente):
    """
    Crea un cliente nuevo en la tabla `clientes`.
    Verifica duplicados por identificación (exacto) y por nombre (≥60 % similitud).
    """
    try:
        if not body.nombre.strip():
            raise HTTPException(status_code=400, detail="El nombre es obligatorio")

        # ── 1. Duplicado por identificación ───────────────────────────────────
        id_strip = body.identificacion.strip()
        if id_strip:
            existente = db.query_one(
                "SELECT * FROM clientes WHERE identificacion = %s LIMIT 1",
                (id_strip,),
            )
            if existente:
                return {
                    "ok":      True,
                    "existia": True,
                    "cliente": _row_to_cliente(existente),
                    "mensaje": "El cliente ya estaba registrado (misma identificación)",
                }

        # ── 2. Duplicado por nombre (similitud ≥ 60 %) ───────────────────────
        nombre_strip  = body.nombre.strip()
        patron_nombre = f"%{nombre_strip}%"
        candidatos = db.query_all(
            """
            SELECT * FROM clientes
            WHERE nombre ILIKE %s
            ORDER BY id
            LIMIT 5
            """,
            (patron_nombre,),
        )
        nombre_nuevo_norm = _normalizar(nombre_strip)
        palabras_nu = set(nombre_nuevo_norm.split())

        for candidato in candidatos:
            nombre_ex_norm = _normalizar(candidato.get("nombre", "") or "")
            palabras_ex    = set(nombre_ex_norm.split())
            if palabras_ex and palabras_nu:
                interseccion = palabras_ex & palabras_nu
                similitud    = len(interseccion) / max(len(palabras_ex), len(palabras_nu))
                if similitud >= 0.6:
                    return {
                        "ok":      True,
                        "existia": True,
                        "cliente": _row_to_cliente(candidato),
                        "mensaje": (
                            f"Ya existe un cliente con nombre similar: "
                            f"'{candidato.get('nombre')}'"
                        ),
                    }

        # ── 3. Insertar ───────────────────────────────────────────────────────
        nuevo = db.execute_returning(
            """
            INSERT INTO clientes
                (nombre, tipo_id, identificacion, tipo_persona, correo, telefono, direccion)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                nombre_strip.upper(),
                body.tipo_id,
                id_strip,
                body.tipo_persona,
                body.correo.strip(),
                body.telefono.strip(),
                body.direccion.strip(),
            ),
        )

        if not nuevo:
            raise HTTPException(status_code=500, detail="Error guardando cliente en la base de datos")

        return {
            "ok":      True,
            "existia": False,
            "cliente": _row_to_cliente(nuevo),
            "mensaje": f"Cliente '{nombre_strip.upper()}' creado",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("crear_cliente_endpoint")
        raise HTTPException(status_code=500, detail=str(e))

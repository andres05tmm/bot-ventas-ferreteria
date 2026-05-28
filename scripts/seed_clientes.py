"""
scripts/seed_clientes.py — Carga clientes iniciales de una ferretería nueva.

Lee un CSV o XLSX e inserta filas en `clientes`. Idempotente: omite el cliente si
ya existe uno con la misma `identificacion` (o, si no trae identificación, el mismo
`nombre`), para que correrlo dos veces no duplique.

Uso:
    railway run python scripts/seed_clientes.py --file=clientes.csv
    python scripts/seed_clientes.py --file=clientes.xlsx --dry-run

Columnas reconocidas (encabezado, case-insensitive):
    nombre*        — obligatoria
    identificacion — opcional (recomendada para idempotencia y FE)
    tipo_id        — opcional (ej: CC, NIT)
    tipo_persona   — opcional (natural | juridica)
    correo, telefono, direccion, ciudad_nombre — opcionales
    regimen_fiscal — opcional (1=Responsable IVA, 2=No responsable; default 2)
    municipio_dian — opcional (ID interno DIAN; default 149 = Cartagena)
"""

# -- stdlib --
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import db as _db


def _leer_filas(ruta: str) -> list[dict]:
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".csv":
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            return [{(k or "").strip().lower(): v for k, v in fila.items()}
                    for fila in csv.DictReader(f)]
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            print("❌ Para XLSX se necesita openpyxl.")
            sys.exit(1)
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            heads = [str(c).strip().lower() if c is not None else "" for c in next(it)]
        except StopIteration:
            return []
        return [dict(zip(heads, fila)) for fila in it
                if fila and not all(c is None for c in fila)]
    print(f"❌ Extensión no soportada: {ext}. Usa .csv o .xlsx")
    sys.exit(1)


def _val(fila: dict, key: str):
    v = fila.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int_or_none(fila: dict, key: str):
    v = _val(fila, key)
    if v is None:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _ya_existe(nombre: str, identificacion: str | None) -> bool:
    if identificacion:
        row = _db.query_one(
            "SELECT 1 FROM clientes WHERE identificacion = %s LIMIT 1", [identificacion])
    else:
        row = _db.query_one(
            "SELECT 1 FROM clientes WHERE LOWER(nombre) = LOWER(%s) LIMIT 1", [nombre])
    return row is not None


def main() -> int:
    ap = argparse.ArgumentParser(description="Carga clientes iniciales.")
    ap.add_argument("--file", required=True, help="Ruta al CSV o XLSX.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ Archivo no encontrado: {args.file}")
        return 1
    filas = _leer_filas(args.file)
    if not filas:
        print("❌ El archivo no tiene filas de datos.")
        return 1
    if not args.dry_run and not _db.init_db():
        print("❌ No se pudo conectar a la BD. ¿DATABASE_URL configurada?")
        return 1

    insertados = saltados = duplicados = 0
    for i, fila in enumerate(filas, start=2):
        nombre = _val(fila, "nombre")
        if not nombre:
            print(f"  ⚠ fila {i} saltada (sin nombre): {fila}")
            saltados += 1
            continue
        ident = _val(fila, "identificacion")

        if args.dry_run:
            print(f"  [dry] {nombre} | id={ident or '-'} | tel={_val(fila,'telefono') or '-'}")
            insertados += 1
            continue

        if _ya_existe(nombre, ident):
            duplicados += 1
            continue

        _db.execute(
            """
            INSERT INTO clientes (nombre, tipo_id, identificacion, tipo_persona,
                                  correo, telefono, direccion, regimen_fiscal,
                                  municipio_dian, ciudad_nombre)
            VALUES (%s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s, 2), COALESCE(%s, 149), COALESCE(%s, 'Cartagena'))
            """,
            [nombre, _val(fila, "tipo_id"), ident, _val(fila, "tipo_persona"),
             _val(fila, "correo"), _val(fila, "telefono"), _val(fila, "direccion"),
             _int_or_none(fila, "regimen_fiscal"), _int_or_none(fila, "municipio_dian"),
             _val(fila, "ciudad_nombre")],
        )
        insertados += 1

    print(f"\n✅ Clientes procesados: {insertados} nuevos, {duplicados} ya existían, "
          f"{saltados} saltados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

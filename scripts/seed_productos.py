"""
scripts/seed_productos.py — Carga el catálogo inicial de una ferretería nueva.

Lee un archivo CSV o XLSX y hace UPSERT en la tabla `productos` (idempotente por
`clave`, que es UNIQUE). Si la fila no trae `clave`, se deriva del nombre.

Uso:
    railway run python scripts/seed_productos.py --file=catalogo.csv
    python scripts/seed_productos.py --file=catalogo.xlsx

Columnas reconocidas (encabezado, case-insensitive; el resto se ignora):
    nombre*        — obligatoria
    precio_unidad* — obligatoria (entero, sin separadores de miles)
    clave          — opcional (se deriva de nombre si falta)
    categoria      — opcional
    codigo         — opcional
    unidad_medida  — opcional (default "Unidad")

Ejemplo CSV:
    nombre,categoria,precio_unidad,unidad_medida
    Martillo,Herramienta,24000,Unidad
    Lija N°100,Abrasivos,2000,Unidad
"""

# -- stdlib --
import argparse
import csv
import os
import re
import sys
import unicodedata

# Permitir `import db` al correr desde la raíz del repo o desde scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Consola en UTF-8 (los mensajes usan ✅/⚠; evita crash en Windows cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# -- terceros --
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -- propios --
import db as _db


def _slug(nombre: str) -> str:
    """Deriva una clave estable estilo catálogo: 'Lija N°100' → 'lija_n100'."""
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^\w\s/-]", "", s)        # quitar °, ", etc.
    s = re.sub(r"[\s/-]+", "_", s.strip())  # espacios/barras → _
    return re.sub(r"_+", "_", s).strip("_")


def _parse_precio(valor) -> int | None:
    if valor is None:
        return None
    s = str(valor).strip().replace("$", "").replace(".", "").replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _leer_filas(ruta: str) -> list[dict]:
    """Lee CSV o XLSX → lista de dicts con claves de encabezado en minúscula."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".csv":
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            return [{(k or "").strip().lower(): v for k, v in fila.items()}
                    for fila in csv.DictReader(f)]
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            print("❌ Para archivos XLSX se necesita openpyxl (pip install openpyxl).")
            sys.exit(1)
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb.active
        filas_iter = ws.iter_rows(values_only=True)
        try:
            encabezados = [str(c).strip().lower() if c is not None else "" for c in next(filas_iter)]
        except StopIteration:
            return []
        out = []
        for fila in filas_iter:
            if fila is None or all(c is None for c in fila):
                continue
            out.append(dict(zip(encabezados, fila)))
        return out
    print(f"❌ Extensión no soportada: {ext}. Usa .csv o .xlsx")
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Carga catálogo inicial a productos.")
    ap.add_argument("--file", required=True, help="Ruta al CSV o XLSX del catálogo.")
    ap.add_argument("--dry-run", action="store_true", help="No escribe; solo muestra qué haría.")
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

    insertados = actualizados = saltados = 0
    for i, fila in enumerate(filas, start=2):  # fila 1 = encabezado
        nombre = str(fila.get("nombre", "") or "").strip()
        precio = _parse_precio(fila.get("precio_unidad"))
        if not nombre or precio is None:
            print(f"  ⚠ fila {i} saltada (falta nombre o precio_unidad válido): {fila}")
            saltados += 1
            continue

        clave = str(fila.get("clave", "") or "").strip() or _slug(nombre)
        categoria = str(fila.get("categoria", "") or "").strip() or "Otros"
        codigo = str(fila.get("codigo", "") or "").strip() or None
        unidad = str(fila.get("unidad_medida", "") or "").strip() or "Unidad"

        if args.dry_run:
            print(f"  [dry] {clave} | {nombre} | {categoria} | ${precio} | {unidad}")
            insertados += 1
            continue

        row = _db.execute_returning(
            """
            INSERT INTO productos (clave, nombre, nombre_lower, categoria, codigo,
                                   precio_unidad, unidad_medida, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (clave) DO UPDATE SET
                nombre        = EXCLUDED.nombre,
                nombre_lower  = EXCLUDED.nombre_lower,
                categoria     = EXCLUDED.categoria,
                codigo        = EXCLUDED.codigo,
                precio_unidad = EXCLUDED.precio_unidad,
                unidad_medida = EXCLUDED.unidad_medida,
                activo        = TRUE,
                updated_at    = NOW()
            RETURNING (xmax = 0) AS insertado
            """,
            [clave, nombre, nombre.lower(), categoria, codigo, precio, unidad],
        )
        if row and row.get("insertado"):
            insertados += 1
        else:
            actualizados += 1

    print(f"\n✅ Catálogo procesado: {insertados} nuevos, {actualizados} actualizados, "
          f"{saltados} saltados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

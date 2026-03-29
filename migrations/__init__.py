# migrations/__init__.py
# Directorio de scripts de migración de datos a PostgreSQL.
# Cada script es idempotente (seguro de re-ejecutar).
#
# Orden de ejecución (dependencias):
#   001_migrate_memoria.py      — catálogo + inventario base
#   002_migrate_historico.py    — histórico de ventas diario
#   003_migrate_ventas.py       — ventas detalladas desde Excel
#   004_migrate_gastos_caja.py  — gastos y estado de caja
#   005_migrate_compras.py      — historial de compras
#   006_migrate_fiados.py       — fiados por cliente
#   007_migrate_proveedores.py  — facturas y abonos a proveedores
#
# Ejecutar individualmente en Railway:
#   railway run python migrations/001_migrate_memoria.py

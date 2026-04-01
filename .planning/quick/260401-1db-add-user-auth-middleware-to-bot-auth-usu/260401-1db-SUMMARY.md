# Quick Task 260401-1db: Summary

**Task:** Add user auth middleware to bot — auth/usuarios.py, /confirmar, /registrar_vendedor, tag inserts with usuario_id  
**Date:** 2026-04-01  
**Commits:** 0fa5584 (feat), a18514e (docs)

## What was delivered

### New files
- `auth/__init__.py` — makes auth a package
- `auth/usuarios.py` — 4 DB functions: get_usuario, is_admin, registrar_telegram_id, crear_vendedor
- `handlers/cmd_auth.py` — /confirmar and /registrar_vendedor command handlers
- `tests/test_auth_usuarios.py` — 16 unit tests for auth functions

### Modified files
- `handlers/mensajes.py` — auth gate at top of _procesar_mensaje (unregistered users blocked)
- `handlers/comandos.py` — exports comando_confirmar, comando_registrar_vendedor
- `ventas_state.py` — INSERT INTO ventas includes usuario_id
- `handlers/cmd_inventario.py` — INSERT INTO compras includes usuario_id
- `services/caja_service.py` — guardar_gasto accepts optional usuario_id
- `routers/caja.py` — INSERT INTO gastos includes usuario_id
- `routers/ventas.py` — INSERT INTO ventas includes usuario_id

## Test results

- 16 new auth tests: all passed
- Full suite: 161 tests, 0 failed (145 pre-existing + 16 new)

## Key decisions

- Lazy imports in auth/usuarios.py to avoid circular imports with handlers
- usuario_id optional (None default) in all insert signatures — backward compatible
- Auth gate uses `update.effective_user.id` in _procesar_mensaje before any dispatch

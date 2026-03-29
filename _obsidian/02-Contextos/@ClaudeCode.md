# @ClaudeCode — Contexto de trabajo FerreBot

> Pega este contexto al inicio de cada sesión de Claude Code, o ponlo en `CLAUDE.md` para que lo lea automáticamente.

---

## 🤖 Eres el agente de refactorización de FerreBot

FerreBot es un bot de Telegram para una ferretería en Cartagena, Colombia. Gestiona ventas, inventario, caja, fiados y catálogo de productos. Corre en Railway con PostgreSQL.

---

## 📌 Reglas absolutas

1. **NUNCA borres** funciones o archivos existentes sin instrucción explícita
2. **NUNCA toques** `db.py`, `config.py`, `main.py` — están bien como están
3. **Respeta imports existentes** — si `handlers/mensajes.py` importa de `memoria.py`, `memoria.py` sigue existiendo
4. **Un commit por tarea** cuando termines
5. **Verifica siempre** que `python main.py` arranca sin errores antes de hacer commit

---

## 🗂️ Estructura del proyecto

```
bot-ventas-ferreteria/
├── ai.py              # Motor principal Claude (2685 líneas — reducir en Tarea I)
├── memoria.py         # Capa de datos (convertir en thin wrapper en Tarea H)
├── handlers/
│   ├── comandos.py    # Handlers de comandos Telegram (dividir en Tarea F)
│   ├── mensajes.py
│   ├── callbacks.py
│   └── productos.py
├── routers/           # API FastAPI
├── skills/            # Archivos .md con conocimiento del dominio
├── db.py              # ⛔ NO TOCAR
├── config.py          # ⛔ NO TOCAR
├── main.py            # ⛔ NO TOCAR
└── _obsidian/         # Vault de Obsidian — tus notas de tareas
    └── 01-Proyecto/
        ├── MAPA.md
        ├── TAREA-A.md ... TAREA-J.md
```

---

## 🚦 Cómo recibir una tarea

Cuando el usuario te diga "ejecuta TAREA-X":

1. Lee `_obsidian/01-Proyecto/TAREA-X.md`
2. Verifica que sus dependencias estén completas
3. Ejecuta exactamente lo que indica
4. Corre los tests indicados
5. Verifica `python main.py`
6. Haz commit con el mensaje indicado en la tarea
7. Reporta: ✅ TAREA X COMPLETA

---

## 🧪 Comandos de verificación estándar

```bash
# Verificar imports
python -c "import ai; import memoria; print('OK')"

# Correr tests del módulo nuevo
python -m pytest tests/test_MODULO.py -v

# Correr todos los tests unitarios
python -m pytest tests/ -v --ignore=test_suite.py

# Verificar que el bot arranca
python main.py &
sleep 3 && kill %1
```

---

## 📦 Variables de entorno necesarias

El bot usa estas variables (en Railway o `.env`):
- `DATABASE_URL` — PostgreSQL
- `TELEGRAM_TOKEN` — token del bot
- `ANTHROPIC_API_KEY` — Claude API
- `AUTHORIZED_CHAT_IDS` — nueva (Tarea A) — IDs separados por coma

---

## 🗺️ Dependencias entre módulos

```
config.py ← todos
db.py ← memoria.py, routers/, ventas_state.py
memoria.py ← ai.py, handlers/
ai.py ← handlers/mensajes.py, handlers/comandos.py
ventas_state.py ← handlers/callbacks.py, handlers/mensajes.py
```

# claude-mem — memoria persistente para sesiones de dev

`claude-mem` es un plugin de Claude Code que captura automáticamente lo que
pasa en cada sesión, lo comprime con Claude agent-sdk y lo inyecta como
contexto en la siguiente sesión. Esto elimina el "blank slate problem" cada
vez que abrís Claude Code en este repo.

> **OJO — esto es para el CLI de desarrollo, no para el bot.** El bot tiene
> su propio sistema de memoria (Capas 1-4 con el compresor nocturno de
> Haiku que corre en Railway). `claude-mem` solo afecta a vos cuando estás
> codeando con `claude` local.

---

## Instalación

**Ya está instalado en este workspace** (abril 2026). El plugin
`claude-mem@thedotmack` quedó registrado en
`~/.claude/settings.json` → `enabledPlugins`. La próxima vez que abras
una sesión de Claude Code en este repo, los hooks arrancan automático.

Si alguna vez tenés que reinstalarlo o hacerlo en otra máquina:

```bash
# 1. Verificar que Claude Code está instalado y en PATH
claude --version

# 2. Instalar claude-mem para Claude Code
npx claude-mem install --ide claude-code

# 3. Verificar que quedó registrado
cat ~/.claude/settings.json | grep claude-mem
```

La instalación registra un plugin via el marketplace `thedotmack` y
activa los 5 hooks: `SessionStart`, `UserPromptSubmit`, `PostToolUse`,
`Stop`, `SessionEnd`.

### Worker service (opcional — requiere Bun)

El worker habilita búsqueda FTS5 en memorias viejas y un dashboard web
en `http://localhost:37777`. **Requiere Bun** (no Node). Para activarlo:

```bash
# 1. Instalar Bun: https://bun.sh
curl -fsSL https://bun.sh/install | bash

# 2. Reiniciar terminal y arrancar worker
npx claude-mem start

# 3. Verificar
npx claude-mem status
```

Sin el worker, los hooks siguen capturando contexto, pero `/mem-search`
y el dashboard no funcionan. El valor principal (inyección automática
de contexto al arrancar una sesión) funciona igual.

---

## Comandos útiles dentro de Claude Code

Una vez instalado, en cualquier sesión de Claude Code:

| Comando | Qué hace |
|---|---|
| `/mem-search <query>` | Busca en la memoria comprimida de sesiones pasadas |
| `/mem-recent` | Muestra las últimas observaciones capturadas |
| `/mem-stats` | Estadísticas de la base de memoria |

Además, al abrir una sesión nueva, claude-mem inyecta automáticamente el
contexto relevante (decisiones, bugs resueltos, patrones del repo).

---

## Seguridad — qué no indexar

`claude-mem` **no tiene un ignore file nativo** (última versión revisada:
v12.2.0, abril 2026). Todo lo que Claude Code lee o escribe durante la
sesión queda capturado.

### Mitigaciones para FerreBot

1. **Nunca leer `.env` ni credenciales dentro de una sesión**. Los
   secrets reales viven en Railway, no en disco local — no hay razón para
   que Claude Code los lea. Si necesitás verificar una env var, preguntale
   a Claude qué var y mirá Railway vos directo.

2. **No pegar tokens en el chat** con claude-mem activo. Si tenés que
   debugear un token, apagá temporalmente el worker (`npx claude-mem
   stop`), hacé el debug y volvelo a prender.

3. **`.gitignore`** del repo ya excluye `.env`, `*.key`, `*.pem`,
   `memoria.json`, `ventas.xlsx` — esto protege contra commits
   accidentales, pero **no** contra captura por claude-mem. Es una capa
   diferente.

4. **Revisar la memoria periódicamente**:
   ```bash
   npx claude-mem search "SECRET\|TOKEN\|API_KEY\|password"
   ```
   Si aparece algo, hay comando para purgar (ver docs claude-mem).

5. **Desinstalar cuando termine el proyecto** o si se lo va a usar otro
   dev en la misma máquina:
   ```bash
   npx claude-mem uninstall
   ```

---

## Troubleshooting

**"claude-mem installed with some IDE setup failures"**
Significa que `claude` CLI no está en PATH cuando corriste el install.
Agregalo y corré `npx claude-mem install --ide claude-code` de nuevo.

**La memoria no se inyecta en sesiones nuevas**
Verificá que el worker esté corriendo: `npx claude-mem status`. Si dice
stopped, arrancalo con `npx claude-mem start`.

**La memoria es demasiado ruidosa**
claude-mem tiene un setting `CLAUDE_MEM_SKIP_TOOLS` (env var) para
excluir herramientas del tracking. Por ejemplo, para no capturar lecturas
de binarios y logs grandes:
```bash
export CLAUDE_MEM_SKIP_TOOLS="Bash,Glob"
```
(pero eso también se pierde contexto valioso — probá sin skip primero)

---

## Referencia

- Repo: https://github.com/thedotmack/claude-mem
- Docs: https://docs.claude-mem.ai
- npm: https://www.npmjs.com/package/claude-mem

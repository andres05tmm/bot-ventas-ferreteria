# Cherry-pick de everything-claude-code (ECC)

Este documento resume qué se cherry-pickeó del repo
[`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code)
para FerreBot y por qué.

El **plugin completo** también está instalado globalmente en Claude Code
(`~/.claude/plugins/marketplaces/affaan-m-everything-claude-code/` +
`"everything-claude-code@everything-claude-code": true` en
`~/.claude/settings.json`), lo que habilita también los hooks
automáticos (pre-bash dispatcher, config protection, continuous learning,
etc).

Los archivos duplicados en `.claude/` del repo existen para **portabilidad**:
si alguien clona FerreBot sin haber instalado el plugin ECC, igual tiene
los agents, commands y skills esenciales disponibles.

---

## Agents en `.claude/agents/` (17 totales)

### Core workflow (ya referenciados en `rules/agents.md`)
- `planner` — plan de implementación para features complejas
- `architect` — decisiones de diseño y trade-offs
- `tdd-guide` — test-driven development
- `code-reviewer` — review general
- `security-reviewer` — análisis de seguridad
- `build-error-resolver` — resolver errores de build
- `e2e-runner` — testing end-to-end
- `refactor-cleaner` — limpieza de código muerto
- `doc-updater` — mantenimiento de docs

### Revisores específicos por stack
- `python-reviewer` — Python (crítico, FerreBot es 100% Python)
- `database-reviewer` — revisión de queries/migraciones PG

### Detección y análisis
- `silent-failure-hunter` — busca patrones fail-silent sospechosos.
  Particularmente útil en FerreBot donde muchas funciones retornan
  `[] / None / False` ante excepción (diseño intencional, pero hay que
  distinguir lo intencional de lo que debería ser propagado).
- `performance-optimizer` — busca N+1 queries, bucles ineficientes
- `comment-analyzer` — detecta comments obsoletos o misleading

### Research y contexto
- `docs-lookup` — consulta docs externas (Context7, vendor docs)
- `conversation-analyzer` — revisa sesiones pasadas (pair con claude-mem)
- `harness-optimizer` — optimiza prompts y tool use (meta)

---

## Commands en `.claude/commands/`

| Comando | Qué hace |
|---|---|
| `/plan` | Crea plan de implementación con el planner agent |
| `/tdd` | Arranca ciclo TDD (red → green → refactor) |
| `/code-review` | Review completo (code-reviewer + security-reviewer) |
| `/python-review` | Review específico de Python con python-reviewer |
| `/test-coverage` | Auditoría de coverage con sugerencias |
| `/checkpoint` | Snapshot del progreso actual (complementa claude-mem) |

---

## Skills en `.claude/skills/` (13 totales)

### Pre-existentes (cherry-pick previo, origen ECC)
`api-design`, `backend-patterns`, `database-migrations`, `postgres-patterns`,
`python-patterns`, `python-testing`, `security-review`, `tdd-workflow`,
`ui-ux-pro-max`

### Nuevos en este cherry-pick
- `deep-research` — framework para investigación profunda antes de
  implementar. Refuerza la regla 0 de `development-workflow.md`
  (GitHub search → vendor docs → Exa → package registries).
- `codebase-onboarding` — orientación rápida al entrar a un área nueva
  del repo. Útil cuando Claude toca un módulo que no conocía.
- `coding-standards` — convenciones reforzadas, complementa lo que
  ya está en `rules/coding-style.md`.
- `documentation-lookup` — búsqueda y cacheo de docs de librerías.

---

## Hooks (vía plugin, no en repo)

Los hooks viven en el plugin global y **no se commitean al repo** — si
alguien los necesita, tiene que instalar el plugin ECC. Los más
relevantes que se activan automáticamente:

- **pre:bash:dispatcher** — consolida preflight checks (quality, tmux,
  push, GateGuard) antes de cualquier `bash` tool call.
- **pre:write:doc-file-warning** — warning al crear docs no estándar.
- **pre:edit-write:suggest-compact** — sugiere compactar contexto
  cada cierto volumen de ediciones.
- **pre:observe:continuous-learning** — captura observaciones de uso
  de herramientas para aprendizaje continuo (skill `continuous-learning-v2`).
- **pre:config-protection** — bloquea modificación accidental de configs
  de linter/formatter; fuerza al agente a arreglar el código en vez de
  ablandar el config.
- **pre:governance-capture** — captura eventos de gobernanza (secrets,
  violaciones de política) cuando `ECC_GOVERNANCE_CAPTURE=1`.

Si alguno genera fricción, se puede desactivar puntualmente editando
`~/.claude/settings.json` (pero mejor ajustar el comportamiento del
agente que el hook).

---

## Fuente

- Repo: https://github.com/affaan-m/everything-claude-code
- Commit base del cherry-pick: abril 2026
- Versión: ver `VERSION` en el plugin instalado

Para actualizar:
```bash
npx claude plugin update everything-claude-code@everything-claude-code
```

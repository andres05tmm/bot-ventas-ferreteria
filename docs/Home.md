# FerreBot — Documentación del sistema

> Mapa de contenido (MOC) de la documentación de FerreBot: bot de Telegram + dashboard
> web para ventas, inventario, caja y facturación electrónica DIAN de Ferretería Punto Rojo.
>
> **Cómo usar este vault:** abre la carpeta raíz del repo en Obsidian
> (*Open folder as vault*). Los diagramas (Mermaid) se renderizan solos y el
> *Graph view* muestra cómo se conectan los documentos. Cada `[[enlace]]` lleva a su nota.

---

## Empezar aquí (orden de lectura recomendado)

1. [[PRODUCT]] — qué es el producto, a nivel funcional.
2. [[CLAUDE]] — arquitectura en 1 página: 2 servicios, stack, **mapa de archivos**, flujos.
3. [[01-mapa-estructural]] — estructura del sistema *(con diagramas)*.

---

## Cómo funciona el código (la parte visual)

| Nota | Qué muestra | Diagramas |
|------|-------------|:---------:|
| [[01-mapa-estructural]] | Los 2 servicios (bot / api), routers, flujo de requests | 3 |
| [[02-modelo-de-datos]] | Las tablas de la BD y sus relaciones (ER) por dominio | 13 |
| [[03-logica-negocio]] | Flujos paso a paso: venta, caja, fiados, facturación… | 12 |
| [[10-auditoria-chatbot]] | Cómo el bot interpreta los mensajes (motor IA) | 1 |

---

## Mapa del código (referencia rápida por área)

- [[codebase/ARCHITECTURE|ARCHITECTURE]] — arquitectura general
- [[STRUCTURE]] — organización de carpetas y módulos
- [[codebase/STACK|STACK]] — tecnologías usadas
- [[INTEGRATIONS]] — integraciones externas (Telegram, MATIAS/DIAN, Cloudinary…)
- [[CONVENTIONS]] — convenciones de código
- [[TESTING]] — estrategia de pruebas
- [[CONCERNS]] — riesgos y deudas técnicas

---

## Auditoría y estado del proyecto

- [[auditoria/README|Resumen auditoría]] — resumen ejecutivo + TOP-10 hallazgos
- [[04-hallazgos]] — 47 hallazgos con su estado (CRITICAL/HIGH resueltos)
- [[08-validacion-empirica]] · [[09-validacion-funcional]] — validación contra la BD real

## Clonar a otra ferretería

- [[05-reutilizable-vs-especifico]] — qué es reutilizable vs específico de Punto Rojo
- [[06-nueva-arquitectura]] — propuesta de template-base
- [[07-onboarding-nueva-ferreteria]] — checklist paso a paso para montar una ferretería nueva

---

## Probar el motor de ventas (en vivo, sin Telegram)

El arnés `pruebas_motor.py` mete frases reales por el mismo pipeline del bot y muestra
qué producto/precio resuelve, sin registrar nada:

```
python pruebas_motor.py drywall      # o: fracciones, wayper, puntillas, multi_problemas, ...
```

---
title: El vibe coding no escala. La spec sí.
date: 2026-10-14
platform: linkedin
format: carrusel (documento PDF)
product: astromesh-sdd
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04, 05, 06, 07]
carrusel: carrusel.pdf  # LinkedIn: subir como «documento», título sugerido: «El vibe coding no escala. La spec sí.»
fuentes: astromesh-sdd v0.1.0 (README, CHANGELOG, docs/install.md), examples/specs/001-slugify-title (7 REQ, 3 tareas, suite de 8 tests OK, PASS), corrida en Claude Code (5 NEEDS CLARIFICATION a partir de un pedido de una línea), corrida en OpenCode (planificó con 2 dudas abiertas tras un «aprobado»), revisión final independiente (2 críticos + 6 importantes, cada uno arreglado con un test que falló primero)
primer_comentario: "Repo, instalación para cada agente y el ejemplo completo: https://github.com/monaccode/astromesh-sdd · Docs: https://monaccode.github.io/astromesh/sdd/introduction/"
---

El vibe coding no escala. La spec sí.

Construyo con agentes de código todos los días. El problema nunca fue que escribieran mal. Fue que se olvidaban del porqué: cada sesión nueva arrancaba de cero y las decisiones quedaban enterradas en un chat.

Así que hice lo que hago con cualquier cosa que va a producción: le puse un proceso que deja evidencia.

Hoy libero astromesh-sdd, open source. Siete skills de Spec-Driven Development: spec → plan → tareas → código → verificación. Cada fase es un archivo al lado de tu código, y cada requisito termina trazado a un test.

La misma carpeta sirve para Claude Code, Codex, OpenCode, Kimi, Gemini y Copilot.

En el carrusel, la prueba real: le pedí una línea y me devolvió cinco preguntas que yo no me había hecho.

Repo en el primer comentario 👇

#SpecDrivenDevelopment #AgentesDeIA #ClaudeCode #OpenSource #SoftwareEngineering #Astromesh

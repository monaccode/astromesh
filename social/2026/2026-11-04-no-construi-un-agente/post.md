---
title: No construí un agente
date: 2026-11-04
platform: linkedin
format: post + infografía (1 lámina, plantilla nueva "infografía")
product: ecosistema astromesh
status: published
url: https://lnkd.in/p/dngvWFdn
images: [01]
relacionado: 2026/2026-11-04-el-viaje-de-un-hola (segunda parte, carrusel, para publicar 2026-11-05)
fuentes: docs-site/src/data/ecosystem.ts (19 componentes, 6 grupos, versiones); README.md (7 patrones · 7 tipos de tool; librerías sin runtime desde LangChain, CrewAI, PydanticAI, OpenAI Agents SDK…); memoria astromesh-context (nivel 2 pendiente, documentado). Cifras medidas el 2026-11-04 en 13 repos locales (astromesh, -a2a, -context, -cortex, -herald, -leia, -nebula, -nexus, -okf, -os, -prisma, -rag, -sdd): 2.665 commits sin merges (git log --no-merges); ~4.900 funciones de test (def test_ Python 3.548 + func Test Go 889 + it/test TS 488; los parametrizados cuentan una vez); 9 públicos y 4 privados (Cortex, Herald, Nexus, Prisma) según gh repo view.
retorica: "10 meses" es el marco del autor; el primer commit de astromesh es 2026-03-06 (Clarus, 2025-12-17, no entra en las cifras). Bowshock (privado) queda fuera a propósito. El párrafo de Runa está pendiente: lo escribe Juan Carlos.
---

No construí un agente en estos 10 meses.

Construí todo lo que un agente necesita para no quedarse en demo.

Un agente que responde bien en una notebook es la parte fácil. Lo difícil es lo de alrededor: quién lo escribe, qué lee antes de responder, por dónde llega a la gente, dónde corre, quién paga cada llamada y qué pasa cuando otro agente le habla.

Eso es Astromesh hoy: 19 componentes en 6 capas, cada uno con su propio release.

→ Escribir: YAML, Python, un builder visual, un IDE de escritorio, lenguaje natural desde Claude Code y specs para agentes de código.
→ Ejecutar: un runtime con 7 patrones de orquestación, y tres librerías que deciden qué conocimiento entra en la ventana del modelo.
→ Llegar: WhatsApp, Instagram, Messenger, Telegram y web chat para las personas; A2A para agentes de otros frameworks, sin confiar en ellos.
→ Desplegar y operar: servicio nativo, un Linux inmutable con rollback, GCP en un comando y un control plane multi-tenant que mide y factura.

Lo que más valoro no se ve en el diagrama:

• Cada lenguaje donde rinde: Python para los agentes, Go en el gateway y el control plane, Rust donde hay CPU, TypeScript en las interfaces.
• Cerca de 4.900 tests en 13 repositorios. Sin eso, 19 piezas son 19 formas de romperse.
• Cada pieza vive sola. Las librerías de conocimiento y A2A no necesitan mi runtime: funcionan desde LangChain, CrewAI, PydanticAI o el SDK de OpenAI.
• Cuando algo no está medido, lo digo. La doc de Context dice qué eval falta correr.

[RUNA — 1 a 3 líneas tuyas. Ej.: "En paralelo, en Runa ___. Mucho de lo que está en este mapa lo aprendí ahí." Sin clientes ni números internos.]

No me interesa tener el framework más popular. Me interesa que entre el mensaje del cliente y la factura no quede ninguna capa sin dueño.

Mañana: el viaje completo de un "hola" por WhatsApp, capa por capa.

Mapa completo en el primer comentario 👇

#AIAgents #AgenticAI #PlatformEngineering #OpenSource #LLMOps #SoftwareArchitecture

---

**Primer comentario:**

Mapa del ecosistema, con versiones al día: https://monaccode.github.io/astromesh/#ecosystem
Repo: https://github.com/monaccode/astromesh

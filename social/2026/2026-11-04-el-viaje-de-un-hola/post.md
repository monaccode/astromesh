---
title: El viaje de un "hola"
date: 2026-11-04
publicar: 2026-11-05
platform: linkedin
format: post + carrusel infográfico (4 láminas, plantilla "infografía")
product: ecosistema astromesh (Herald + Nexus + Core)
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04]
relacionado: 2026/2026-11-04-no-construi-un-agente (primera parte, infografía del ecosistema)
fuentes: astromesh-herald README (HMAC-SHA256, Idempotency-Key + session_id estable por conversación, outbox en Postgres, Go); astromesh-nexus internal/server/handlers/invocations.go (Idempotency-Key = id de invocación, replay idempotente); CLAUDE.md del core (pipeline: guardrails de entrada → memoria → prompt Jinja2 → patrón → router → tools → guardrails de salida → memoria; circuit breaker 3 fallos → 60 s; estrategias sliding_window/summary/token_budget); core 0.73 (`origen`: un turno de agente nunca confirma una tool `confirm`); astromesh-a2a README (eval de 9 trampas en CI, salida envuelta como no confiable); memoria A2A (Nexus factura el uso de sub-agentes); ecosystem.ts (Nexus: tokens y créditos por run).
retorica: el mensaje "hola, ¿tienen turno mañana?" es ilustrativo. "9 pasos" es una agrupación editorial del pipeline, no una constante del código.
---

Un "hola" por WhatsApp cruza 9 pasos antes de volver.

Ayer mostré el mapa: 19 piezas en 6 capas. Hoy, lo que pasa cuando alguien le escribe al agente de un negocio. Nadie ve estos pasos. Todos notan cuando falta uno.

La ida, antes de que el modelo lea una palabra:

→ El gateway verifica la firma de Meta y le pone al mensaje una clave de idempotencia. Si Meta reintenta, el control plane reconoce la clave y no abre un segundo run.
→ El control plane decide qué tenant, qué versión publicada del agente y si tiene acceso.
→ El runtime aplica guardrails de entrada, arma la memoria con un presupuesto y corre el patrón del agente.

La vuelta, que tiene que poder fallar bien:

→ El router elige modelo por costo o latencia. Un proveedor que falla 3 veces seguidas queda 60 segundos afuera y responde el fallback.
→ Una tool marcada para confirmación espera a una persona. Otro agente nunca puede confirmarla por ella.
→ Cada run queda medido en tokens y créditos, sub-agentes incluidos. La respuesta sale por un outbox con reintentos.

Lo que más me importa de este recorrido:

• Tres sistemas, una sola conversación. Go en el borde, Python en el runtime.
• Cada paso tiene dueño. Si algo falla, sé en cuál fue.
• Nada de esto es la parte vistosa. Es la parte que hace que un negocio pueda confiarle su WhatsApp a un agente.

Un agente es una llamada a un modelo. Un producto es los otros 8 pasos.

Docs en el primer comentario 👇

#AIAgents #WhatsApp #PlatformEngineering #DistributedSystems #LLMOps

---

**Primer comentario:**

Mapa del ecosistema: https://monaccode.github.io/astromesh/#ecosystem
Herald: https://monaccode.github.io/astromesh/herald/introduction/
Nexus: https://monaccode.github.io/astromesh/nexus/introduction/

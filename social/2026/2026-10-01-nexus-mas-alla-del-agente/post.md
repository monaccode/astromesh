---
title: Nexus, más allá del agente
date: 2026-10-01
platform: linkedin
format: carrusel
product: nexus
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04]
video: true          # video.mp4, sin voz
music: "Minimal Techno 01 · Mixkit (mixkit.co/free-stock-music/tech-house/) · Mixkit License, gratis; verificar términos"
---

Hacer un agente de IA es el 10% del trabajo.

El otro 90% empieza el día que alguien más lo tiene que usar en serio: ¿quién lo puede llamar? ¿cuánto puede gastar? ¿qué versión está corriendo hoy? ¿cuánto le cobro a cada cliente por lo que consumió?

Eso es lo que resuelve Astromesh Nexus, el plano de control de nuestra nube de agentes.

Cómo funciona, en simple:
→ Una sola puerta (REST o WhatsApp). La credencial define el tenant; nunca se lo pedimos al body.
→ Cada llamada pasa por el mismo camino: tenant → límites → despacho → medición → registro.
→ Los agentes corren en un pool compartido de runtimes, no en un nodo dedicado por cliente.
→ La fuente de verdad es PostgreSQL: cada publicación queda versionada, con autor y checksum.

Lo que más me gusta de haberlo construido así:
• Multi-tenant de verdad: aislamiento y contabilidad por cliente desde el día uno.
• Medición y facturación por corrida, por modelo y por tenant, con tarifas, planes y suscripciones.
• Streaming que se puede cancelar a mitad de camino y se factura al cierre.
• Credenciales por corrida: un agente puede enviar un mensaje proactivo sin que el pool guarde ningún secreto del cliente.

Los agentes son la parte visible. Nexus es lo que los convierte en un producto.

Está escrito en Go y se despliega con Kustomize. Docs en el primer comentario 👇

#IA #AgentesDeIA #PlatformEngineering #Go #Astromesh

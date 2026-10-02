---
title: Un deck no contesta un WhatsApp
date: 2026-10-02
platform: linkedin
format: carrusel + video
product: herald + nexus
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04]
video: true          # video.mp4, sin voz ni subtítulos, sin avatar
music: "Trap Electro Vibes · Alejandro Magaña (A. M.) · Mixkit (mixkit.co/free-stock-music/mood/energetic/) · Mixkit Stock Music Free License (verificada 2026-10-02: uso comercial y en videos de redes, sin atribución; no CD/DVD, TV/radio, videojuegos ni registrarla como propia)"
fuentes: astromesh-herald/README.md (WhatsApp Meta Cloud API, HMAC-SHA256, outbox Postgres FOR UPDATE SKIP LOCKED, backoff 30s×2^n máx 10, at-least-once, AES-GCM, sesiones, agente de entrada, ventana 24h + plantillas), astromesh-nexus/README.md (tenant desde la credencial, límites, medición y facturación, planes, token por corrida)
---

Una consultora te puede entregar un diagnóstico de IA impecable. La pregunta es otra: ¿quién lo opera el lunes a las 3 de la mañana?

Lo digo con algo de cansancio: mucho de lo que veo vendido como "IA para empresas" en LATAM es una presentación, un piloto en un notebook y una factura por horas. Cuando ese piloto le tiene que contestar a un cliente real por WhatsApp, aparecen las preguntas que nadie cotizó.

Esas preguntas son las que resuelven Herald y Nexus, y no se contestan con slides:

→ El mensaje no se pierde. Herald recibe WhatsApp verificando la firma de Meta, y todo lo que sale pasa por un outbox en Postgres: reintentos con backoff, varias réplicas sin pisarse, entrega garantizada al menos una vez.
→ La conversación tiene dueño. Cada chat conserva su sesión, y un agente de entrada decide a quién derivarlo.
→ Cada cliente está aislado y paga lo que usa. Nexus saca el tenant de la credencial, aplica sus límites, mide cada corrida y factura con planes y suscripciones.
→ Los secretos no viajan. Un agente puede escribirle a un cliente a mitad de una corrida con un token que vive solo esa corrida; el pool compartido no guarda credenciales de nadie.

Lo que más me importa de esto:
• Es producto, no proyecto. Lo que aprendo con un cliente queda en el código para el siguiente.
• Está hecho para el LATAM real: WhatsApp como canal principal, con la ventana de 24 horas de Meta resuelta con plantillas.
• Se puede auditar: cada corrida queda registrada con su consumo.

La IA en las empresas no se gana con el mejor deck. Se gana con lo que sigue funcionando cuando nadie está mirando.

Docs en el primer comentario 👇

#IA #AgentesDeIA #WhatsApp #LATAM #Astromesh

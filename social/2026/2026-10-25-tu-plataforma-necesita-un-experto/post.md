---
title: Si tu plataforma necesita un experto, no tenés una plataforma
date: 2026-10-25
platform: linkedin
format: post + carrusel (4 láminas)   # modo historia, tono disruptivo, posicionamiento de autoridad (pedido 2026-10-25)
product: astromesh-leia
status: published    # draft | published
url: https://lnkd.in/p/dZZXwuHq
images: [01, 02, 03, 04]
relacionado: 2026/2026-10-22-que-lee-tu-agente (serie del ecosistema)
logo: images/leia.svg (astromesh-leia/assets/leia-logo.svg: Leia dibujada en vector calcando su foto, dentro de un casco de astronauta)
fuentes: astromesh-leia 0.11.0 (README «Leia is a real dog») (CHANGELOG, schemas/ecosystem.md «When the user asks for… → point at», agents/leia-interpreter.md «Spanish input»); docs-site/src/data/ecosystem.ts (19 componentes con versión); docs Prisma (in development, provisiona nada), Nebula/Centinela (preview), context eval (nivel 2 sin correr)
retorica: "una noche me llegó una pregunta" no es un dato, es recurso narrativo; los diálogos de las láminas 2 y 3 son ilustrativos (rotulados)
---

Una noche me llegó una pregunta que no supe contestar rápido.

"¿Para esto uso astromesh-rag o knowledge.pipeline?"

Yo escribí el código de los dos. Y aun así tuve que abrir dos repos para estar seguro.

Ahí entendí algo incómodo: el ecosistema que armé ya tiene 19 componentes con versión propia. Y el único índice completo estaba en mi cabeza.

Si tu plataforma necesita un experto para explicarse, no tenés una plataforma. Tenés un experto. Y los expertos no escalan.

Así que le enseñé el mapa entero a Leia.

Leia es mi beagle lemon. Los beagles son sabuesos: siguen un rastro hasta encontrar lo que buscan, y no se distraen con nada más. Por eso el agente que opera Astromesh desde Claude Code lleva su nombre. Ahora su olfato cubre todo el ecosistema:

→ Le pedís en castellano o en inglés: "que mi agente de LangGraph hable con este", "lo quiero como agente nativo de GCP", "¿por qué no aparece la card?".
→ Te responde con el componente que lo resuelve, la versión que lo trae y qué hace ella: diseñar el YAML, desplegarlo o solo explicarte.
→ "Creá", "desplegá", "probalo", "no anda": entiende el verbo, no el idioma.

Lo que más me importa:

• Sabe decir que no. Prisma está en desarrollo y no provisiona nada: no te lo ofrece como listo.
• No exagera. El nivel 2 del eval de contexto no se corrió: no va a decirte que mejora tus respuestas.
• Si no está documentado, no lo promete.

La mayoría de los productos de IA compiten por tener más features. El que gana es el que te dice cuál usar, y cuál todavía no.

Open source, Apache-2.0. Repo y docs en el primer comentario 👇

#AIAgents #ClaudeCode #DeveloperExperience #OpenSource #LLM

---

**Primer comentario:**

Leia (repo): https://github.com/monaccode/astromesh-leia
Docs: https://monaccode.github.io/astromesh/leia/introduction/
Mapa del ecosistema: https://monaccode.github.io/astromesh/#ecosystem

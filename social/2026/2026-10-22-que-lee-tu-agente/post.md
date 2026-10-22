---
title: ¿Qué lee tu agente?
date: 2026-10-22
platform: linkedin
format: post + video   # cuerpo: versión con íconos y tono controversial (pedido 2026-10-22); la sobria queda al final
product: astromesh-context
status: published    # draft | published
url: https://lnkd.in/p/d_yXCk4A
images: []
thumbnail: thumbnail.png   # frame 440 del video (T+00:14): las cuatro fuentes y la ventana llena
video: true          # video.mp4 (50 s, 9:16), plantilla HUD (social/_video/src/hud.tsx), sin voz ni subtítulos, sin avatar
music: "Vastness · Andrew Ev · Mixkit (mixkit.co/free-stock-music/tag/space/, https://assets.mixkit.co/music/184/184.mp3) · Mixkit Stock Music Free License (leída 2026-10-22: uso comercial y en posts de video en redes, sin atribución; no CD/DVD, TV/radio ni videojuegos; no remezclar, registrarla ni reclamarla como propia). Usada entera, sólo con fundido."
fuentes: astromesh-context/README.es.md (Resultados, nivel 1 corrido 2026-10-15, corpus Nimbus, 60 casos, presupuestos 750/1000/2000; superseded_rate antes 0.15–0.52 en el commit 170d40a; nivel 2 pendiente), docs-site context/eval
---

🔥 Dejá de culpar al modelo. Tu agente no alucina: lee basura y la repite con total seguridad.

En hasta la mitad de las preguntas, mi agente leía una política que ya no existía. 📉 Y no era el modelo: para medirlo ni siquiera llamé a uno.

¿La respuesta de la industria? Ventanas de un millón de tokens. 🙃 Meter más no es decidir mejor. Es pagar más para leer lo mismo, desordenado.

Por eso construí astromesh-context 👇

🎯 Un solo presupuesto: RAG, conocimiento, memoria e historial compiten por los mismos tokens. Nada de porciones fijas.
🧬 Deduplica entre fuentes: si un chunk viene de una política deprecada, hereda la marca y queda afuera.
⚡ Lo estable primero, idéntico byte a byte, para el prompt cache.
🧾 Cada ítem vuelve con su motivo: budget, duplicate_of, below_floor, source_cap, deprecated.

📊 Y lo medí (60 preguntas, nivel 1):
✅ Políticas reemplazadas en la ventana: de 15–52 % a 0–3 %.
✅ Con 750 tokens, recupera 0.55 de la evidencia contra 0.33 de las porciones fijas.
⚠️ El precio: entran más distractores.
❌ Mi propia idea perdió (0.27). La apagué por defecto.
⏳ Si las respuestas mejoran, todavía no lo sé. No lo voy a afirmar hasta medirlo.

💬 Opinión impopular: la mayoría de los agentes no tiene un problema de modelo. Tiene un problema de contexto que nadie mide.

👀 ¿Sabés qué leyó tu agente antes de su última respuesta?

Open source, Apache-2.0. Docs y resultados en el primer comentario 👇

#AIAgents #ContextEngineering #RAG #LLM #OpenSource

---

**Primer comentario:**

Docs: https://monaccode.github.io/astromesh/context/introduction/
Resultados del eval: https://monaccode.github.io/astromesh/context/eval/
Repo: https://github.com/monaccode/astromesh-context
`pip install astromesh-context`

---

**Versión sobria (sin íconos, la primera):**

En hasta la mitad de las preguntas, mi agente leía una política que ya no existía. Y respondía igual de seguro.

No era el modelo. Era lo que le llegaba. RAG trae fragmentos, la base de conocimiento trae conceptos, la memoria trae hechos y el historial no para de crecer. Cada uno con su porción fija de tokens, y nadie decidiendo —ni midiendo— qué entra en la ventana.

Por eso armé astromesh-context: esa decisión, tomada en un solo lugar.

→ Un solo presupuesto. RAG, OKF, memoria e historial compiten por los mismos tokens con un puntaje calibrado, no con porciones fijas.
→ Deduplica entre fuentes. Si RAG trae un pedazo de una política que OKF marcó como deprecada, la copia hereda la marca y queda afuera.
→ Lo estable va primero, idéntico byte a byte, para aprovechar el prompt cache.
→ Cada ítem vuelve con su motivo: incluido, budget, duplicate_of, below_floor, source_cap, deprecated.

Lo que más valoro es que lo medí, sin llamar a ningún modelo:

• Políticas reemplazadas en la ventana: de 15–52 % a 0–3 %.
• Con 750 tokens, el presupuesto calibrado recupera 0.55 de la evidencia contra 0.33 de las porciones fijas. El precio: entran más distractores.
• Mi propia idea perdió. Ponderar por valor por token bajó el recall a 0.27, así que quedó apagada por defecto.
• Lo que todavía no medí: si las respuestas mejoran. Ese es el nivel 2, y está pendiente.

Un agente no responde con lo que sabe. Responde con lo que lee.

Open source, Apache-2.0, en PyPI. Docs y resultados en el primer comentario 👇

#AIAgents #ContextEngineering #RAG #LLM #OpenSource #Python

---
title: Cada cosa en su capa
date: 2026-10-01
platform: linkedin
format: carrusel + video
product: astromesh
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04]
video: true          # video.mp4, sin voz
video_narrado: video-narrado.mp4  # avatar nivel 1 + voz PROVISIONAL (say); rehacer con su voz antes de publicar
music: "Minimal Techno 01 · Mixkit (mixkit.co/free-stock-music/tech-house/) · Mixkit Stock Music Free License (verificada 2026-10-02: uso comercial y en videos de redes, sin atribución; no CD/DVD, TV/radio, videojuegos ni registrarla como propia)"
fuentes: CHANGELOG 0.51.0 (prefetch), docs-site configuration/glyph.md, docs/NATIVE_ESTENSIONS_RUST.md, native/src/*.rs, tests/conftest.py (use_native)
---

No todo lo que hace un agente de IA debería pasar por el modelo.

En Astromesh, cada cosa va en la capa que le corresponde. El modelo razona; lo demás es trabajo determinista, y no debería costar tokens ni segundos.

Tres ejemplos de cómo lo aplicamos:

→ Los caminos calientes, en Rust. Chunking para RAG, redacción de PII, presupuesto de tokens, rate limiting, ranking de modelos, costos y JSON: siete módulos nativos que el runtime usa si están compilados; si no, cae solo a Python y los tests corren ambos backends.
→ Las búsquedas, antes del modelo. Con prefetch, el runtime corre las consultas de solo lectura que el agente siempre hace y entrega el resultado al prompt. En un agente auditor de CLARUS, un viaje al LLM costaba ~5 s; la búsqueda, ~55 ms.
→ Los planes, escritos una vez. Glyph nació para reemplazar varias vueltas al modelo por un programa. Lo medimos con tres modelos y la premisa no se sostuvo: como patrón de runtime costó entre +164% y +2839% más que ReAct, porque el modelo escribe el programa en cada corrida. Conviene lo contrario: el modelo lo escribe una vez, una persona lo revisa y el runtime lo ejecuta sin llamar al modelo.

Lo que más valoro de este trabajo:
• Medir antes de contar. Dejamos documentado el resultado que contradijo nuestra hipótesis y reorientamos el diseño.
• Poner la ingeniería donde mueve la aguja: ni todo al modelo, ni optimizar por optimizar.

Llevar IA real a una empresa no es un prompt más largo. Es decidir, capa por capa, qué hace el modelo y qué no.

Docs en el primer comentario 👇

#IA #AgentesDeIA #Rust #IngenieriaDeSoftware #Astromesh

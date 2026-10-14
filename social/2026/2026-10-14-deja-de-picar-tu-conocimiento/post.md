---
title: Dejá de picar tu conocimiento en pedacitos
date: 2026-10-14
platform: linkedin
format: carrusel (documento PDF)
product: astromesh-okf
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04, 05, 06, 07]
carrusel: carrusel.pdf  # LinkedIn: subir como «documento», título sugerido: «Dejá de picar tu conocimiento en pedacitos»
relacionado: 2026/2026-10-14-el-vibe-coding-no-escala (mismo formato, astromesh-sdd)
fuentes: astromesh-okf 0.1.0 (README «Why navigate instead of RAG» y «What we learned», CHANGELOG), salida real del CLI sobre examples/bundles/support (docs-site okf/introduction), CI contra los 4 bundles de ejemplo de Google (9+9+9+26 = 53 conceptos, 0 descartados), core astromesh 0.69.0 depende de astromesh-okf
primer_comentario: "Repo, quickstart y un ejemplo por framework: https://github.com/monaccode/astromesh-okf · pip install astromesh-okf · Docs: https://monaccode.github.io/astromesh/okf/introduction/"
---

Dejá de picar tu conocimiento en pedacitos. ✂️

Te cuento cómo llegué acá.

Mis agentes usaban RAG para todo: trocear, embeber, recuperar fragmentos. Pero un fragmento no sabe si sigue vigente, quién lo revisó ni a qué otro documento apunta. 🤷

Y una persona no lee así. Abre el índice, sigue los links, mira la fecha. 📚

Así que le di eso a mis agentes dentro de Astromesh: tres herramientas para navegar un bundle de Open Knowledge Format como lo haría yo. Después lo saqué del runtime para que lo use cualquiera.

Hoy libero astromesh-okf, open source y en PyPI:

🧭 Índice → búsqueda → concepto → link, con cada link ya resuelto
⚠️ Lo deprecado se lee igual, pero con la advertencia puesta
🔌 LangChain, CrewAI, Google ADK, OpenAI Agents, PydanticAI, LlamaIndex, smolagents, Microsoft Agent Framework y MCP
✅ Probado contra los 4 bundles de ejemplo de Google: 53 conceptos, ninguno descartado

¿Mata a RAG? No. Para miles de documentos sin estructura, RAG gana. Para tu conocimiento curado, navegar gana. 🎯

Repo en el primer comentario 👇

#AgentesDeIA #RAG #OpenSource #LangChain #Python #Astromesh

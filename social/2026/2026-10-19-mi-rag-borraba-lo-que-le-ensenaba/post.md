---
title: Mi RAG borraba lo que le enseñaba
date: 2026-10-19
platform: linkedin
format: post + carrusel (4 láminas)
product: astromesh-rag
status: draft        # draft | published
url:                 # link al post al publicarlo
images: [01, 02, 03, 04]
relacionado: 2026/2026-10-14-deja-de-picar-tu-conocimiento (astromesh-okf, mismo movimiento de extraer del core)
fuentes: astromesh-rag 0.1.0 (CHANGELOG «Fixed», README «Cómo lo usa Astromesh», «Una consulta hybrid, etapa por etapa», «Benchmark»)
aviso: astromesh-rag 0.1.0 publicado en PyPI el 2026-10-20 (pip install astromesh-rag).
primer_comentario: "Repo, CHANGELOG con cada bug y el benchmark: https://github.com/monaccode/astromesh-rag · Docs: https://monaccode.github.io/astromesh/rag/introduction/"
---

Saqué el RAG de mi propio runtime para liberarlo.
Y descubrí que la segunda ingesta borraba la primera.

Cada documento generaba fragmentos con los mismos ids: doc_0, doc_1… Ingerías el documento B y el A desaparecía del índice. Sin error. Sin aviso. El agente seguía respondiendo, y un RAG que responde parece un RAG que funciona.

Al extraerlo como librería aparecieron más:

→ similarity_threshold y reranking.top_k: el YAML los aceptaba y los ignoraba
→ Un overlap mayor o igual que el chunk colgaba el splitter
→ Cada base fallaba distinto: Qdrant rechazaba los ids, pgvector interpolaba los filtros en el SQL, Chroma medía L2 en vez de coseno
→ El chunking semantic caía en silencio a partir por oraciones

Todo corregido y listado en el CHANGELOG. Así nació astromesh-rag v0.1.0, open source:

• Cada consulta devuelve un trace: una entrada por etapa, con su tiempo, cuántos candidatos entran y cuántos salen
• Cuatro patrones (naive, hybrid, multi_query, hyde) armados con las mismas piezas: cambiás una línea
• Un corpus con trampas etiquetadas (ERR-4012 contra ERR-4013, la política 2024 contra la 2026) para medir en vez de adivinar
• Depende sólo de PyYAML; cada modelo y cada base vectorial es un extra

Lo que me llevo: un RAG no falla con un error. Falla con una respuesta plausible.

Repo y CHANGELOG en el primer comentario 👇

#RAG #AgentesDeIA #OpenSource #Python #LLM #Astromesh

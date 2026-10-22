# Banco de posts de RRSS

Histórico de publicaciones de Astromesh. Un post = una carpeta.

## Estructura

```
social/
├── README.md
├── render.sh                      # regenera las imágenes de un post
├── _shared/                       # assets comunes (logo)
├── _video/                        # proyecto Remotion de los videos (npm install; ver skill social-post)
└── <AAAA>/
    └── <AAAA-MM-DD>-<slug>/       # fecha de redacción + tema en kebab-case
        ├── post.md                # texto + frontmatter (plataforma, estado, url)
        ├── slides.html            # fuente de las imágenes (design system Mission Control)
        ├── images/01.png …        # láminas finales, en orden de carrusel
        └── video.mp4              # opcional: reel/short 9:16 (fuente en _video/)
```

## Reglas

- **Nombre**: `AAAA-MM-DD-slug`. La fecha es la de redacción; si se publica otro día, se anota en `post.md`.
- **`post.md`**: frontmatter con `title, date, platform, format, product, status, url, images`. El cuerpo es el texto tal cual se pega en la plataforma.
- **Estado**: `draft` al crearlo; al publicar pasa a `published` y se completa `url`.
- **Imágenes**: numeradas `01.png`, `02.png`… Se versionan los PNG (son lo publicado) junto con `slides.html` (para poder editarlas).
- **Estilo visual**: tokens de `docs-site/src/styles/custom.css` (fondo `#060d15`, DM Sans + JetBrains Mono, acento por producto: Nexus ámbar `#fbbf24`/`#f59e0b`, base cyan `#00d4ff`). Lo más fácil es copiar el `slides.html` de un post anterior.
- Un post nuevo de otra plataforma sobre el mismo tema es otra carpeta; se enlazan en `post.md`.

## Índice

| Fecha | Post | Plataforma | Producto | Estado |
|-------|------|-----------|----------|--------|
| 2026-10-01 | [Nexus, más allá del agente](2026/2026-10-01-nexus-mas-alla-del-agente/post.md) | LinkedIn | Nexus | draft |
| 2026-10-01 | [Cada cosa en su capa](2026/2026-10-01-cada-cosa-en-su-capa/post.md) | LinkedIn | Astromesh | draft |
| 2026-10-02 | [Un deck no contesta un WhatsApp](2026/2026-10-02-un-deck-no-contesta-whatsapp/post.md) | LinkedIn | Herald + Nexus | draft |
| 2026-10-14 | [El vibe coding no escala. La spec sí.](2026/2026-10-14-el-vibe-coding-no-escala/post.md) | LinkedIn | astromesh-sdd | draft |
| 2026-10-14 | [Dejá de picar tu conocimiento en pedacitos](2026/2026-10-14-deja-de-picar-tu-conocimiento/post.md) | LinkedIn | astromesh-okf | draft |
| 2026-10-19 | [Mi RAG borraba lo que le enseñaba](2026/2026-10-19-mi-rag-borraba-lo-que-le-ensenaba/post.md) | LinkedIn | astromesh-rag | draft |
| 2026-10-20 | [Otro agente no es tu usuario](2026/2026-10-20-otro-agente-no-es-tu-usuario/post.md) | LinkedIn | astromesh-a2a | draft |
| 2026-10-22 | [¿Qué lee tu agente?](2026/2026-10-22-que-lee-tu-agente/post.md) | LinkedIn (video) | astromesh-context | draft |

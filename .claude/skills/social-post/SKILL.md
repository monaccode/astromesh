---
name: social-post
description: Crea un post de redes (LinkedIn por defecto) en la voz de Juan Carlos Romero Fulfaro, con carrusel de imágenes en el design system de Astromesh, y lo archiva en social/. Úsalo cuando pida "un post", "contenido para redes", "publicación para LinkedIn" o hablar de un producto/release de Astromesh.
---

# social-post

Produce un post listo para publicar: **texto + láminas + carpeta archivada** en `social/`. Quien habla es **Juan Carlos Romero Fulfaro** ([LinkedIn](https://www.linkedin.com/in/juan-carlos-romero-fulfaro/)): todo se escribe en **primera persona singular**, como si lo publicara él.

## Flujo

1. **Entender el tema.** Si nombra un producto (Nexus, Cortex, Herald, Orbit…), lee su `README.md`, `CHANGELOG.md` y docs en `../astromesh-<producto>/` o este repo. Nunca inventes capacidades: cada afirmación debe salir del código/docs. Si algo es una frase retórica y no un dato medido, dilo al entregar.
2. **Formato — ofrécelo siempre.** Antes de producir, pregunta (AskUserQuestion) si quiere **solo post** (texto), **post + carrusel** (texto + 4 láminas, lo habitual), **solo carrusel** o **video** (reel/short 9:16). Si elige video, pregunta también el **modo**: sin voz (por defecto), con su **voz clonada**, o con **avatar** (ver Video). Si ya lo dijo en el pedido, no vuelvas a preguntar.
   **Ángulo.** Elige UNA idea central (un gancho, no un resumen del producto). Pregunta solo si hay una decisión real (ángulo técnico vs. negocio); si no, elige y propón variantes al final.
   **Ofrecimiento proactivo:** cuando termines un release, feature o doc relevante de Astromesh/Nexus/etc. (aunque no hable de redes), cierra tu respuesta ofreciendo crear un post o un carrusel sobre ello. Una línea, sin insistir.
3. **Texto** en `post.md` (ver Voz y Estructura).
4. **Láminas** (omitir si eligió solo post): copia `slides.html` del post más reciente en `social/` y reescribe el contenido. 4 láminas, 1080×1350: portada con gancho → cómo funciona → bondades/detalle → cierre. Mismos tokens (ver abajo).
5. **Render**: `social/render.sh <año>/<carpeta>` (o Playwright sirviendo la carpeta por HTTP). **Mira cada PNG**: nada desbordado ni pisando el pie, logo sin chocar con el título.
6. **Archivar** (el video va como `video.mp4` en la misma carpeta; añade `video: true` al frontmatter) siguiendo `social/README.md`: carpeta `social/AAAA/AAAA-MM-DD-slug/` (`post.md` con frontmatter, `slides.html`, `images/01.png…`), y añade la fila al índice del README. Estado `draft`.
7. **Entregar**: el texto del post en el chat (para copiar), la ruta, y las dudas abiertas. **No publiques ni commitees** sin que lo pida.

## Video (reel/short 9:16, 1080×1920, 30 fps)

Proyecto Remotion compartido en `social/_video/` (`npm install` una vez; `npx remotion studio src/index.ts` para previsualizar). Las piezas de marca (tokens, fondo, subtítulos, título) están en `src/kit.tsx`; cada video es un archivo `src/<Nombre>.tsx` con su `<Composition>` en `Root.tsx`. Referencia: `NexusReel.tsx` (5 escenas, ~47 s: gancho → una puerta → el camino → medición/registro → cierre).

- **Guion = el contenido del post**, no láminas animadas: una idea visual por escena (partículas, pipeline, contadores, constelación). Subtítulos grandes siempre (se ve sin sonido). Zona segura de Reels: nada importante en los 250 px superiores ni en los 380 inferiores.
- **Datos ilustrativos** (créditos, hashes) se rotulan como tales en pantalla.
- **Render**: `npx remotion render src/index.ts <Id> ../AAAA/<carpeta>/video.mp4 --codec=h264` (añade `--props='{"music":true}'` si hay música). Antes revisa cuadros clave con `npx remotion still … --frame=N` y mira el PNG.
- **Música**: la elige/descarga Juan Carlos (licencia libre: Pixabay, Mixkit, etc.; anota licencia y fuente en `post.md`). Se guarda como `social/_video/public/music.mp3`. **No descargues archivos sin pedirle permiso** (nombre, fuente, tamaño).

### Voz clonada (cuando haga falta su voz)

Solo la voz **de Juan Carlos**, con su consentimiento explícito y para su contenido. Flujo: guion de narración (primera persona, frases cortas, ~150 palabras/min) → audio → `<Audio src={staticFile('voz.mp3')}/>` y subtítulos sincronizados con los tiempos reales → mezcla con música a volumen bajo (`volume` ~0.15 bajo la voz).
- Opción con servicio (mejor calidad): ElevenLabs u otro TTS con clonación; requiere que **él** cree la cuenta, grabe/suba sus muestras y entregue la API key como variable de entorno. Nunca pegues keys en archivos del repo; no subas sus grabaciones a ningún servicio sin su OK en ese momento.
- Opción local (sin cuentas): modelo abierto de clonación (p. ej. XTTS / F5-TTS) con una muestra limpia de 30–60 s suya; calidad variable, siempre dar a escuchar antes de usar.
- Guarda la muestra fuente fuera del repo; en `social/` solo va el audio final de cada video.

### Avatar de Juan Carlos (de menos a más realista)

Mismo principio: solo su imagen, con su consentimiento, y él crea las cuentas/entrega credenciales. Sube de nivel solo si el anterior ya funciona.
1. **Ilustrado/estilizado** (nivel base, 100% local): avatar 2D en Remotion (SVG) con boca animada por la amplitud del audio y gestos simples. Sin foto ni servicios. Se integra como un componente más de `kit.tsx`.
2. **Estilizado 3D**: avatar 3D tipo caricatura con `@remotion/three`, sincronía labial básica con la voz.
3. **Foto animada (talking head)**: servicio que anima una foto suya con su voz clonada (HeyGen, D-ID, etc.). El clip se compone sobre las escenas de Remotion.
4. **Clon de video realista**: avatar entrenado con una grabación suya (HeyGen/Synthesia u otro), con la verificación de consentimiento que exija el proveedor. El más realista: usarlo solo en piezas donde se aclare que es un avatar generado.
En cualquier nivel, indica en `post.md` que el video usa voz/avatar generado, y respeta la política de contenido sintético de la plataforma donde se publique.

## Voz (Juan Carlos)

- Español neutro latino, primera persona singular ("construí", "me gusta", "lo que aprendí"). Evita el "nosotros" corporativo salvo que sea literal el equipo.
- Directo, técnico pero explicable a alguien no técnico. Oraciones cortas. Sin hype ni superlativos vacíos ("revolucionario", "game-changer").
- Habla de **lo que hay detrás** (operación, costos, aislamiento, medición), no solo de la feature vistosa.
- Cuenta decisiones y trade-offs: por qué así y qué se descartó.
- Sin emojis decorativos; máximo uno funcional (👇 antes del link). 4–6 hashtags al final.
- Nada de datos personales, clientes reales ni números de negocio no públicos.
- *Esta sección es una semilla: afínala con posts reales de su perfil (pídele que pegue 2–3) y actualiza aquí.*

## Estructura del texto

1. Gancho de 1–2 líneas (idea contraintuitiva o pregunta).
2. El problema real en un párrafo corto.
3. Qué es / cómo funciona, en 3–4 viñetas con `→`.
4. Lo que más valora el autor, 3–4 viñetas con `•`.
5. Frase de cierre memorable + CTA ("Docs en el primer comentario 👇").
6. Hashtags.

Largo objetivo: 1.200–1.800 caracteres. Links van en el primer comentario, no en el cuerpo.

## Design system (Mission Control)

Fuente: `docs-site/src/styles/custom.css`. Fondo `#060d15` con grilla sutil, DM Sans (títulos light 300 con la palabra clave en 800 con degradado) + JetBrains Mono (etiquetas, chips, código). Acento por producto: **Nexus** ámbar `#fbbf24`/`#f59e0b`; base/Astromesh cyan `#00d4ff`; mira `docs-site/src/components/*Showcase.astro` para el acento del producto. Logo: `social/_shared/astromesh-logo.png`. Tarjetas: borde `rgba(255,255,255,.08)`, fondo `rgba(255,255,255,.03)`, radio 14px.

## Reglas

- Cada afirmación verificable en código/docs; evita cifras inventadas.
- Una carpeta por post; no sobrescribas posts anteriores.
- Otra plataforma sobre el mismo tema = otra carpeta, enlazada en `post.md`.

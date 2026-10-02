---
name: social-post
description: Crea un post de redes (LinkedIn por defecto) en la voz de Juan Carlos Romero Fulfaro, con carrusel de imágenes en el design system de Astromesh, y lo archiva en social/. Úsalo cuando pida "un post", "contenido para redes", "publicación para LinkedIn" o hablar de un producto/release de Astromesh.
---

# social-post

Produce un post listo para publicar: **texto + láminas + carpeta archivada** en `social/`. Quien habla es **Juan Carlos Romero Fulfaro** ([LinkedIn](https://www.linkedin.com/in/juan-carlos-romero-fulfaro/)): todo se escribe en **primera persona singular**, como si lo publicara él.

## Flujo

1. **Entender el tema.** Si nombra un producto (Nexus, Cortex, Herald, Orbit…), lee su `README.md`, `CHANGELOG.md` y docs en `../astromesh-<producto>/` o este repo. Nunca inventes capacidades: cada afirmación debe salir del código/docs. Si algo es una frase retórica y no un dato medido, dilo al entregar.
2. **Formato — ofrécelo siempre.** Antes de producir, pregunta (AskUserQuestion) si quiere **solo post** (texto), **post + carrusel** (texto + 4 láminas, lo habitual), **solo carrusel** o **video** (reel/short 9:16). **Si el formato incluye video, pregunta SIEMPRE (AskUserQuestion, en la misma tanda) dos cosas por separado, aunque el pedido no las mencione:**
   - **Voz en off**: sin voz (solo subtítulos) · su voz grabada (`archivo`) · su voz clonada (`elevenlabs`) · provisional para probar tiempos (`say`, no publicable).
   - **Avatar**: sin avatar · avatar nivel 1 (ilustrado, local) · niveles superiores (requieren servicios y cuentas suyas; ver Video).
   El avatar solo tiene sentido con voz; si elige avatar sin voz, avísale. Solo omite estas preguntas si en el mismo pedido ya dijo qué quiere para voz y avatar.
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
- **Música — una pista por video, alineada con el contenido.** Se puede cambiar la música de cualquier post por otra pista **pública y de licencia libre**. Juan Carlos dio permiso permanente para buscarla y descargarla desde el navegador **siempre que sea pública**; igual informa nombre, fuente, tamaño y licencia al entregar.
  - **Elegirla por el tono del post**, no por defecto: técnico/reflexivo → ambient o minimal sobrio; disruptivo/campaña → pulso marcado, más energía; cierre emocional o de marca → piano/ambient cálido. Sin voces cantadas que compitan con el texto; ≥ duración del video (o que cicle bien).
  - **Fuentes**: Mixkit, Pixabay Music o similares con licencia de uso libre. Preferir licencias **sin atribución**; si pide atribución, va en `post.md` y en el primer comentario. Lee los términos de la licencia en la página (no asumir); si no se pueden leer, dilo y márcalo "verificar términos". Nada de pistas comerciales, con Content ID o "sin copyright" de origen dudoso.
  - **Archivo**: `social/_video/public/musica/<slug-del-post>.mp3` (recortada/normalizada con ffmpeg si hace falta). Render con `--props='{"music":true,"musica":"musica/<slug>.mp3"}'`; todos los reels aceptan `musica` (por defecto `music.mp3`) y la ciclan si es corta. En videos narrados la música queda bajo la voz (~0.12).
  - **Registrar** en el frontmatter de `post.md`: `music: "<título> · <fuente> (<url>) · <licencia>"`.

### Voz en off (narración)

Flujo ya implementado y probado con `CapasNarrado` (post `2026-10-01-cada-cosa-en-su-capa`):
1. **Guion** en la carpeta del post: `guion.json` con `voz` (backend), `pausa` y `escenas[]` (`min` en segundos + `lineas`: frases cortas, primera persona, una idea por línea; los números escritos como se dicen).
2. **Voz**: `cd social/_video && npm run narrar -- ../AAAA/<post>/guion.json <id>` → `public/voz/<id>/` (`voz.wav` + `timeline.json`; ignorado por git). Cada escena dura lo que su narración (o su `min`).
3. **Composición narrada** `<Reel>Narrado`: el reel acepta `durs` (frames por escena) y se envuelve en `<NoCaps.Provider value>`; encima va `<Narracion timeline avatar>` (`avatar={false}` = voz en off sin avatar) (`src/voz.tsx`: pista de voz, avatar, subtítulos sincronizados y etiqueta de transparencia). La duración sale de `calculateMetadata` con `cargarTimeline`. La música baja a ~0.12 bajo la voz.
4. Render como siempre; el archivo final es `video-narrado.mp4` en la carpeta del post.

Backends (`guion.voz.backend`), solo con la voz **de Juan Carlos** y su consentimiento:
- `say`: voz de macOS, **provisional** para probar tiempos; en pantalla dice "voz provisional · sintética". No publicar con esta voz como si fuera la suya.
- `archivo`: sus grabaciones línea por línea (`<post>/grabaciones/01.wav`…). Es su voz real, sin clonar.
- `elevenlabs`: voz clonada. Él crea la cuenta, sube su muestra y exporta `ELEVENLABS_API_KEY`; `voz.voice_id` en el guion. Nunca pegues la key en archivos. En pantalla dice "voz generada". (Implementado, sin probar contra la API real.)
- Modelo local (XTTS/F5-TTS): pendiente; requiere descargar modelos pesados, pedir permiso antes.
La muestra para clonar se graba con `social/_video/tools/muestra-de-voz.md` y **no se versiona**.

### Avatar de Juan Carlos (de menos a más realista)

Mismo principio: solo su imagen, con su consentimiento, y él crea las cuentas/entrega credenciales. Sube de nivel solo si el anterior ya funciona.
1. **Ilustrado/estilizado** (nivel base, 100% local) — **implementado**: `Avatar` en `src/voz.tsx`, SVG con boca movida por la amplitud de la voz, parpadeo y leve movimiento de cabeza. Sus rasgos (`RASGOS`: piel, pelo, peinado, barba, lentes, ropa) son provisionales hasta que Juan Carlos los confirme o mande una foto de referencia.
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

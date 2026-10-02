#!/usr/bin/env node
// Genera la voz en off de un video a partir de su guion.
//
//   node tools/narrar.mjs ../2026/<post>/guion.json <id>
//
// Salida en public/voz/<id>/: lineas/NN.wav, voz.wav (pista completa) y timeline.json
// (inicio y duración de cada línea y de cada escena, en segundos). Remotion lee el
// timeline para estirar las escenas, sincronizar subtítulos y mover la boca del avatar.
//
// Backends (guion.voz.backend):
//   say        voz sintética de macOS. Solo provisional: NO es la voz de Juan Carlos.
//   archivo    grabaciones propias: <carpeta del guion>/grabaciones/NN.(wav|m4a|mp3), una por línea.
//   elevenlabs voz clonada por servicio. Requiere ELEVENLABS_API_KEY en el entorno y
//              guion.voz.voice_id. Sin probar contra la API real todavía.
import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';

const [guionPath, id] = process.argv.slice(2);
if (!guionPath || !id) {
  console.error('Uso: node tools/narrar.mjs <guion.json> <id>');
  process.exit(1);
}
const guion = JSON.parse(readFileSync(guionPath, 'utf8'));
const out = resolve('public/voz', id);
mkdirSync(join(out, 'lineas'), {recursive: true});

const GAP = guion.pausa ?? 0.3; // silencio entre líneas
const LEAD = 0.4; // aire al empezar cada escena
const TAIL = 0.6; // aire al terminar cada escena

const ff = (...args) => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args]);
const dur = (f) => Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());
const toWav = (src, dst) => ff('-i', src, '-ac', '1', '-ar', '44100', dst);

async function sintetizar(texto, n, dst) {
  const {backend, voice, rate} = guion.voz;
  if (backend === 'say') {
    const tmp = dst.replace(/\.wav$/, '.aiff');
    execFileSync('say', ['-v', voice, ...(rate ? ['-r', String(rate)] : []), '-o', tmp, texto]);
    return toWav(tmp, dst);
  }
  if (backend === 'archivo') {
    const base = join(dirname(guionPath), 'grabaciones', n);
    const src = ['wav', 'm4a', 'mp3'].map((e) => `${base}.${e}`).find(existsSync);
    if (!src) throw new Error(`Falta la grabación ${base}.(wav|m4a|mp3) para: "${texto}"`);
    return toWav(src, dst);
  }
  if (backend === 'elevenlabs') {
    const key = process.env.ELEVENLABS_API_KEY;
    if (!key || !guion.voz.voice_id) throw new Error('elevenlabs requiere ELEVENLABS_API_KEY y voz.voice_id');
    const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${guion.voz.voice_id}?output_format=mp3_44100_128`, {
      method: 'POST',
      headers: {'xi-api-key': key, 'content-type': 'application/json'},
      body: JSON.stringify({text: texto, model_id: guion.voz.model_id ?? 'eleven_multilingual_v2'}),
    });
    if (!r.ok) throw new Error(`elevenlabs ${r.status}: ${await r.text()}`);
    const mp3 = dst.replace(/\.wav$/, '.mp3');
    writeFileSync(mp3, Buffer.from(await r.arrayBuffer()));
    return toWav(mp3, dst);
  }
  throw new Error(`Backend desconocido: ${backend}`);
}

// Línea por línea: archivo y duración.
const lineas = [];
let n = 0;
for (const [e, esc] of guion.escenas.entries()) {
  for (const texto of esc.lineas) {
    const nn = String(++n).padStart(2, '0');
    const f = join(out, 'lineas', `${nn}.wav`);
    await sintetizar(texto, nn, f);
    lineas.push({escena: e, texto, archivo: f, dur: dur(f)});
  }
}

// Ubicación en el tiempo: cada escena dura lo que su narración (o su mínimo).
const escenas = [];
let t = 0;
for (const [e, esc] of guion.escenas.entries()) {
  let c = t + LEAD;
  for (const l of lineas.filter((x) => x.escena === e)) {
    l.start = c;
    c += l.dur + GAP;
  }
  const d = Math.max(esc.min ?? 0, c - GAP + TAIL - t);
  escenas.push({start: t, dur: d});
  t += d;
}

// Pista completa: cada línea con su retardo, mezcladas sobre silencio.
const inputs = lineas.flatMap((l) => ['-i', l.archivo]);
const delays = lineas.map((l, i) => `[${i}]adelay=${Math.round(l.start * 1000)}:all=1[a${i}]`).join(';');
const mix = `${lineas.map((_, i) => `[a${i}]`).join('')}amix=inputs=${lineas.length}:normalize=0,apad=whole_dur=${t.toFixed(3)}`;
ff(...inputs, '-filter_complex', `${delays};${mix}`, '-ac', '1', '-ar', '44100', join(out, 'voz.wav'));

const timeline = {
  backend: guion.voz.backend,
  audio: `voz/${id}/voz.wav`,
  total: t,
  escenas,
  lineas: lineas.map(({escena, texto, start, dur: d}) => ({escena, texto, start, dur: d})),
};
writeFileSync(join(out, 'timeline.json'), JSON.stringify(timeline, null, 2));
console.log(`${lineas.length} líneas, ${escenas.length} escenas, ${t.toFixed(1)} s → ${join(out, 'timeline.json')}`);

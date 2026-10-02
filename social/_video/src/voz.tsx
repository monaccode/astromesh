// Voz en off + avatar (nivel 1: ilustrado, 100% local). La voz la genera tools/narrar.mjs.
import React from 'react';
import {Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {useAudioData, visualizeAudio} from '@remotion/media-utils';
import {C, clamp, mono, sans} from './kit';

export type Timeline = {
  backend: 'say' | 'archivo' | 'elevenlabs';
  audio: string;
  total: number;
  escenas: {start: number; dur: number}[];
  lineas: {escena: number; texto: string; start: number; dur: number}[];
};

// Para calculateMetadata: la duración del video sale de la narración.
export const cargarTimeline = async (voz: string, fps: number) => {
  const timeline: Timeline = await fetch(staticFile(`voz/${voz}/timeline.json`)).then((r) => r.json());
  return {timeline, durationInFrames: Math.ceil(timeline.total * fps), durs: timeline.escenas.map((e) => Math.round(e.dur * fps))};
};

// Rasgos del avatar. PROVISIONALES hasta que Juan Carlos los confirme (o mande una foto de referencia).
export type Rasgos = {piel: string; pelo: string; peinado: 'corto' | 'largo' | 'calvo'; barba: boolean; lentes: boolean; ropa: string};
export const RASGOS: Rasgos = {piel: '#d6a07a', pelo: '#2a211d', peinado: 'corto', barba: false, lentes: false, ropa: '#0e2233'};

// Amplitud de la voz en este frame (0..1), promediada con el anterior para que la boca no tiemble.
const useAmplitud = (src: string) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const audioData = useAudioData(src);
  if (!audioData) return 0;
  const nivel = (frame: number) => {
    const v = visualizeAudio({fps, frame: Math.max(0, frame), audioData, numberOfSamples: 16});
    return v.slice(0, 6).reduce((a, b) => a + b, 0) / 6;
  };
  return Math.min(1, ((nivel(f) + nivel(f - 1)) / 2) * 5);
};

export const Avatar: React.FC<{src: string; rasgos?: Rasgos; x?: number; y?: number; size?: number}> = ({src, rasgos = RASGOS, x = 60, y = 1270, size = 230}) => {
  const f = useCurrentFrame();
  const amp = useAmplitud(src);
  const parpadeo = f % 110 < 4; // un parpadeo cada ~3,7 s
  const bob = Math.sin(f / 12) * 1.5 - amp * 2;
  const r = rasgos;
  return (
    <svg width={size} height={size} viewBox="0 0 240 240" style={{position: 'absolute', left: x, top: y, filter: `drop-shadow(0 0 24px ${C.cyan}55)`}}>
      <defs><clipPath id="marco"><circle cx="120" cy="120" r="116" /></clipPath></defs>
      <circle cx="120" cy="120" r="116" fill="#0b1622" stroke={C.cyan} strokeWidth="3" />
      <g clipPath="url(#marco)">
        <g transform={`translate(0 ${bob}) rotate(${Math.sin(f / 40) * 2} 120 140)`}>
          <ellipse cx="120" cy="250" rx="96" ry="62" fill={r.ropa} />
          <rect x="104" y="150" width="32" height="40" rx="10" fill={r.piel} />
          {r.peinado === 'largo' && <path d="M62 110 Q60 40 120 38 Q180 40 178 110 L182 175 L58 175 Z" fill={r.pelo} />}
          <ellipse cx="120" cy="108" rx="52" ry="60" fill={r.piel} />
          {r.peinado !== 'calvo' && <path d="M68 100 Q66 46 120 44 Q174 46 172 100 Q160 70 120 68 Q82 70 68 100 Z" fill={r.pelo} />}
          {r.barba && <path d="M70 112 Q74 168 120 172 Q166 168 170 112 Q160 150 120 152 Q80 150 70 112 Z" fill={r.pelo} opacity="0.9" />}
          <path d="M88 92 Q98 86 108 91 M132 91 Q142 86 152 92" stroke={r.pelo} strokeWidth="4" fill="none" strokeLinecap="round" />
          <ellipse cx="98" cy="106" rx="5.5" ry={parpadeo ? 0.8 : 6} fill="#1b1b1b" />
          <ellipse cx="142" cy="106" rx="5.5" ry={parpadeo ? 0.8 : 6} fill="#1b1b1b" />
          {r.lentes && <g stroke="#111" strokeWidth="3" fill="none"><rect x="80" y="94" width="36" height="26" rx="8" /><rect x="124" y="94" width="36" height="26" rx="8" /><path d="M116 104 L124 104" /></g>}
          <path d="M118 112 Q114 128 122 130" stroke="#00000030" strokeWidth="3" fill="none" strokeLinecap="round" />
          <ellipse cx="120" cy="146" rx={13 + amp * 4} ry={1.6 + amp * 11} fill="#3b1515" />
        </g>
      </g>
    </svg>
  );
};

const ETIQUETA: Record<Timeline['backend'], string | null> = {
  say: 'voz provisional · sintética',
  elevenlabs: 'voz generada',
  archivo: null, // su propia voz grabada
};

// Subtítulos a la derecha del avatar, sincronizados con cada línea de la voz.
export const Subtitulos: React.FC<{timeline: Timeline; izquierda?: number}> = ({timeline, izquierda = 320}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = f / fps;
  const l = timeline.lineas.find((x) => t >= x.start - 0.1 && t < x.start + x.dur + 0.25);
  if (!l) return null;
  const o = interpolate(t, [l.start - 0.1, l.start + 0.1, l.start + l.dur + 0.1, l.start + l.dur + 0.25], [0, 1, 1, 0], clamp);
  return (
    <div style={{position: 'absolute', left: izquierda, right: 60, top: 1270, height: 230, display: 'flex', alignItems: 'center', fontFamily: sans, fontWeight: 600,
      fontSize: l.texto.length > 70 ? 38 : 44, lineHeight: 1.25, color: '#e2e8f0', opacity: o}}>
      {l.texto}
    </div>
  );
};

// Todo junto: pista de voz, avatar, subtítulos y la etiqueta de transparencia.
export const Narracion: React.FC<{timeline: Timeline; avatar?: boolean}> = ({timeline, avatar = true}) => {
  const src = staticFile(timeline.audio);
  const etiqueta = ETIQUETA[timeline.backend];
  return (
    <>
      <Audio src={src} />
      {avatar && <Avatar src={src} />}
      <Subtitulos timeline={timeline} izquierda={avatar ? 320 : 70} />
      {etiqueta && <div style={{position: 'absolute', left: avatar ? 60 : 70, top: 1508, width: avatar ? 230 : 600, textAlign: avatar ? 'center' : 'left', fontFamily: mono, fontSize: 18, color: C.g3}}>{etiqueta}</div>}
    </>
  );
};

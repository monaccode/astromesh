// Plantilla "HUD": telemetría de misión sobre un campo de estrellas.
// Otra forma de presentar, al lado de Mission Control (kit.tsx), que sigue igual:
// mismas fuentes y tokens de color, pero el lenguaje es el de una consola de vuelo
// (marco de instrumentos, reloj T+, lecturas que cuentan, órbitas). Pensada para
// videos sin voz ni subtítulos: el texto es corto y vive en los instrumentos.
import React from 'react';
import {AbsoluteFill, interpolate, random, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, clamp, ease, mono, sans} from './kit';

export const H = {
  ...C,
  pink: '#f472b6', ok: '#34d399', line: 'rgba(148,163,184,.22)', dim: 'rgba(148,163,184,.55)',
};

export const fadeIn = (f: number, from: number, len = 14) => interpolate(f, [from, from + len], [0, 1], clamp);
export const rise = (f: number, from: number, px = 36) => `translateY(${(1 - fadeIn(f, from, 18)) * px}px)`;

// Campo de estrellas determinista con parpadeo y deriva lenta (dos planos de paralaje).
const STARS = Array.from({length: 170}, (_, i) => ({
  x: random('sx' + i) * 1080, y: random('sy' + i) * 1920, r: 0.6 + random('sr' + i) * 1.8,
  z: random('sz' + i) > 0.7 ? 1 : 0.35, tw: random('st' + i) * Math.PI * 2,
}));
export const Starfield: React.FC<{drift?: number}> = ({drift = 0.25}) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: 'radial-gradient(ellipse 120% 80% at 50% 35%, #0b1626 0%, #060d15 55%, #03070c 100%)'}}>
      {STARS.map((s, i) => (
        <div key={i} style={{
          position: 'absolute', left: s.x, top: (s.y + f * drift * s.z * 2) % 1920, width: s.r * 2, height: s.r * 2, borderRadius: '50%',
          background: '#e2e8f0', opacity: (0.35 + 0.65 * s.z) * (0.55 + 0.45 * Math.sin(f / 18 + s.tw)),
        }} />
      ))}
      <AbsoluteFill style={{background: 'radial-gradient(circle at 80% 12%, rgba(244,114,182,.12), transparent 40%), radial-gradient(circle at 15% 85%, rgba(0,212,255,.10), transparent 45%)'}} />
    </AbsoluteFill>
  );
};

const pad = (n: number) => String(Math.floor(n)).padStart(2, '0');

// Marco de instrumentos: esquinas, barra de misión con reloj T+ y barra de estado.
// Queda dentro de la zona segura de Reels (barra superior bajo y = 250, inferior sobre 1540).
export const HudFrame: React.FC<{phase: string; start: number; status?: string}> = ({phase, start, status = 'NOMINAL'}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = (start + f) / fps;
  const corner = (s: React.CSSProperties) => (
    <div style={{position: 'absolute', width: 60, height: 60, borderColor: H.dim, borderStyle: 'solid', borderWidth: 0, ...s}} />
  );
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {corner({left: 40, top: 260, borderLeftWidth: 2, borderTopWidth: 2})}
      {corner({right: 40, top: 260, borderRightWidth: 2, borderTopWidth: 2})}
      {corner({left: 40, top: 1480, borderLeftWidth: 2, borderBottomWidth: 2})}
      {corner({right: 40, top: 1480, borderRightWidth: 2, borderBottomWidth: 2})}
      <div style={{position: 'absolute', left: 70, right: 70, top: 280, display: 'flex', justifyContent: 'space-between', fontFamily: mono, fontSize: 24, letterSpacing: '.12em', color: H.dim}}>
        <span>ASTROMESH-CONTEXT · <span style={{color: H.pink}}>{phase}</span></span>
        <span>T+{pad(t / 60)}:{pad(t % 60)}</span>
      </div>
      <div style={{position: 'absolute', left: 70, right: 70, top: 1500, display: 'flex', justifyContent: 'space-between', fontFamily: mono, fontSize: 22, letterSpacing: '.12em', color: H.dim}}>
        <span>LINK <span style={{color: H.ok}}>●</span> {status}</span>
        <span><span style={{color: Math.sin(f / 7) > 0 ? H.pink : H.dim}}>●</span> TELEMETRÍA</span>
      </div>
    </AbsoluteFill>
  );
};

// Escena HUD: fundido, estrellas y marco. `start` es el frame global (para el reloj T+).
export const HScene: React.FC<{d: number; start: number; phase: string; status?: string; children: React.ReactNode}> = ({d, start, phase, status, children}) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{opacity: interpolate(f, [0, 12, d - 12, d], [0, 1, 1, 0], clamp)}}>
      <Starfield />
      <HudFrame phase={phase} start={start} status={status} />
      {children}
    </AbsoluteFill>
  );
};

// Etiqueta de instrumento: texto mono chico, mayúsculas espaciadas.
export const Label: React.FC<{x: number; y: number; c?: string; size?: number; from?: number; children: React.ReactNode}> = ({x, y, c = H.dim, size = 26, from = 0, children}) => {
  const f = useCurrentFrame();
  return <div style={{position: 'absolute', left: x, top: y, fontFamily: mono, fontSize: size, letterSpacing: '.1em', color: c, opacity: fadeIn(f, from), whiteSpace: 'nowrap'}}>{children}</div>;
};

// Titular de la escena: light 300 con la palabra clave en 800.
export const Headline: React.FC<{top: number; from?: number; size?: number; children: React.ReactNode}> = ({top, from = 0, size = 84, children}) => {
  const f = useCurrentFrame();
  return (
    <div style={{position: 'absolute', top, left: 70, right: 70, fontFamily: sans, fontWeight: 300, fontSize: size, lineHeight: 1.08, color: C.g2,
      opacity: fadeIn(f, from), transform: rise(f, from)}}>{children}</div>
  );
};
export const K: React.FC<{c?: string; children: React.ReactNode}> = ({c = H.pink, children}) => <b style={{fontWeight: 800, color: c}}>{children}</b>;

// Lectura numérica que cuenta desde `fromValue` hasta `value` entre los frames `from` y `from + len`.
export const Readout: React.FC<{x: number; y: number; label: string; value: number; fromValue?: number; digits?: number; suffix?: string; c?: string; from: number; len?: number; size?: number}> = (
  {x, y, label, value, fromValue = 0, digits = 3, suffix = '', c = H.cyan, from, len = 40, size = 120},
) => {
  const f = useCurrentFrame();
  const v = interpolate(f, [from, from + len], [fromValue, value], {...clamp, easing: ease});
  return (
    <div style={{position: 'absolute', left: x, top: y, opacity: fadeIn(f, from - 6)}}>
      <div style={{fontFamily: mono, fontSize: 24, letterSpacing: '.12em', color: H.dim}}>{label}</div>
      <div style={{fontFamily: mono, fontWeight: 700, fontSize: size, color: c, textShadow: `0 0 30px ${c}66`, lineHeight: 1.05}}>{v.toFixed(digits)}{suffix}</div>
    </div>
  );
};

// Barra de instrumento horizontal (0..1) con su etiqueta y valor.
export const Gauge: React.FC<{x: number; y: number; w: number; label: string; value: number; shown: string; c: string; from: number; note?: string}> = ({x, y, w, label, value, shown, c, from, note}) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [from, from + 36], [0, value], {...clamp, easing: ease});
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, opacity: fadeIn(f, from - 8)}}>
      <div style={{display: 'flex', justifyContent: 'space-between', fontFamily: mono, fontSize: 28, color: C.g2, marginBottom: 12}}>
        <span>{label}</span><span style={{color: c, fontWeight: 700}}>{shown}</span>
      </div>
      <div style={{height: 26, borderRadius: 4, background: 'rgba(255,255,255,.05)', border: `1px solid ${H.line}`, overflow: 'hidden'}}>
        <div style={{width: `${p * 100}%`, height: '100%', background: `linear-gradient(90deg, ${c}55, ${c})`, boxShadow: `0 0 24px ${c}88`}} />
      </div>
      {note && <div style={{fontFamily: mono, fontSize: 22, color: H.dim, marginTop: 10, opacity: fadeIn(f, from + 30)}}>{note}</div>}
    </div>
  );
};

// Órbita punteada alrededor de (cx, cy).
export const Ring: React.FC<{cx: number; cy: number; r: number; c?: string; from?: number; dash?: string}> = ({cx, cy, r, c = H.line, from = 0, dash = '6 10'}) => {
  const f = useCurrentFrame();
  return (
    <svg style={{position: 'absolute', left: cx - r - 2, top: cy - r - 2, overflow: 'visible', opacity: fadeIn(f, from, 20)}} width={r * 2 + 4} height={r * 2 + 4}>
      <circle cx={r + 2} cy={r + 2} r={r} fill="none" stroke={c} strokeWidth={2} strokeDasharray={dash} transform={`rotate(${f * 0.3} ${r + 2} ${r + 2})`} />
    </svg>
  );
};

// Mission Control: tokens y piezas compartidas de todos los videos.
import React, {createContext, useContext} from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import {loadFont as loadSans} from '@remotion/google-fonts/DMSans';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

export const sans = loadSans('normal', {weights: ['300', '500', '800'], subsets: ['latin']}).fontFamily;
export const mono = loadMono('normal', {weights: ['400', '700'], subsets: ['latin']}).fontFamily;

export const C = {
  bg: '#060d15', amber: '#fbbf24', amberD: '#f59e0b', cyan: '#00d4ff',
  g2: '#cbd5e1', g3: '#94a3b8', red: '#f87171',
  tenants: ['#fbbf24', '#00d4ff', '#a78bfa', '#34d399'],
};
export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
export const ease = Easing.bezier(0.22, 1, 0.36, 1);
export const grad = `linear-gradient(135deg, ${C.amber}, ${C.amberD} 55%, ${C.cyan})`;

export const Bg: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <AbsoluteFill style={{
        backgroundImage: 'linear-gradient(rgba(251,191,36,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(251,191,36,.05) 1px,transparent 1px)',
        backgroundSize: '60px 60px', backgroundPosition: `0 ${f * 0.4}px`,
        WebkitMaskImage: 'radial-gradient(ellipse 90% 60% at 50% 40%,#000 30%,transparent 100%)',
      }} />
      <AbsoluteFill style={{background: 'radial-gradient(circle at 85% 8%, rgba(245,158,11,.18), transparent 45%)'}} />
    </AbsoluteFill>
  );
};

// Fundido de entrada/salida de una escena de d frames.
export const Scene: React.FC<{d: number; children: React.ReactNode}> = ({d, children}) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{opacity: interpolate(f, [0, 10, d - 10, d], [0, 1, 1, 0], clamp)}}>
      <Bg />
      {children}
    </AbsoluteFill>
  );
};

// Con narración, los subtítulos salen del timeline de la voz y estos se apagan.
export const NoCaps = createContext(false);

// Subtítulo grande, fuera de la zona que tapa la UI de Reels.
export const Cap: React.FC<{from: number; to: number; children: React.ReactNode}> = ({from, to, children}) => {
  const f = useCurrentFrame();
  if (useContext(NoCaps)) return null;
  return (
    <div style={{
      position: 'absolute', left: 70, right: 70, top: 1290, display: 'flex', justifyContent: 'center',
      textAlign: 'center', fontFamily: sans, fontWeight: 500, fontSize: 50, lineHeight: 1.25, color: C.g2,
      opacity: interpolate(f, [from, from + 10, to - 8, to], [0, 1, 1, 0], clamp),
      transform: `translateY(${interpolate(f, [from, from + 14], [18, 0], {...clamp, easing: ease})}px)`,
    }}>
      <span>{children}</span>
    </div>
  );
};

export const Title: React.FC<{children: React.ReactNode; delay?: number}> = ({children, delay = 0}) => {
  const f = useCurrentFrame();
  return (
    <div style={{
      position: 'absolute', top: 220, left: 70, right: 70, fontFamily: sans, fontWeight: 300, fontSize: 72,
      color: C.g2, letterSpacing: '-0.01em',
      opacity: interpolate(f, [delay, delay + 14], [0, 1], clamp),
      transform: `translateY(${interpolate(f, [delay, delay + 20], [30, 0], {...clamp, easing: ease})}px)`,
    }}>{children}</div>
  );
};

export const A: React.FC<{children: React.ReactNode}> = ({children}) => (
  <b style={{fontWeight: 800, color: C.amber}}>{children}</b>
);

export const Dot: React.FC<{x: number; y: number; color: string; r?: number; glow?: number}> = ({x, y, color, r = 8, glow = 1}) => (
  <div style={{
    position: 'absolute', left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: '50%', background: color,
    boxShadow: `0 0 ${24 * glow}px ${color}, 0 0 ${60 * glow}px ${color}55`,
  }} />
);

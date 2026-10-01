import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {A, C, Cap, Dot, Scene, Title, clamp, ease, grad, mono, sans} from './kit';

const D = [150, 300, 450, 300, 210];
const START = D.reduce<number[]>((a, d, i) => [...a, (a[i - 1] ?? 0) + (D[i - 1] ?? 0)], []);
export const NEXUS_FRAMES = D.reduce((a, b) => a + b, 0);

// ── 1 · Gancho ────────────────────────────────────────────────
const Word: React.FC<{t: string; delay: number}> = ({t, delay}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: f - delay, fps, config: {damping: 200}});
  return <span style={{display: 'inline-block', marginRight: 28, opacity: s, transform: `translateY(${(1 - s) * 50}px)`}}>{t}</span>;
};

const S1: React.FC = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const big = spring({frame: f - 62, fps, config: {damping: 11, stiffness: 120}});
  return (
    <Scene d={D[0]}>
      {[0, 1, 2].map((i) => {
        const p = ((f + i * 20) % 60) / 60;
        return <div key={i} style={{position: 'absolute', left: 540 - 220 * p, top: 400 - 220 * p, width: 440 * p, height: 440 * p, borderRadius: '50%',
          border: `2px solid ${C.amber}`, opacity: (1 - p) * 0.5 * interpolate(f, [0, 20], [0, 1], clamp)}} />;
      })}
      <Dot x={540} y={400} color={C.amber} r={16 + Math.sin(f / 4) * 3} />
      <div style={{position: 'absolute', top: 540, left: 0, right: 0, textAlign: 'center', fontFamily: sans, fontWeight: 300, fontSize: 118, lineHeight: 1.08, color: C.g2}}>
        <div><Word t="Hacer" delay={12} /><Word t="un" delay={18} /></div>
        <div><Word t="agente" delay={24} /></div>
        <div><Word t="es" delay={38} /><Word t="el" delay={44} /></div>
        <div style={{fontWeight: 800, fontSize: 300, lineHeight: 1.1, background: grad, WebkitBackgroundClip: 'text', color: 'transparent',
          transform: `scale(${big})`, opacity: big, filter: `drop-shadow(0 0 ${40 * big}px rgba(251,191,36,.45))`}}>10%</div>
      </div>
      <Cap from={95} to={148}>El otro 90% es lo que lo <A>sostiene en producción</A>.</Cap>
    </Scene>
  );
};

// ── 2 · Una sola puerta ───────────────────────────────────────
const N = 60;
const GATE = 760, Y0 = 330, Y1 = 1180, LANES = [150, 410, 670, 930];

const S2: React.FC = () => {
  const f = useCurrentFrame();
  const ps = Array.from({length: N}, (_, i) => ({i, start: 15 + i * 3.5, x0: 80 + random('x' + i) * 920, lane: i % 4}));
  const counts = [0, 0, 0, 0];
  return (
    <Scene d={D[1]}>
      <Title>Una sola <A>puerta</A>.</Title>
      <div style={{position: 'absolute', left: 0, right: 0, top: GATE, height: 3, background: `linear-gradient(90deg, transparent, ${C.amber}, transparent)`,
        boxShadow: `0 0 30px ${C.amber}`, opacity: interpolate(f, [5, 25], [0, 1], clamp)}} />
      <div style={{position: 'absolute', right: 60, top: GATE + 20, fontFamily: mono, fontSize: 26, color: C.amber, opacity: interpolate(f, [20, 40], [0, 1], clamp)}}>
        API key · JWT → tenant
      </div>
      {ps.map(({i, start, x0, lane}) => {
        const p = interpolate(f, [start, start + 60], [0, 1], clamp);
        if (p <= 0) return null;
        const y = Y0 + p * (Y1 - Y0);
        const past = y > GATE;
        if (p >= 1) counts[lane]++;
        const x = p < 0.5 ? x0 : interpolate(p, [0.5, 0.85], [x0, LANES[lane]], {...clamp, easing: ease});
        return <Dot key={i} x={x} y={y} r={past ? 8 : 6} color={past ? C.tenants[lane] : C.g3} glow={past ? 1 : 0.2} />;
      })}
      {LANES.map((x, i) => (
        <div key={i} style={{position: 'absolute', left: x - 105, top: 1195, width: 210, textAlign: 'center', fontFamily: mono, fontSize: 24, color: C.tenants[i],
          border: `1px solid ${C.tenants[i]}66`, borderRadius: 10, padding: '10px 0', background: `${C.tenants[i]}12`}}>
          tenant {'ABCD'[i]} · {counts[i]}
        </div>
      ))}
      <Cap from={20} to={150}>REST o WhatsApp: <A>una sola entrada</A>.</Cap>
      <Cap from={155} to={295}>La credencial define el tenant. <A>Nunca el body</A>.</Cap>
    </Scene>
  );
};

// ── 3 · El mismo camino ───────────────────────────────────────
const NODES = [
  ['01 · TENANT', 'La credencial dice quién llama'],
  ['02 · LÍMITES', 'Cuánto puede usar cada tenant'],
  ['03 · DESPACHO', 'Pool compartido de runtimes'],
  ['04 · MEDICIÓN', 'Por corrida, por modelo, por tenant'],
  ['05 · REGISTRO', 'La invocación queda en PostgreSQL'],
];
const T = [30, 110, 190, 270, 350];
const top = (i: number) => 330 + i * 180;

const S3: React.FC = () => {
  const f = useCurrentFrame();
  const py = interpolate(f, T, NODES.map((_, i) => top(i) + 60), {...clamp, easing: ease});
  const blocked = interpolate(f, [125, 150], [1010, 900], {...clamp, easing: ease});
  const blockOp = interpolate(f, [120, 130, 250, 270], [0, 1, 1, 0], clamp);
  const lit = Math.floor(random('pod' + Math.floor(f / 18)) * 9);
  return (
    <Scene d={D[2]}>
      <Title>El mismo camino, <A>siempre</A>.</Title>
      <div style={{position: 'absolute', left: 83, top: top(0) + 60, width: 4, height: top(4) - top(0), background: `${C.amber}33`}} />
      {NODES.map(([t, d], i) => {
        const a = interpolate(f, [T[i] - 8, T[i] + 6], [0, 1], clamp);
        const vis = interpolate(f, [i * 8, i * 8 + 14], [0, 1], clamp);
        return (
          <div key={i} style={{position: 'absolute', left: 140, top: top(i), width: 840, height: 120, borderRadius: 14, boxSizing: 'border-box', padding: '22px 30px',
            border: `1px solid rgba(251,191,36,${0.15 + 0.85 * a})`, background: 'rgba(10,12,18,.85)', boxShadow: `0 0 ${50 * a}px rgba(251,191,36,${0.22 * a})`,
            opacity: vis, transform: `translateX(${(1 - vis) * 40}px)`}}>
            <div style={{fontFamily: mono, fontWeight: 700, fontSize: 24, letterSpacing: '.08em', color: C.amber}}>{t}</div>
            <div style={{fontFamily: sans, fontWeight: 300, fontSize: 34, color: C.g2, marginTop: 6}}>{d}</div>
            {i === 2 && (
              <div style={{position: 'absolute', right: 34, top: 28, display: 'grid', gridTemplateColumns: 'repeat(3, 18px)', gap: 8, opacity: a}}>
                {Array.from({length: 9}, (_, k) => <div key={k} style={{width: 18, height: 18, borderRadius: 5, background: k === lit ? C.cyan : '#ffffff18', boxShadow: k === lit ? `0 0 14px ${C.cyan}` : 'none'}} />)}
              </div>
            )}
          </div>
        );
      })}
      <Dot x={85} y={py} color={C.amber} r={14} />
      <div style={{opacity: blockOp}}>
        <Dot x={blocked} y={top(1) + 60} color={C.red} r={9} />
        <div style={{position: 'absolute', right: 60, top: top(1) + 128, fontFamily: mono, fontSize: 22, color: C.red}}>✕ límite alcanzado</div>
      </div>
      <Cap from={10} to={105}>Cada llamada pasa por <A>el mismo camino</A>.</Cap>
      <Cap from={112} to={262}>Valida el límite y despacha a un <A>pool compartido</A>.</Cap>
      <Cap from={270} to={445}>Se mide el consumo y <A>queda registrada</A>.</Cap>
    </Scene>
  );
};

// ── 4 · Medición y registro ───────────────────────────────────
const VALUES = [412, 1280, 236, 905];
const HASH = ['3f9a1c', 'b72e04', 'e5d8a7'];

const S4: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <Scene d={D[3]}>
      <Title>Se <A>mide</A>. Se <A>registra</A>.</Title>
      <div style={{position: 'absolute', left: 80, top: 330, fontFamily: mono, fontSize: 24, color: C.g3}}>créditos del período · datos ilustrativos</div>
      {VALUES.map((v, i) => {
        const p = interpolate(f, [15 + i * 10, 140 + i * 10], [0, 1], {...clamp, easing: ease});
        return (
          <div key={i} style={{position: 'absolute', left: 80, top: 390 + i * 120, width: 920, height: 60}}>
            <div style={{fontFamily: mono, fontSize: 26, color: C.tenants[i], width: 190, lineHeight: '60px'}}>tenant {'ABCD'[i]}</div>
            <div style={{position: 'absolute', left: 200, top: 12, width: 540, height: 36, borderRadius: 8, background: '#ffffff0d'}}>
              <div style={{width: `${(v / 1280) * 100 * p}%`, height: '100%', borderRadius: 8, background: C.tenants[i], boxShadow: `0 0 24px ${C.tenants[i]}88`}} />
            </div>
            <div style={{position: 'absolute', right: 0, top: 0, fontFamily: mono, fontWeight: 700, fontSize: 38, color: C.amber, lineHeight: '60px'}}>{Math.round(v * p)}</div>
          </div>
        );
      })}
      <div style={{position: 'absolute', left: 80, top: 905, fontFamily: mono, fontWeight: 700, fontSize: 24, letterSpacing: '.08em', color: C.amber, opacity: interpolate(f, [160, 175], [0, 1], clamp)}}>
        REGISTRO VERSIONADO
      </div>
      {HASH.map((h, i) => {
        const t = 170 + i * 28;
        const o = interpolate(f, [t, t + 14], [0, 1], clamp);
        const last = i === 2;
        return (
          <div key={i} style={{position: 'absolute', left: 80, top: 955 + i * 100, width: 920, height: 80, boxSizing: 'border-box', borderRadius: 12, padding: '0 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            border: `1px solid ${last ? C.amber : 'rgba(255,255,255,.1)'}`, background: last ? 'rgba(251,191,36,.08)' : 'rgba(255,255,255,.03)',
            opacity: o, transform: `translateX(${(1 - o) * -50}px)`, fontFamily: mono, fontSize: 28, color: last ? '#fde68a' : C.g2}}>
            <span style={{fontWeight: 700}}>v{i + 1}</span><span>autor · sha256 {h}…</span>
          </div>
        );
      })}
      <Cap from={10} to={155}>Por corrida, por modelo, <A>por tenant</A>.</Cap>
      <Cap from={160} to={295}>Cada publicación: <A>autor y checksum</A>.</Cap>
    </Scene>
  );
};

// ── 5 · Cierre ────────────────────────────────────────────────
const STARS = Array.from({length: 36}, (_, i) => ({x: 60 + random('sx' + i) * 960, y: 300 + random('sy' + i) * 960, i}));

const S5: React.FC = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const logo = spring({frame: f - 8, fps, config: {damping: 200}});
  const pos = STARS.map(({x, y, i}) => [x + Math.sin(f / 40 + i) * 12, y + Math.cos(f / 50 + i) * 12] as const);
  return (
    <Scene d={D[4]}>
      <svg width={1080} height={1920} style={{position: 'absolute', inset: 0, opacity: 0.55 * interpolate(f, [0, 30], [0, 1], clamp)}}>
        {pos.flatMap(([x, y], a) => pos.slice(a + 1).map(([x2, y2], b) => {
          const d = Math.hypot(x - x2, y - y2);
          return d < 280 ? <line key={a + '-' + b} x1={x} y1={y} x2={x2} y2={y2} stroke={C.amber} strokeOpacity={(1 - d / 280) * 0.5} strokeWidth={2} /> : null;
        }))}
        {pos.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={5 + Math.sin(f / 10 + i) * 2} fill={C.tenants[i % 4]} />)}
      </svg>
      <Img src={staticFile('astromesh-logo.png')} style={{position: 'absolute', left: 150, top: 430, width: 780, opacity: logo, transform: `scale(${0.85 + 0.15 * logo})`, filter: 'drop-shadow(0 0 40px rgba(0,212,255,.35))'}} />
      <div style={{position: 'absolute', top: 900, left: 70, right: 70, textAlign: 'center', fontFamily: sans, fontWeight: 300, fontSize: 64, color: C.g2,
        opacity: interpolate(f, [40, 56], [0, 1], clamp)}}>Los agentes son lo visible.</div>
      <div style={{position: 'absolute', top: 1000, left: 70, right: 70, textAlign: 'center', fontFamily: sans, fontWeight: 800, fontSize: 76, lineHeight: 1.1,
        background: grad, WebkitBackgroundClip: 'text', color: 'transparent', opacity: interpolate(f, [85, 105], [0, 1], clamp),
        transform: `translateY(${interpolate(f, [85, 110], [24, 0], {...clamp, easing: ease})}px)`}}>
        Nexus es la plataforma que los vuelve un producto.
      </div>
      <div style={{position: 'absolute', top: 1330, left: 0, right: 0, textAlign: 'center', fontFamily: mono, fontSize: 28, color: C.g3, opacity: interpolate(f, [130, 150], [0, 1], clamp)}}>
        monaccode.github.io/astromesh/nexus
      </div>
    </Scene>
  );
};

export const NexusReel: React.FC<{music: boolean}> = ({music}) => (
  <AbsoluteFill style={{background: C.bg}}>
    {[S1, S2, S3, S4, S5].map((S, i) => <Sequence key={i} from={START[i]} durationInFrames={D[i]}><S /></Sequence>)}
    {music && <Audio src={staticFile('music.mp3')} volume={(f) => interpolate(f, [0, 30, NEXUS_FRAMES - 60, NEXUS_FRAMES], [0, 0.6, 0.6, 0], clamp)} />}
  </AbsoluteFill>
);

// "Cada cosa en su capa" (2026-10-01): Rust nativo, prefetch y Glyph medido. ~37 s, 9:16, sin voz.
import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, Cap, Dot, NoCaps, Scene, Title, clamp, ease, mono, sans} from './kit';
import {Narracion, Timeline} from './voz';

const D = [120, 270, 270, 270, 180];
const starts = (ds: number[]) => ds.reduce<number[]>((a, _, i) => [...a, i ? a[i - 1] + ds[i - 1] : 0], []);
export const CAPAS_FRAMES = D.reduce((a, b) => a + b, 0);

const CY = C.cyan; // acento de la base Astromesh (Nexus usa ámbar)
const Hl: React.FC<{children: React.ReactNode}> = ({children}) => <b style={{fontWeight: 800, color: CY}}>{children}</b>;
const fade = (f: number, from: number, len = 14) => interpolate(f, [from, from + len], [0, 1], clamp);
const Tag: React.FC<{children: React.ReactNode}> = ({children}) => (
  <div style={{position: 'absolute', left: 70, top: 330, fontFamily: mono, fontSize: 24, color: C.g3}}>{children}</div>
);

// 1 · Gancho
const S1: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: f - 8, fps, config: {damping: 200}});
  return (
    <Scene d={d}>
      {[0, 1, 2].map((i) => {
        const p = ((f + i * 20) % 60) / 60;
        return <div key={i} style={{position: 'absolute', left: 540 - 200 * p, top: 420 - 200 * p, width: 400 * p, height: 400 * p, borderRadius: '50%', border: `2px solid ${CY}`, opacity: (1 - p) * 0.5}} />;
      })}
      <Dot x={540} y={420} color={CY} r={18 + Math.sin(f / 4) * 3} />
      <div style={{position: 'absolute', top: 640, left: 70, right: 70, textAlign: 'center', fontFamily: sans, fontWeight: 300, fontSize: 112, lineHeight: 1.1, color: C.g2,
        opacity: s, transform: `translateY(${(1 - s) * 50}px)`}}>
        No todo debe pasar por el <span style={{fontWeight: 800, color: CY, filter: `drop-shadow(0 0 30px ${CY}88)`}}>modelo</span>.
      </div>
      <Cap from={70} to={115}>Cada cosa, <Hl>en su capa</Hl>.</Cap>
    </Scene>
  );
};

// 2 · Capas
const LAYERS: [string, string][] = [
  ['MODELO', 'razona y decide'],
  ['PLAN · GLYPH', 'se escribe una vez, se revisa'],
  ['RUNTIME · PREFETCH', 'búsquedas antes del modelo'],
  ['NATIVO · RUST', 'caminos calientes de CPU'],
];
const BY = (i: number) => 340 + i * 215;
const S2: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const py = interpolate(f, [60, 90, 150, 175, 200, 225, 250], [BY(0) + 85, BY(0) + 85, BY(1) + 85, BY(2) + 85, BY(3) + 85, BY(3) + 85, BY(3) + 85], {...clamp, easing: ease});
  return (
    <Scene d={d}>
      <Title>Una capa para <Hl>cada trabajo</Hl></Title>
      {LAYERS.map(([t, d], i) => {
        const o = fade(f, 10 + i * 10);
        const hot = (i === 0 && f > 60 && f < 130) || (i === 3 && f > 200);
        return (
          <div key={i} style={{position: 'absolute', left: 80, top: BY(i), width: 920, height: 170, boxSizing: 'border-box', borderRadius: 16, padding: '34px 40px',
            border: `1px solid ${hot ? CY : 'rgba(255,255,255,.1)'}`, background: 'rgba(10,12,18,.85)', boxShadow: hot ? `0 0 50px ${CY}33` : 'none', opacity: o, transform: `translateX(${(1 - o) * 40}px)`}}>
            <div style={{fontFamily: mono, fontWeight: 700, fontSize: 28, letterSpacing: '.08em', color: CY}}>{t}</div>
            <div style={{fontFamily: sans, fontWeight: 300, fontSize: 38, color: C.g2, marginTop: 8}}>{d}</div>
            {i === 0 && f > 60 && f < 130 && <div style={{position: 'absolute', right: 40, top: 56, fontFamily: mono, fontSize: 28, color: C.g3}}>$ tokens</div>}
          </div>
        );
      })}
      {f > 200 && Array.from({length: 14}, (_, k) => <Dot key={k} x={130 + ((f * 16 + k * 61) % 800)} y={BY(3) + 130} r={6} color={CY} glow={0.5} />)}
      <Dot x={50} y={py} color="#ffffff" r={12} />
      <Cap from={20} to={120}>El modelo razona. <Hl>Solo eso</Hl> cuesta tokens.</Cap>
      <Cap from={130} to={265}>Lo determinista baja de capa, con <Hl>fallback a Python</Hl>.</Cap>
    </Scene>
  );
};

// 3 · Prefetch
const S3: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const llm = interpolate(f, [30, 150], [0, 1], {...clamp, easing: (t) => t});
  const fast = interpolate(f, [30, 33], [0, 1], clamp);
  return (
    <Scene d={d}>
      <Title><Hl>Prefetch</Hl>: la búsqueda, antes</Title>
      <Tag>medido en un agente auditor de CLARUS</Tag>
      <div style={{position: 'absolute', left: 80, top: 480, fontFamily: mono, fontSize: 30, color: C.g3}}>viaje al LLM para decidir buscar</div>
      <div style={{position: 'absolute', left: 80, top: 530, width: 920, height: 54, borderRadius: 10, background: '#ffffff10'}}>
        <div style={{width: `${llm * 100}%`, height: '100%', borderRadius: 10, background: C.g3}} />
      </div>
      <div style={{position: 'absolute', left: 80, top: 600, fontFamily: mono, fontWeight: 700, fontSize: 56, color: C.g2}}>~{(llm * 5).toFixed(1)} s</div>

      <div style={{position: 'absolute', left: 80, top: 760, fontFamily: mono, fontSize: 30, color: CY}}>búsqueda directa (prefetch)</div>
      <div style={{position: 'absolute', left: 80, top: 810, width: 920, height: 54, borderRadius: 10, background: '#ffffff10'}}>
        <div style={{width: `${(55 / 5000) * 100 * fast}%`, minWidth: fast * 8, height: '100%', borderRadius: 10, background: CY, boxShadow: `0 0 30px ${CY}`}} />
      </div>
      <div style={{position: 'absolute', left: 80, top: 880, fontFamily: mono, fontWeight: 700, fontSize: 56, color: CY, opacity: fast}}>~55 ms</div>
      <Cap from={20} to={130}>Un viaje al LLM <Hl>solo para decidir buscar</Hl>.</Cap>
      <Cap from={140} to={265}>El runtime hace la consulta de solo lectura <Hl>antes</Hl>.</Cap>
    </Scene>
  );
};

// 4 · Glyph medido
const S4: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const react = interpolate(f, [10, 40], [0, 1], {...clamp, easing: ease});
  const gl = interpolate(f, [40, 100], [0, 1], {...clamp, easing: ease});
  const steps = ['el modelo escribe 1 vez', 'una persona lo revisa', 'el runtime lo ejecuta'];
  return (
    <Scene d={d}>
      <Title><Hl>Glyph</Hl>: lo medimos</Title>
      <Tag>costo como patrón de runtime · 3 modelos</Tag>
      <div style={{position: 'absolute', left: 80, top: 430, fontFamily: mono, fontSize: 28, color: C.g3}}>ReAct</div>
      <div style={{position: 'absolute', left: 80, top: 475, width: 300 * react, height: 50, borderRadius: 10, background: C.g3}} />
      <div style={{position: 'absolute', left: 80, top: 570, fontFamily: mono, fontSize: 28, color: C.red}}>Glyph, programa en cada corrida</div>
      <div style={{position: 'absolute', left: 80, top: 615, width: 920 * gl, height: 50, borderRadius: 10, background: C.red, boxShadow: `0 0 30px ${C.red}66`}} />
      <div style={{position: 'absolute', left: 80, top: 690, fontFamily: mono, fontWeight: 700, fontSize: 54, color: C.red, opacity: fade(f, 90)}}>+164% a +2839%</div>
      {steps.map((t, i) => {
        const o = fade(f, 140 + i * 25);
        return (
          <div key={i} style={{position: 'absolute', left: 80, top: 850 + i * 105, width: 920, boxSizing: 'border-box', padding: '22px 30px', borderRadius: 14, border: `1px solid ${i === 2 ? CY : 'rgba(255,255,255,.12)'}`,
            background: 'rgba(10,12,18,.85)', fontFamily: sans, fontWeight: 500, fontSize: 36, color: C.g2, opacity: o, transform: `translateX(${(1 - o) * -40}px)`}}>
            <span style={{fontFamily: mono, color: CY, marginRight: 18}}>{i + 1}</span>{t}
          </div>
        );
      })}
      <div style={{position: 'absolute', right: 80, top: 1165, fontFamily: mono, fontWeight: 700, fontSize: 30, color: CY, opacity: fade(f, 225)}}>0 llamadas al modelo</div>
      <Cap from={20} to={130}>Como patrón de runtime, <Hl>costó más que ReAct</Hl>.</Cap>
      <Cap from={140} to={265}>Sirve si el programa se escribe <Hl>una vez</Hl>.</Cap>
    </Scene>
  );
};

// 5 · Cierre
const S5: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: f - 4, fps, config: {damping: 200}});
  return (
    <Scene d={d}>
      <Img src={staticFile('astromesh-logo.png')} style={{position: 'absolute', left: 190, top: 330, width: 700, opacity: s, filter: 'drop-shadow(0 0 40px rgba(0,212,255,.35))'}} />
      <div style={{position: 'absolute', top: 830, left: 70, right: 70, textAlign: 'center', fontFamily: sans, fontWeight: 300, fontSize: 84, lineHeight: 1.1, color: C.g2, opacity: fade(f, 20)}}>
        Medir antes<br /><Hl>de contar</Hl>.
      </div>
      <div style={{position: 'absolute', top: 1110, left: 90, right: 90, textAlign: 'center', fontFamily: sans, fontWeight: 500, fontSize: 40, color: C.g3, opacity: fade(f, 60)}}>
        Capa por capa: qué hace el modelo y qué no.
      </div>
      <div style={{position: 'absolute', top: 1330, left: 0, right: 0, textAlign: 'center', fontFamily: mono, fontSize: 28, color: C.g3, opacity: fade(f, 100)}}>monaccode.github.io/astromesh</div>
    </Scene>
  );
};

// durs: duración de cada escena en frames (la narración las estira); musicVol baja la música bajo la voz.
export const CapasReel: React.FC<{music: boolean; musica?: string; durs?: number[]; musicVol?: number}> = ({music, musica = 'music.mp3', durs = D, musicVol = 0.6}) => {
  const st = starts(durs);
  const total = st[st.length - 1] + durs[durs.length - 1];
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {[S1, S2, S3, S4, S5].map((S, i) => <Sequence key={i} from={st[i]} durationInFrames={durs[i]}><S d={durs[i]} /></Sequence>)}
      {music && <Audio src={staticFile(musica)} loop volume={(f) => interpolate(f, [0, 30, total - 45, total], [0, musicVol, musicVol, 0], clamp)} />}
    </AbsoluteFill>
  );
};

// Versión narrada: la voz (tools/narrar.mjs) estira las escenas y reemplaza los subtítulos fijos.
export const CapasNarrado: React.FC<{voz: string; avatar?: boolean; musica?: string; timeline?: Timeline; durs?: number[]}> = ({timeline, durs, avatar = true, musica}) =>
  timeline ? (
    <AbsoluteFill>
      <NoCaps.Provider value>
        <CapasReel music musica={musica} durs={durs} musicVol={0.12} />
      </NoCaps.Provider>
      <Narracion timeline={timeline} avatar={avatar} />
    </AbsoluteFill>
  ) : null;

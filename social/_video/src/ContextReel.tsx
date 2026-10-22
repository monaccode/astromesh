// "¿Qué lee tu agente?" (2026-10-22): astromesh-context, con la plantilla HUD (hud.tsx).
// ~50 s, 9:16, sin voz ni subtítulos. Cifras del nivel 1 de ContextEval publicado en el README
// (corrida 2026-10-15, corpus Nimbus, 60 casos); el nivel 2 está pendiente y el cierre lo dice.
import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, random, staticFile, useCurrentFrame} from 'remotion';
import {C, Dot, clamp, ease, mono, sans} from './kit';
import {Gauge, H, HScene, Headline, K, Label, Readout, Ring, fadeIn, rise} from './hud';

const D = [180, 300, 270, 300, 240, 210];
const ST = D.reduce<number[]>((a, _, i) => [...a, i ? a[i - 1] + D[i - 1] : 0], []);
export const CONTEXT_FRAMES = D.reduce((a, b) => a + b, 0);

const VIO = '#a78bfa';
// La ventana de contexto: un rectángulo central que se llena.
const WIN = {x: 330, y: 760, w: 420, h: 330};

const Window: React.FC<{fill: number; from?: number; label?: string}> = ({fill, from = 0, label = 'VENTANA · 750 TOKENS'}) => {
  const f = useCurrentFrame();
  return (
    <div style={{position: 'absolute', left: WIN.x, top: WIN.y, width: WIN.w, height: WIN.h, opacity: fadeIn(f, from, 20)}}>
      <div style={{position: 'absolute', inset: 0, border: `2px solid ${H.pink}`, borderRadius: 10, boxShadow: `0 0 40px ${H.pink}33, inset 0 0 40px ${H.pink}14`}} />
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: `${fill * 100}%`, background: `linear-gradient(0deg, ${H.pink}40, ${H.pink}10)`, borderRadius: '0 0 10px 10px'}} />
      <div style={{position: 'absolute', top: -46, left: 0, right: 0, textAlign: 'center', fontFamily: mono, fontSize: 24, letterSpacing: '.12em', color: H.pink}}>{label}</div>
    </div>
  );
};

// 1 · Ignición: la pregunta
const S1: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  return (
    <HScene d={d} start={ST[0]} phase="IGNICIÓN">
      <Headline top={360} size={92}>¿Qué <K>lee</K> tu agente antes de responder?</Headline>
      <Window fill={0} from={50} />
      <Label x={330} y={1130} from={80} c={H.dim}>RAG · OKF · MEMORIA · HISTORIAL</Label>
      <Label x={330} y={1180} from={100} c={Math.floor(f / 15) % 2 ? H.pink : H.dim}>▸ ESPERANDO CANDIDATOS</Label>
    </HScene>
  );
};

// 2 · Candidatos: cuatro fuentes compiten por un presupuesto
const SRC = [
  {n: 'RAG', c: C.cyan, x: 170, y: 640},
  {n: 'OKF', c: H.pink, x: 910, y: 640},
  {n: 'MEMORIA', c: VIO, x: 170, y: 1290},
  {n: 'HISTORIAL', c: H.ok, x: 910, y: 1290},
];
const N = 32;
const REASONS = ['budget', 'duplicate_of', 'below_floor', 'source_cap'];
const PARTS = Array.from({length: N}, (_, i) => ({
  s: i % 4, t0: 30 + i * 6, ok: random('ok' + i) < 0.5,
  gx: WIN.x + 40 + (i % 6) * 64, gy: WIN.y + WIN.h - 40 - Math.floor(i / 6) * 50,
  ox: random('ox' + i) > 0.5 ? 1120 : -40, oy: 600 + random('oy' + i) * 700,
}));
const S2: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const landed = PARTS.filter((p) => p.ok && f > p.t0 + 40).length;
  const total = PARTS.filter((p) => p.ok).length;
  return (
    <HScene d={d} start={ST[1]} phase="CANDIDATOS">
      <Headline top={350} size={78}>Cuatro fuentes. <K>Un</K> presupuesto.</Headline>
      <Ring cx={WIN.x + WIN.w / 2} cy={WIN.y + WIN.h / 2} r={330} from={10} />
      <Ring cx={WIN.x + WIN.w / 2} cy={WIN.y + WIN.h / 2} r={430} from={20} dash="2 14" />
      <Window fill={(landed / total) * 0.92} />
      {SRC.map((s, i) => (
        <React.Fragment key={s.n}>
          <Dot x={s.x} y={s.y} color={s.c} r={20} glow={0.8} />
          <Label x={s.x > 540 ? s.x - 190 : s.x - 40} y={s.y > 1000 ? s.y + 36 : s.y - 74} c={s.c} from={10 + i * 6}>{s.n}</Label>
        </React.Fragment>
      ))}
      {PARTS.map((p, i) => {
        const s = SRC[p.s];
        const k = interpolate(f, [p.t0, p.t0 + 40], [0, 1], {...clamp, easing: ease});
        if (k <= 0) return null;
        const tx = p.ok ? p.gx : interpolate(k, [0, 0.55, 1], [s.x, WIN.x + WIN.w / 2, p.ox]);
        const ty = p.ok ? p.gy : interpolate(k, [0, 0.55, 1], [s.y, WIN.y - 40, p.oy]);
        const x = p.ok ? interpolate(k, [0, 1], [s.x, tx]) : tx;
        const y = p.ok ? interpolate(k, [0, 1], [s.y, ty]) : ty;
        const c = p.ok ? s.c : interpolate(k, [0.5, 0.7], [0, 1], clamp) > 0.5 ? '#64748b' : s.c;
        return <Dot key={i} x={x} y={y} r={p.ok ? 11 : 8} color={c} glow={p.ok ? 0.7 : 0.25} />;
      })}
      {REASONS.map((r, i) => (
        <Label key={r} x={i % 2 ? 640 : 90} y={1380 + Math.floor(i / 2) * 44} from={130 + i * 18} c="#64748b" size={24}>✕ {r}</Label>
      ))}
      <Label x={WIN.x} y={WIN.y + WIN.h + 24} from={40} c={C.g2}>{Math.round((landed / total) * 750)} / 750 TOKENS</Label>
    </HScene>
  );
};

// 3 · Deprecado: el chunk de RAG hereda la marca del concepto OKF y queda afuera
const Card: React.FC<{x: number; y: number; c: string; title: string; sub: string; style?: React.CSSProperties}> = ({x, y, c, title, sub, style}) => (
  <div style={{position: 'absolute', left: x, top: y, width: 600, padding: '26px 30px', borderRadius: 14, border: `2px solid ${c}88`,
    backgroundColor: '#0a1220', backgroundImage: `linear-gradient(${c}14, ${c}14)`, boxSizing: 'border-box', ...style}}>
    <div style={{fontFamily: mono, fontSize: 24, letterSpacing: '.1em', color: c}}>{title}</div>
    <div style={{fontFamily: sans, fontSize: 40, color: C.g2, marginTop: 8}}>{sub}</div>
  </div>
);
const S3: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const merge = interpolate(f, [60, 100], [0, 1], {...clamp, easing: ease});
  const stamp = fadeIn(f, 105, 8);
  const eject = interpolate(f, [140, 175], [0, 1], {...clamp, easing: ease});
  return (
    <HScene d={d} start={ST[2]} phase="DEDUPLICACIÓN" status="DEPRECATED → AFUERA">
      <Headline top={350} size={80}>Lo deprecado <K>no entra</K>.</Headline>
      <div style={{position: 'absolute', inset: 0, transform: `translateX(${eject * 700}px)`, opacity: 1 - eject * 0.7}}>
        <Card x={240} y={interpolate(merge, [0, 1], [820, 590])} c={C.cyan} title="RAG · CHUNK" sub="…la misma política" style={{opacity: 1 - merge}} />
        <Card x={240} y={560} c={H.pink} title="OKF · CONCEPTO" sub="Política de reembolsos v1" />
        <div style={{position: 'absolute', left: 620, top: 540, padding: '8px 18px', border: `3px solid ${C.red}`, borderRadius: 8, fontFamily: mono, fontWeight: 700, fontSize: 30, color: C.red,
          transform: `rotate(-8deg) scale(${0.6 + stamp * 0.4})`, opacity: stamp}}>DEPRECATED</div>
      </div>
      <Label x={240} y={1000} from={70} c={C.g2} size={26}>CONTENCIÓN ≥ 0.8 · LA COPIA HEREDA LA MARCA</Label>
      <Label x={90} y={1110} from={150} size={24}>POLÍTICAS REEMPLAZADAS EN LA VENTANA</Label>
      <Label x={90} y={1150} from={155} c={C.red} size={30}>ANTES · 0.15 – 0.52</Label>
      <Readout x={90} y={1200} label="AHORA · MÁXIMO" value={0.033} fromValue={0.52} from={165} len={45} c={H.ok} size={130} />
    </HScene>
  );
};

// 4 · Telemetría: recall con 750 tokens, y la idea propia que perdió
const S4: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  return (
    <HScene d={d} start={ST[3]} phase="TELEMETRÍA">
      <Headline top={350} size={80}>Lo <K>medí</K>. Hasta mi idea perdió.</Headline>
      <Label x={90} y={590} from={20} size={24}>RECALL DE LA EVIDENCIA · 750 TOKENS</Label>
      <Gauge x={90} y={650} w={900} label="presupuesto calibrado" value={0.55} shown="0.550" c={C.cyan} from={40} note="precio: más distractores (0.350 contra 0.283)" />
      <Gauge x={90} y={850} w={900} label="porciones fijas por fuente" value={0.333} shown="0.333" c="#94a3b8" from={80} />
      <Gauge x={90} y={1020} w={900} label="mi idea: valor por token" value={0.267} shown="0.267" c={C.red} from={130} note="perdió → apagada por defecto (beta = 0)" />
      <div style={{position: 'absolute', left: 90, right: 90, top: 1250, padding: '22px 26px', borderRadius: 12, border: `1px solid ${H.line}`, background: 'rgba(255,255,255,.03)',
        fontFamily: mono, fontSize: 26, color: C.g2, lineHeight: 1.5, opacity: fadeIn(f, 190), transform: rise(f, 190)}}>
        60 preguntas · nivel 1 · <span style={{color: H.ok}}>sin llamar a ningún modelo</span>
      </div>
    </HScene>
  );
};

// 5 · Cache: lo estable primero, idéntico entre llamadas; y una traza por ítem
const BLOCKS = [
  {n: 'ESTABLE', c: H.pink, h: 120},
  {n: 'SESIÓN', c: VIO, h: 90},
  {n: 'VOLÁTIL', c: C.cyan, h: 70},
];
const Stack: React.FC<{x: number; from: number; call: string; vary: boolean}> = ({x, from, call, vary}) => {
  const f = useCurrentFrame();
  let y = 620;
  return (
    <>
      <Label x={x} y={570} from={from} size={22}>{call}</Label>
      {BLOCKS.map((b, i) => {
        const top = y;
        y += b.h + 14;
        const changed = vary && i > 0;
        return (
          <div key={b.n} style={{position: 'absolute', left: x, top, width: 380, height: b.h, borderRadius: 8, border: `2px solid ${b.c}${changed ? '55' : 'aa'}`,
            background: `${b.c}${changed ? '0c' : '22'}`, display: 'flex', alignItems: 'center', paddingLeft: 22, boxSizing: 'border-box',
            fontFamily: mono, fontSize: 24, color: b.c, opacity: fadeIn(f, from + i * 10), transform: rise(f, from + i * 10, 20)}}>
            {b.n}{changed ? ' ≠' : ''}
          </div>
        );
      })}
    </>
  );
};
const TRACE = ['incluido', 'budget', 'duplicate_of', 'below_floor', 'source_cap', 'deprecated'];
const S5: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const link = fadeIn(f, 70, 20);
  return (
    <HScene d={d} start={ST[4]} phase="CACHE · TRAZA">
      <Headline top={350} size={80}>Lo estable, <K>primero</K>.</Headline>
      <Stack x={90} from={15} call="LLAMADA 1" vary={false} />
      <Stack x={610} from={40} call="LLAMADA 2" vary />
      <div style={{position: 'absolute', left: 470, top: 678, width: 140, height: 4, background: H.pink, boxShadow: `0 0 18px ${H.pink}`, opacity: link, transformOrigin: 'left', transform: `scaleX(${link})`}} />
      <Label x={90} y={960} from={80} c={H.pink} size={24}>ESTABLE: IDÉNTICO BYTE A BYTE ENTRE LLAMADAS</Label>
      <Label x={90} y={1060} from={110} size={24}>CADA ÍTEM VUELVE CON SU MOTIVO</Label>
      <div style={{position: 'absolute', left: 90, right: 90, top: 1110, display: 'flex', flexWrap: 'wrap', gap: 14}}>
        {TRACE.map((t, i) => {
          const c = i === 0 ? H.ok : i === TRACE.length - 1 ? C.red : '#94a3b8';
          return (
            <span key={t} style={{fontFamily: mono, fontSize: 28, color: c, border: `1px solid ${c}66`, background: `${c}14`, borderRadius: 10, padding: '10px 18px',
              opacity: fadeIn(f, 125 + i * 10), transform: rise(f, 125 + i * 10, 16)}}>{t}</span>
          );
        })}
      </div>
    </HScene>
  );
};

// 6 · Cierre
const S6: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  return (
    <HScene d={d} start={ST[5]} phase="ÓRBITA ESTABLE">
      <Img src={staticFile('astromesh-logo.png')} style={{position: 'absolute', left: 290, top: 380, width: 500, opacity: fadeIn(f, 0, 20), filter: 'drop-shadow(0 0 40px rgba(244,114,182,.35))'}} />
      <Headline top={760} from={20} size={86}>Un agente responde con <K>lo que lee</K>.</Headline>
      <div style={{position: 'absolute', left: 90, right: 90, top: 1060, padding: '24px 28px', borderRadius: 12, border: `2px solid ${H.pink}`, background: `${H.pink}12`,
        fontFamily: mono, fontWeight: 700, fontSize: 36, color: '#fbcfe8', opacity: fadeIn(f, 50), transform: rise(f, 50)}}>pip install astromesh-context</div>
      <Label x={90} y={1190} from={80} c={C.g2} size={26}>APACHE-2.0 · PYPI 0.1.0</Label>
      <Label x={90} y={1240} from={95} size={24}>NIVEL 2 (CALIDAD DE RESPUESTA) · PENDIENTE</Label>
    </HScene>
  );
};

export const ContextReel: React.FC<{music: boolean; musica?: string}> = ({music, musica = 'music.mp3'}) => (
  <AbsoluteFill style={{background: '#03070c'}}>
    {[S1, S2, S3, S4, S5, S6].map((S, i) => (
      <Sequence key={i} from={ST[i]} durationInFrames={D[i]}><S d={D[i]} /></Sequence>
    ))}
    {music && <Audio src={staticFile(musica)} volume={(f) => interpolate(f, [0, 45, CONTEXT_FRAMES - 60, CONTEXT_FRAMES], [0, 0.75, 0.75, 0], clamp)} />}
  </AbsoluteFill>
);

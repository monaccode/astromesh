// "Un deck no contesta un WhatsApp" (2026-10-02): Herald + Nexus frente al proyecto de consultoría.
// ~36 s, 9:16, sin voz ni subtítulos: el texto vive dentro de cada escena.
import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, Dot, Scene, clamp, ease, mono, sans} from './kit';

const D = [150, 210, 270, 270, 180];
const starts = (ds: number[]) => ds.reduce<number[]>((a, _, i) => [...a, i ? a[i - 1] + ds[i - 1] : 0], []);
export const DECK_FRAMES = D.reduce((a, b) => a + b, 0);

const CY = C.cyan, HER = '#10b981', NEX = C.amber;
const fade = (f: number, from: number, len = 14) => interpolate(f, [from, from + len], [0, 1], clamp);
const up = (f: number, from: number) => `translateY(${(1 - fade(f, from, 18)) * 40}px)`;
const Big: React.FC<{top: number; from: number; size?: number; children: React.ReactNode}> = ({top, from, size = 96, children}) => {
  const f = useCurrentFrame();
  return <div style={{position: 'absolute', top, left: 70, right: 70, fontFamily: sans, fontWeight: 300, fontSize: size, lineHeight: 1.08, color: C.g2,
    opacity: fade(f, from), transform: up(f, from)}}>{children}</div>;
};
const B: React.FC<{c?: string; children: React.ReactNode}> = ({c = CY, children}) => <b style={{fontWeight: 800, color: c}}>{children}</b>;
const Chip: React.FC<{c: string; children: React.ReactNode}> = ({c, children}) => (
  <span style={{display: 'inline-block', whiteSpace: 'nowrap', marginBottom: 16, fontFamily: mono, fontSize: 28, color: c, border: `1px solid ${c}66`, background: `${c}14`, borderRadius: 10, padding: '10px 18px', marginRight: 14}}>{children}</span>
);

// 1 · 03:00, llega un WhatsApp
const S1: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const msg = spring({frame: f - 30, fps, config: {damping: 14}});
  return (
    <Scene d={d}>
      <div style={{position: 'absolute', top: 240, left: 0, right: 0, textAlign: 'center', fontFamily: mono, fontWeight: 700, fontSize: 150, color: C.g2, opacity: fade(f, 0)}}>03:00</div>
      <div style={{position: 'absolute', left: 300, top: 470, width: 480, height: 560, borderRadius: 48, border: '3px solid rgba(255,255,255,.18)', background: 'rgba(10,12,18,.9)'}}>
        <div style={{position: 'absolute', left: 30, top: 70, maxWidth: 380, padding: '20px 26px', borderRadius: '22px 22px 22px 6px', background: '#1f2c34', fontFamily: sans, fontSize: 34, color: '#e9edef',
          transform: `scale(${msg})`, transformOrigin: 'left top'}}>Hola, ¿dónde está mi pedido?</div>
        <div style={{position: 'absolute', left: 30, top: 240, fontFamily: mono, fontSize: 26, color: C.g3, opacity: fade(f, 70)}}>escribiendo… nadie</div>
      </div>
      <Big top={1110} from={80} size={84}>Un deck no contesta <B c={HER}>un WhatsApp</B>.</Big>
    </Scene>
  );
};

// 2 · Lo que se suele vender
const ITEMS = ['Una presentación', 'Un piloto en un notebook', 'Horas facturadas'];
const S2: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  return (
    <Scene d={d}>
      <div style={{position: 'absolute', top: 240, left: 70, fontFamily: mono, fontWeight: 700, fontSize: 30, letterSpacing: '.1em', color: C.red, opacity: fade(f, 0)}}>LO QUE SE SUELE VENDER</div>
      {ITEMS.map((t, i) => (
        <div key={i} style={{position: 'absolute', left: 70, top: 320 + i * 170, width: 940, boxSizing: 'border-box', padding: '40px 44px', borderRadius: 18, border: '1px solid rgba(248,113,113,.3)',
          background: 'rgba(248,113,113,.05)', fontFamily: sans, fontWeight: 500, fontSize: 52, color: C.g2, opacity: fade(f, 15 + i * 22), transform: up(f, 15 + i * 22)}}>{t}</div>
      ))}
      <Big top={900} from={100} size={92}>¿Y el lunes, <B c={C.red}>quién lo opera</B>?</Big>
    </Scene>
  );
};

// 3 · Herald: el mensaje no se pierde
const S3: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const fail = interpolate(f, [120, 135], [0, 1], clamp), retry = fade(f, 175, 10);
  return (
    <Scene d={d}>
      <Big top={230} from={0} size={78}><B c={HER}>Herald</B>: el mensaje no se pierde.</Big>
      {Array.from({length: 9}, (_, i) => {
        const p = interpolate(f, [20 + i * 9, 80 + i * 9], [0, 1], {...clamp, easing: ease});
        return <Dot key={i} x={interpolate(p, [0, 1], [-40, 470])} y={720 + (random('h' + i) - 0.5) * 120 * (1 - p)} r={12} color={HER} glow={0.6} />;
      })}
      <div style={{position: 'absolute', left: 440, top: 630, width: 6, height: 180, background: HER, boxShadow: `0 0 30px ${HER}`, opacity: fade(f, 10)}} />
      <div style={{position: 'absolute', left: 330, top: 570, fontFamily: mono, fontSize: 26, color: HER, opacity: fade(f, 30)}}>firma de Meta ✓</div>
      <div style={{position: 'absolute', left: 520, top: 630, width: 480, height: 180, borderRadius: 16, border: `1px solid ${HER}66`, background: 'rgba(16,185,129,.06)', padding: 22, boxSizing: 'border-box', opacity: fade(f, 40)}}>
        <div style={{fontFamily: mono, fontWeight: 700, fontSize: 24, color: HER}}>OUTBOX · POSTGRES</div>
        <div style={{display: 'flex', gap: 10, marginTop: 22}}>{Array.from({length: 7}, (_, k) => <div key={k} style={{width: 50, height: 50, borderRadius: 10, background: k === 3 ? (retry ? HER : fail ? C.red : `${HER}55`) : `${HER}55`}} />)}</div>
      </div>
      <div style={{position: 'absolute', left: 300, top: 850, fontFamily: mono, fontSize: 30, color: C.red, opacity: fail * (1 - retry)}}>✕ falló · reintento con backoff</div>
      <div style={{position: 'absolute', left: 520, top: 850, fontFamily: mono, fontSize: 30, color: HER, opacity: retry}}>✓ entregado</div>
      <div style={{position: 'absolute', left: 70, top: 1010, right: 70, opacity: fade(f, 190)}}>
        <Chip c={HER}>al menos una vez</Chip><Chip c={HER}>varias réplicas sin pisarse</Chip><Chip c={HER}>cada chat con su sesión</Chip>
      </div>
    </Scene>
  );
};

// 4 · Nexus: aislado, medido, sin secretos
const S4: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  const key = interpolate(f, [150, 165, 215, 240], [0, 1, 1, 0], clamp);
  return (
    <Scene d={d}>
      <Big top={230} from={0} size={78}><B c={NEX}>Nexus</B>: cada cliente, aislado y medido.</Big>
      <div style={{position: 'absolute', left: 70, top: 440, fontFamily: mono, fontSize: 24, color: C.g3, opacity: fade(f, 10)}}>consumo por tenant · ilustrativo</div>
      {[0.42, 0.9, 0.24, 0.66].map((v, i) => {
        const p = interpolate(f, [20 + i * 8, 120 + i * 8], [0, v], {...clamp, easing: ease});
        return (
          <div key={i} style={{position: 'absolute', left: 70, top: 490 + i * 90, width: 940, height: 60, opacity: fade(f, 10 + i * 6)}}>
            <div style={{fontFamily: mono, fontSize: 28, color: C.tenants[i], lineHeight: '60px'}}>tenant {'ABCD'[i]}</div>
            <div style={{position: 'absolute', left: 200, top: 13, width: 740, height: 34, borderRadius: 8, background: '#ffffff0d'}}>
              <div style={{width: `${p * 100}%`, height: '100%', borderRadius: 8, background: C.tenants[i]}} />
            </div>
          </div>
        );
      })}
      <div style={{position: 'absolute', left: 70, top: 900, right: 70, display: 'flex', alignItems: 'center', gap: 30, opacity: fade(f, 140)}}>
        <div style={{fontSize: 90, opacity: 0.3 + 0.7 * key, filter: `drop-shadow(0 0 ${30 * key}px ${NEX})`}}>🔑</div>
        <div style={{fontFamily: sans, fontWeight: 500, fontSize: 44, color: C.g2, lineHeight: 1.2}}>Token que vive <B c={NEX}>una sola corrida</B>.<br /><span style={{fontSize: 34, color: C.g3}}>El pool no guarda credenciales.</span></div>
      </div>
    </Scene>
  );
};

// 5 · Cierre
const S5: React.FC<{d: number}> = ({d}) => {
  const f = useCurrentFrame();
  return (
    <Scene d={d}>
      <Big top={330} from={5} size={110}>Producto,<br /><B>no proyecto.</B></Big>
      <Big top={680} from={45} size={52}>La IA no se gana con el mejor deck. Se gana con lo que sigue funcionando <B>cuando nadie está mirando</B>.</Big>
      <Img src={staticFile('astromesh-logo.png')} style={{position: 'absolute', left: 240, top: 1080, width: 600, opacity: fade(f, 90), filter: 'drop-shadow(0 0 40px rgba(0,212,255,.35))'}} />
      <div style={{position: 'absolute', top: 1360, left: 0, right: 0, textAlign: 'center', fontFamily: mono, fontSize: 28, color: C.g3, opacity: fade(f, 110)}}>monaccode.github.io/astromesh</div>
    </Scene>
  );
};

export const DeckReel: React.FC<{music: boolean; musica?: string}> = ({music, musica = 'music.mp3'}) => {
  const st = starts(D);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {[S1, S2, S3, S4, S5].map((S, i) => <Sequence key={i} from={st[i]} durationInFrames={D[i]}><S d={D[i]} /></Sequence>)}
      {music && <Audio src={staticFile(musica)} loop volume={(f) => interpolate(f, [0, 30, DECK_FRAMES - 45, DECK_FRAMES], [0, 0.6, 0.6, 0], clamp)} />}
    </AbsoluteFill>
  );
};

import React from 'react';
import {Composition} from 'remotion';
import {NexusReel, NEXUS_FRAMES} from './NexusReel';
import {CapasNarrado, CapasReel, CAPAS_FRAMES} from './CapasReel';
import {cargarTimeline} from './voz';
import {DeckReel, DECK_FRAMES} from './DeckReel';

export const Root: React.FC = () => (
  <>
  <Composition
    id="NexusReel"
    component={NexusReel}
    durationInFrames={NEXUS_FRAMES}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={{music: false}}
  />
  <Composition id="CapasReel" component={CapasReel} durationInFrames={CAPAS_FRAMES} fps={30} width={1080} height={1920} defaultProps={{music: false}} />
  <Composition
    id="CapasNarrado"
    component={CapasNarrado}
    durationInFrames={1}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={{voz: 'capas', avatar: true}}
    calculateMetadata={async ({props}) => {
      const {timeline, durationInFrames, durs} = await cargarTimeline(props.voz, 30);
      return {durationInFrames, props: {...props, timeline, durs}};
    }}
  />
  <Composition id="DeckReel" component={DeckReel} durationInFrames={DECK_FRAMES} fps={30} width={1080} height={1920} defaultProps={{music: false}} />
  </>
);

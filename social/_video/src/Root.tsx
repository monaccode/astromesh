import React from 'react';
import {Composition} from 'remotion';
import {NexusReel, NEXUS_FRAMES} from './NexusReel';

export const Root: React.FC = () => (
  <Composition
    id="NexusReel"
    component={NexusReel}
    durationInFrames={NEXUS_FRAMES}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={{music: false}}
  />
);

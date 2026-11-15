import { Composition } from 'remotion'

import { FPS, Pitch, TOTAL } from './Pitch'

export const Root = () => (
  <Composition id="Pitch" component={Pitch} durationInFrames={TOTAL} fps={FPS} width={1920} height={1080} />
)

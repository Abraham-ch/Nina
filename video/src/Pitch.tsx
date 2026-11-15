import type { CSSProperties, ReactNode } from 'react'
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  OffthreadVideo,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion'

// The same figures the landing page shows, so the video and the app never disagree.
import evidence from '../../web/public/assets/peru-evidence.json'
import world from '../../web/public/assets/world-evidence.json'

// Files in video/public/. intro is the ComfyUI clip; rec_*.webm come from record/record.mjs (Playwright).
const INTRO: string | null = 'intro.webm'
// Narration: video/aud/aud1-5.ogg with the leading silence trimmed and sped up evenly (x1.112, pitch kept) so the
// five takes fill 30 s: ffmpeg -ss <lead> -i aud/audN.ogg -af atempo=1.1119 public/voiceN.ogg. [file, first frame].
const VOICES: [string, number][] = [
  ['voice1.ogg', 0],
  ['voice2.ogg', 140],
  ['voice3.ogg', 311],
  ['voice4.ogg', 576],
  ['voice5.ogg', 715],
]

export const FPS = 30
const C = { bg: '#050708', sand: '#f3c27b', cyan: '#28d2ff', red: '#ff5a36', text: '#f4efe6', dim: '#9aa3a6' }
const font = 'Inter, "Segoe UI", system-ui, sans-serif'

const sept = evidence.september_2024
const cost = evidence.human_cost.september_2024
const gate = world.modis_gate
const canada = world.registries.Canada.rate
const pct = (n: number) => `${Math.round(n * 100)}%`
const TEAM = [
  ['Marlon Bustos', 'Data & harmonization'],
  ['Abraham Chafloque', 'UX/UI & frontend'],
  ['Anthony Luzquiños', 'Backend & API'],
]

// [frames, caption]: the 30-second pitch, one entry per slide (7 slides, 900 frames), timed to the voices above.
const SCENES: [number, string][] = [
  [140, "In September 2024, Peru's fires killed nine people and left 848 homeless."],
  [68, 'Yet no one could say how unusual that was,'],
  [103, "because in 2012, NASA's fire satellites changed, and the record broke."],
  [132, 'We built NINA. It learns the conversion for each country, ecosystem and month,'],
  [133, 'giving fire managers one comparable calendar since 2000, in thirty-one countries.'],
  [139, 'Tested on years it never saw, it typically matches the new satellite within eight percent.'],
  [185, "I'm Steve, and together with Abraham and Marlon, we'd love to test NINA with CENEPRED, Peru's disaster-risk agency."],
]
export const TOTAL = SCENES.reduce((s, [f]) => s + f, 0)

export const Pitch = () => {
  let from = 0
  const slides = [Problem, Question, Break, Method, Calendar, Trust, Ask]
  return (
    <AbsoluteFill style={{ background: C.bg, color: C.text, fontFamily: font }}>
      {VOICES.map(([file, from]) => (
        <Sequence key={file} from={from}>
          <Audio src={staticFile(file)} />
        </Sequence>
      ))}
      {SCENES.map(([frames, caption], i) => {
        const Slide = slides[i],
          start = from
        from += frames
        return (
          <Sequence key={i} from={start} durationInFrames={frames}>
            <Fade>
              <Slide />
            </Fade>
            <Caption text={caption} />
          </Sequence>
        )
      })}
    </AbsoluteFill>
  )
}

// ---- Building blocks -----------------------------------------------------------------------
function Fade({ children }: { children: ReactNode }) {
  const f = useCurrentFrame()
  return <AbsoluteFill style={{ opacity: interpolate(f, [0, 8], [0, 1], { extrapolateRight: 'clamp' }) }}>{children}</AbsoluteFill>
}
function Caption({ text }: { text: string }) {
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '28px 90px 44px', textAlign: 'center', fontSize: 34, lineHeight: 1.35, background: 'linear-gradient(transparent, rgba(0,0,0,.85) 35%)' }}>
      {text}
    </div>
  )
}
function Center({ children }: { children: ReactNode }) {
  return <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 24, paddingBottom: 140 }}>{children}</AbsoluteFill>
}
function Kicker({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 28, letterSpacing: 4, textTransform: 'uppercase', color: C.sand }}>{children}</div>
}
function Big({ children, color = C.text }: { children: ReactNode; color?: string }) {
  return <div style={{ fontSize: 150, fontWeight: 700, color, lineHeight: 1 }}>{children}</div>
}
/** A still from Presentation.pdf (video/public/pdf_*), revealed left to right. */
function Wipe({ src, style }: { src: string; style: CSSProperties }) {
  const f = useCurrentFrame()
  const shown = interpolate(f, [4, 40], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  return <Img src={staticFile(src)} style={{ position: 'absolute', clipPath: `inset(0 ${100 - shown}% 0 0)`, ...style }} />
}
function useCount(to: number, frames = 45) {
  return interpolate(useCurrentFrame(), [0, frames], [0, to], { extrapolateRight: 'clamp' })
}
function Card({ children, style }: { children: ReactNode; style: CSSProperties }) {
  return <div style={{ position: 'absolute', padding: '26px 34px', background: 'rgba(5,7,8,.9)', border: `1px solid ${C.sand}`, borderRadius: 10, ...style }}>{children}</div>
}
/** Fades a card in after `delay` frames. */
function Later({ delay, children }: { delay: number; children: ReactNode }) {
  const f = useCurrentFrame()
  return <AbsoluteFill style={{ opacity: interpolate(f, [delay, delay + 10], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }}>{children}</AbsoluteFill>
}
/**
 * A Playwright recording of the app, cut into [from, to] second ranges that are played back to back and
 * stretched to fill the scene, so loading time disappears and only the actions remain.
 */
function Rec({ name, cuts }: { name: string; cuts: [number, number][] }) {
  const { durationInFrames } = useVideoConfig()
  const total = cuts.reduce((s, [a, b]) => s + b - a, 0)
  let at = 0
  return (
    <AbsoluteFill>
      {cuts.map(([a, b], i) => {
        const frames = i === cuts.length - 1 ? durationInFrames - at : Math.round(((b - a) / total) * durationInFrames)
        const start = at
        at += frames
        return (
          <Sequence key={i} from={start} durationInFrames={frames}>
            <OffthreadVideo
              src={staticFile(`rec_${name}.webm`)}
              muted
              trimBefore={Math.round(a * FPS)}
              playbackRate={((b - a) * FPS) / frames}
              style={{ width: '100%', height: '100%' }}
            />
          </Sequence>
        )
      })}
    </AbsoluteFill>
  )
}

// ---- Slides (visuals and figures from Presentation.pdf and the app's evidence files) ----------
function Problem() {
  const figure = (value: number, label: string, color: string, frames?: number) => (
    <div style={{ textAlign: 'center' }}>
      <Big color={color}>{Math.round(useCount(value, frames)).toLocaleString('en-US')}</Big>
      <div style={{ fontSize: 34 }}>{label}</div>
    </div>
  )
  return (
    <>
      {INTRO && (
        <AbsoluteFill style={{ opacity: 0.6 }}>
          <OffthreadVideo src={staticFile(INTRO)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={{ position: 'absolute', top: 36, right: 46, fontSize: 20, color: C.dim }}>Illustration · AI-generated</div>
        </AbsoluteFill>
      )}
      <Center>
        <Kicker>Peru · forest fires · September 2024</Kicker>
        <div style={{ display: 'flex', gap: 110 }}>
          {figure(cost.deaths, 'lives lost', C.red, 30)}
          {figure(cost.homeless, 'left homeless', C.sand)}
          {figure(cost.affected, 'people affected', C.text)}
        </div>
        <div style={{ fontSize: 20, color: C.dim }}>
          INDECI SINPAD · {cost.emergencies} emergencies in {cost.departments} regions
        </div>
      </Center>
    </>
  )
}

// Landing → atlas, with the question nobody could answer (slide 1).
function Question() {
  return (
    <>
      <Rec name="landing" cuts={[[1.8, 3.0], [5.7, 7.5]]} />
      <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(5,7,8,.92) 0, rgba(5,7,8,.75) 40%, transparent 62%)' }} />
      <Card style={{ top: 230, left: 70, maxWidth: 820 }}>
        <div style={{ fontSize: 22, color: C.sand, letterSpacing: 3 }}>WHAT A FIRE MANAGER NEEDS TO KNOW</div>
        <div style={{ fontSize: 64, fontWeight: 700, lineHeight: 1.1, marginTop: 8 }}>“Is this fire season normal?”</div>
      </Card>
    </>
  )
}

// The 2012 break (slide 2).
function Break() {
  return (
    <>
      <div style={{ position: 'absolute', top: 80, left: 90 }}>
        <Kicker>In 2012 the camera changed. The fire did not.</Kicker>
      </div>
      <Wipe src="pdf_break.png" style={{ top: 150, left: 90, width: 1140 }} />
      <Later delay={40}>
        <Card style={{ top: 230, right: 70, width: 620 }}>
          <div style={{ fontSize: 22, color: C.sand, letterSpacing: 3 }}>NASA FIRE SATELLITES</div>
          <div style={{ fontSize: 30, marginTop: 10 }}>MODIS · 1 km pixels · since 2000</div>
          <div style={{ fontSize: 30 }}>VIIRS · 375 m pixels · since 2012</div>
          <div style={{ fontSize: 26, color: C.red, marginTop: 14 }}>3 to 5× more hotspots on the very same fires</div>
        </Card>
      </Later>
    </>
  )
}

// Lab: the harmonized series against one observer, with the three steps of the method (slide 4).
function Method() {
  const f = useCurrentFrame()
  const steps = [
    'Same ruler: 5 km² cells burning each day, not pixels',
    'Learned conversion for each country, ecosystem and month',
    'Honest gaps: a day without data stays blank, never zero',
  ]
  return (
    <>
      <Rec name="lab" cuts={[[3.4, 8.9]]} />
      <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(5,7,8,.95) 0, rgba(5,7,8,.85) 36%, transparent 55%)' }} />
      <div style={{ position: 'absolute', top: 300, left: 70, width: 620, display: 'grid', gap: 16 }}>
        <div style={{ fontSize: 60, fontWeight: 700 }}>
          NINA <span style={{ fontSize: 28, color: C.sand, fontWeight: 400 }}>the memory of fire</span>
        </div>
        {steps.map((t, i) => (
          <div
            key={t}
            style={{
              padding: '16px 20px',
              border: `1px solid ${C.sand}`,
              borderRadius: 10,
              background: 'rgba(5,7,8,.9)',
              fontSize: 25,
              opacity: interpolate(f, [12 + i * 14, 24 + i * 14], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }),
            }}
          >
            <span style={{ color: C.red, fontWeight: 700, marginRight: 12 }}>{i + 1}</span>
            {t}
          </div>
        ))}
      </div>
    </>
  )
}

// Calendar: one comparable record since 2000, in 31 countries (slides 4 and 7).
function Calendar() {
  return (
    <>
      <Rec name="calendar" cuts={[[1.5, 5.9]]} />
      <Card style={{ top: 170, right: 70, textAlign: 'right' }}>
        <div style={{ fontSize: 22, color: C.sand, letterSpacing: 3 }}>ONE COMPARABLE CALENDAR</div>
        <div style={{ fontSize: 86, fontWeight: 700, color: C.cyan, lineHeight: 1.05 }}>since 2000</div>
        <div style={{ fontSize: 86, fontWeight: 700, color: C.sand, lineHeight: 1.05 }}>{world.countries} countries</div>
        <div style={{ fontSize: 24, marginTop: 8 }}>~{pct(world.archive_share)} of NASA's fire detections</div>
      </Card>
      <Later delay={70}>
        <Card style={{ left: 70, bottom: 150 }}>
          <div style={{ fontSize: 80, fontWeight: 700, color: C.sand, lineHeight: 1 }}>
            #{sept.rank_2003_2025} of {sept.years_compared}
          </div>
          <div style={{ fontSize: 26, marginTop: 8 }}>September 2024: the most fire since 2003</div>
        </Card>
      </Later>
    </>
  )
}

// Why trust it (slide 6): the old satellite converted by NINA against what the new one saw.
function Trust() {
  return (
    <AbsoluteFill style={{ background: '#f4efe6' }}>
      <Wipe src="pdf_trust.png" style={{ top: 110, left: 70, width: 1150 }} />
      <div style={{ position: 'absolute', top: 150, right: 90, width: 540, color: '#1d2a2c' }}>
        {/* Presentation.pdf, slide 6: each year checked with a conversion that never used it. */}
        <div style={{ fontSize: 130, fontWeight: 700, color: '#e8562a', lineHeight: 1 }}>8%</div>
        <div style={{ fontSize: 26 }}>typical difference from the new satellite, on years the conversion never saw</div>
        <div style={{ fontSize: 96, fontWeight: 700, color: '#e8562a', lineHeight: 1, marginTop: 26 }}>{pct(canada)}</div>
        <div style={{ fontSize: 26 }}>of Canada's large recorded wildfires also found</div>
        <div style={{ fontSize: 20, color: '#6b7376', marginTop: 18 }}>
          {gate.passed} of {gate.evaluable} country–ecosystem tests pass · {world.countries} countries
        </div>
      </div>
    </AbsoluteFill>
  )
}

// The team over the area drawing, then the ask: a pilot with CENEPRED.
function Ask() {
  const f = useCurrentFrame()
  return (
    <>
      <Sequence durationInFrames={95}>
        <Rec name="polygon" cuts={[[3.6, 6.5], [8.4, 9.6]]} />
        <div style={{ position: 'absolute', left: 70, right: 70, bottom: 150, display: 'flex', gap: 24, justifyContent: 'center' }}>
          {TEAM.map(([name, role], i) => (
            <div
              key={name}
              style={{
                width: 400,
                padding: '20px 24px',
                background: 'rgba(5,7,8,.9)',
                border: `1px solid ${C.sand}`,
                borderRadius: 10,
                textAlign: 'center',
                opacity: interpolate(f, [8 + i * 8, 20 + i * 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }),
              }}
            >
              <div style={{ fontSize: 32, fontWeight: 700 }}>{name}</div>
              <div style={{ fontSize: 22, color: C.sand, marginTop: 4 }}>{role}</div>
            </div>
          ))}
        </div>
      </Sequence>
      <Sequence from={95}>
        <Rec name="countries" cuts={[[2.4, 3.8], [9.2, 10.8]]} />
        <AbsoluteFill style={{ background: 'rgba(5,7,8,.6)' }} />
        <Center>
          <Card style={{ position: 'relative', textAlign: 'center', padding: '34px 54px' }}>
            <div style={{ fontSize: 24, color: C.sand, letterSpacing: 4 }}>NEXT</div>
            <div style={{ fontSize: 76, fontWeight: 700 }}>A pilot with CENEPRED</div>
            <div style={{ fontSize: 26, color: C.dim, marginTop: 6 }}>Peru's disaster-risk agency</div>
          </Card>
          <div style={{ fontSize: 32, fontWeight: 700, marginTop: 6 }}>
            Satellites will keep changing. The memory of fire must not.
          </div>
          <div style={{ fontSize: 20, color: C.dim }}>NINA · Data: NASA FIRMS (MODIS C6.1, VIIRS 375 m C2)</div>
        </Center>
      </Sequence>
    </>
  )
}

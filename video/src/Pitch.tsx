import type { CSSProperties, ReactNode } from 'react'
import {
  AbsoluteFill,
  Audio,
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

// Files in video/public/. intro is the ComfyUI clip; rec_*.webm come from record/record.mjs (Playwright).
const INTRO: string | null = 'intro.webm'
const VOICE: string | null = null // e.g. 'voice.mp3'

export const FPS = 30
const C = { bg: '#050708', sand: '#f3c27b', cyan: '#28d2ff', red: '#ff5a36', text: '#f4efe6', dim: '#9aa3a6' }
const font = 'Inter, "Segoe UI", system-ui, sans-serif'

const jump = evidence.september_mean_ratio_2012_2023_vs_2003_2011
const sept = evidence.september_2024
const r = evidence.inpe_agreement.annual_pearson_2012_2025
const top3 = [...evidence.detected_vs_reported.departments_2024]
  .sort((a, b) => b.detected_share - a.detected_share)
  .slice(0, 3)
const pct = (n: number) => `${Math.round(n * 100)}%`
const detected = pct(top3.reduce((s, d) => s + d.detected_share, 0))
const reported = pct(top3.reduce((s, d) => s + d.reported_share, 0))
const TEAM = [
  ['Marlon Bustos', 'Data & harmonization'],
  ['Abraham Chafloque', 'UX/UI & frontend'],
  ['Steve Luzquiños', 'Backend & API'],
]

// [frames, caption]: the 30-second pitch, one entry per slide (7 slides, 900 frames).
const SCENES: [number, string][] = [
  [105, "In 2024, fire reached 22 of Peru's 25 departments,"],
  [120, `but its satellite record broke: a new sensor in 2012 made detections jump ×${jump.raw_pixels.toFixed(1)}.`],
  [105, 'For the Harmonization of MODIS and VIIRS Hot Spots challenge, we wanted one record planners can trust.'],
  [165, 'NINA merges 25 years into one consistent series, and shows where fire burns unreported.'],
  [120, `Built on NASA FIRMS and tested in five countries, it matches Brazil's INPE record at r = ${r.toFixed(2)}.`],
  [120, "Marlon's data science, Abraham's design and Steve's engineering turn the science into a tool."],
  [165, 'It shows September 2024 as a record five days before the emergency decree. Next: a CENEPRED pilot and publishing the method.'],
]
export const TOTAL = SCENES.reduce((s, [f]) => s + f, 0)

export const Pitch = () => {
  let from = 0
  const slides = [Problem, Break, Challenge, Solution, Validation, Team, Impact]
  return (
    <AbsoluteFill style={{ background: C.bg, color: C.text, fontFamily: font }}>
      {VOICE && <Audio src={staticFile(VOICE)} />}
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
    <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '28px 160px 44px', textAlign: 'center', fontSize: 34, lineHeight: 1.35, background: 'linear-gradient(transparent, rgba(0,0,0,.85) 35%)' }}>
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

// ---- Slides --------------------------------------------------------------------------------
function Problem() {
  return (
    <>
      {INTRO && (
        <AbsoluteFill style={{ opacity: 0.75 }}>
          <OffthreadVideo src={staticFile(INTRO)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={{ position: 'absolute', top: 36, right: 46, fontSize: 20, color: C.dim }}>Illustration · AI-generated</div>
        </AbsoluteFill>
      )}
      <Center>
        <Kicker>Peru · 2024</Kicker>
        <Big color={C.red}>{Math.round(useCount(22))} / 25</Big>
        <div style={{ fontSize: 40 }}>departments with fire activity</div>
      </Center>
    </>
  )
}

function Break() {
  const f = useCurrentFrame(),
    { fps } = useVideoConfig(),
    grow = spring({ frame: f, fps, config: { damping: 18 } }),
    bar = (ratio: number, color: string, label: string) => (
      <div style={{ display: 'flex', alignItems: 'center', gap: 30 }}>
        <div style={{ width: 360, fontSize: 32, textAlign: 'right' }}>{label}</div>
        <div style={{ height: 70, width: grow * ratio * 230, background: color, borderRadius: 6 }} />
        <div style={{ fontSize: 56, fontWeight: 700, color }}>×{ratio.toFixed(ratio < 2 ? 2 : 1)}</div>
      </div>
    )
  return (
    <Center>
      <Kicker>Peru · September, 2012–2023 vs 2003–2011</Kicker>
      {bar(jump.raw_pixels, C.red, 'Raw detections')}
      {bar(jump.harmonized, C.cyan, 'Harmonized (NINA)')}
      <div style={{ marginTop: 30, fontSize: 30, color: C.dim, opacity: interpolate(f, [60, 80], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }}>
        A change of instrument, not of fire
      </div>
    </Center>
  )
}

// Landing → atlas, with the challenge as a title card.
function Challenge() {
  return (
    <>
      <Rec name="landing" cuts={[[1.8, 3.0], [5.7, 7.5]]} />
      <Card style={{ top: 170, left: 70, maxWidth: 820 }}>
        <div style={{ fontSize: 22, color: C.sand, letterSpacing: 3 }}>NASA SPACE APPS CHALLENGE 2026</div>
        <div style={{ fontSize: 50, fontWeight: 700, lineHeight: 1.1, marginTop: 8 }}>Harmonization of MODIS and VIIRS Hot Spots</div>
      </Card>
    </>
  )
}

// Lab: harmonized series (cyan) against NOAA-20 (red), divider dragged; then detected vs reported.
function Solution() {
  return (
    <>
      <Rec name="lab" cuts={[[3.4, 8.9]]} />
      <Later delay={75}>
        <Card style={{ top: 170, right: 70, textAlign: 'right' }}>
          <div style={{ fontSize: 22, color: C.sand, letterSpacing: 3 }}>DETECTED IS NOT REPORTED · 2024</div>
          <div style={{ fontSize: 76, fontWeight: 700 }}>
            <span style={{ color: C.cyan }}>{detected}</span> <span style={{ fontSize: 40, color: C.dim }}>vs</span>{' '}
            <span style={{ color: C.red }}>{reported}</span>
          </div>
          <div style={{ fontSize: 24, maxWidth: 560 }}>
            of Peru's detected fire activity vs of reported emergencies, in Ucayali, San Martín and Loreto
          </div>
        </Card>
      </Later>
    </>
  )
}

// Any country: Peru → Brazil → Peru, with the independent check.
function Validation() {
  return (
    <>
      <Rec name="countries" cuts={[[3.4, 4.6], [8.2, 9.6], [10.6, 12.4]]} />
      <Card style={{ top: 170, right: 70, textAlign: 'right' }}>
        <div style={{ fontSize: 22, color: C.sand, letterSpacing: 3 }}>INDEPENDENT CHECK · 2012–2025</div>
        <div style={{ fontSize: 90, fontWeight: 700, color: C.cyan, lineHeight: 1.05 }}>r = {useCount(r).toFixed(2)}</div>
        <div style={{ fontSize: 24 }}>NINA vs INPE Programa Queimadas</div>
        <div style={{ fontSize: 20, color: C.dim, marginTop: 6 }}>Tested in Peru, Brazil, Australia, Indonesia and the USA</div>
      </Card>
    </>
  )
}

// Drawing a custom area, with the team on screen.
function Team() {
  const f = useCurrentFrame()
  return (
    <>
      <Rec name="polygon" cuts={[[3.6, 7.1], [8.0, 9.6]]} />
      <div style={{ position: 'absolute', left: 70, right: 70, bottom: 150, display: 'flex', gap: 24, justifyContent: 'center' }}>
        {TEAM.map(([name, role], i) => (
          <div key={name} style={{ width: 400, padding: '20px 24px', background: 'rgba(5,7,8,.9)', border: `1px solid ${C.sand}`, borderRadius: 10, textAlign: 'center', opacity: interpolate(f, [10 + i * 8, 22 + i * 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) }}>
            <div style={{ fontSize: 32, fontWeight: 700 }}>{name}</div>
            <div style={{ fontSize: 22, color: C.sand, marginTop: 4 }}>{role}</div>
          </div>
        ))}
      </div>
    </>
  )
}

// Calendar: sweep along 2024 to the record September.
function Impact() {
  return (
    <>
      <Rec name="calendar" cuts={[[1.5, 5.9]]} />
      <Later delay={70}>
        <Card style={{ left: 70, bottom: 150 }}>
          <div style={{ fontSize: 90, fontWeight: 700, color: C.sand, lineHeight: 1 }}>
            #{sept.rank_2003_2025} of {sept.years_compared}
          </div>
          <div style={{ fontSize: 28, marginTop: 8 }}>September 2024 · record 5 days before the emergency decree</div>
          <div style={{ fontSize: 26, color: C.cyan, marginTop: 14 }}>Next: CENEPRED pilot · publish the method</div>
          <div style={{ fontSize: 18, color: C.dim, marginTop: 12 }}>Data: NASA FIRMS (MODIS C6.1, VIIRS 375 m C2)</div>
        </Card>
      </Later>
    </>
  )
}

// Landing scene performance test (src/landing/scene.ts).
// Paste into the DevTools console on the landing page (http://127.0.0.1:8000/) and await the result.
// It times every draw() call (script + canvas command recording) while scrolling world → Peru → indicators.
// Use DevTools > Performance > CPU 4x/6x slowdown to emulate the slow environments.
// A frame budget of 16.7 ms is 60 fps; draw() above ~8 ms leaves no room for raster/compositing.
;(async (steps = 24, framesPerStep = 12) => {
  const raf = window.requestAnimationFrame
  const samples = []
  let phase = 'idle'
  window.requestAnimationFrame = (cb) =>
    raf((now) => {
      const t = performance.now()
      cb(now)
      samples.push({ phase, ms: performance.now() - t })
    })
  const frames = (n) => new Promise((r) => { let k = 0; const f = () => (++k >= n ? r() : raf(f)); raf(f) })
  const top = (id) => document.getElementById(id).getBoundingClientRect().top + scrollY
  const peru = top('landing-peru'), impact = document.querySelector('.landing-impact')
  const end = impact ? impact.getBoundingClientRect().top + scrollY : peru + innerHeight
  scrollTo(0, 0)
  await frames(30)
  for (let i = 0; i <= steps; i++) {
    const y = (end * i) / steps
    phase = y < peru - innerHeight * 1.6 ? 'world' : y < peru ? 'morph' : 'peru'
    scrollTo(0, y)
    await frames(framesPerStep)
  }
  window.requestAnimationFrame = raf
  const stat = (xs) => {
    const s = xs.map((x) => x.ms).sort((a, b) => a - b)
    return { frames: s.length, median: +s[s.length >> 1].toFixed(2), p95: +s[Math.floor(s.length * 0.95)].toFixed(2), max: +s.at(-1).toFixed(2) }
  }
  const out = {}
  for (const p of ['world', 'morph', 'peru']) {
    const xs = samples.filter((x) => x.phase === p)
    if (xs.length) out[p] = stat(xs)
  }
  const c = document.querySelector('.landing-canvas')
  out.canvas = `${c.width}×${c.height} @dpr ${devicePixelRatio}`
  console.table(out)
  return out
})()

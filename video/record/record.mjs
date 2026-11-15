// Records real use of NINA (local server at :8000) into video/public/rec_<name>.webm,
// plus record/marks.json with the second at which each step happened, for trimming in Remotion.
import fs from 'node:fs'
import { chromium } from 'playwright'

const BASE = 'http://127.0.0.1:8000'
const W = 1920,
  H = 1080
const link = (s) => `${BASE}/?s=${encodeURIComponent(JSON.stringify(s))}`
const only = process.argv.slice(2)

// Playwright videos do not show the mouse: draw one, with a ring on every click.
const CURSOR = `
addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div')
  c.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M4 2l16 10-7 1.5L9.5 21z" fill="#fff" stroke="#000" stroke-width="1.4"/></svg>'
  Object.assign(c.style, { position: 'fixed', left: '-50px', top: '-50px', zIndex: 2147483647, pointerEvents: 'none', transform: 'translate(-3px,-2px)', filter: 'drop-shadow(0 2px 4px #0008)' })
  document.body.appendChild(c)
  addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px' }, true)
  addEventListener('mousedown', (e) => {
    const r = document.createElement('div')
    Object.assign(r.style, { position: 'fixed', left: e.clientX - 22 + 'px', top: e.clientY - 22 + 'px', width: '44px', height: '44px', borderRadius: '50%', border: '3px solid #f3c27b', zIndex: 2147483646, pointerEvents: 'none', transition: 'transform .45s ease-out, opacity .45s ease-out' })
    document.body.appendChild(r)
    requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0' })
    setTimeout(() => r.remove(), 600)
  }, true)
})`

const ready = (page) =>
  page.waitForFunction(() => /on screen/.test(document.querySelector('.map-data-note')?.textContent || ''), null, { timeout: 180000 })

async function glide(page, from, to, steps = 25) {
  await page.mouse.move(...from)
  await page.mouse.move(...to, { steps })
}
async function moveTo(page, selector) {
  const b = await page.locator(selector).first().boundingBox()
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 20 })
}

const CLIPS = {
  // Landing → atlas.
  async landing(page, mark) {
    await page.goto(BASE + '/')
    await page.waitForTimeout(1500)
    mark('start')
    await glide(page, [960, 900], [960, 700])
    await moveTo(page, '.landing-cta')
    await page.waitForTimeout(300)
    mark('click')
    await page.locator('.landing-cta').first().click()
    await ready(page)
    mark('ready')
    await page.waitForTimeout(2000)
  },
  // Choosing territories: Brazil, then back to Peru.
  async countries(page, mark) {
    await page.goto(link({ place: 'PER', tab: 'atlas' }))
    await ready(page)
    await page.waitForTimeout(1000)
    mark('start')
    const territory = 'select[aria-label="Territory"]'
    for (const label of ['Brazil', 'Peru · historical archive']) {
      await moveTo(page, territory)
      await page.mouse.down()
      await page.mouse.up()
      await page.selectOption(territory, { label })
      mark('select:' + label)
      await page.waitForTimeout(500)
      await ready(page)
      mark('ready:' + label)
      await page.waitForTimeout(2200)
    }
  },
  // Lab: drag the divider between the harmonized series and NOAA-20.
  async lab(page, mark) {
    await page.goto(link({ selection: { scope: 'PER', source: 'viirs-jpss1', platform: 'all', year_start: 2025, year_end: 2026, selected_year: 2026, selected_month: 7 }, place: 'PER', tab: 'lab' }))
    await page.waitForFunction(() => /detections/.test(document.querySelector('.sensor-tag.right')?.textContent || ''), null, { timeout: 180000 })
    await page.waitForTimeout(1500)
    mark('start')
    const b = await page.locator('.comparison-seam button').boundingBox()
    const x = b.x + b.width / 2,
      y = b.y + b.height / 2
    await page.mouse.move(x - 200, y + 120)
    await page.mouse.move(x, y, { steps: 15 })
    await page.mouse.down()
    await page.mouse.move(x - 380, y, { steps: 45 })
    await page.mouse.move(x + 380, y, { steps: 70 })
    await page.mouse.move(x, y, { steps: 40 })
    await page.mouse.up()
    mark('end')
    await page.waitForTimeout(800)
  },
  // Drawing a custom area around the central Peruvian hot spots.
  async polygon(page, mark) {
    await page.goto(link({ place: 'PER', tab: 'atlas' }))
    await ready(page)
    await page.waitForTimeout(1000)
    mark('start')
    await moveTo(page, '[aria-label="Draw an area"]')
    await page.locator('[aria-label="Draw an area"]').click()
    await page.waitForTimeout(400)
    const pts = [[850, 350], [1060, 420], [1090, 700], [900, 730], [790, 520], [850, 350]]
    for (const [px, py] of pts) {
      await page.mouse.move(px, py, { steps: 18 })
      await page.mouse.click(px, py)
      await page.waitForTimeout(250)
    }
    mark('closed')
    await ready(page)
    mark('ready')
    await page.waitForTimeout(2500)
  },
  // Calendar: run the cursor along 2024 to the record September, then open it on the map.
  async calendar(page, mark) {
    await page.goto(link({ selection: { scope: 'PER', source: 'harmonized', platform: 'all', year_start: 2003, year_end: 2025, selected_year: 2024, selected_month: 9 }, place: 'PER', tab: 'calendar' }))
    await page.waitForFunction(() => document.body.innerText.includes('20,909'), null, { timeout: 180000 })
    await page.waitForTimeout(1200)
    mark('start')
    const cell = page.locator('td button[aria-label^="Sep 2024"], td button[aria-label^="September 2024"]').first()
    const jan = await page.locator('td button[aria-label^="Jan 2024"], td button[aria-label^="January 2024"]').first().boundingBox()
    const b = await cell.boundingBox()
    await page.mouse.move(jan.x + jan.width / 2, jan.y + jan.height / 2, { steps: 15 })
    // A visible sweep along 2024 (about 1.5 s) instead of an instant jump.
    for (let i = 1; i <= 50; i++) {
      const k = i / 50
      await page.mouse.move(jan.x + jan.width / 2 + (b.x - jan.x) * k, b.y + b.height / 2)
      await page.waitForTimeout(30)
    }
    mark('september')
    await page.waitForTimeout(1500)
    await cell.click()
    await page.waitForTimeout(1200)
    mark('end')
  },
}

const marks = fs.existsSync('record/marks.json') ? JSON.parse(fs.readFileSync('record/marks.json', 'utf8')) : {}
const browser = await chromium.launch({ headless: false, args: [`--window-size=${W},${H + 140}`] })
for (const [name, run] of Object.entries(CLIPS)) {
  if (only.length && !only.includes(name)) continue
  const context = await browser.newContext({
    viewport: { width: W, height: H },
    recordVideo: { dir: 'record/raw', size: { width: W, height: H } },
    reducedMotion: 'no-preference',
  })
  await context.addInitScript(CURSOR)
  const page = await context.newPage()
  const t0 = Date.now(),
    m = {}
  await run(page, (k) => (m[k] = +((Date.now() - t0) / 1000).toFixed(2)))
  const video = page.video()
  await context.close()
  fs.copyFileSync(await video.path(), `public/rec_${name}.webm`)
  marks[name] = m
  console.log(name, JSON.stringify(m))
}
await browser.close()
fs.writeFileSync('record/marks.json', JSON.stringify(marks, null, 2))

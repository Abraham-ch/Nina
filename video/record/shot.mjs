// Dry run: one 1920x1080 screenshot of a view, to pick coordinates for the recorder.
import { chromium } from 'playwright'

const [url, out] = process.argv.slice(2)
const browser = await chromium.launch({ headless: false, args: ['--window-size=1920,1200'] })
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, reducedMotion: 'no-preference' })
await page.goto(url)
await page.waitForFunction(() => /on screen/.test(document.querySelector('.map-data-note')?.textContent || ''), null, { timeout: 120000 })
await page.waitForTimeout(2500)
await page.screenshot({ path: out })
await browser.close()

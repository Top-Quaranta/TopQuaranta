/**
 * Accessibility audit of /staff/* pages.
 *
 * Authenticates via a pre-minted Django session cookie
 * (SESSION_ID env var, see /tmp/axe/staff_session.py for how to
 * mint one). Iterates the staff routes, runs axe-core, and reports
 * violations. Same WCAG tags as the public audit (run.js).
 */
const puppeteer = require('puppeteer')
const { AxePuppeteer } = require('@axe-core/puppeteer')

const SESSION_ID = process.env.SESSION_ID
if (!SESSION_ID) {
  console.error('Set SESSION_ID env var')
  process.exit(1)
}

const URLS = [
  '/staff',
  '/staff/pendents',
  '/staff/artistes',
  '/staff/cancons',
  '/staff/albums',
  '/staff/top',
  '/staff/propostes',
  '/staff/solicituds',
  '/staff/senyal',
  '/staff/historial',
  '/staff/configuracio',
  '/staff/auditlog',
  '/staff/usuaris',
  '/staff/feedback',
  '/staff/social',
  '/staff/estat',
  '/staff/publicacions',
]

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium-browser',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900 })
  await page.setCookie({
    name: 'sessionid',
    value: SESSION_ID,
    domain: 'www.topquaranta.cat',
    path: '/',
    secure: true,
    httpOnly: true,
  })

  let totalViolations = 0
  const summary = {}

  for (const path of URLS) {
    const url = `https://www.topquaranta.cat${path}`
    try {
      await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 })
    } catch (e) {
      console.log(`\n=== ${path} ===\n  LOAD FAILED: ${e.message}`)
      continue
    }
    // Give the SPA a beat to fetch + render the data-driven content.
    await new Promise(r => setTimeout(r, 1500))

    const r = await new AxePuppeteer(page)
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()

    console.log(`\n=== ${path} ===`)
    console.log(`  violations: ${r.violations.length}`)
    totalViolations += r.violations.length
    for (const v of r.violations) {
      console.log(`  [${v.impact}] ${v.id}  (${v.help})`)
      console.log(`    nodes: ${v.nodes.length}`)
      summary[v.id] = (summary[v.id] || 0) + v.nodes.length
      for (const n of v.nodes.slice(0, 4)) {
        console.log(`    · ${n.target.join(' ')}`)
        if (n.failureSummary) {
          console.log(`      ${n.failureSummary.split('\n')[0]}`)
        }
      }
    }
  }

  console.log('\n=== Resum global ===')
  console.log(`  violacions totals (suma per pàgina): ${totalViolations}`)
  for (const [id, n] of Object.entries(summary).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${id}: ${n} nodes`)
  }

  await browser.close()
})()

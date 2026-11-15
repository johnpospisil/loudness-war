// P22 browser smoke test for the "How loud is my album?" app and the site around it.
// Serve docs/ first (`python3 -m http.server 8765 -d docs`), then run with the Playwright
// skill runner: node run.js app/tests/smoke.js. Env: SITE_URL, HEADLESS=1, SHOT=<png path>.
const { chromium } = require("playwright");

const SITE = process.env.SITE_URL || "http://127.0.0.1:8765";
const SHOT = process.env.SHOT || "figures/p22_app_screenshot.png";
const fails = [];
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"}  ${msg}`); if (!ok) fails.push(msg); };

(async () => {
  const browser = await chromium.launch({ headless: process.env.HEADLESS === "1" });
  const page = await browser.newPage({ viewport: { width: 1100, height: 1500 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  // 1. app loads the catalogue
  const t0 = Date.now();
  await page.goto(`${SITE}/app/`);
  await page.waitForFunction(() => !document.getElementById("q").disabled, null, { timeout: 90000 });
  check(true, `catalogue loaded in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  const n = await page.textContent("#n-albums");
  check(/^\d{3},\d{3}$/.test(n.trim()), `album count shown (${n})`);

  // 2. search
  await page.fill("#q", "californication");
  await page.press("#q", "Enter");
  await page.waitForSelector("#results li");
  const first = await page.textContent("#results li .r-title");
  check(first.trim() === "Californication", `top result is Californication (${first})`);

  // accent-insensitive search
  await page.fill("#q", "bjork homogenic");
  await page.press("#q", "Enter");
  const bj = await page.waitForSelector('#results li .r-sub:has-text("Björk")', { timeout: 10000 }).catch(() => null);
  check(bj !== null, "accent-free query finds Björk");

  // empty result gives directions
  await page.fill("#q", "zzqqxx nonexistent album");
  await page.press("#q", "Enter");
  await page.waitForFunction(() => document.getElementById("status").textContent.startsWith("No albums"));
  check(true, "no-match message shown");

  // 3. open an album
  await page.fill("#q", "californication");
  await page.press("#q", "Enter");
  await page.waitForSelector("#results li");
  await page.click("#results li button");
  await page.waitForSelector("#album:not([hidden])");
  const lufs = await page.textContent("#a-lufs");
  const verdict = await page.textContent("#a-lufs-text");
  check(/^−\d+\.\d$/.test(lufs), `loudness shown (${lufs})`);
  check(/^Louder than (over |under )?\d+% of albums released 1997–2001/.test(verdict), `verdict: ${verdict}`);
  check((await page.locator("#m-svg rect.bar").count()) > 40, "meter histogram drawn");
  check((await page.locator("#m-svg rect.bar.mine").count()) === 1, "album's bin highlighted");
  check((await page.locator("#t-svg circle.dot").count()) === 1, "album dot on the trend chart");
  const hash = new URL(page.url()).hash;
  check(/^#[0-9a-f-]{36}$/.test(hash), `deep-link hash set (${hash})`);
  await page.screenshot({ path: SHOT, fullPage: true });
  console.log(`screenshot: ${SHOT}`);

  // 4. toggles
  const capAll = await page.textContent("#m-caption");
  await page.click("#t-genre");
  const capGenre = await page.textContent("#m-caption");
  check(capAll !== capGenre && /rock albums/.test(capGenre), `genre toggle (${capGenre})`);
  await page.click('[data-metric="lra"]');
  check((await page.textContent("#m-caption")).includes("loudness range"), "loudness-range toggle");

  // 5. deep link in a fresh page
  const p2 = await browser.newPage();
  await p2.goto(`${SITE}/app/${hash}`);
  await p2.waitForSelector("#album:not([hidden])", { timeout: 90000 });
  check((await p2.textContent("#a-title")) === "Californication", "deep link opens the album");

  // 6. mobile width: no horizontal scroll
  await p2.setViewportSize({ width: 375, height: 800 });
  const overflow = await p2.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check(overflow <= 0, `no horizontal scroll at 375 px (overflow ${overflow})`);
  await p2.screenshot({ path: SHOT.replace(".png", "_mobile.png"), fullPage: true });

  // 7. article links to the app and the interactive chart
  await p2.setViewportSize({ width: 1100, height: 900 });
  await p2.goto(`${SITE}/`);
  for (const href of ["app/index.html", "figures/final_hero_lufs.html"]) {
    const r = await p2.request.get(`${SITE}/${href}`);
    check((await p2.locator(`a[href="${href}"]`).count()) > 0 && r.ok(), `article links to ${href}`);
  }

  check(errors.length === 0, `no page errors (${errors.join(" | ")})`);
  await browser.close();
  console.log(fails.length ? `\n${fails.length} FAILED` : "\nALL PASSED");
  process.exit(fails.length ? 1 : 0);
})();

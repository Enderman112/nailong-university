#!/usr/bin/env node
/**
 * 站点自检：真实 Chromium 里渲染两个页面，验证
 *   1. 每张图真的解码成功（不是 404，也不是 0 字节）
 *   2. 没有 console 报错 / 加载失败的请求
 *   3. 主页面（不带 ?stay）在等待若干秒后，真的跳到了目标网址
 *   4. 顺带截图（桌面 / 手机 / 深色）存到 shots/
 *
 *   node tools/check-site.mjs                          # 默认 http://127.0.0.1:8791/
 *   node tools/check-site.mjs https://xn--xxx.org/
 *   node tools/check-site.mjs http://127.0.0.1:8791/ --expect https://www.example.edu.cn/
 *
 * 需要 playwright：npm i -D playwright && npx playwright install chromium
 */
import { mkdirSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { createRequire } from 'node:module';

const args = process.argv.slice(2);
const base = (args.find(a => !a.startsWith('--')) || 'http://127.0.0.1:8791/').replace(/\/?$/, '/');
const expectIdx = args.indexOf('--expect');
const expectArg = expectIdx >= 0 ? args[expectIdx + 1] : null;

async function loadPlaywright() {
  const req = createRequire(import.meta.url);
  const tries = ['playwright', 'playwright-core'];
  try {
    const root = execSync('npm root -g', { encoding: 'utf8' }).trim();
    tries.push(`${root}/playwright`);
  } catch { /* npm 不可用就算了 */ }
  for (const t of tries) {
    try { return req(t); } catch { /* 继续试 */ }
  }
  console.error('找不到 playwright。先跑：npm i -D playwright && npx playwright install chromium');
  process.exit(2);
}

const { chromium } = await loadPlaywright();
const fails = [];
const ok = m => console.log('  \u2713 ' + m);
const bad = m => { fails.push(m); console.log('  \u2717 ' + m); };

mkdirSync('shots', { recursive: true });
const browser = await chromium.launch();

async function render(name, url, { width = 900, height = 760, dark = false, wait = 1300 } = {}) {
  console.log(`\n[${name}] ${url}`);
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 2, colorScheme: dark ? 'dark' : 'light' });
  const page = await ctx.newPage();
  const errors = [];
  // 页面到点会自己跳到学校官网；跳走之后的报错是对方站点的，不能算我们头上。
  // 用 framenavigated 盯着「还在不在我们这」，离开就把耳朵闭上。
  let onOurSite = true;
  const ourOrigin = new URL(base).origin;
  page.on('framenavigated', f => {
    if (f === page.mainFrame()) onOurSite = f.url().startsWith(ourOrigin);
  });
  page.on('pageerror', e => { if (onOurSite) errors.push('pageerror: ' + e.message); });
  page.on('console', m => { if (onOurSite && m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('requestfailed', r => { if (onOurSite) errors.push('requestfailed: ' + r.url()); });

  const resp = await page.goto(url, { waitUntil: 'load' });
  if (!resp || resp.status() !== 200) bad(`HTTP ${resp && resp.status()}（期望 200，若为 301 说明旧的跳转还没拆）`);
  else ok('HTTP 200');

  const h1 = (await page.textContent('h1').catch(() => '') || '').trim();
  if (h1) ok(`h1 = ${h1}`); else bad('找不到 h1');

  const imgs = await page.$$eval('img', as => as.map(i => ({ src: i.getAttribute('src'), w: i.naturalWidth, h: i.naturalHeight })));
  if (!imgs.length) bad('页面里没有任何 <img>');
  for (const i of imgs) {
    if (i.w > 0 && i.h > 0) ok(`${i.src}  ${i.w}x${i.h}`);
    else bad(`${i.src} 没解码成功（naturalWidth=0，通常是 404 或路径不对；注意资源是绝对路径 /xxx，必须部署在根目录）`);
  }

  // 「关于」弹窗要在离场动画开始前测：进入 leaving 之后再点，按设计就是打不开的
  const hasAbout = await page.$('#about-btn');
  if (hasAbout && wait < 2600) {
    await page.click('#about-btn');
    await page.waitForTimeout(400);
    const dlg = await page.$('#about[open]');
    if (dlg) ok('「关于」弹窗能打开（打开时会暂停倒计时）'); else bad('点了「关于」却没打开');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  }

  await page.waitForTimeout(wait);
  await page.screenshot({ path: `shots/${name}.png`, fullPage: false });
  if (errors.length) errors.forEach(e => bad(e)); else ok('无 console 报错 / 无失败请求');
  await ctx.close();
}

// 1) 主页面（演示模式，不跳走）
await render('index', base + 'index.html?stay');
await render('index-mobile', base + 'index.html?stay', { width: 390, height: 844, wait: 2600 });
await render('index-mobile-dialog', base + 'index.html?stay', { width: 390, height: 844, wait: 1200 });
await render('index-dark', base + 'index.html?stay', { dark: true });
// 2) 备选版式。首页版式可切换（见 config.json 的 homepage），另一个页面叫
//    mascot.html 或 rotate.html。**不能用 HTTP 状态码判断它存不存在**：
//    Cloudflare Pages 对任意未知路径都会回 index.html + 200，
//    所以只能比对内容 —— 和 index.html 一模一样的，就是 fallback，不是真页面。
async function findAlt() {
  const idx = await fetch(base + 'index.html').then(r => r.ok ? r.text() : '').catch(() => '');
  const tried = [];
  for (const c of ['mascot.html', 'rotate.html']) {
    const r = await fetch(base + c).catch(() => null);
    if (!r || !r.ok) { tried.push(`${c}(HTTP ${r ? r.status : '连不上'})`); continue; }
    const body = await r.text();
    if (body.trim() === idx.trim()) { tried.push(`${c}(返回的是 index 的 fallback)`); continue; }
    console.log(`\n[备选版式] ${c} ✓` + (tried.length ? `   已排除：${tried.join('、')}` : ''));
    return c;
  }
  console.log(`\n[备选版式] 没找到真页面，试过：${tried.join('、')}`);
  return null;
}

const alt = await findAlt();
if (alt) await render(alt.replace(/\.html$/, ''), base + alt, { wait: 2200 });
else bad('备选页面找不到（mascot.html / rotate.html 都只是 index 的 fallback）');

// 3) 真的会跳吗
console.log('\n[redirect] 不带 ?stay，等它自己走');
for (const file of ['index.html', ...(alt ? [alt] : [])]) {
  const ctx = await browser.newContext({ viewport: { width: 900, height: 760 } });
  const page = await ctx.newPage();
  await page.goto(base + file, { waitUntil: 'load' });
  let target = expectArg;
  if (!target) {
    const html = await page.content();
    const m = html.match(/http-equiv="refresh"\s+content="\d+;url=([^"]+)"/i)
      || html.match(/<a[^>]+href="(https?:\/\/[^"]+)"/i);
    target = m && m[1];
  }
  const before = page.url();
  await page.waitForTimeout(9000);   // 外站导航提交有延迟，等宽一点，避免误报
  const after = page.url();
  if (after !== before && target && after.startsWith(target.replace(/\/$/, ''))) ok(`${file} → ${after}`);
  else if (after !== before) ok(`${file} → ${after}（没配 --expect，跳到别处了也能接受）`);
  else bad(`${file} 9 秒后还停在 ${after}，没跳转`);
  await ctx.close();
}

await browser.close();
console.log('\n' + (fails.length ? `\u2717 ${fails.length} 项没通过:\n  - ` + fails.join('\n  - ') : '\u2713 全部通过'));
process.exit(fails.length ? 1 : 0);

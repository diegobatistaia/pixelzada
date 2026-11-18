// Modelo 3: fundo desfocado, título grande no topo, clipe inteiro (com a câmera) no meio, legenda falada embaixo.
const { chromium } = require('playwright');
const { spawnSync } = require('child_process');
const fs = require('fs');
const [,, entrada, falasJson, saida, G] = process.argv;
const F = JSON.parse(fs.readFileSync(falasJson, 'utf8'));
const VY = 656, VH = 608;
const css = `@font-face{font-family:A;font-weight:800;src:url(file://${G}/fonts/f3.ttf)}*{margin:0}body{width:1080px;height:1920px;background:transparent}
.t{position:absolute;left:50px;right:50px;bottom:${1920 - VY + 50}px;text-align:center;font-family:A;font-weight:800;color:#fff;font-size:76px;line-height:1.12;
 -webkit-text-stroke:3px #000;paint-order:stroke fill;text-shadow:0 4px 0 #000,0 0 18px rgba(0,0,0,.6)}
.f{position:absolute;left:40px;right:40px;top:${VY + VH + 150}px;text-align:center;font-family:A;font-weight:800;color:#fff;font-size:84px;
 -webkit-text-stroke:10px #000;paint-order:stroke fill;text-transform:uppercase}.f b{color:#FFD23F;font-weight:800}`;
const esc = t => String(t || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  const H = saida + '.html';
  async function png(corpo, arq, ajuste) {
    fs.writeFileSync(H, `<!doctype html><html><head><meta charset="utf-8"><style>${css}</style></head><body>${corpo}</body></html>`);
    await p.goto('file://' + H); await p.evaluate(() => document.fonts.ready);
    if (ajuste) await p.evaluate(() => { const t = document.querySelector('.t'); let s = 76; while (t.offsetHeight > 3 * s * 1.12 + 4 && s > 46) { s -= 2; t.style.fontSize = s + 'px'; } });
    await p.screenshot({ path: arq, omitBackground: true });
  }
  const tit = saida + '-t.png';
  await png(`<div class="t">${esc(F.titulo)} ${esc(F.emoji || '')}</div>`, tit, true);
  const falas = (F.falas || []).filter(x => x.texto && x.fim > x.ini);
  const pngs = [];
  for (let i = 0; i < falas.length; i++) {
    const w = esc(falas[i].texto).split(' '); const ult = w.pop();
    const arq = `${saida}-f${i}.png`; await png(`<div class="f">${w.join(' ')} <b>${ult}</b></div>`, arq); pngs.push(arq);
  }
  await b.close();
  const ins = ['-i', entrada, '-loop', '1', '-i', tit]; pngs.forEach(f => ins.push('-loop', '1', '-i', f));
  let f = `[0:v]split[a][b];[a]scale=-2:1920,crop=1080:1920,boxblur=40:2,eq=brightness=-0.12[bg];[b]scale=1080:${VH}:force_original_aspect_ratio=increase,crop=1080:${VH}[v];` +
          `[bg][v]overlay=0:${VY}[x0];[x0][1:v]overlay=0:0:shortest=1[y0]`;
  let ult = 'y0';
  falas.forEach((x, i) => { f += `;[${ult}][${i + 2}:v]overlay=0:0:shortest=1:enable='between(t,${x.ini},${x.fim})'[y${i + 1}]`; ult = `y${i + 1}`; });
  f += `;[${ult}]fps=30,format=yuv420p[o]`;
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', ...ins, '-filter_complex', f, '-map', '[o]', '-map', '0:a?', '-t', '59',
    '-c:v', 'libx264', '-crf', '20', '-preset', 'veryfast', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-shortest', saida], { encoding: 'utf8' });
  [H, tit, ...pngs].forEach(x => fs.rmSync(x, { force: true }));
  if (r.status) { console.error(r.stderr.slice(-800)); process.exit(1); }
})();

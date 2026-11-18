// Modelo 2, só o topo: repinta o cabeçalho branco + título de um Reel do modelo 2 já pronto
// (título novo pela regra de 18/11, scripts/social/titulos.py). Mesmo HTML do streamer-modelo2.js.
// Uso: node topo-modelo2.js REEL.mp4 "título" SAIDA.mp4 scripts/social/gerador
const { chromium } = require('playwright');
const { spawnSync } = require('child_process');
const [,, entrada, titulo, saida, G] = process.argv;  // G = pasta scripts/social/gerador
const TOPO = 560;
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  const H = saida + '.html'; require('fs').writeFileSync(H, `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:A;font-weight:800;src:url(file://${G}/fonts/f3.ttf)}
@font-face{font-family:B;src:url(file://${G}/fonts/f2.ttf)}
*{margin:0;box-sizing:border-box}body{width:1080px;height:1920px;background:#fff;font-family:A}
#topo{height:${TOPO}px;display:flex;flex-direction:column;justify-content:flex-end;padding:0 0 34px}
.cab{display:flex;align-items:center;gap:24px;padding:0 64px 26px}
.av{width:112px;height:112px;border-radius:50%;background:url(file://${G}/avatar.png) center/cover;box-shadow:0 0 0 3px #ECECF0}
.nm{font-weight:800;font-size:44px;color:#0B0A10;display:flex;align-items:center;gap:12px}
.px{width:14px;height:14px;background:#C6FF1A;outline:2px solid #0B0A10}.at{font-family:B;font-size:34px;color:#5B5B66;margin-top:4px}
.t{font-weight:800;font-size:56px;line-height:1.1;color:#0B0A10;text-transform:uppercase;padding:0 64px;letter-spacing:-.3px}
</style></head><body><div id="topo"><div class="cab"><div class="av"></div><div><div class="nm">Pixelzada<span class="px"></span></div><div class="at">@pixelzada.br</div></div></div>
<div class="t">${titulo}</div></div></body></html>`); await p.goto('file://' + H);
  await p.evaluate(() => document.fonts.ready);
  await p.evaluate(() => { const t = document.querySelector('.t'); let s = 56; while (t.offsetHeight > 3 * s * 1.1 + 4 && s > 38) { s -= 2; t.style.fontSize = s + 'px'; } });
  const png = saida + '.png'; await p.screenshot({ path: png }); await b.close();
  const f = `[1:v]crop=1080:${TOPO}:0:0[t];[0:v][t]overlay=0:0:shortest=1,format=yuv420p[o]`;
  const x = spawnSync('ffmpeg', ['-v', 'error', '-y', '-i', entrada, '-loop', '1', '-i', png, '-filter_complex', f, '-map', '[o]', '-map', '0:a?',
    '-c:v', 'libx264', '-crf', '20', '-preset', 'veryfast', '-c:a', 'copy', '-movflags', '+faststart', '-shortest', saida], { encoding: 'utf8' });
  require('fs').rmSync(png, { force: true }); require('fs').rmSync(H, { force: true });
  if (x.status) { console.error(x.stderr); process.exit(1); }
})();

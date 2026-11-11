// Moldura simples (teste do Diego, 11/11): fundo liso branco ou preto, cabeçalho de
// "post" (avatar + Pixelzada + @pixelzada.br), título grande em caixa alta e o vídeo
// inteiro logo abaixo, o mais largo possível. Sem CTA e sem selo de verificado.
//   estilo 'simples-branca' ou 'simples-preta' no pedido do montar.js
const { spawnSync } = require('child_process');
const fs = require('fs'), path = require('path');

const ESTILOS = { 'simples-branca': 'Simples branca', 'simples-preta': 'Simples preta' };
const TOPO = 250, BASE = 230;   // margens mínimas (interface do Reel em cima e embaixo)
const limpa = t => (Array.isArray(t) ? t[0] : t || '').replace(/<br\s*\/?>/g, ' ').replace(/<[^>]+>/g, '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/\b(GTA|Battlefield|Forza Horizon|Red Dead Redemption|Red Dead) (\d|VI|V)\b/g, m => m.replace(/ /g, ' '));

function html(estilo, titulo, vw, vh, pasta) {
  const preta = estilo === 'simples-preta';
  const bg = preta ? '#000' : '#fff', fg = preta ? '#fff' : '#0B0A10', sub = preta ? '#A9A9B3' : '#5B5B66';
  return `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:A;font-weight:800;src:url(file://${pasta}/fonts/f3.ttf)}
@font-face{font-family:B;src:url(file://${pasta}/fonts/f2.ttf)}
*{margin:0;box-sizing:border-box}
body{width:1080px;height:1920px;background:${bg};font-family:A;display:flex;flex-direction:column;justify-content:center;align-items:center;padding:${TOPO}px 0 ${BASE}px}
#topo{width:1080px}
.cab{display:flex;align-items:center;gap:26px;padding:0 70px 34px}
.av{width:132px;height:132px;border-radius:50%;flex:none;background:url(file://${pasta}/avatar.png) center/cover;box-shadow:0 0 0 3px ${preta ? '#2A2A30' : '#ECECF0'}}
.nm{font-weight:800;font-size:50px;color:${fg};display:flex;align-items:center;gap:14px;line-height:1.1}
.px{width:16px;height:16px;background:#C6FF1A;${preta ? '' : 'outline:2px solid #0B0A10;'}}
.at{font-family:B;font-size:38px;color:${sub};margin-top:6px}
.t{font-weight:800;font-size:58px;line-height:1.12;color:${fg};text-transform:uppercase;padding:0 70px 44px;letter-spacing:-.3px}
#v{background:${bg}}
</style></head><body><div id="topo">
<div class="cab"><div class="av"></div><div><div class="nm">Pixelzada<span class="px"></span></div><div class="at">@pixelzada.br</div></div></div>
<div class="t">${limpa(titulo)}</div></div><div id="v"></div>
<script>window.__monta=()=>{const t=document.querySelector('.t');let s=58;while(t.offsetHeight>5*s*1.12+50&&s>42){s-=2;t.style.fontSize=s+'px'}
const livre=1920-${TOPO}-${BASE}-document.getElementById('topo').offsetHeight;let w=1080,h=Math.round(1080*${vh}/${vw});
if(h>livre){h=livre;w=Math.round(h*${vw}/${vh})}w-=w%2;h-=h%2;const v=document.getElementById('v');v.style.width=w+'px';v.style.height=h+'px';
const r=v.getBoundingClientRect();return{x:Math.round(r.x),y:Math.round(r.y),w,h}}</script></body></html>`;
}

// p = página do Playwright; S = pasta de trabalho (com fonts/); entrada já preparada (tem áudio)
async function montarSimples(p, S, v, entrada, crop, mp4) {
  fs.copyFileSync(path.join(__dirname, 'avatar.png'), path.join(S, 'avatar.png'));
  const pagina = path.join(S, 'simples.html'), png = path.join(S, 'simples-' + Date.now() + '.png');
  fs.writeFileSync(pagina, html(v.estilo, v.titulo, crop.w, crop.h, S));
  await p.goto('file://' + pagina);
  await p.evaluate(() => document.fonts.ready);
  const r = await p.evaluate(() => window.__monta());
  await p.screenshot({ path: png });
  const f = `[0:v]crop=${crop.w}:${crop.h}:${crop.x}:${crop.y},scale=${r.w}:${r.h},setsar=1[v];[1:v][v]overlay=${r.x}:${r.y}:shortest=1,format=yuv420p,fps=30[o]`;
  const x = spawnSync('ffmpeg', ['-v', 'error', '-y', '-i', entrada, '-loop', '1', '-i', png, '-filter_complex', f,
    '-map', '[o]', '-map', '0:a', '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-c:a', 'aac', '-b:a', '160k',
    '-movflags', '+faststart', '-shortest', mp4], { encoding: 'utf8' });
  fs.rmSync(png, { force: true });
  if (x.status) throw new Error('ffmpeg simples: ' + (x.stderr || '').slice(0, 400));
  return r;
}

module.exports = { ESTILOS, montarSimples };

// 20 molduras de Reel de vídeo da Pixelzada (1080x1920).
// Zona segura: tudo importante entre y=260 e y=1580 (centro da capa 4:5 no grid e fora da interface do Reel).
let chromium; try { ({ chromium } = require('playwright')); } catch (e) { ({ chromium } = require('/opt/node-tools/node_modules/playwright')); }
const { spawnSync } = require('child_process');
const fs = require('fs'), path = require('path');
// Pasta de trabalho (fora do repositório): recebe as fontes e logos e os PNGs intermediários.
const S = process.env.GERADOR_TRABALHO || path.join(require('os').tmpdir(), 'pixelzada-gerador');
fs.mkdirSync(path.join(S, 'fonts'), { recursive: true });
for (const f of fs.readdirSync(path.join(__dirname, 'fonts'))) fs.copyFileSync(path.join(__dirname, 'fonts', f), path.join(S, 'fonts', f));
for (const f of fs.readdirSync(__dirname).filter(f => f.endsWith('.svg'))) fs.copyFileSync(path.join(__dirname, f), path.join(S, f));
const CSS = `
@font-face{font-family:Anton;src:url(fonts/f1.ttf)}
@font-face{font-family:Archivo;font-weight:700;src:url(fonts/f2.ttf)}
@font-face{font-family:Archivo;font-weight:800;src:url(fonts/f3.ttf)}
@font-face{font-family:Silkscreen;font-weight:400;src:url(fonts/f4.ttf)}
@font-face{font-family:Silkscreen;font-weight:700;src:url(fonts/f5.ttf)}
:root{--noite:#0B0A10;--carvao:#17151F;--linha:#2A2733;--lima:#C6FF1A;--cinza:#A7A3B5;--px:16px}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;background:transparent;color:#fff;font-family:Archivo}
.abs{position:absolute}
.rec{clip-path:polygon(0 calc(var(--px)*2),var(--px) calc(var(--px)*2),var(--px) var(--px),calc(var(--px)*2) var(--px),calc(var(--px)*2) 0,calc(100% - var(--px)*2) 0,calc(100% - var(--px)*2) var(--px),calc(100% - var(--px)) var(--px),calc(100% - var(--px)) calc(var(--px)*2),100% calc(var(--px)*2),100% calc(100% - var(--px)*2),calc(100% - var(--px)) calc(100% - var(--px)*2),calc(100% - var(--px)) calc(100% - var(--px)),calc(100% - var(--px)*2) calc(100% - var(--px)),calc(100% - var(--px)*2) 100%,calc(var(--px)*2) 100%,calc(var(--px)*2) calc(100% - var(--px)),var(--px) calc(100% - var(--px)),var(--px) calc(100% - var(--px)*2),0 calc(100% - var(--px)*2))}
h1{font-family:Anton;font-weight:400;text-transform:uppercase;line-height:1.04;letter-spacing:.5px;text-wrap:balance}
h1 em{font-style:normal;color:var(--d)}
.mk{background:var(--d);color:var(--noite);padding:0 .12em;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.pix{font:700 26px/1 Silkscreen;text-transform:uppercase;letter-spacing:1px}
.tag{display:inline-block;background:var(--d);color:var(--noite);font:700 26px/1 Silkscreen;text-transform:uppercase;padding:12px 16px 10px;letter-spacing:1px}
.cta{font:800 32px/1.15 Archivo;font-stretch:90%}
.seta{display:inline-block;flex:none;width:22px;height:32px;background:currentColor;clip-path:polygon(0 0,50% 0,50% 25%,100% 25%,100% 75%,50% 75%,50% 100%,0 100%)}
.fuj{position:absolute;width:24px;height:24px;background:var(--d)}
.deg{position:absolute;display:flex}.deg i{width:24px;height:24px;background:var(--d);display:block}.deg i:nth-child(2){opacity:.6}.deg i:nth-child(3){opacity:.3}
`;
const FIT = `window.__fit=()=>document.querySelectorAll('[data-fit]').forEach(el=>{const max=+el.dataset.fit;let s=parseFloat(getComputedStyle(el).fontSize);while(el.offsetHeight>max&&s>34){s-=2;el.style.fontSize=s+'px';}});`;
const fit = (vw, vh, b) => { const s = Math.min(b.w / vw, b.h / vh); const w = Math.round(vw * s / 2) * 2, h = Math.round(vh * s / 2) * 2; return { x: Math.round(b.x + (b.w - w) / 2), y: Math.round(b.y + (b.h - h) / 2), w, h } };
const plain = t => t.replace(/<\/?em>/g, '').replace(/<br>/g, ' ');
const mark = t => t.replace(/<br>/g, ' ').replace(/<em>(.*?)<\/em>/g, '<span class="mk">$1</span>');
const emTxt = c => { const m = c.titulo.match(/<em>(.*?)<\/em>/); return m ? m[1] : plain(c.titulo).split(' ')[0] };
const LOGO = (mono) => `<div class="abs" style="left:0;right:0;top:260px;text-align:center"><img src="${mono ? 'pixelzada-logo-mono-preto.svg' : 'pixelzada-logo-transparente.svg'}" style="height:44px;display:block;margin:0 auto"><div style="font:800 28px/1 Archivo;margin-top:8px;color:${mono ? '#0B0A10' : '#D2CEDE'}">@pixelzada.br</div></div>`;
const TIT = (c, x, y, w, h, size, extra = '', html) => `<h1 data-fit="${h}" class="abs" style="left:${x}px;top:${y}px;width:${w}px;font-size:${size}px;${extra}">${html || c.titulo}</h1>`;
// CTA sem faixa: texto solto na base da zona segura (borda de baixo em y=1580), para o Reel não parecer o rodapé dos carrosséis no grid
const FX = (c, bg = 'var(--d)', fg = 'var(--noite)', extra = '') => { const cor = bg === 'var(--d)' ? '#fff' : (bg === 'var(--noite)' && fg === '#fff') ? 'var(--noite)' : fg; const sombra = cor === '#fff' ? 'text-shadow:0 2px 14px rgba(0,0,0,.75);' : ''; return `<div class="abs" style="left:0;right:0;bottom:340px;color:${cor};padding:0 72px;text-align:center;${sombra}"><span class="cta" style="font-size:36px">${c.frase}</span></div>`; };
const SHADE = 'repeating-linear-gradient(to bottom,rgba(0,0,0,.22) 0 2px,transparent 2px 6px)';
const solid = bg => `<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:${bg}"></div>`;
const HALF = (cor, op = .18) => `radial-gradient(circle,${cor} 0 3px,transparent 3.5px) 0 0/22px 22px`;

const E = {};
// 20 molduras de Reel (v4, 10/10): vídeo GRANDE (1032x~1470 em pé), moldura mínima, título em cima e título embaixo, sem faixa.
// bg/fg recebem (c, w, V): w = retângulo real do vídeo. V = vídeo em pé; H = vídeo horizontal (títulos fora do vídeo).
// Zona segura y=260..1580. Logo no topo (sobre o vídeo em V, no fundo em H).
const BV = { x: 36, y: 240, w: 1008, h: 1440 };   // caixa do vídeo em pé
const BV2 = { x: 36, y: 500, w: 1008, h: 980 };  // vídeo mais quadrado: começa abaixo do título
const BH = { x: 24, y: 690, w: 1032, h: 680 };    // caixa do vídeo horizontal
const CORES2 = { '#C6FF1A': ['#FF3D8B', '#2EE6FF'], '#FF3D8B': ['#2EE6FF', '#C6FF1A'], '#FF8A1F': ['#FF3D8B', '#2EE6FF'], '#2EE6FF': ['#FF3D8B', '#C6FF1A'] };
const BGID = (c, v = 0) => { const [b1, b2] = CORES2[c.cor] || ['#FF3D8B', '#2EE6FF'];
  const glows = [`radial-gradient(circle at 8% 14%,color-mix(in srgb,var(--d) 34%,transparent),transparent 46%),radial-gradient(circle at 96% 82%,color-mix(in srgb,${b1} 30%,transparent),transparent 48%),radial-gradient(circle at 70% 4%,color-mix(in srgb,${b2} 18%,transparent),transparent 40%)`,
    `radial-gradient(circle at 94% 12%,color-mix(in srgb,var(--d) 34%,transparent),transparent 46%),radial-gradient(circle at 6% 86%,color-mix(in srgb,${b1} 30%,transparent),transparent 48%),radial-gradient(circle at 30% 2%,color-mix(in srgb,${b2} 18%,transparent),transparent 40%)`,
    `radial-gradient(circle at 50% 8%,color-mix(in srgb,var(--d) 30%,transparent),transparent 50%),radial-gradient(circle at 12% 92%,color-mix(in srgb,${b1} 28%,transparent),transparent 46%),radial-gradient(circle at 92% 88%,color-mix(in srgb,${b2} 24%,transparent),transparent 46%)`,
    `radial-gradient(circle at 50% 96%,color-mix(in srgb,var(--d) 30%,transparent),transparent 50%),radial-gradient(circle at 4% 10%,color-mix(in srgb,${b1} 28%,transparent),transparent 46%),radial-gradient(circle at 96% 14%,color-mix(in srgb,${b2} 24%,transparent),transparent 46%)`][v % 4];
  const deco = [`<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:${HALF('color-mix(in srgb,var(--d) 22%,transparent)')};-webkit-mask-image:linear-gradient(135deg,#000,transparent 55%);mask-image:linear-gradient(135deg,#000,transparent 55%)"></div>`,
    `<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:repeating-linear-gradient(135deg,color-mix(in srgb,var(--d) 9%,transparent) 0 3px,transparent 3px 44px)"></div>`,
    `<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:${HALF('color-mix(in srgb,' + b1 + ' 20%,transparent)')};-webkit-mask-image:linear-gradient(45deg,#000,transparent 55%);mask-image:linear-gradient(45deg,#000,transparent 55%)"></div>`,
    `<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:repeating-linear-gradient(0deg,rgba(255,255,255,.05) 0 2px,transparent 2px 8px);-webkit-mask-image:linear-gradient(180deg,transparent 30%,#000);mask-image:linear-gradient(180deg,transparent 30%,#000)"></div>`][v % 4];
  const px = v % 2 ? ['left:70px;top:170px', 'left:102px;top:202px', 'left:134px;top:170px', 'left:900px;top:1560px', 'left:932px;top:1592px', 'left:964px;top:1560px'] : ['left:900px;top:170px', 'left:932px;top:202px', 'left:964px;top:170px', 'left:70px;top:1560px', 'left:102px;top:1592px', 'left:134px;top:1560px'];
  return `<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:${glows},linear-gradient(165deg,#0B0A10,#17151F 55%,#0B0A10)"></div>${deco}
<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:repeating-linear-gradient(0deg,rgba(255,255,255,.035) 0 2px,transparent 2px 64px),repeating-linear-gradient(90deg,rgba(255,255,255,.035) 0 2px,transparent 2px 64px)"></div>
<i class="fuj" style="${px[0]};background:${b2}"></i><i class="fuj" style="${px[1]};background:var(--d);opacity:.7"></i><i class="fuj" style="${px[2]};background:${b1};opacity:.5"></i>
<i class="fuj" style="${px[3]};background:${b1}"></i><i class="fuj" style="${px[4]};background:${b2};opacity:.7"></i><i class="fuj" style="${px[5]};background:var(--d);opacity:.5"></i>`; };
// fundo de cor cheia (Cartaz, Quadrinho) para vídeo horizontal: cor da identidade com pontilhado, brilho e grade
const BGACC = c => `<div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:radial-gradient(circle at 50% 100%,rgba(11,10,16,.45),transparent 60%),radial-gradient(circle at 10% 8%,rgba(255,255,255,.28),transparent 45%),var(--d)"></div><div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:${HALF('rgba(11,10,16,.22)')}"></div><div class="abs" style="left:0;top:0;width:1080px;height:1920px;background:repeating-linear-gradient(0deg,rgba(11,10,16,.07) 0 2px,transparent 2px 64px),repeating-linear-gradient(90deg,rgba(11,10,16,.07) 0 2px,transparent 2px 64px)"></div><i class="fuj" style="left:900px;top:170px;background:#0B0A10"></i><i class="fuj" style="left:932px;top:202px;background:#fff"></i><i class="fuj" style="left:70px;top:1560px;background:#0B0A10"></i><i class="fuj" style="left:102px;top:1592px;background:#fff"></i>`;
const sh = 'text-shadow:0 2px 14px rgba(0,0,0,.75);';
const GRB = w => w.y >= 330 ? `<div class="abs" style="left:0;top:240px;width:1080px;height:${w.y - 240}px;background:linear-gradient(to bottom,transparent,rgba(11,10,16,.7) 40%,transparent)"></div><div class="abs" style="left:0;top:${w.y + w.h}px;width:1080px;height:300px;background:linear-gradient(to bottom,rgba(11,10,16,.7),transparent)"></div>` : '';
const GR = w => { const g = Math.min(380, Math.round(w.h * 0.3)); return `${w.y < 330 ? `<div class="abs" style="left:${w.x}px;top:${w.y}px;width:${w.w}px;height:380px;background:linear-gradient(to bottom,rgba(11,10,16,.9),transparent)"></div>` : ''}${w.y < 330 ? `<div class="abs" style="left:${w.x}px;top:${w.y + w.h - g}px;width:${w.w}px;height:${g}px;background:linear-gradient(to top,rgba(11,10,16,.92),transparent)"></div>` : ''}`; };
const RING = (w, n, col, extra = '') => `<div class="abs" style="left:${w.x}px;top:${w.y}px;width:${w.w}px;height:${w.h}px;border:${n}px solid ${col};${extra}"></div>`;
const BOXE = (w, x, y, ww, hh, st) => `<div class="abs" style="left:${w.x + x}px;top:${w.y + y}px;width:${ww}px;height:${hh}px;${st}"></div>`;
// título de cima
function TTL(c, V, k = 'mk') {
  const sz = V ? 58 : 80, mx = V ? 150 : 250, y = 352;
  if (k === 'box') return `<div class="abs" style="left:64px;right:64px;top:${y}px;background:rgba(11,10,16,.92);border:6px solid var(--d);padding:${V ? '10px 22px' : '18px 28px'};text-align:center"><h1 data-fit="${V ? 120 : 220}" style="font-size:${V ? 54 : 76}px;line-height:1.14">${mark(c.titulo)}</h1></div>`;
  if (k === 'sticker') return `<div class="abs" style="left:56px;right:56px;top:${y}px;background:#fff;color:#0B0A10;padding:${V ? '10px 26px' : '16px 28px'};transform:rotate(-1.5deg);text-align:center"><h1 data-fit="${V ? 120 : 220}" style="font-size:${V ? 54 : 76}px;line-height:1.14">${plain(c.titulo)}</h1></div>`;
  if (k === 'bubble') return `<div class="abs" style="left:64px;right:64px;top:${y}px;background:#fff;color:#0B0A10;border:6px solid #0B0A10;border-radius:44px;padding:${V ? '12px 30px' : '18px 34px'};text-align:center"><h1 data-fit="${V ? 120 : 220}" style="font-size:${V ? 54 : 76}px;line-height:1.14">${plain(c.titulo)}</h1></div>`;
  if (k === 'giant') { const m = c.titulo.match(/<em>(.*?)<\/em>/); const big = m ? m[1] : plain(c.titulo).split(' ')[0]; const rest = plain(c.titulo).replace(big, '').trim(); const f = Math.min(V ? 150 : 200, Math.floor(1900 / Math.max(big.length, 1))); return `<div class="abs" style="left:24px;right:24px;top:${V ? 330 : 340}px;text-align:center;${sh}"><div style="font:400 ${f}px/1 Anton;color:var(--d);text-transform:uppercase">${big}</div><h1 data-fit="${V ? 110 : 150}" style="font-size:${V ? 46 : 60}px;line-height:1.14;margin-top:6px">${rest}</h1></div>`; }
  return TIT(c, 48, y, 984, mx, sz, `text-align:center;line-height:1.22;${sh}`, mark(c.titulo));
}
// título de baixo (frase)
function CTAX(c, w, V, k = 'anton', col = 'var(--d)', dark = false) {
  const abaixo = V && w.y >= 330; const pos = V ? (abaixo ? `top:${w.y + w.h + 26}px` : 'bottom:338px') : `top:${w.y + w.h + 44}px`; const fs = abaixo ? 46 : 54;
  if (k === 'plain') return `<div class="abs" style="left:48px;right:48px;${pos};text-align:center;color:${dark && !V ? '#0B0A10' : '#fff'};font:800 ${V ? (abaixo ? 36 : 38) : 42}px/1.15 Archivo;font-stretch:90%;${dark && !V ? '' : sh}">${c.frase}</div>`;
  if (k === 'pill') return `<div class="abs" style="left:64px;right:64px;${pos};height:92px;border:4px solid ${col};border-radius:46px;display:flex;align-items:center;justify-content:center;padding:0 36px;color:${col};font:800 32px/1.1 Archivo;text-align:center;${sh}"><span>${c.frase}</span></div>`;
  return `<div class="abs" style="left:48px;right:48px;${pos};text-align:center;color:${col};font:400 ${V ? fs : 62}px/1.08 Anton;text-transform:uppercase;letter-spacing:.5px;${sh}">${c.frase}</div>`;
}
// monta um estilo: frame(c,w,V) devolve a moldura; bgx = camada atrás do vídeo
let NI = 0;
const mk = ({ nome, shape = 'rect', raio, solido = false, mono = false, bgH = 'id', bgx = () => '', frame = () => '', tt = 'mk', cta = 'anton', ctaCol }, v = NI++) => ({
  nome, box: BH, boxV: BV, boxV2: BV2, shape, raio, solido,
  bg: (c, w, V) => `${V ? GRB(w) : (bgH === 'acento' ? BGACC(c) : BGID(c, v))}${bgx(c, w, V)}${V ? '' : LOGO(mono)}`,
  fg: (c, w, V) => `${V ? GR(w) + LOGO(false) : ''}${frame(c, w, V)}${TTL(c, V, tt)}${CTAX(c, w, V, cta, ctaCol, bgH === 'acento')}`
});
const tag = (w, txt, x = 24, y = 24, st = '') => `<span class="tag abs" style="left:${w.x + x}px;top:${w.y + y}px;${st}">${txt}</span>`;
// 01
E.moldura = mk({ nome: 'Moldura', shape: 'rec', bgx: (c, w, V) => `<div class="rec abs" style="left:${w.x - 14}px;top:${w.y - 14}px;width:${w.w + 28}px;height:${w.h + 28}px;background:var(--d)"></div>` });
// 02
E.legenda = mk({ nome: 'Legenda', frame: (c, w) => tag(w, c.jogo || 'GTA 6', 24, 24), cta: 'plain' });
// 03
E.faixa = mk({ nome: 'Faixa', frame: (c, w) => BOXE(w, 0, 0, w.w, 8, 'background:var(--d)') + BOXE(w, 0, w.h - 8, w.w, 8, 'background:var(--d)') });
// 04
E.hud = mk({ nome: 'HUD', frame: (c, w) => { const L = (css) => `<div class="abs" style="width:64px;height:64px;border:0 solid var(--d);${css}"></div>`; const o = 16; return `${L(`left:${w.x + o}px;top:${w.y + o}px;border-left-width:8px;border-top-width:8px`)}${L(`left:${w.x + w.w - o - 64}px;top:${w.y + o}px;border-right-width:8px;border-top-width:8px`)}${L(`left:${w.x + o}px;top:${w.y + w.h - o - 64}px;border-left-width:8px;border-bottom-width:8px`)}${L(`left:${w.x + w.w - o - 64}px;top:${w.y + w.h - o - 64}px;border-right-width:8px;border-bottom-width:8px`)}<div class="abs pix" style="left:${w.x + w.w - 170}px;top:${w.y + 28}px;color:#fff;font-size:22px"><span style="color:#E5252A">●</span> REC</div>`; }, cta: 'plain' });
// 05
E.fliperama = mk({ nome: 'Fliperama', frame: (c, w) => RING(w, 6, 'var(--d)', 'box-shadow:0 0 30px var(--d),inset 0 0 30px color-mix(in srgb,var(--d) 40%,transparent)') + `<div class="abs pix" style="left:${w.x}px;width:${w.w}px;top:${w.y + 22}px;text-align:center;color:#fff;font-size:20px;display:none">1UP</div>` });
// 06
E.polaroid = mk({ nome: 'Polaroid', bgx: (c, w) => `<div class="abs" style="left:${w.x - 16}px;top:${w.y - 16}px;width:${w.w + 32}px;height:${w.h + 32}px;background:#fff"></div>`, frame: (c, w) => `<div class="abs" style="left:${w.x + 40}px;top:${w.y - 26}px;width:130px;height:40px;background:rgba(255,61,139,.85);transform:rotate(-6deg)"></div><div class="abs" style="left:${w.x + w.w - 170}px;top:${w.y - 26}px;width:130px;height:40px;background:rgba(255,61,139,.85);transform:rotate(5deg)"></div>` });
// 07
E.conversa = mk({ nome: 'Conversa', shape: 'round', raio: 44, frame: (c, w) => RING(w, 4, 'rgba(255,255,255,.35)', 'border-radius:44px'), tt: 'bubble', cta: 'plain' });
// 08
E.plantao = mk({ nome: 'Plantão', frame: (c, w, V) => `<div class="abs" style="left:${w.x}px;top:${w.y}px;width:${w.w}px;height:32px;background:var(--d);color:var(--noite);display:flex;align-items:center;gap:30px;padding:0 24px;overflow:hidden;white-space:nowrap"><span class="pix" style="font-size:16px">Plantão Pixelzada</span><i class="fuj" style="position:static;background:var(--noite);width:14px;height:14px"></i><span class="pix" style="font-size:16px">${c.jogo || 'GTA 6'}</span><i class="fuj" style="position:static;background:var(--noite);width:14px;height:14px"></i><span class="pix" style="font-size:16px">Plantão Pixelzada</span></div><div class="abs" style="left:${w.x + 20}px;top:${w.y + 50}px;display:flex;align-items:center;gap:10px;background:#E5252A;padding:8px 14px 6px;font:700 20px/1 Silkscreen">● AO VIVO</div>`, cta: 'plain' });
// 09
E.cartaz = mk({ nome: 'Cartaz', mono: true, bgH: 'acento', bgx: (c, w) => `<div class="abs" style="left:${w.x - 14}px;top:${w.y - 14}px;width:${w.w + 28}px;height:${w.h + 28}px;background:var(--d)"></div>`, frame: (c, w) => RING(w, 8, '#0B0A10'), tt: 'sticker', cta: 'plain' });
// 10
E.gigante = mk({ nome: 'Gigante', tt: 'giant', frame: (c, w) => RING(w, 3, 'rgba(255,255,255,.25)') });
// 11
E.celular = mk({ nome: 'Celular', shape: 'round', raio: 56, bgx: (c, w) => `<div class="abs" style="left:${w.x - 16}px;top:${w.y - 16}px;width:${w.w + 32}px;height:${w.h + 32}px;border-radius:72px;background:#1d1b27;border:3px solid #3a3748"></div>`, cta: 'pill', ctaCol: '#fff' });
// 12
E.stories = mk({ nome: 'Stories', shape: 'round', raio: 36, frame: (c, w) => `<div class="abs" style="left:${w.x + 20}px;right:${1080 - w.x - w.w + 20}px;top:${w.y + 18}px;display:flex;gap:8px"><i style="flex:1;height:6px;background:#fff;border-radius:3px"></i><i style="flex:1;height:6px;background:rgba(255,255,255,.4);border-radius:3px"></i><i style="flex:1;height:6px;background:rgba(255,255,255,.4);border-radius:3px"></i></div><div class="abs" style="left:${w.x + 24}px;top:${w.y + 40}px;display:flex;align-items:center;gap:12px"><img src="pixelzada-simbolo.svg" style="width:52px;height:52px;border-radius:50%;border:3px solid var(--d)"><div><div style="font:800 24px/1 Archivo">pixelzada.br</div><div style="font:700 17px/1 Archivo;color:#cfcbe0;margin-top:4px">agora · patrocinado por GTA 6</div></div></div>`, cta: 'pill', ctaCol: '#fff' });
// 13
E.tv = mk({ nome: 'TV', shape: 'round', raio: 34, bgx: (c, w) => `<div class="abs" style="left:${w.x - 20}px;top:${w.y - 20}px;width:${w.w + 40}px;height:${w.h + 40}px;border-radius:50px;background:#0f0e15;border:3px solid var(--d)"></div>`, frame: (c, w) => `<div class="abs" style="left:${w.x}px;top:${w.y}px;width:${w.w}px;height:${w.h}px;border-radius:34px;background:${SHADE};opacity:.5"></div><div class="abs pix" style="left:${w.x + w.w - 130}px;top:${w.y + 30}px;color:var(--d);font-size:22px;${sh}">CH 19</div>`, cta: 'plain' });
// 14
E.claquete = mk({ nome: 'Claquete', frame: (c, w) => `<div class="abs" style="left:${w.x}px;top:${w.y}px;width:${w.w}px;height:28px;background:repeating-linear-gradient(135deg,#0B0A10 0 20px,#fff 20px 40px)"></div>` + RING(w, 4, '#fff'), cta: 'plain' });
// 15
E.missao = mk({ nome: 'Missão', frame: (c, w) => RING(w, 4, 'var(--d)') + tag(w, 'Nova missão', 20, 20, 'font-size:20px;padding:10px 14px 8px') + `<div class="abs" style="left:${w.x + w.w - 78}px;top:${w.y + 18}px;width:56px;height:56px;border:4px solid var(--d)"><i class="fuj" style="left:8px;top:8px;width:14px;height:14px"></i><i class="fuj" style="left:30px;top:30px;width:14px;height:14px;opacity:.6"></i></div>` });
// 16
E.conquista = mk({ nome: 'Conquista', frame: (c, w) => RING(w, 4, 'var(--d)') + `<div class="abs pix" style="left:${w.x + 20}px;top:${w.y + 20}px;background:rgba(11,10,16,.9);border:3px solid var(--d);color:var(--d);padding:10px 14px 8px;font-size:20px">Conquista!</div>`, cta: 'plain' });
// 17
E.quadrinho = mk({ nome: 'Quadrinho', mono: true, bgH: 'acento', bgx: (c, w) => `<div class="abs" style="left:${w.x - 14}px;top:${w.y - 14}px;width:${w.w + 28}px;height:${w.h + 28}px;background:var(--d)"></div>`, frame: (c, w) => RING(w, 10, '#0B0A10'), tt: 'bubble', cta: 'plain' });
// 18
E.figurinha = mk({ nome: 'Figurinha', shape: 'round', raio: 40, bgx: (c, w) => `<div class="abs" style="left:${w.x - 14}px;top:${w.y - 14}px;width:${w.w + 28}px;height:${w.h + 28}px;border-radius:54px;background:#fff;box-shadow:0 8px 30px rgba(0,0,0,.6)"></div>`, tt: 'sticker' });
// 19
E.inventario = mk({ nome: 'Inventário', frame: (c, w) => RING(w, 4, 'var(--d)') + [[0, 0], [w.w - 22, 0], [0, w.h - 22], [w.w - 22, w.h - 22]].map(([x, y]) => BOXE(w, x, y, 22, 22, 'background:var(--d)')).join('') + tag(w, 'Lendário', 40, 40, 'background:#FF8A1F;font-size:20px;padding:10px 14px 8px'), cta: 'pill' });
// 20
E.carregando = mk({ nome: 'Carregando', frame: (c, w) => `<div class="abs" style="left:${w.x + 24}px;top:${w.y + 20}px;width:${w.w - 48}px;height:14px;background:rgba(255,255,255,.2)"><i style="display:block;width:72%;height:100%;background:var(--d)"></i></div><div class="abs pix" style="left:${w.x + 24}px;width:${w.w - 48}px;top:${w.y + 44}px;color:#fff;font-size:18px;display:flex;justify-content:space-between"><span>Carregando...</span><span>72%</span></div>` });
const ORDEM = Object.keys(E);
const ehV = (vw, vh) => vw / vh < 1.15;
// recorte vertical de um vídeo horizontal: corta a largura até a proporção da caixa V do estilo (foco = 0..1 na horizontal)
function cropV(sw, sh, estilo, foco = 0.5, asp) { const b = E[estilo].boxV; const A = asp || b.w / b.h; if (A >= sw / sh) return { x: 0, y: 0, w: sw, h: sh }; const cw = Math.round(sh * A / 2) * 2; return { x: Math.round((sw - cw) * foco), y: 0, w: cw, h: sh } }
// nome do jogo + número nunca se separam em linhas diferentes; CTA com linhas equilibradas
const NB = t => (t || '').replace(/(\bo )?\b(GTA|Battlefield|Forza Horizon|Red Dead Redemption|Red Dead) (\d|VI|V)\b/g, m => m.replace(/ /g, '\u00a0'));
async function render(p, c, estilo, vw, vh, tag, forcaV) {
  c = { ...c, titulo: Array.isArray(c.titulo) ? c.titulo.map(NB) : NB(c.titulo), frase: c.frase ? `<span style="display:block;text-wrap:balance">${NB(c.frase)}</span>` : c.frase };
  const e = E[estilo]; const V = forcaV === undefined ? ehV(vw, vh) : forcaV; const w = fit(vw, vh, c.box || (V ? (vw / vh >= 0.8 && e.boxV2 ? e.boxV2 : e.boxV) : (vw / vh > 1.15 && e.boxL) || e.box));
  const titulos = Array.isArray(c.titulo) ? c.titulo : [c.titulo];
  const out = { w, imgs: [], blur: !e.solido };
  const shot = async (html, name, transp) => { fs.writeFileSync(path.join(S, 'tmp.html'), html); await p.goto('file://' + path.join(S, 'tmp.html')); await p.evaluate(async () => { await document.fonts.ready; window.__fit && window.__fit(); }); await p.screenshot({ path: path.join(S, name), omitBackground: true }); return name };
  const page = inner => `<html><head><meta charset="utf-8"><style>${CSS}:root{--d:${c.cor}}</style><script>${FIT}</script></head><body>${inner}</body></html>`;
  for (let i = 0; i < titulos.length; i++) {
    const cc = { ...c, titulo: titulos[i] };
    out.imgs.push({ bg: await shot(page(e.bg(cc, w, V)), `${tag}-bg${i}.png`), fg: await shot(page(e.fg(cc, w, V)), `${tag}-fg${i}.png`) });
  }
  const forma = e.shape === 'rec' ? 'rec' : '';
  const rad = e.shape === 'round' ? `border-radius:${e.raio || 36}px;` : '';
  out.mask = await (async () => { fs.writeFileSync(path.join(S, 'tmp.html'), `<html><head><style>${CSS}html,body{background:#000}</style></head><body><div class="abs ${forma}" style="left:${w.x}px;top:${w.y}px;width:${w.w}px;height:${w.h}px;background:#fff;${rad}"></div></body></html>`); await p.goto('file://' + path.join(S, 'tmp.html')); await p.screenshot({ path: path.join(S, `${tag}-mask.png`) }); return `${tag}-mask.png` })();
  return out;
}
function compor(videoFile, crop, r, saida, { corte, still, ini } = {}) {
  const a = ['-v', 'error', '-y']; if (still || ini) a.push('-ss', String((still || 0) + (ini || 0)));
  a.push('-i', videoFile);
  r.imgs.forEach(i => { a.push('-loop', '1', '-i', path.join(S, i.bg), '-loop', '1', '-i', path.join(S, i.fg)) });
  a.push('-loop', '1', '-i', path.join(S, r.mask));
  const n = r.imgs.length, mi = 1 + 2 * n;
  let f = `[0:v]crop=${crop.w}:${crop.h}:${crop.x}:${crop.y},split=2[va][vb];[vb]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=34:3,eq=brightness=-0.2:saturation=1.35[bb];`;
  f += `[va]scale=${r.w.w}:${r.w.h},setsar=1,pad=1080:1920:${r.w.x}:${r.w.y}:black,format=rgba[v];[${mi}:v]format=gray[m];[v][m]alphamerge[vm];`;
  let cur = 'bb';
  if (r.blur) { f += `[bb][1:v]overlay=shortest=1[base0];`; cur = 'base0'; } else { f += `[bb][1:v]overlay=shortest=1[base0];`; cur = 'base0'; }
  if (n > 1) { f += `[${cur}][3:v]overlay=enable='gte(t,${corte})'[b1];`; cur = 'b1'; }
  f += `[${cur}][vm]overlay=shortest=1[o1];`;
  if (n > 1) f += `[o1][2:v]overlay=enable='lt(t,${corte})'[o2];[o2][4:v]overlay=enable='gte(t,${corte})',format=yuv420p,fps=30[out]`;
  else f += `[o1][2:v]overlay,format=yuv420p,fps=30[out]`;
  a.push('-filter_complex', f, '-map', '[out]');
  if (still) a.push('-frames:v', '1', saida);
  else a.push('-map', '0:a', '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-shortest', saida);
  const x = spawnSync('ffmpeg', a, { cwd: S, encoding: 'utf8' }); if (x.status) console.error(x.stderr.slice(0, 600));
}
module.exports = { E, ORDEM, render, compor, cropV, chromium, S };

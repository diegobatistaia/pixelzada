// Monta Reels na identidade da Pixelzada a partir de uma lista (JSON).
//
//   node scripts/social/gerador/montar.js pedido.json
//
// pedido.json = [{ video, saida, estilo, cor, jogo, titulo, frase, crop?, max_seg? }, ...]
//   video   caminho do vídeo bruto (mp4)
//   saida   caminho final sem extensão (gera saida.mp4 e saida.jpg)
//   estilo  uma das 20 molduras de estilos.js (moldura, polaroid, tv, ...)
//   crop    {x,y,w,h} do pedaço do vídeo que entra na moldura; sem ele, tira as
//           barras pretas sozinho (cropdetect)
//   max_seg corta o vídeo nesse tamanho (padrão 45s)
const { render, compor, chromium, S } = require('./estilos.js');
const { spawnSync } = require('child_process');
const fs = require('fs'), path = require('path');

const run = (cmd, args) => spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 1 << 26 });

function sonda(f) {
  const x = run('ffprobe', ['-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json', f]);
  const j = JSON.parse(x.stdout || '{}');
  const v = (j.streams || []).find(s => s.codec_type === 'video');
  return { w: v && v.width, h: v && v.height, dur: parseFloat((j.format || {}).duration || '0'), audio: (j.streams || []).some(s => s.codec_type === 'audio') };
}

// Normaliza: corta no tamanho máximo, garante trilha de áudio (o compor exige) e dimensões pares.
function preparar(entrada, destino, max) {
  const i = sonda(entrada);
  const a = ['-v', 'error', '-y', '-i', entrada];
  if (!i.audio) a.push('-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo');
  a.push('-t', String(Math.min(max, i.dur || max)), '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1',
    '-map', '0:v:0', '-map', i.audio ? '0:a:0' : '1:a:0', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17',
    '-c:a', 'aac', '-b:a', '192k', '-shortest', destino);
  const x = run('ffmpeg', a);
  if (x.status) throw new Error('ffmpeg preparar: ' + x.stderr.slice(0, 400));
  return sonda(destino);
}

// Tira barras pretas: pega o recorte mais frequente do cropdetect.
function recorte(f, info) {
  const x = run('ffmpeg', ['-v', 'info', '-i', f, '-vf', 'fps=2,cropdetect=24:2:0', '-f', 'null', '-']);
  const conta = {};
  for (const m of (x.stderr || '').matchAll(/crop=(\d+):(\d+):(\d+):(\d+)/g)) conta[m.slice(1).join(':')] = (conta[m.slice(1).join(':')] || 0) + 1;
  const melhor = Object.entries(conta).sort((a, b) => b[1] - a[1])[0];
  if (!melhor) return { x: 0, y: 0, w: info.w, h: info.h };
  let [w, h, cx, cy] = melhor[0].split(':').map(Number);
  // recorte pequeno demais é engano do detector: usa o quadro inteiro
  if (w < info.w * 0.4 || h < info.h * 0.25) return { x: 0, y: 0, w: info.w, h: info.h };
  w -= w % 2; h -= h % 2;
  return { x: cx, y: cy, w, h };
}

(async () => {
  const pedido = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  const feitos = [];
  for (const [n, v] of pedido.entries()) {
    try {
      const tag = 'z' + Date.now() + '-' + n;
      const tmp = path.join(S, tag + '-in.mp4');
      const info = preparar(path.resolve(v.video), tmp, v.max_seg || 45);
      const crop = v.crop || recorte(tmp, info);
      const r = await render(p, { titulo: v.titulo, frase: v.frase, cor: v.cor, jogo: v.jogo }, v.estilo, crop.w, crop.h, tag);
      const mp4 = path.resolve(v.saida + '.mp4'), jpg = path.resolve(v.saida + '.jpg');
      fs.mkdirSync(path.dirname(mp4), { recursive: true });
      compor(tmp, crop, r, mp4);
      if (!fs.existsSync(mp4) || fs.statSync(mp4).size < 50000) throw new Error('vídeo final não saiu');
      const ss = Math.min(2.3, Math.max(0, (info.dur || 4) / 2));
      run('ffmpeg', ['-v', 'error', '-y', '-ss', String(ss), '-i', mp4, '-frames:v', '1', '-q:v', '2', jpg]);
      for (const f of fs.readdirSync(S).filter(f => f.startsWith(tag))) fs.rmSync(path.join(S, f), { force: true });
      feitos.push({ saida: v.saida, ok: true, crop, segundos: Math.round(Math.min(v.max_seg || 45, info.dur)) });
      console.log('ok', path.basename(v.saida), JSON.stringify(crop));
    } catch (e) {
      feitos.push({ saida: v.saida, ok: false, erro: String(e.message || e).slice(0, 300) });
      console.error('falhou', v.saida, e.message || e);
    }
  }
  await b.close();
  fs.writeFileSync(process.argv[3] || '/dev/stdout', JSON.stringify(feitos, null, 1) + '\n');
})();

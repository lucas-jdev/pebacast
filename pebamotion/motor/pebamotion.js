// Pebamotion: linguagem de motion do Pebacast.
// Desenho em modo imediato: cada quadro é uma função pura do tempo, então qualquer instante renderiza igual.
// Fontes, paisagens e cores vêm do site (site/fontes, --cena-* de site/estilo.css): o palco carrega e preenche PM.cenas.

const PM = (() => {
  const TOKENS = {
    papel: '#efe4c8', papel2: '#e6d6b0', papel3: '#cbb689', branco: '#fffaf0',
    tinta: '#15110c', tintaSuave: '#4a3e2e', destaque: '#f2c53d', azul: '#1e4f8f',
    madeira: '#c8a46a', madeiraEscura: '#8a6a3c',
    sisal: { sombra: '#2a1a0b', base: '#6a4520', fio: '#c99459', torcao: '#9c6a36' },
    titulo: "'Alfa Slab One'", texto: "'Literata'",
  };

  const SAGAS = {
    software: { nome: 'Software', cor: '#f2a7bf', cena: 'cena-vila' },
    solucoes: { nome: 'Soluções', cor: '#8ccfc0', cena: 'cena-litoral' },
    sistemas: { nome: 'Sistemas', cor: '#a9c8ec', cena: 'cena-mar-aberto' },
    dados: { nome: 'Dados e Informação', cor: '#c6dc8e', cena: 'cena-sertao' },
    infraestrutura: { nome: 'Infraestrutura', cor: '#d8b98a', cena: 'cena-chao' },
    seguranca: { nome: 'Segurança', cor: '#f2a46b', cena: 'cena-noite' },
    corporativa: { nome: 'Corporativa', cor: '#cdb8ea', cena: 'cena-por-do-sol' },
  };

  const FORMATOS = {
    vertical: {
      W: 1080, H: 1920,
      tipo: { x: 80, y: 250, w: 920, h: 330, tam: 112 },
      palco: { x: 40, y: 560, escala: 1.0 },
      legenda: { x: 70, y: 1400, w: 940, tam: 48 },
      etiqueta: { x: 92, y: 118, escala: 1.25 },
    },
    horizontal: {
      W: 1920, H: 1080,
      tipo: { x: 110, y: 210, w: 740, h: 420, tam: 118 },
      palco: { x: 870, y: 175, escala: 1.0 },
      legenda: { x: 100, y: 830, w: 760, tam: 40 },
      etiqueta: { x: 128, y: 96, escala: 1.15 },
    },
  };

  // ---------- tempo e curvas ----------
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const prog = (t, t0, d) => clamp((t - t0) / d);
  const E = {
    out: k => 1 - Math.pow(1 - k, 3),
    in: k => k * k * k,
    inOut: k => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
    back: k => { const c = 1.9; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); },
  };
  const pendulo = (t, amp, f = 1.05, z = 2.4) => (t < 0 ? amp : amp * Math.exp(-z * t) * Math.cos(2 * Math.PI * f * t));
  const mola = (t, f = 1.6, z = 4.2) => (t <= 0 ? 0 : 1 - Math.exp(-z * t) * Math.cos(2 * Math.PI * f * t));

  function aleatorio(semente) {
    let a = typeof semente === 'string' ? [...semente].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7) : semente;
    return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }

  // ---------- texto ----------
  const ctx2d = document.createElement('canvas').getContext('2d');
  const medir = (txt, tam, fonte = TOKENS.titulo, peso = 400) => { ctx2d.font = `${peso} ${tam}px ${fonte}`; return ctx2d.measureText(txt).width; };
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Tinta viva: o contorno da tinta "ferve" 8 vezes por segundo, como xilogravura reimpressa.
  let fervura = 0;
  const tinta = () => `url(#tinta${fervura})`;

  // ---------- primitivas gráficas ----------
  function barbante(x1, y1, x2, y2, curva = 30, esp = 7, desenho = 1) {
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2 + curva;
    const d = `M${x1} ${y1}Q${mx} ${my} ${x2} ${y2}`;
    const comp = Math.hypot(x2 - x1, y2 - y1) + Math.abs(curva);
    const tr = desenho < 1 ? `stroke-dasharray="${comp * 1.1}" stroke-dashoffset="${comp * 1.1 * (1 - desenho)}"` : '';
    const s = TOKENS.sisal;
    return `<g fill="none" stroke-linecap="round">
      <path d="${d}" stroke="${s.sombra}" stroke-opacity=".32" stroke-width="${esp}" transform="translate(1.6 2.4)" ${tr}/>
      <path d="${d}" stroke="${s.base}" stroke-width="${esp + 1}" ${tr}/>
      <path d="${d}" stroke="${s.fio}" stroke-width="${esp * 0.72}" ${tr}/>
      ${desenho >= 1 ? `<path d="${d}" stroke="${s.torcao}" stroke-width="${esp * 0.5}" stroke-dasharray="2 ${esp * 0.9}"/>` : ''}
    </g>`;
  }

  function pregador(x, y, esc = 1, rot = 0) {
    return `<g transform="translate(${x} ${y}) rotate(${rot}) scale(${esc})">
      <rect x="-8" y="-22" width="16" height="44" rx="3" fill="${TOKENS.madeira}" stroke="${TOKENS.tinta}" stroke-width="3"/>
      <path d="M0 -20V20" stroke="${TOKENS.madeiraEscura}" stroke-width="2"/>
      <rect x="-10" y="-4" width="20" height="7" rx="2" fill="#8f8a80" stroke="${TOKENS.tinta}" stroke-width="2"/>
    </g>`;
  }

  // Folheto: o cartão do site (borda grossa e sombra amarela deslocada).
  function folheto({ x, y, w, h, fundo = TOKENS.branco, rot = 0, px = w / 2, py = 0, sombra = 12, hachura = false, escala = 1, opacidade = 1 }, miolo = '') {
    const hach = hachura ? `<rect x="0" y="0" width="${w}" height="${h}" fill="url(#hachura)"/>` : '';
    return `<g transform="translate(${x} ${y}) rotate(${rot} ${px} ${py}) scale(${escala})" opacity="${opacidade}">
      ${sombra ? `<rect x="${sombra}" y="${sombra}" width="${w}" height="${h}" fill="${TOKENS.destaque}" stroke="${TOKENS.tinta}" stroke-width="3"/>` : ''}
      <rect x="0" y="0" width="${w}" height="${h}" fill="${fundo}"/>${hach}
      <rect x="0" y="0" width="${w}" height="${h}" fill="none" stroke="${TOKENS.tinta}" stroke-width="4.5"/>
      ${miolo}
    </g>`;
  }

  function no(x, y, r = 22, rotulo = '', escala = 1, cor = TOKENS.tinta, corte = TOKENS.papel) {
    if (escala <= 0) return '';
    return `<g transform="translate(${x} ${y}) scale(${escala})">
      <circle r="${r}" fill="${cor}"/>
      <circle r="${r * 0.56}" fill="none" stroke="${corte}" stroke-width="${Math.max(2, r * 0.12)}"/>
      ${rotulo ? `<text y="${r + 30}" text-anchor="middle" font-family="${TOKENS.texto}" font-weight="600" font-size="24" fill="${TOKENS.tinta}">${esc(rotulo)}</text>` : ''}
    </g>`;
  }

  function cilindro(x, y, w, h, fundo = TOKENS.branco, escala = 1, rot = 0, boca = 0) {
    const ry = w * 0.18;
    return `<g transform="translate(${x} ${y}) rotate(${rot}) scale(${escala})">
      <path d="M${-w / 2} ${-h / 2}V${h / 2}A${w / 2} ${ry} 0 0 0 ${w / 2} ${h / 2}V${-h / 2}" fill="${fundo}" stroke="${TOKENS.tinta}" stroke-width="5"/>
      <path d="M${-w / 2} ${-h / 2}V${h / 2}A${w / 2} ${ry} 0 0 0 ${w / 2} ${h / 2}V${-h / 2}" fill="url(#hachura)"/>
      <path d="M${-w / 2} ${-h / 6}A${w / 2} ${ry} 0 0 0 ${w / 2} ${-h / 6}M${-w / 2} ${h / 6}A${w / 2} ${ry} 0 0 0 ${w / 2} ${h / 6}" fill="none" stroke="${TOKENS.tinta}" stroke-width="4"/>
      <ellipse cx="0" cy="${-h / 2}" rx="${w / 2}" ry="${ry * (1 + boca * 0.6)}" fill="${boca > 0 ? TOKENS.tinta : fundo}" stroke="${TOKENS.tinta}" stroke-width="5"/>
    </g>`;
  }

  // O bug em xilogravura: massa preta com cortes em papel.
  function inseto(x, y, escala = 1, rot = 0, passo = 0, cor = TOKENS.tinta, corte = TOKENS.papel) {
    const p = Math.sin(passo) * 6;
    return `<g transform="translate(${x} ${y}) rotate(${rot}) scale(${escala})">
      <g stroke="${cor}" stroke-width="6" stroke-linecap="round" fill="none">
        <path d="M-26 -14l-26 ${-12 + p}M-30 6l-30 ${2 - p}M-26 24l-24 ${20 + p}M26 -14l26 ${-12 - p}M30 6l30 ${2 + p}M26 24l24 ${20 - p}"/>
        <path d="M-8 -52q-8-20-22-26M8 -52q8-20 22-26" stroke-width="4"/>
      </g>
      <ellipse cx="0" cy="8" rx="34" ry="44" fill="${cor}"/>
      <circle cx="0" cy="-44" r="17" fill="${cor}"/>
      <g stroke="${corte}" stroke-linecap="round" fill="none">
        <path d="M0 -30V50" stroke-width="3"/>
        <path d="M-20 -10q8 4 12 14M20 -10q-8 4-12 14M-22 18q8 4 12 14M22 18q-8 4-12 14" stroke-width="2.5"/>
      </g>
      <circle cx="-7" cy="-48" r="3" fill="${corte}"/><circle cx="7" cy="-48" r="3" fill="${corte}"/>
    </g>`;
  }

  function peba(x, y, larg = 160, cor = TOKENS.tinta, corte = TOKENS.papel, virar = false, passo = 0) {
    const h = larg * 80 / 128, sx = virar ? -1 : 1, bob = Math.abs(Math.sin(passo)) * -larg * 0.02;
    return `<g transform="translate(${x} ${y + bob}) scale(${sx} 1)" style="color:${cor};--corte:${corte}">
      <svg x="${-larg / 2}" y="${-h}" width="${larg}" height="${h}" viewBox="0 0 128 80"><use href="#peba"/></svg>
    </g>`;
  }

  // ---------- carimbo: palavra que cai na página como uma prensa ----------
  function carimbo(txt, x, y, tam, t, t0, { ancora = 'start', cor = TOKENS.tinta, fonte = TOKENS.titulo, peso = 400, rot = null, dur = 0.22, saida = null, sublinhar = null } = {}) {
    if (t < t0) return '';
    const k = prog(t, t0, dur);
    const r = rot === null ? (aleatorio(txt)() - 0.5) * 3 : rot;
    const s = 1 + 0.55 * Math.pow(1 - E.out(k), 2) - 0.04 * Math.sin(Math.PI * clamp(k * 1.6));
    let op = clamp(k * 5);
    let dy = 0;
    if (saida !== null && t > saida) { const q = prog(t, saida, 0.18); op *= 1 - q; dy = -20 * E.in(q); }
    if (op <= 0) return '';
    const larg = medir(txt, tam, fonte, peso);
    const cx = ancora === 'middle' ? 0 : ancora === 'end' ? -larg / 2 : larg / 2;
    let sub = '';
    if (sublinhar !== null && t > sublinhar) {
      const q = E.out(prog(t, sublinhar, 0.35));
      const x0 = ancora === 'middle' ? -larg / 2 : ancora === 'end' ? -larg : 0;
      sub = `<rect x="${x0}" y="${tam * 0.12}" width="${larg * q}" height="${tam * 0.13}" fill="${TOKENS.destaque}"/>`;
    }
    return `<g transform="translate(${x} ${y + dy}) rotate(${r})" opacity="${op}">
      <g transform="translate(${cx} ${-tam * 0.35}) scale(${s}) translate(${-cx} ${tam * 0.35})">
        ${sub}<text text-anchor="${ancora}" font-family="${fonte}" font-weight="${peso}" font-size="${tam}" fill="${cor}" filter="${tinta()}">${esc(txt)}</text>
      </g></g>`;
  }

  // Bloco de tipografia cinética: linhas empilhadas, cada uma com seu instante de carimbo, ajustadas à largura.
  function blocoDeTipo(f, t, linhas, { alinhar = 'start', saida = null, cor = TOKENS.tinta } = {}) {
    const z = f.tipo;
    let y = z.y, out = '';
    for (const l of linhas) {
      const fonte = l.fonte || TOKENS.titulo, peso = l.peso || 400;
      let tam = (l.tam || 1) * z.tam;
      const larg = medir(l.txt, tam, fonte, peso);
      if (larg > z.w) tam *= z.w / larg;
      y += tam * (l.entrelinha || 1.02);
      const x = alinhar === 'middle' ? z.x + z.w / 2 : z.x;
      out += carimbo(l.txt, x, y, tam, t, l.t, { ancora: alinhar, cor: l.cor || cor, fonte, peso, saida, sublinhar: l.sublinhar ?? null, rot: l.rot ?? null });
      y += l.respiro || 0;
    }
    return out;
  }

  // ---------- legenda karaokê ----------
  function blocosDeLegenda(clipe, f) {
    const z = f.legenda, maxW = z.w - 80;
    const blocos = [];
    let atual = null;
    for (const [p, a, b] of clipe.palavras) {
      if (!atual) atual = { palavras: [], linhas: [[]] };
      const linha = atual.linhas[atual.linhas.length - 1];
      const tentativa = [...linha.map(w => w[0]), p].join(' ');
      if (medir(tentativa, z.tam, TOKENS.texto, 600) > maxW) {
        if (atual.linhas.length >= 2) { blocos.push(atual); atual = { palavras: [], linhas: [[]] }; }
        else atual.linhas.push([]);
      }
      atual.linhas[atual.linhas.length - 1].push([p, a, b]);
      atual.palavras.push([p, a, b]);
      const fimDeFrase = /[.?!]$/.test(p) || (/,$/.test(p) && atual.palavras.length >= 5);
      if (fimDeFrase) { blocos.push(atual); atual = null; }
    }
    if (atual && atual.palavras.length) blocos.push(atual);
    return blocos;
  }

  function legenda(f, t, clipes, saga, ocultar = []) {
    const z = f.legenda;
    let ativo = null, idx = -1;
    for (let i = 0; i < clipes.length; i++) {
      const c = clipes[i];
      const fim = c.fim + (clipes[i + 1] && clipes[i + 1].inicio - c.fim < 0.5 ? clipes[i + 1].inicio - c.fim : 0.35);
      if (t >= c.inicio - 0.12 && t < fim) { ativo = c; idx = i; }
    }
    if (!ativo || ocultar.includes(ativo.id)) return '';
    const blocos = blocosDeLegenda(ativo, f);
    let b = blocos[0];
    for (const bl of blocos) if (t >= bl.palavras[0][1] - 0.1) b = bl;
    const lh = z.tam * 1.38, pad = 34;
    const h = b.linhas.length * lh + pad * 2 - z.tam * 0.25;
    const anterior = clipes[idx - 1];
    const continuo = anterior && ativo.inicio - anterior.fim < 0.5;
    const entrada = continuo ? 1 : E.back(prog(t, ativo.inicio - 0.12, 0.25));
    const camila = ativo.persona === 'camila';
    const nome = camila ? 'CAMILA' : 'DAVI';
    const virada = continuo && anterior.persona !== ativo.persona ? E.out(prog(t, ativo.inicio - 0.12, 0.2)) : 1;
    let txt = '';
    b.linhas.forEach((linha, li) => {
      let x = pad;
      const y = pad + li * lh + z.tam * 0.92;
      for (const [p, a, bb] of linha) {
        const w = medir(p, z.tam, TOKENS.texto, 600);
        const falando = t >= a - 0.03 && t < bb + 0.06;
        const dita = t >= a - 0.03;
        if (falando) txt += `<rect x="${x - 6}" y="${y - z.tam * 0.78}" width="${w + 12}" height="${z.tam * 1.02}" fill="${TOKENS.destaque}"/>`;
        txt += `<text x="${x}" y="${y}" font-family="${TOKENS.texto}" font-weight="600" font-size="${z.tam}" fill="${TOKENS.tinta}" opacity="${dita ? 1 : 0.32}">${esc(p)}</text>`;
        x += w + medir(' ', z.tam, TOKENS.texto, 600);
      }
    });
    const chipW = medir(nome, 26, TOKENS.titulo) + 36;
    return `<g transform="translate(${z.x} ${z.y + (1 - entrada) * 40})" opacity="${clamp(entrada * 2)}">
      <rect x="12" y="12" width="${z.w}" height="${h}" fill="${TOKENS.destaque}" stroke="${TOKENS.tinta}" stroke-width="3"/>
      <rect width="${z.w}" height="${h}" fill="${TOKENS.branco}" stroke="${TOKENS.tinta}" stroke-width="4.5"/>
      ${txt}
      <g transform="translate(26 -26) scale(1 ${virada})">
        <rect x="4" y="4" width="${chipW}" height="44" fill="${TOKENS.tinta}"/>
        <rect width="${chipW}" height="44" fill="${camila ? saga.cor : TOKENS.papel}" stroke="${TOKENS.tinta}" stroke-width="3"/>
        <text x="${chipW / 2}" y="32" text-anchor="middle" font-family="${TOKENS.titulo}" font-size="26" fill="${TOKENS.tinta}">${nome}</text>
      </g>
    </g>`;
  }

  // ---------- etiqueta da saga amarrada com sisal ----------
  function etiqueta(f, t, saga, codigo, { t0 = 0, saida = null } = {}) {
    const z = f.etiqueta;
    if (t < t0) return '';
    const queda = E.out(prog(t, t0, 0.35));
    let ang = pendulo(t - t0, 14, 0.9, 2.2) - 3;
    let dy = (1 - queda) * -160;
    if (saida !== null && t > saida) dy -= 260 * E.in(prog(t, saida, 0.35));
    const rotulo = `Saga ${saga.nome}`;
    const w1 = medir(rotulo, 30, TOKENS.titulo), w2 = medir(codigo, 26, TOKENS.texto, 700);
    const w = 52 + w1 + 22 + w2 + 26, h = 56;
    return `<g transform="translate(${z.x} ${z.y + dy}) scale(${z.escala}) rotate(${ang} 22 ${h / 2})">
      <path d="M22 ${h / 2}C2 ${h / 2 - 34} -26 -40 -40 -70" fill="none" stroke="${TOKENS.sisal.base}" stroke-width="7" stroke-linecap="round"/>
      <path d="M22 ${h / 2}C2 ${h / 2 - 34} -26 -40 -40 -70" fill="none" stroke="${TOKENS.sisal.fio}" stroke-width="5" stroke-linecap="round"/>
      <path d="M22 ${h / 2}C2 ${h / 2 - 34} -26 -40 -40 -70" fill="none" stroke="${TOKENS.sisal.torcao}" stroke-width="3" stroke-dasharray="2 6"/>
      <polygon points="24,6 ${w + 6},6 ${w + 6},${h + 6} 24,${h + 6} 4,${h / 2 + 6}" fill="${TOKENS.tinta}"/>
      <polygon points="20,0 ${w},0 ${w},${h} 20,${h} 0,${h / 2}" fill="${saga.cor}" stroke="${TOKENS.tinta}" stroke-width="3.5"/>
      <polygon points="20,0 ${w},0 ${w},${h} 20,${h} 0,${h / 2}" fill="url(#hachura)"/>
      <circle cx="22" cy="${h / 2}" r="6.5" fill="${TOKENS.tinta}"/>
      <text x="44" y="${h / 2 + 11}" font-family="${TOKENS.titulo}" font-size="30" fill="${TOKENS.tinta}">${esc(rotulo)}</text>
      <text x="${44 + w1 + 22}" y="${h / 2 + 10}" font-family="${TOKENS.texto}" font-weight="700" font-size="26" fill="${TOKENS.tinta}">· ${esc(codigo)}</text>
    </g>`;
  }

  // ---------- fundo, paisagem e moldura de cordel ----------
  // nome da cena (--cena-* do estilo.css) → URL da imagem; preenchido pelo palco
  const cenas = {};
  function fundo(f, t, saga, { escuro = 0 } = {}) {
    const deriva = (t * 9) % 1600;
    const alturaCena = f.W === 1080 ? 520 : 380;
    const yCena = f.H - alturaCena - 10;
    const cena = cenas[saga.cena];
    return `<rect width="${f.W}" height="${f.H}" fill="${TOKENS.papel}"/>
      <g opacity=".17">
        <image href="${cena}" x="${-deriva}" y="${yCena}" width="${f.W === 1080 ? 1600 : 1920}" height="${alturaCena}" preserveAspectRatio="xMidYMax slice"/>
        <image href="${cena}" x="${-deriva + (f.W === 1080 ? 1600 : 1920)}" y="${yCena}" width="${f.W === 1080 ? 1600 : 1920}" height="${alturaCena}" preserveAspectRatio="xMidYMax slice"/>
        <image href="${cenas['cena-ceu']}" x="${-deriva * 0.5}" y="20" width="${f.W * 1.5}" height="${f.H * 0.22}" preserveAspectRatio="xMidYMin slice"/>
      </g>
      ${escuro > 0 ? `<rect width="${f.W}" height="${f.H}" fill="${TOKENS.tinta}" opacity="${escuro}"/>` : ''}`;
  }

  function moldura(f) {
    const b = 18;
    return `<g fill="url(#losangos)">
      <rect x="0" y="0" width="${f.W}" height="${b}"/><rect x="0" y="${f.H - b}" width="${f.W}" height="${b}"/>
      <rect x="0" y="0" width="${b}" height="${f.H}"/><rect x="${f.W - b}" y="0" width="${b}" height="${f.H}"/>
    </g><rect x="${b}" y="${b}" width="${f.W - 2 * b}" height="${f.H - 2 * b}" fill="none" stroke="${TOKENS.tinta}" stroke-width="3"/>`;
  }

  function defs() {
    const filtros = [0, 1, 2, 3].map(i => `<filter id="tinta${i}" x="-5%" y="-20%" width="110%" height="140%">
      <feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="2" seed="${i * 7 + 3}"/>
      <feDisplacementMap in="SourceGraphic" scale="3.4" xChannelSelector="R" yChannelSelector="G"/></filter>`).join('');
    return `<defs>${filtros}
      <pattern id="hachura" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
        <line x1="0" y1="0" x2="0" y2="10" stroke="${TOKENS.tinta}" stroke-opacity=".14" stroke-width="2"/></pattern>
      <pattern id="hachuraClara" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
        <line x1="0" y1="0" x2="0" y2="10" stroke="${TOKENS.papel}" stroke-opacity=".16" stroke-width="2"/></pattern>
      <pattern id="losangos" width="18" height="18" patternUnits="userSpaceOnUse">
        <rect width="18" height="18" fill="${TOKENS.tinta}"/>
        <g fill="${TOKENS.papel}" transform="scale(.3333)"><path d="M18 14l9-9 9 9zM18 40l9 9 9-9zM14 18l-9 9 9 9zM40 18l9 9-9 9z"/>
        <path d="M9 4l5 5-5 5-5-5zM45 4l5 5-5 5-5-5zM9 40l5 5-5 5-5-5zM45 40l5 5-5 5-5-5z"/></g></pattern>
      <symbol id="peba" viewBox="0 0 128 80">
        <path fill="currentColor" d="M104 55c9 1 16 6 22 15-8-3-15-6-23-7z"/>
        <path fill="currentColor" d="M36 59h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2zm14 0h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2zm34 0h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2zm14 0h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2z"/>
        <path fill="currentColor" d="M28 60c0-27 19-44 42-44s40 17 40 44z"/>
        <path fill="currentColor" d="M36 44c-9-2-18 2-25 8L3 59c-1 1-1 4 2 4h30z"/>
        <path fill="currentColor" d="M33 47c-3-6-2-13 2-15 3 3 3 10 0 15z"/>
        <g fill="none" stroke="var(--corte, #efe4c8)" stroke-linecap="round">
          <path stroke-width="2.4" d="M50 23c-3 11-4 24-4 34M61 18c-2 12-2 26-2 39M72 17c0 13 0 27 0 40M83 19c2 12 2 25 2 38M94 25c3 10 4 21 4 32"/>
          <path stroke-width="1.6" d="M32 56c24-3 50-3 76 0"/>
          <path stroke-width="1.4" d="M38 30l4 3m-6 4 4 2m62-9-4 3m6 4-4 2"/>
        </g>
        <circle cx="16" cy="54" r="1.8" fill="var(--corte, #efe4c8)"/>
      </symbol></defs>`;
  }

  // Caminho SVG medido uma vez: ponto e direção a uma distância s, e de que lado fica o "casco"
  // de quem anda nele (+1 indo para a direita, -1 para a esquerda), com histerese e giro em 30 px.
  const caminhos = new Map();
  let medidor = null;
  function caminho(d) {
    if (!caminhos.has(d)) {
      if (!medidor) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '0'); svg.setAttribute('height', '0'); svg.style.position = 'absolute';
        medidor = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        svg.appendChild(medidor); document.body.appendChild(svg);
      }
      medidor.setAttribute('d', d);
      const L = medidor.getTotalLength(), pts = [];
      for (let i = 0; i <= 400; i++) { const p = medidor.getPointAtLength(L * i / 400); pts.push([p.x, p.y]); }
      caminhos.set(d, { L, pts });
    }
    const { L, pts } = caminhos.get(d);
    const indice = s => Math.max(0, Math.min(399, Math.floor((s / L) * 400)));
    return {
      L,
      ponto(s) {
        const i = indice(s), [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
        return [x0, y0, Math.atan2(y1 - y0, x1 - x0) * 180 / Math.PI];
      },
      lado(s) {
        const fim = indice(s);
        let estado = 1, troca = -Infinity;
        for (let i = 0; i <= fim; i++) {
          const dx = pts[i + 1][0] - pts[i][0], dy = pts[i + 1][1] - pts[i][1];
          const c = dx / (Math.hypot(dx, dy) || 1);
          if (estado === 1 && c < -0.35) { estado = -1; troca = i; } else if (estado === -1 && c > 0.35) { estado = 1; troca = i; }
        }
        const andado = (fim - troca) * L / 400;
        return andado >= 30 ? estado : -estado + 2 * estado * E.inOut(andado / 30);
      },
    };
  }

  // Câmera: tremida curta a cada carimbo pesado.
  function tremida(t, impactos, forca = 9) {
    let dx = 0, dy = 0;
    for (const t0 of impactos) {
      const d = t - t0;
      if (d >= 0 && d < 0.22) { const a = forca * (1 - d / 0.22); dx += Math.sin(d * 95) * a; dy += Math.cos(d * 80) * a * 0.7; }
    }
    return [dx, dy];
  }

  function montar(f, t, partes) {
    fervura = Math.floor(t * 8) % 4;
    return partes;
  }

  return { TOKENS, SAGAS, FORMATOS, clamp, lerp, prog, E, pendulo, mola, aleatorio, medir, esc, tinta: () => tinta(),
    barbante, pregador, folheto, no, cilindro, inseto, peba, carimbo, blocoDeTipo, legenda, etiqueta, fundo, moldura, defs, tremida, montar, cenas, caminho };
})();

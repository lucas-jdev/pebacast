// DA 001 — Modelos de dados: relacional, documento e grafo.
// O palco expõe LINHA (linha.json) antes de carregar este arquivo; ele devolve quadro(), quadroEncerramento(),
// eventosSonoros() e eventosDoFim().
// Cada cena desenha o palco (diagrama, espaço 1000×800) e a tipografia a partir do tempo do trailer.

const EPISODIO = {
  saga: PM.SAGAS.dados,
  codigo: 'DA 001',
  titulo: 'Modelos de dados: relacional, documento e grafo',
  site: 'lucas-jdev.github.io/pebacast',
};

const { TOKENS: K, clamp, lerp, prog, E, pendulo, aleatorio, medir, esc } = PM;
const clipe = id => LINHA.clipes.find(c => c.id === id);
const P = (id, i) => clipe(id).palavras[i][1];
const ini = id => clipe(id).inicio;
const fimDe = id => clipe(id).fim;

const T = {
  caso: ini('caso') - 0.06,
  copia: ini('copia'),
  grafo: ini('grafo'),
  consultas: ini('consultas'),
  ferramenta: ini('ferramenta'),
  aceita: ini('aceita'),
  negativo: ini('bug') - 0.42,
  roubar: ini('roubar'),
  puxao: P('roubar', 2),
  dono: ini('dono'),
  fim: fimDe('dono') + 0.15,
};

const IMPACTOS = [P('forma', 9), P('caso', 11), P('copia', 27), P('grafo', 4), P('consultas', 9), P('aceita', 5),
  P('bug', 1), P('bug', 5), P('bug', 13), P('dono', 4), T.fim + 1.25];

const COM_NOMES = new URLSearchParams(location.search).get('nomes') !== '0';
const nomeAntigo = 'Dr. Lima', nomeNovo = 'Dr. Lima Rocha';
// Sem nomes, o nome do médico vira tarja de tinta: o tamanho da tarja muda quando o nome muda.
function nomeSvg(nome, x, y, tam, cor = K.tinta) {
  if (COM_NOMES) return `<text x="${x}" y="${y}" font-family="${K.texto}" font-weight="700" font-size="${tam}" fill="${cor}">${esc(nome)}</text>`;
  const w = medir(nome, tam, K.texto, 700) * 0.9;
  return `<rect x="${x}" y="${y - tam * 0.74}" width="${w}" height="${tam * 0.7}" rx="2" fill="${cor}"/>`;
}
const PRETO = K.tinta, CRU = K.papel;

// ---------------------------------------------------------------- cena 1: a forma
function cenaForma(t) {
  const rnd = aleatorio(11);
  const tMorf = P('forma', 9), tPerg = P('forma', 11), tFac = P('forma', 13), tSof = P('forma', 17);
  const saida = T.caso;
  const k = E.inOut(prog(t, tMorf, 0.7));
  const sai = E.in(prog(t, saida - 0.05, 0.3));
  const centros = [170, 500, 830];
  let out = '';

  // estruturas desenhadas por baixo dos pontos
  const desenho = E.out(prog(t, tMorf + 0.25, 0.6));
  if (desenho > 0) {
    // tabela
    const tx = centros[0] - 130, ty = 210;
    out += `<g opacity="${desenho}">
      <rect x="${tx}" y="${ty}" width="260" height="250" fill="${K.branco}" stroke="${PRETO}" stroke-width="4.5"/>
      <rect x="${tx}" y="${ty}" width="${260 * desenho}" height="52" fill="${PRETO}"/>
      ${[1, 2, 3].map(i => `<line x1="${tx}" y1="${ty + 52 + i * 49}" x2="${tx + 260 * desenho}" y2="${ty + 52 + i * 49}" stroke="${PRETO}" stroke-width="3"/>`).join('')}
      <line x1="${tx + 96}" y1="${ty}" x2="${tx + 96}" y2="${ty + 250 * desenho}" stroke="${PRETO}" stroke-width="3"/>
      <text x="${tx + 18}" y="${ty + 36}" font-family="${K.texto}" font-weight="700" font-size="24" fill="${CRU}">id</text>
      <text x="${tx + 114}" y="${ty + 36}" font-family="${K.texto}" font-weight="700" font-size="24" fill="${CRU}">fato</text>
    </g>`;
    // documento
    const dx = centros[1] - 120, dy = 200;
    out += PM.folheto({ x: dx, y: dy, w: 240, h: 270, sombra: 9, opacidade: desenho, hachura: true, fundo: EPISODIO.saga.cor },
      `<path d="M40 74V${74 + 150 * desenho}M40 116h${30 * desenho}M40 172h${30 * desenho}M88 172V${172 + 52 * desenho}M88 222h${26 * desenho}" stroke="${PRETO}" stroke-width="4" fill="none"/>`);
    // grafo
    const g = [[centros[2], 225], [centros[2] - 105, 330], [centros[2] + 105, 330], [centros[2], 440]];
    out += [[0, 1], [0, 2], [1, 3], [2, 3], [1, 2]].map(([a, b], i) =>
      PM.barbante(g[a][0], g[a][1], g[b][0], g[b][1], 14, 6, clamp(desenho * 1.4 - i * 0.12))).join('');
  }

  // os doze fatos: aparecem soltos, depois se organizam em três formas
  const destinos = [];
  for (let i = 0; i < 4; i++) destinos.push([centros[0] + 8, 210 + 52 + 24 + i * 49 - 24 + 12]);
  [[centros[1] - 80, 300 - 6], [centros[1] - 80 + 30 + 18, 342], [centros[1] - 80 + 30 + 18, 398], [centros[1] - 80 + 78 + 18, 448]]
    .forEach(p => destinos.push(p));
  [[centros[2], 225], [centros[2] - 105, 330], [centros[2] + 105, 330], [centros[2], 440]].forEach(p => destinos.push(p));
  for (let i = 0; i < 12; i++) {
    const x0 = 120 + rnd() * 760, y0 = 140 + rnd() * 400;
    const t0 = 0.5 + i * 0.14;
    if (t < t0) continue;
    const ki = E.inOut(clamp((k * 1.25) - (i % 4) * 0.06));
    const x = lerp(x0, destinos[i][0], ki), y = lerp(y0, destinos[i][1], ki);
    const s = E.back(prog(t, t0, 0.25));
    const r = i < 4 ? 13 : i < 8 ? 15 : 24;
    out += PM.no(x, y, lerp(17, r, ki), '', s);
  }

  // rótulos
  if (t > tMorf + 0.5) {
    ['relacional', 'documento', 'grafo'].forEach((r, i) => {
      out += PM.carimbo(r, centros[i], 545, 40, t, tMorf + 0.5 + i * 0.1, { ancora: 'middle', fonte: K.texto, peso: 700, rot: 0 });
    });
  }
  // perguntas fáceis e sofridas
  for (let i = 0; i < 3; i++) {
    const cx = centros[i];
    out += PM.carimbo('?', cx, 168, 72, t, tPerg + i * 0.08, { ancora: 'middle' });
    if (t > tFac + i * 0.06) {
      const q = E.out(prog(t, tFac + i * 0.06, 0.35));
      out += `<rect x="${cx - 95}" y="582" width="${190 * q}" height="12" fill="${K.destaque}"/>`;
      out += `<path d="M${cx - 34} 640l18 18 36-40" fill="none" stroke="${PRETO}" stroke-width="9" stroke-linecap="round" stroke-dasharray="90" stroke-dashoffset="${90 * (1 - q)}"/>`;
    }
    if (t > tSof + i * 0.06) {
      const q = prog(t, tSof + i * 0.06, 0.5);
      const rr = aleatorio(40 + i);
      let d = `M${cx + 50} 630`;
      for (let j = 0; j < 9; j++) d += `Q${cx + 20 + rr() * 90} ${600 + rr() * 80} ${cx + 30 + rr() * 70} ${610 + rr() * 60}`;
      out += `<path d="${d}" fill="none" stroke="${PRETO}" stroke-width="5" stroke-linecap="round" stroke-dasharray="1400" stroke-dashoffset="${1400 * (1 - q)}"/>`;
    }
  }
  return `<g transform="translate(0 ${-sai * 120})" opacity="${1 - sai}">${out}</g>`;
}

function tipoForma(t, f) {
  const saida = T.caso - 0.05;
  if (t > saida + 0.3) return '';
  let s = PM.blocoDeTipo(f, t, [
    { txt: 'O FORMATO', t: P('forma', 2) },
    { txt: 'DECIDE', t: P('forma', 9), tam: 1.25 },
  ], { saida });
  // fáceis × sofrimento: duas palavras que viram sinal gráfico
  const z = f.tipo, y = z.y + z.tam * 2.55 + 70, tam = z.tam * 0.46;
  if (t < saida + 0.3) {
    s += PM.carimbo('fáceis', z.x, y, tam, t, P('forma', 13), { fonte: K.texto, peso: 700, sublinhar: P('forma', 13) + 0.1, saida });
    const tS = P('forma', 17);
    if (t > tS) {
      const tremor = Math.max(0, 1 - (t - tS) / 0.9) * 5;
      const xs = z.x + medir('fáceis', tam, K.texto, 700) + 60;
      const letras = [...'sofrimento'];
      let x = xs;
      const rr = aleatorio(Math.floor(t * 20));
      letras.forEach(l => {
        s += PM.carimbo(l, x + (rr() - 0.5) * tremor * 2, y + (rr() - 0.5) * tremor * 2, tam, t, tS, { fonte: K.texto, peso: 700, rot: (rr() - 0.5) * tremor * 3, saida });
        x += medir(l, tam, K.texto, 700);
      });
    }
  }
  return s;
}

// ---------------------------------------------------------------- cenas 2 e 3: a ficha e a cópia
function fichaPaciente(i, t, nomeAtual, destaqueMedico) {
  const num = ['0142', '0387', '0911'][i];
  const linhas = [
    `<rect x="0" y="0" width="270" height="62" fill="${PRETO}"/>`,
    `<text x="20" y="42" font-family="${K.titulo}" font-size="26" fill="${CRU}">PACIENTE</text>`,
    `<text x="254" y="41" text-anchor="end" font-family="${K.texto}" font-weight="700" font-size="17" fill="${CRU}">#${num}</text>`,
    `<rect x="22" y="86" width="150" height="12" fill="${K.tintaSuave}" opacity=".5"/><rect x="22" y="110" width="200" height="12" fill="${K.tintaSuave}" opacity=".5"/>`,
    `<text x="22" y="164" font-family="${K.texto}" font-weight="700" font-size="24" fill="${PRETO}">consultas</text>`,
    `<path d="M30 176V318M30 226h18M30 302h18" stroke="${PRETO}" stroke-width="3.5" fill="none"/>`,
  ];
  [0, 1].forEach(j => {
    const y = 214 + j * 76;
    const nome = nomeAtual(j);
    const w = medir(nome, 26, K.texto, 700);
    if (destaqueMedico > 0) linhas.push(`<rect x="54" y="${y - 2}" width="${(w + 14) * destaqueMedico}" height="34" fill="${K.destaque}"/>`);
    linhas.push(nomeSvg(nome, 60, y + 24, 26));
    linhas.push(`<text x="60" y="${y + 52}" font-family="${K.texto}" font-style="italic" font-size="21" fill="${K.tintaSuave}">${j ? 'retorno' : 'cardiologia'}</text>`);
  });
  return linhas.join('');
}

function cenaFicha(t) {
  if (t < T.caso || t > T.grafo + 0.4) return '';
  const tLinha = T.caso, tSaida = P('copia', 18);
  const sai = E.in(prog(t, tSaida - 0.12, 0.3));
  let out = `<g opacity="${1 - sai}" transform="translate(0 ${-sai * 60})">${PM.barbante(-30, 70, 1030, 70, 36, 7, E.out(prog(t, tLinha, 0.45)))}</g>`;
  const tMed = P('copia', 1), tNovo1 = P('copia', 9), tNovo3 = P('copia', 12), tParte = P('copia', 16);
  const atualizado = [tNovo1 + 0.12, Infinity, tNovo3 + 0.12];
  for (let i = 0; i < 3; i++) {
    const t0 = P('caso', 2) + i * 0.17;
    if (t < t0) continue;
    const x = 40 + i * 320, queda = E.out(prog(t, t0, 0.3));
    const rot = pendulo(t - t0, 10 - i * 2, 1.0, 2.2);
    const y = 70 + 16 - (1 - queda) * 500;
    const destaque = E.out(prog(t, tMed + i * 0.08, 0.3));
    const miolo = fichaPaciente(i, t, () => (t > atualizado[i] ? nomeNovo : nomeAntigo), destaque);
    out += `<g transform="translate(0 ${sai * 260})" opacity="${1 - sai}">${PM.folheto({ x, y, w: 270, h: 400, rot, px: 135, py: 0, sombra: 10 }, miolo)}${PM.pregador(x + 135, y - 2, 1, rot * 0.4)}</g>`;
  }
  // o carimbo de mão que atualiza só parte das fichas
  for (const [alvo, tc] of [[0, tNovo1], [2, tNovo3]]) {
    const d = t - (tc - 0.25);
    if (d < 0 || d > 0.75) continue;
    const desce = d < 0.25 ? E.in(d / 0.25) : d < 0.4 ? 1 : 1 - E.out((d - 0.4) / 0.35);
    const x = 40 + alvo * 320 + 135, y = lerp(-20, 250, desce);
    out += `<g transform="translate(${x} ${y})" opacity="${clamp(desce * 3)}">
      <rect x="-26" y="-150" width="52" height="110" rx="20" fill="${K.madeira}" stroke="${PRETO}" stroke-width="4"/>
      <rect x="-90" y="-44" width="180" height="40" fill="${K.madeiraEscura}" stroke="${PRETO}" stroke-width="4"/>
      <rect x="-96" y="-6" width="192" height="22" fill="${PRETO}"/></g>`;
  }
  // divergência: o mesmo médico com dois nomes
  if (t > tParte && t < tSaida) {
    [0, 1].forEach(j => { out += PM.carimbo('≠', 335 + j * 320, 330, 90, t, tParte + j * 0.12, { ancora: 'middle', rot: 0 }); });
  }
  // relatório mensal
  const tRel = P('copia', 18);
  if (t > tRel) {
    const ent = E.out(prog(t, tRel, 0.45));
    const tDiv = P('copia', 25), tDois = P('copia', 27);
    const div = E.inOut(prog(t, tDiv, 0.55));
    const barras = [['Dr. Costa', 0.55], ['Dr. Souza', 0.42]];
    let miolo = `<text x="40" y="70" font-family="${K.titulo}" font-size="40" fill="${PRETO}">Relatório mensal</text>
      <text x="40" y="112" font-family="${K.texto}" font-style="italic" font-size="26" fill="${K.tintaSuave}">consultas por médico</text>`;
    const bx = 250, bw = 500;
    barras.forEach(([n, v], j) => {
      const y = 160 + j * 78;
      miolo += `${nomeSvg(n, 40, y + 38, 26)}
        <rect x="${bx}" y="${y + 8}" width="${bw * v * ent}" height="42" fill="${PRETO}"/>`;
    });
    const yA = 160 + 2 * 78, yB = yA + 78 * div;
    const vA = lerp(0.68, 0.42, div), vB = 0.26 * div;
    miolo += `<rect x="20" y="${yA - 4}" width="800" height="${66 + 78 * div}" fill="${K.destaque}" opacity="${clamp(div * 1.2) * 0.9}"/>`;
    miolo += `${nomeSvg(nomeAntigo, 40, yA + 38, 26)}
      <rect x="${bx}" y="${yA + 8}" width="${bw * vA * ent}" height="42" fill="${PRETO}"/>`;
    if (div > 0) miolo += `<g opacity="${div}">${nomeSvg(nomeNovo, 40, yB + 38, 26)}
      <rect x="${bx + 40}" y="${yB + 8}" width="${bw * vB}" height="42" fill="${PRETO}"/></g>`;
    if (t > tDois) {
      const q = E.out(prog(t, tDois, 0.3));
      miolo += `<path d="M${bx + 40 + bw * 0.42 + 40} ${yA + 10}q30 0 30 30v${40 + 18}q0 20 22 30q-22 10-22 30v${0}q0 30-30 30" fill="none" stroke="${PRETO}" stroke-width="5" stroke-dasharray="320" stroke-dashoffset="${320 * (1 - q)}" transform="translate(0 -20)"/>`;
      miolo += PM.carimbo('2', bx + 40 + bw * 0.42 + 160, yA + 98, 90, t, tDois + 0.1, { ancora: 'middle', rot: -6 });
    }
    const saiR = E.in(prog(t, T.grafo - 0.02, 0.3));
    out += `<g transform="translate(0 ${(1 - ent) * 700}) scale(${1 - saiR * 0.4})" opacity="${1 - saiR}" style="transform-origin:500px 330px">${PM.folheto({ x: 70, y: 110, w: 860, h: 470, sombra: 14 }, miolo)}</g>`;
  }
  return out;
}

function tipoFicha(t, f) {
  let s = '';
  if (t > T.caso && t < T.copia + 0.3) {
    s += PM.blocoDeTipo(f, t, [
      { txt: 'BANCO DE', t: P('caso', 9), tam: 0.8 },
      { txt: 'DOCUMENTOS', t: P('caso', 11) },
      { txt: 'um documento só.', t: P('caso', 16), tam: 0.5, fonte: K.texto, peso: 700, sublinhar: P('caso', 16) + 0.15, respiro: 0 },
    ], { saida: T.copia - 0.12 });
  }
  if (t > T.copia && t < P('copia', 18) + 0.3) {
    s += PM.blocoDeTipo(f, t, [
      { txt: 'UM MÉDICO', t: P('copia', 1) },
      { txt: 'MUDOU O NOME', t: P('copia', 2), tam: 0.8 },
      { txt: 'só em parte das fichas.', t: P('copia', 13), tam: 0.5, fonte: K.texto, peso: 700, sublinhar: P('copia', 15) },
    ], { saida: P('copia', 18) - 0.05 });
  }
  if (t > P('copia', 18) && t < T.grafo + 0.3) {
    s += PM.blocoDeTipo(f, t, [
      { txt: 'O MESMO MÉDICO', t: P('copia', 24), tam: 0.78 },
      { txt: 'COMO SE', t: P('copia', 27) },
      { txt: 'FOSSEM DOIS.', t: P('copia', 29), sublinhar: P('copia', 30) },
    ], { saida: T.grafo - 0.04 });
  }
  return s;
}

// ---------------------------------------------------------------- cena 4: a tentação do grafo
const NOS = [[500, 330], [270, 190], [740, 170], [180, 450], [380, 560], [640, 540], [830, 390], [520, 120], [880, 620], [120, 260]];
const ARESTAS = [[0, 1], [0, 2], [0, 4], [0, 5], [1, 3], [3, 4], [5, 6], [2, 6], [1, 7], [7, 2], [6, 8], [5, 8], [1, 9], [9, 3]];
function cenaGrafo(t) {
  if (t < T.grafo || t > T.consultas + 1.4) return '';
  const tQueda = P('consultas', 6);
  const queda = prog(t, tQueda, 0.7);
  const giro = (t - T.grafo) * 3;
  let out = '';
  ARESTAS.forEach(([a, b], i) => {
    const td = T.grafo + 0.35 + i * 0.1;
    const pa = NOS[a], pb = NOS[b];
    const g = 600 * queda * queda;
    out += `<g opacity="${1 - queda}">${PM.barbante(pa[0], pa[1] + g, pb[0], pb[1] + g * 1.1, 12 + queda * 160, 6, E.out(prog(t, td, 0.35)))}</g>`;
  });
  NOS.forEach(([x, y], i) => {
    const t0 = T.grafo + 0.05 + i * 0.09;
    const g = 700 * queda * queda * (1 + (i % 3) * 0.2);
    out += `<g opacity="${1 - queda}">${PM.no(x, y + g, i === 0 ? 34 : 24, '', E.back(prog(t, t0, 0.28)))}</g>`;
  });
  const rot = [['paciente', 0], ['médico', 2], ['consulta', 4]];
  rot.forEach(([r, i], j) => {
    out += `<g opacity="${1 - queda}">${PM.carimbo(r, NOS[i][0], NOS[i][1] + 66, 28, t, T.grafo + 1.2 + j * 0.15, { ancora: 'middle', fonte: K.texto, peso: 700, rot: 0 })}</g>`;
  });
  [['indicou', 1, 3], ['encaminhou', 2, 6]].forEach(([r, a, b], j) => {
    const x = (NOS[a][0] + NOS[b][0]) / 2, y = (NOS[a][1] + NOS[b][1]) / 2;
    out += `<g opacity="${1 - queda}">${PM.carimbo(r, x + 18, y - 4, 24, t, T.grafo + 1.6 + j * 0.15, { fonte: K.texto, peso: 400, rot: 0, cor: K.tintaSuave })}</g>`;
  });
  return `<g transform="rotate(${giro} 500 380)">${out}</g>`;
}

function tipoGrafo(t, f) {
  if (t < T.grafo || t > T.consultas + 0.3) return '';
  return PM.blocoDeTipo(f, t, [
    { txt: 'MIGRAR', t: P('grafo', 4), tam: 1.15 },
    { txt: 'TUDO', t: P('grafo', 5), tam: 1.15 },
    { txt: 'pra um banco de grafo.', t: P('grafo', 8), tam: 0.5, fonte: K.texto, peso: 700 },
  ], { saida: T.consultas - 0.05 });
}

// ---------------------------------------------------------------- cena 5: as consultas
function cenaConsultas(t) {
  if (t < P('consultas', 8) || t > T.aceita + 0.5) return '';
  const tC = P('consultas', 9), tF = P('ferramenta', 0), tD = P('ferramenta', 1);
  const sai = E.in(prog(t, T.aceita - 0.3, 0.25));
  let out = `<g opacity="${1 - sai}">${PM.barbante(-30, 60, 1030, 60, 30, 7, E.out(prog(t, tC - 0.25, 0.4)))}</g>`;
  const cartoes = [
    ['abrir a ficha', 'milhares', 'por dia', 46],
    ['indicações', '1×', 'por semana', 1],
    ['relatório', '1×', 'por mês', 1],
  ];
  const frente = E.out(prog(t, tD, 0.4));
  cartoes.forEach(([titulo, n, por, marcas], i) => {
    const t0 = tC + i * 0.16;
    if (t < t0) return;
    const x = 30 + i * 325, queda = E.out(prog(t, t0, 0.28));
    const y = 76 - (1 - queda) * 140;
    const rot = pendulo(t - t0, 8 - i * 2, 1.1, 2.4);
    let miolo = `<rect width="280" height="70" fill="${PRETO}"/>
      <text x="140" y="46" text-anchor="middle" font-family="${K.titulo}" font-size="${titulo.length > 11 ? 26 : 30}" fill="${CRU}">${esc(titulo)}</text>
      <text x="140" y="${n.length > 3 ? 158 : 166}" text-anchor="middle" font-family="${K.titulo}" font-size="${n.length > 3 ? 50 : 80}" fill="${PRETO}">${esc(n)}</text>
      <text x="140" y="206" text-anchor="middle" font-family="${K.texto}" font-style="italic" font-size="28" fill="${PRETO}">${por}</text>`;
    // marcas de contagem: risquinhos de giz, agrupados de cinco
    const vis = Math.floor(marcas * clamp((t - t0 - 0.2) / 0.8));
    for (let m = 0; m < vis; m++) {
      const g = Math.floor(m / 5), p = m % 5;
      const gx = 26 + (g % 5) * 48, gy = 236 + Math.floor(g / 5) * 34;
      miolo += p < 4 ? `<line x1="${gx + p * 9}" y1="${gy}" x2="${gx + p * 9}" y2="${gy + 26}" stroke="${PRETO}" stroke-width="3.5"/>`
        : `<line x1="${gx - 4}" y1="${gy + 20}" x2="${gx + 32}" y2="${gy + 6}" stroke="${PRETO}" stroke-width="3.5"/>`;
    }
    const fundo = i === 0 ? EPISODIO.saga.cor : K.branco;
    out += `<g opacity="${1 - sai}" transform="translate(0 ${sai * 200}) translate(${x + 140} 76) scale(${1 + frente * 0.03}) translate(${-x - 140} -76)">
      ${PM.folheto({ x, y, w: 280, h: i === 0 ? 420 : 320, rot, px: 140, py: 0, fundo, hachura: i === 0, sombra: 10, opacidade: clamp(queda * 2.5) }, miolo)}${PM.pregador(x + 140, y - 4, 1, rot * 0.4)}</g>`;
  });
  // ferramenta vem depois: o banco aparece e vai para o fundo da fila
  if (t > tF) {
    const s = E.back(prog(t, tF, 0.25));
    const recua = E.inOut(prog(t, tD, 0.5));
    const y = lerp(640, 690, recua);
    out = `<g opacity="${(1 - recua * 0.55) * (1 - sai)}">${PM.cilindro(500, y, lerp(200, 150, recua), lerp(150, 110, recua), K.branco, s)}
      ${PM.carimbo('banco', 500 + lerp(140, 110, recua), y + 10, 32, t, tF + 0.15, { fonte: K.texto, peso: 700, rot: 0 })}</g>` + out;
  }
  return out;
}

function tipoConsultas(t, f) {
  let s = '';
  if (t > T.consultas && t < T.ferramenta + 0.3) {
    s += PM.blocoDeTipo(f, t, [
      { txt: 'você ainda não olhou', t: P('consultas', 4), tam: 0.5, fonte: K.texto, peso: 700 },
      { txt: 'PARA AS', t: P('consultas', 8), tam: 0.8 },
      { txt: 'CONSULTAS.', t: P('consultas', 10), sublinhar: P('consultas', 10) + 0.2 },
    ], { saida: T.ferramenta - 0.04 });
  }
  if (t > T.ferramenta && t < T.aceita + 0.3) {
    s += PM.blocoDeTipo(f, t, [
      { txt: 'FERRAMENTA', t: P('ferramenta', 0) },
      { txt: 'VEM DEPOIS.', t: P('ferramenta', 1), tam: 0.9 },
    ], { saida: T.aceita - 0.3 });
  }
  return s;
}

// ---------------------------------------------------------------- cena 6: o banco aceita tudo
function cenaAceita(t) {
  if (t < T.aceita || t > T.negativo + 0.1) return '';
  const tA = P('aceita', 5);
  const s = E.back(prog(t, T.aceita + 0.02, 0.3));
  let engole = 0, out = '';
  const n = 7;
  for (let i = 0; i < n; i++) {
    const t0 = T.aceita + 0.35 + i * 0.22;
    if (t < t0) continue;
    const k = prog(t, t0, 0.42);
    if (k >= 1) { engole = Math.max(engole, 1 - prog(t, t0 + 0.42, 0.12)); continue; }
    const rr = aleatorio(i + 3);
    const x = lerp(220 + rr() * 560, 500, E.in(k)), y = lerp(-40, 300, E.in(k));
    const esc = lerp(0.55, 0.12, E.in(k));
    out += PM.folheto({ x: x - 135 * esc, y, w: 270, h: 360, escala: esc, rot: (rr() - 0.5) * 40 * (1 - k), sombra: 10, opacidade: clamp(k * 6) },
      `<rect width="270" height="62" fill="${PRETO}"/><rect x="22" y="100" width="${120 + rr() * 100}" height="16" fill="${K.tintaSuave}" opacity=".5"/><rect x="22" y="140" width="${80 + rr() * 120}" height="16" fill="${K.tintaSuave}" opacity=".5"/>`);
  }
  const boca = 0.6 + engole * 0.5;
  const banco = PM.cilindro(500, 520, 380 * (1 + engole * 0.04), 380 * (1 - engole * 0.04), EPISODIO.saga.cor, s, 0, boca);
  return banco + out + (t > tA ? '' : '');
}

function tipoAceita(t, f) {
  if (t < T.aceita || t > T.negativo + 0.2) return '';
  return PM.blocoDeTipo(f, t, [
    { txt: 'o banco não reclama.', t: P('aceita', 1), tam: 0.5, fonte: K.texto, peso: 700 },
    { txt: 'ELE ACEITA', t: P('aceita', 5) },
    { txt: 'TUDO.', t: P('aceita', 6), tam: 1.3 },
  ], { saida: T.negativo });
}

// ---------------------------------------------------------------- cenas 7 e 8: o negativo, a frase e o roubo
function painelNegativo(t, f) {
  if (t < T.negativo || t > T.puxao + 0.7) return '';
  const vertical = f.W < f.H;
  const sobe = E.in(prog(t, T.puxao, 0.5));
  const dy = -sobe * (f.H + 200);
  const entra = 1;
  const soco = 1 + 0.035 * (1 - E.out(prog(t, T.negativo, 0.18)));
  const m = 52;
  let c = `<rect x="${m + 14}" y="${m + 14}" width="${f.W - 2 * m}" height="${f.H - 2 * m}" fill="${K.destaque}" stroke="${PRETO}" stroke-width="3"/>
    <rect x="${m}" y="${m}" width="${f.W - 2 * m}" height="${f.H - 2 * m}" fill="${PRETO}"/>
    <rect x="${m}" y="${m}" width="${f.W - 2 * m}" height="${f.H - 2 * m}" fill="url(#hachuraClara)"/>
    <rect x="${m + 16}" y="${m + 16}" width="${f.W - 2 * m - 32}" height="${f.H - 2 * m - 32}" fill="none" stroke="${CRU}" stroke-width="3"/>`;
  const L = vertical ? [
    ['O BUG', 'bug', 1, 210, 520], ['NÃO LIGA PRO', 'bug', 2, 92, 650], ['BANCO,', 'bug', 5, 170, 820],
    ['ELE LIGA PRA ONDE', 'bug', 6, 72, 1010], ['O DADO ESTÁ', 'bug', 10, 92, 1120], ['COPIADO.', 'bug', 13, 176, 1310],
  ] : [
    ['O BUG NÃO LIGA PRO', 'bug', 1, 100, 300], ['BANCO,', 'bug', 5, 150, 450],
    ['ELE LIGA PRA ONDE O DADO ESTÁ', 'bug', 6, 64, 620], ['COPIADO.', 'bug', 13, 190, 820],
  ];
  const cx = f.W / 2;
  let yBanco = 0, wBanco = 0, tamBanco = 0;
  L.forEach(([txt, id, i, tam, y]) => {
    let tt = tam; const w = medir(txt, tt);
    if (w > f.W - 240) tt *= (f.W - 240) / w;
    const ehCopia = txt === 'COPIADO.';
    if (txt === 'BANCO,') { yBanco = y; wBanco = medir(txt, tt); tamBanco = tt; }
    if (ehCopia && t > P(id, i) + 0.12) {
      for (let j = 4; j >= 1; j--) {
        const q = E.out(prog(t, P(id, i) + 0.12 + j * 0.07, 0.25));
        if (q <= 0) continue;
        c += `<g opacity="${0.5 - j * 0.09}" transform="translate(${j * 16 * q} ${j * 18 * q})"><text x="${cx}" y="${y}" text-anchor="middle" font-family="${K.titulo}" font-size="${tt}" fill="none" stroke="${K.destaque}" stroke-width="2.5">${txt}</text></g>`;
      }
    }
    c += PM.carimbo(txt, cx, y, tt, t, P(id, i), { ancora: 'middle', cor: ehCopia ? K.destaque : CRU, rot: ehCopia ? -2 : null });
  });
  // o banco riscado
  const tRisco = P('bug', 5) + 0.35;
  if (t > tRisco) {
    const q = E.out(prog(t, tRisco, 0.3));
    c += `<path d="M${cx - wBanco / 2 - 20} ${yBanco - tamBanco * 0.3}L${cx - wBanco / 2 - 20 + (wBanco + 40) * q} ${yBanco - tamBanco * 0.38 - 10 * q}" stroke="${K.destaque}" stroke-width="${tamBanco * 0.13}" stroke-linecap="round"/>`;
  }
  // o bug caminha até onde está a cópia
  const tB = P('bug', 6) - 0.1, tChega = P('bug', 13) + 0.1;
  if (t > tB) {
    const k = E.inOut(prog(t, tB, tChega - tB));
    const yc = vertical ? 1310 : 820;
    const x0 = f.W + 100, y0 = vertical ? 1800 : 1100;
    const x1 = vertical ? f.W - 160 : f.W - 290, y1 = yc + (vertical ? 30 : 110);
    const x = lerp(x0, x1, k), y = lerp(y0, y1, k) + Math.sin(k * 9) * 10;
    c += PM.inseto(x, y, vertical ? 0.9 : 1, -40 + k * 10, (t - tB) * 26 * (1 - k * 0.8), CRU, PRETO);
  }
  // o pregador que vem roubar a frase
  const tP = P('roubar', 0);
  let topo = '';
  if (t > tP) {
    const desce = E.out(prog(t, tP, 0.4));
    const yP = lerp(-140, m + 30, desce);
    topo = `<path d="M${cx} -40V${yP - 20}" stroke="${K.sisal.base}" stroke-width="9"/><path d="M${cx} -40V${yP - 20}" stroke="${K.sisal.fio}" stroke-width="6"/>
      <path d="M${cx} -40V${yP - 20}" stroke="${K.sisal.torcao}" stroke-width="4" stroke-dasharray="2 7"/>${PM.pregador(cx, yP, 2.3)}`;
  }
  return `<g transform="translate(${f.W / 2} ${dy + f.H / 2}) scale(${soco}) translate(${-f.W / 2} ${-f.H / 2})">${c}${topo}</g>`;
}

// ---------------------------------------------------------------- cena 9: quem é o dono
function cenaDono(t) {
  if (t < T.puxao || t > T.fim + 0.5) return '';
  const tJ = P('dono', 0), tDono = P('dono', 4);
  const junta = E.inOut(prog(t, tJ + 0.1, 0.65));
  const sai = E.in(prog(t, T.fim - 0.2, 0.25));
  let out = '';
  const n = 7;
  for (let i = n - 1; i >= 0; i--) {
    const rr = aleatorio(i * 13 + 5);
    const x0 = 60 + rr() * 640, y0 = 40 + rr() * 380, r0 = (rr() - 0.5) * 30;
    const x = lerp(x0, 365, junta), y = lerp(y0, 150, junta), r = lerp(r0, i === 0 ? -2 : (rr() - 0.5) * 6, junta);
    const op = i === 0 ? 1 : 1 - clamp((junta - 0.75) * 4);
    const nome = rr() > 0.5 ? nomeNovo : nomeAntigo;
    out += PM.folheto({ x, y, w: 270, h: 360, rot: r, sombra: 10, opacidade: op },
      `<rect width="270" height="62" fill="${PRETO}"/><text x="22" y="42" font-family="${K.titulo}" font-size="28" fill="${CRU}">MÉDICO</text>
       ${nomeSvg(i === 0 && junta > 0.9 ? nomeNovo : nome, 22, 120, i === 0 && junta > 0.9 ? 30 : 26)}
       <rect x="22" y="150" width="${110 + rr() * 110}" height="14" fill="${K.tintaSuave}" opacity=".5"/><rect x="22" y="182" width="${90 + rr() * 120}" height="14" fill="${K.tintaSuave}" opacity=".5"/>`);
  }
  // a etiqueta "dono", amarrada com sisal
  if (t > tDono) {
    const q = E.out(prog(t, tDono, 0.3));
    const ang = pendulo(t - tDono, 18, 0.9, 2.6) + 8;
    out += `<g transform="translate(${635} ${190 - (1 - q) * 80}) rotate(${ang})" opacity="${q}">
      <path d="M0 0C-20 -10 -30 -26 -24 -44" stroke="${K.sisal.base}" stroke-width="7" fill="none"/><path d="M0 0C-20 -10 -30 -26 -24 -44" stroke="${K.sisal.fio}" stroke-width="5" fill="none"/>
      <polygon points="24,-30 230,-30 230,46 24,46 4,8" fill="${PRETO}" transform="translate(6 6)"/>
      <polygon points="24,-30 230,-30 230,46 24,46 4,8" fill="${EPISODIO.saga.cor}" stroke="${PRETO}" stroke-width="3.5"/>
      <polygon points="24,-30 230,-30 230,46 24,46 4,8" fill="url(#hachura)"/>
      <circle cx="22" cy="8" r="7" fill="${PRETO}"/>
      <text x="48" y="26" font-family="${K.titulo}" font-size="48" fill="${PRETO}">DONO</text></g>`;
  }
  return `<g opacity="${1 - sai}" transform="translate(0 ${sai * 80})">${out}</g>`;
}

function tipoDono(t, f) {
  if (t < T.dono - 0.1 || t > T.fim + 0.4) return '';
  return PM.blocoDeTipo(f, t, [
    { txt: 'descobre', t: P('dono', 0), tam: 0.5, fonte: K.texto, peso: 700 },
    { txt: 'QUEM É O DONO', t: P('dono', 1), tam: 0.95 },
    { txt: 'DO DADO.', t: P('dono', 5), tam: 1.15, sublinhar: P('dono', 6) + 0.1 },
  ], { saida: T.fim - 0.2 });
}

// ---------------------------------------------------------------- cena 10: a toca e a assinatura
function encerramento(t, f, t0 = T.fim) {
  if (t < t0) return '';
  const d = t - t0;
  const vertical = f.W < f.H;
  const saga = EPISODIO.saga;
  // área da toca
  const box = vertical ? { x: 90, y: 700, w: 900, h: 640 } : { x: 120, y: 190, w: 820, h: 700 };
  const chao = box.y + box.h * 0.2;
  const camadas = [['o quê', K.papel2], ['como', K.papel3], ['por quê', '#b9a67d']];
  const hc = (box.y + box.h - chao) / 3;
  let toca = '';
  camadas.forEach(([rot, cor], i) => {
    const q = E.out(prog(d, 0.15 + i * 0.12, 0.45));
    const y = chao + i * hc;
    toca += `<rect x="${box.x}" y="${lerp(box.y + box.h + 40, y, q)}" width="${box.w}" height="${hc + 2}" fill="${cor}" stroke="${PRETO}" stroke-width="3"/>`;
    toca += PM.carimbo(rot, box.x + box.w - 24, y + hc / 2 + 16, 44, d, 0.55 + i * 0.12, { ancora: 'end', rot: 0 });
  });
  // pedras de xilogravura
  const rr = aleatorio(77);
  for (let i = 0; i < 9; i++) {
    const q = E.out(prog(d, 0.6 + i * 0.03, 0.3));
    toca += `<ellipse cx="${box.x + 30 + rr() * (box.w - 260)}" cy="${chao + 30 + rr() * (box.h * 0.8 - 60)}" rx="${8 + rr() * 8}" ry="${5 + rr() * 4}" fill="${PRETO}" opacity="${0.55 * q}"/>`;
  }
  // chão com mato
  const linhaChao = E.out(prog(d, 0, 0.35));
  toca += `<line x1="${box.x - 30}" y1="${chao}" x2="${box.x - 30 + (box.w + 60) * linhaChao}" y2="${chao}" stroke="${PRETO}" stroke-width="5"/>`;
  toca += `<path d="M${box.x + 40} ${chao}c2-14 8-22 16-28m-8 28c0-10-6-18-14-24M${box.x + box.w - 120} ${chao}c2-16 9-26 19-32m-11 32c-1-12-8-20-16-24" stroke="${PRETO}" stroke-width="4" fill="none" opacity="${linhaChao}"/>`;
  // túnel: a toca vai do o quê até o porquê
  const bx = box.x + box.w * 0.62;
  const tunel = `M${bx} ${chao}c0 ${hc * 0.5} ${-box.w * 0.18} ${hc * 0.5} ${-box.w * 0.2} ${hc * 1.05}s${box.w * 0.18} ${hc * 0.55} ${box.w * 0.1} ${hc * 1.0}s${-box.w * 0.3} ${hc * 0.3} ${-box.w * 0.34} ${hc * 0.68}`;
  const tCava = 1.15, durCava = 1.25;
  const cava = E.inOut(prog(d, tCava, durCava));
  const cam = PM.caminho(tunel);
  toca += `<path d="${tunel}" fill="none" stroke="${K.branco}" stroke-width="46" stroke-linecap="round" stroke-dasharray="${cam.L + 10}" stroke-dashoffset="${(cam.L + 10) * (1 - cava)}"/>`;
  toca += `<ellipse cx="${bx}" cy="${chao}" rx="${30 * linhaChao}" ry="7" fill="${K.branco}" stroke="${PRETO}" stroke-width="3"/>`;
  // o peba: chega andando, cava e desce pela toca
  const larg = vertical ? 150 : 132;
  const altura = larg * 80 / 128;
  if (d < tCava) {
    const anda = E.out(prog(d, 0.2, 0.9));
    const x = lerp(box.x - 160, bx - larg * 0.15, anda);
    toca += PM.peba(x, chao + 2, larg, PRETO, CRU, true, d * 18 * (1 - anda));
  } else {
    // O símbolo do peba olha para a esquerda; espelhado, ele olha para onde anda.
    // O focinho gira do chão para dentro da toca e o casco fica sempre para cima.
    const s = Math.min(cava * cam.L, cam.L - 1);
    const [px, py, angCaminho] = cam.ponto(s);
    const k = E.inOut(clamp(s / 70));
    // chegando no porquê, o peba se acomoda deitado na câmara
    const ang = lerp(lerp(0, angCaminho, k), 180, E.out(prog(d, tCava + durCava - 0.1, 0.4)));
    const sy = cam.lado(s);
    const esc = lerp(1, 0.82, k);
    toca += `<g transform="translate(${px - (1 - k) * larg * 0.15} ${py - (1 - k) * altura * 0.5}) rotate(${ang}) scale(${esc} ${sy * esc})">${PM.peba(0, altura / 2, larg, PRETO, K.branco, true, d * 20 * (1 - cava))}</g>`;
  }
  const brilho = d > tCava + durCava ? E.back(prog(d, tCava + durCava, 0.3)) : 0;
  const [fx, fy] = cam.ponto(cam.L);
  if (brilho > 0) toca += `<g fill="${K.destaque}" stroke="${PRETO}" stroke-width="2">${[[-70, -18, 9], [-88, -44, 6], [-52, -50, 7]].map(([a, b, r]) => `<circle cx="${fx + a}" cy="${fy + b}" r="${r * brilho}"/>`).join('')}</g>`;
  // texto da assinatura
  const tx = vertical ? f.W / 2 : 1000, anc = vertical ? 'middle' : 'start';
  const yNome = vertical ? 370 : 330;
  let tipo = PM.carimbo('Pebacast', tx, yNome, vertical ? 168 : 150, d, 1.0, { ancora: anc, rot: 0 });
  const frase1 = 'Cava até achar', frase2 = 'o porquê.';
  const tamF = vertical ? 80 : 74;
  const yF = yNome + (vertical ? 120 : 112);
  tipo += PM.carimbo(frase1, tx, yF, tamF, d, 1.45, { ancora: anc, rot: 0 });
  const tSub = tCava + durCava;
  tipo += PM.carimbo(frase2, tx, yF + tamF * 1.08, tamF, d, 1.75, { ancora: anc, rot: 0 });
  if (d > tSub) {
    const q = E.out(prog(d, tSub, 0.4));
    const wP = medir('porquê', tamF), w0 = medir('o ', tamF), wAll = medir(frase2, tamF);
    const x0 = vertical ? tx - wAll / 2 + w0 : tx + w0;
    tipo += `<rect x="${x0}" y="${yF + tamF * 1.08 + 12}" width="${wP * q}" height="${tamF * 0.13}" fill="${K.destaque}"/>`;
  }
  // ficha do episódio
  const yInfo = vertical ? 1480 : 760;
  const infoOp = E.out(prog(d, 2.55, 0.4));
  const largInfo = vertical ? 900 : 800;
  const xInfo = vertical ? (f.W - largInfo) / 2 : 1000;
  const info = PM.folheto({ x: xInfo, y: yInfo + (1 - infoOp) * 40, w: largInfo, h: vertical ? 200 : 190, sombra: 10, opacidade: infoOp },
    `<rect width="170" height="${vertical ? 200 : 190}" fill="${saga.cor}"/><rect width="170" height="${vertical ? 200 : 190}" fill="url(#hachura)"/>
     <line x1="170" y1="0" x2="170" y2="${vertical ? 200 : 190}" stroke="${PRETO}" stroke-width="4"/>
     <text x="85" y="88" text-anchor="middle" font-family="${K.titulo}" font-size="54" fill="${saga.cor}" stroke="${PRETO}" stroke-width="3" paint-order="stroke">DA</text>
     <text x="85" y="150" text-anchor="middle" font-family="${K.titulo}" font-size="64" fill="${saga.cor}" stroke="${PRETO}" stroke-width="3" paint-order="stroke">001</text>
     <text x="200" y="58" font-family="${K.texto}" font-weight="700" font-size="25" fill="${K.tintaSuave}">Saga ${saga.nome} · episódio 1 de 6</text>
     <text x="200" y="104" font-family="${K.titulo}" font-size="34" fill="${PRETO}">Modelos de dados:</text>
     <text x="200" y="146" font-family="${K.titulo}" font-size="34" fill="${PRETO}">relacional, documento e grafo</text>`);
  const urlOp = E.out(prog(d, 2.9, 0.4));
  const yUrl = vertical ? 1770 : 1010;
  const url = `<g opacity="${urlOp}"><text x="${vertical ? f.W / 2 : 1000}" y="${yUrl}" text-anchor="${anc}" font-family="${K.texto}" font-weight="700" font-size="${vertical ? 34 : 30}" fill="${PRETO}">um porquê por dia · ${EPISODIO.site}</text></g>`;
  return { toca, tipo: tipo + info + url };
}

// ---------------------------------------------------------------- composição
function quadro(t, f, { semLegenda = false } = {}) {
  const saga = EPISODIO.saga;
  PM.montar(f, t);
  const [sx, sy] = PM.tremida(t, IMPACTOS);
  const z = f.palco;
  const palco = [cenaForma(t), cenaFicha(t), cenaGrafo(t), cenaConsultas(t), cenaAceita(t), cenaDono(t)].join('');
  const tipo = [tipoForma(t, f), tipoFicha(t, f), tipoGrafo(t, f), tipoConsultas(t, f), tipoAceita(t, f), tipoDono(t, f)].join('');
  const fim = encerramento(t, f);
  const etiqueta = PM.etiqueta(f, t, saga, EPISODIO.codigo, { t0: 0.05, saida: T.fim - 0.05 });
  const noNegativo = t >= T.negativo && t < ini('roubar') - 0.12;
  const legenda = semLegenda || noNegativo ? '' : PM.legenda(f, t, LINHA.clipes, saga, ['bug']);
  return {
    fundo: PM.fundo(f, t, saga),
    cena: `<g transform="translate(${sx} ${sy})">
      <g transform="translate(${z.x} ${z.y}) scale(${z.escala})">${palco}</g>
      ${tipo}${etiqueta}
      ${fim ? fim.toca + fim.tipo : ''}
    </g>`,
    negativo: painelNegativo(t, f),
    legenda,
  };
}

// ---------------------------------------------------------------- encerramento isolado
function quadroEncerramento(t, f) {
  PM.montar(f, t);
  const fim = encerramento(t, f, 0.25);
  return { fundo: PM.fundo(f, t, EPISODIO.saga), cena: fim ? fim.toca + fim.tipo : '', negativo: '', legenda: '' };
}

// ---------------------------------------------------------------- desenho de som
// Cada evento visual relevante vira um efeito; a mixagem lê esta lista.
function eventosSonoros(t0Fim = T.fim) {
  const ev = [];
  const e = (t, tipo, ganho = 1) => ev.push({ t: +t.toFixed(3), tipo, ganho });
  e(0.05, 'papel', 0.6); e(0.1, 'sisal', 0.5);
  for (let i = 0; i < 12; i++) e(0.5 + i * 0.14, 'tique', 0.35);
  e(P('forma', 2), 'carimbo', 0.8); e(P('forma', 9), 'carimbo', 1);
  e(P('forma', 9) + 0.05, 'papel', 0.5);
  [0, 1, 2].forEach(i => e(P('forma', 11) + i * 0.08, 'tique', 0.4));
  e(P('forma', 13), 'carimbo', 0.45); e(P('forma', 17), 'rabisco', 0.6);
  // a ficha
  e(T.caso, 'sisal', 0.7);
  [0, 1, 2].forEach(i => { e(P('caso', 2) + i * 0.17, 'papel', 0.55); e(P('caso', 2) + i * 0.17 + 0.25, 'pregador', 0.6); });
  e(P('caso', 9), 'carimbo', 0.7); e(P('caso', 11), 'carimbo', 1); e(P('caso', 16), 'carimbo', 0.45);
  // a cópia
  e(P('copia', 1), 'carimbo', 0.85); e(P('copia', 2), 'carimbo', 0.7);
  e(P('copia', 9), 'prensa', 1); e(P('copia', 12), 'prensa', 1);
  e(P('copia', 13), 'carimbo', 0.45);
  e(P('copia', 16), 'carimbo', 0.5); e(P('copia', 16) + 0.12, 'carimbo', 0.5);
  e(P('copia', 18) - 0.12, 'papel', 0.8);
  e(P('copia', 24), 'carimbo', 0.7); e(P('copia', 27), 'carimbo', 1); e(P('copia', 29), 'carimbo', 1);
  e(P('copia', 25), 'rasgo', 0.6);
  // o grafo
  e(T.grafo - 0.02, 'papel', 0.7);
  for (let i = 0; i < 10; i++) e(T.grafo + 0.05 + i * 0.09, 'tique', 0.45);
  e(T.grafo + 0.35, 'sisal', 0.8);
  e(P('grafo', 4), 'carimbo', 1); e(P('grafo', 5), 'carimbo', 0.9); e(P('grafo', 8), 'carimbo', 0.45);
  // as consultas
  e(P('consultas', 6), 'queda', 0.8);
  e(P('consultas', 4), 'carimbo', 0.45); e(P('consultas', 8), 'carimbo', 0.7); e(P('consultas', 10), 'carimbo', 1);
  e(P('consultas', 9) - 0.25, 'sisal', 0.6);
  [0, 1, 2].forEach(i => e(P('consultas', 9) + i * 0.16 + 0.2, 'pregador', 0.55));
  e(P('ferramenta', 0), 'carimbo', 1); e(P('ferramenta', 1), 'carimbo', 0.8); e(P('ferramenta', 1), 'papel', 0.4);
  // o banco aceita
  e(T.aceita - 0.05, 'papel', 0.7); e(T.aceita, 'carimbo', 0.8);
  for (let i = 0; i < 7; i++) e(T.aceita + 0.35 + i * 0.22 + 0.42, 'engole', 0.55);
  e(P('aceita', 1), 'carimbo', 0.45); e(P('aceita', 5), 'carimbo', 1); e(P('aceita', 6), 'carimbo', 1);
  // o negativo
  e(T.negativo, 'corte', 1);
  e(P('bug', 1), 'carimbo', 1.1); e(P('bug', 2), 'carimbo', 0.7); e(P('bug', 5), 'carimbo', 1);
  e(P('bug', 5) + 0.35, 'risco', 0.8);
  e(P('bug', 6), 'carimbo', 0.6); e(P('bug', 10), 'carimbo', 0.6); e(P('bug', 13), 'carimbo', 1.1);
  for (let j = 1; j <= 4; j++) e(P('bug', 13) + 0.12 + j * 0.07, 'tique', 0.35);
  for (let x = P('bug', 6) - 0.1; x < P('bug', 13) + 0.1; x += 0.11) e(x, 'passo', 0.18);
  // o roubo
  e(P('roubar', 0), 'sisal', 0.7); e(P('roubar', 0) + 0.38, 'pregador', 1);
  e(T.puxao, 'puxao', 1);
  // o dono
  e(P('dono', 0) + 0.1, 'papel', 0.7); e(P('dono', 1), 'carimbo', 0.8); e(P('dono', 4), 'papel', 0.6); e(P('dono', 4), 'sisal', 0.5);
  e(P('dono', 5), 'carimbo', 1);
  return ev.concat(eventosDoFim(t0Fim));
}

function eventosDoFim(t0) {
  const ev = [];
  const e = (d, tipo, ganho = 1) => ev.push({ t: +(t0 + d).toFixed(3), tipo, ganho });
  e(0, 'papel', 0.6);
  for (let d = 0.25; d < 1.1; d += 0.16) e(d, 'passo', 0.25);
  e(0.55, 'carimbo', 0.35); e(0.67, 'carimbo', 0.35); e(0.79, 'carimbo', 0.35);
  e(1.15, 'cava', 0.9);
  e(1.45, 'carimbo', 0.7); e(1.75, 'carimbo', 0.7); e(2.4, 'brilho', 0.6); e(2.55, 'papel', 0.5);
  return ev;
}

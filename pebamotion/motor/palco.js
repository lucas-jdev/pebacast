// Palco: carrega a identidade do site, a linha do tempo e as cenas do episódio, e expõe para o renderizador
// window.pronto, window.duracao, window.eventos e window.desenhar(t).
// Parâmetros: ep=<id> (obrigatório), f=vertical|horizontal, so=fim, legenda=0, e os do episódio (nomes=0 no DA 001).

(() => {
  const parametros = new URLSearchParams(location.search);
  const episodio = parametros.get('ep');
  const F = PM.FORMATOS[parametros.get('f') || 'vertical'];
  const soFim = parametros.get('so') === 'fim';
  const semLegenda = parametros.get('legenda') === '0';
  const tela = document.getElementById('tela');
  tela.setAttribute('width', F.W);
  tela.setAttribute('height', F.H);
  tela.setAttribute('viewBox', `0 0 ${F.W} ${F.H}`);

  // As paisagens do site são máscaras SVG em variáveis --cena-* do estilo.css: viram blobs, uma vez.
  async function carregarCenas() {
    const css = await (await fetch('../site/estilo.css')).text();
    for (const [, nome, uri] of css.matchAll(/--(cena-[a-z-]+):\s*url\("data:image\/svg\+xml,([^"]+)"\)/g)) {
      const svg = decodeURIComponent(uri);
      PM.cenas[nome] = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
    }
  }

  // Grão de papel gerado aqui, com semente fixa: todo render sai igual e o repositório não carrega imagem.
  async function gerarGrao() {
    const lado = 960, canvas = document.createElement('canvas');
    canvas.width = canvas.height = lado;
    const ctx = canvas.getContext('2d'), img = ctx.createImageData(lado, lado), rnd = PM.aleatorio(7);
    for (let i = 0; i < lado * lado; i++) {
      const g = Math.sqrt(-2 * Math.log(rnd() || 1e-9)) * Math.cos(2 * Math.PI * rnd());
      img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = 40;
      img.data[i * 4 + 3] = Math.max(0, Math.min(255, -g * 64));
    }
    ctx.putImageData(img, 0, 0);
    const blob = await new Promise(ok => canvas.toBlob(ok, 'image/png'));
    return URL.createObjectURL(blob);
  }

  function carregarScript(src) {
    return new Promise((ok, erro) => {
      const s = document.createElement('script');
      s.src = src; s.onload = ok; s.onerror = () => erro(new Error(`não carregou ${src}`));
      document.body.appendChild(s);
    });
  }

  window.pronto = (async () => {
    if (!episodio) throw new Error('falta o parâmetro ep');
    const [grao] = await Promise.all([
      gerarGrao(),
      carregarCenas(),
      fetch(`episodios/${episodio}/linha.json`).then(r => r.json()).then(l => { window.LINHA = l; }),
      document.fonts.load("400 40px 'Alfa Slab One'"),
      document.fonts.load('400 40px Literata'), document.fonts.load('600 40px Literata'),
      document.fonts.load('700 40px Literata'), document.fonts.load('italic 400 40px Literata'),
    ]);
    await carregarScript(`episodios/${episodio}/cenas.js`);
    const lado = Math.max(F.W, F.H);
    window.duracao = soFim ? 6.0 : LINHA.duracao;
    window.eventos = soFim ? eventosDoFim(0.25) : eventosSonoros();
    window.desenhar = t => {
      const q = soFim ? quadroEncerramento(t, F) : quadro(t, F, { semLegenda });
      tela.innerHTML = PM.defs() + q.fundo + q.cena + q.negativo + q.legenda +
        `<image href="${grao}" width="${lado}" height="${lado}" opacity=".55" style="mix-blend-mode:multiply"/>` + PM.moldura(F);
    };
    window.desenhar(0);
    return true;
  })();
})();

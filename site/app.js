// Player dos episódios, filtro do arquivo e botão de copiar o feed. Sem JS, o <audio controls> nativo continua lá e o arquivo mostra tudo.
(() => {
  const VELOCIDADES = [1, 1.25, 1.5, 1.75, 2, 0.75];

  const formatar = (s) => {
    s = Math.max(0, Math.floor(s || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), seg = String(s % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${seg}` : `${m}:${seg}`;
  };

  const players = [...document.querySelectorAll(".player")];

  players.forEach((player) => {
    const audio = player.querySelector("audio");
    const play = player.querySelector(".player__play");
    const barra = player.querySelector(".player__barra");
    const atual = player.querySelector(".player__atual");
    const velocidade = player.querySelector(".player__velocidade");
    const valorDaVelocidade = velocidade.querySelector(".player__velocidade-valor");
    let arrastando = false;

    audio.removeAttribute("controls");
    player.classList.add("player--js");

    const pintar = () => {
      const max = Number(barra.max) || 1;
      barra.style.setProperty("--progresso", `${(Number(barra.value) / max) * 100}%`);
      barra.setAttribute("aria-valuetext", `${formatar(barra.value)} de ${formatar(barra.max)}`);
    };
    pintar();

    play.addEventListener("click", () => {
      if (audio.paused) {
        players.forEach((outro) => outro !== player && outro.querySelector("audio").pause());
        audio.play();
      } else {
        audio.pause();
      }
    });

    audio.addEventListener("play", () => { player.classList.add("player--tocando"); play.setAttribute("aria-label", "Pausar"); });
    audio.addEventListener("pause", () => { player.classList.remove("player--tocando"); play.setAttribute("aria-label", "Tocar"); });
    audio.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(audio.duration)) barra.max = Math.round(audio.duration);
      pintar();
    });
    audio.addEventListener("timeupdate", () => {
      if (arrastando) return;
      barra.value = Math.floor(audio.currentTime);
      atual.textContent = formatar(audio.currentTime);
      pintar();
    });

    barra.addEventListener("input", () => { arrastando = true; atual.textContent = formatar(barra.value); pintar(); });
    barra.addEventListener("change", () => {
      arrastando = false;
      if (audio.readyState === 0) audio.load();
      audio.currentTime = Number(barra.value);
    });

    velocidade.addEventListener("click", () => {
      const proxima = VELOCIDADES[(VELOCIDADES.indexOf(audio.playbackRate) + 1) % VELOCIDADES.length];
      audio.playbackRate = proxima;
      valorDaVelocidade.textContent = `${String(proxima).replace(".", ",")}×`;
    });
  });

  const chamadaParaOuvir = document.querySelector('.hero__acoes a[href="#episodios"]');
  const playDoMaisRecente = document.querySelector("#episodios .player__play");
  if (chamadaParaOuvir && playDoMaisRecente) {
    chamadaParaOuvir.addEventListener("click", () => {
      if (playDoMaisRecente.closest(".player").querySelector("audio").paused) playDoMaisRecente.click();
      setTimeout(() => playDoMaisRecente.focus({ preventScroll: true }));
    });
  }

  // Links antigos apontavam para index.html#sw-001; hoje só o episódio mais recente mora na página inicial.
  const ancora = decodeURIComponent(location.hash.slice(1));
  if (document.getElementById("inicio") && /^[a-z]{2}-\d{3}$/.test(ancora) && !document.getElementById(ancora)) {
    location.replace(`episodios.html#${ancora}`);
  }

  const filtro = document.querySelector(".filtro");
  if (filtro) {
    const opcoes = [...filtro.querySelectorAll(".filtro__opcao")];
    const meses = [...document.querySelectorAll(".mes")];
    const status = filtro.querySelector("[data-filtro-status]");

    const aplicar = (saga) => {
      let visiveis = 0;
      meses.forEach((mes) => {
        const itens = [...mes.querySelectorAll(".item")];
        itens.forEach((item) => {
          item.hidden = Boolean(saga) && item.dataset.saga !== saga;
          if (item.hidden) item.querySelector("audio").pause();
        });
        const doMes = itens.filter((item) => !item.hidden).length;
        mes.hidden = doMes === 0;
        visiveis += doMes;
      });
      opcoes.forEach((opcao) => opcao.setAttribute("aria-pressed", String(opcao.dataset.saga === saga)));
      status.textContent = `${visiveis} ${visiveis === 1 ? "episódio" : "episódios"}`;
    };

    opcoes.forEach((opcao) => opcao.addEventListener("click", () => aplicar(opcao.dataset.saga)));
    filtro.hidden = false;
  }

  document.querySelectorAll("[data-copiar]").forEach((botao) => {
    const aviso = document.createElement("span");
    aviso.className = "so-leitor";
    aviso.setAttribute("role", "status");
    botao.after(aviso);

    botao.addEventListener("click", async () => {
      const campo = document.getElementById(botao.dataset.copiar);
      try {
        await navigator.clipboard.writeText(campo.value);
      } catch {
        campo.select();
        document.execCommand("copy");
      }
      const original = botao.textContent;
      botao.textContent = "Copiado!";
      aviso.textContent = "Endereço do feed copiado.";
      setTimeout(() => { botao.textContent = original; aviso.textContent = ""; }, 1800);
    });
  });
})();

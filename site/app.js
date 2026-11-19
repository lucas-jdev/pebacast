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
    const aviso = player.querySelector("[data-player-aviso]");
    const fonte = audio.querySelector("source");
    let arrastando = false;

    // Carregando: o MP3 vem de um redirect do GitHub Releases e pode demorar.
    const carregando = (sim) => {
      player.classList.toggle("player--carregando", sim);
      play.setAttribute("aria-label", sim ? "Carregando" : audio.paused ? "Tocar" : "Pausar");
    };
    // Erro: volta para "Tocar" e oferece o arquivo, em vez de ficar parado em "Pausar" no 0:00.
    const falhou = () => {
      carregando(false);
      player.classList.remove("player--tocando");
      play.setAttribute("aria-label", "Tocar");
      aviso.textContent = "Não deu pra carregar o áudio. ";
      const baixar = document.createElement("a");
      baixar.href = fonte?.src || audio.currentSrc;
      baixar.textContent = "Baixar o MP3";
      aviso.append(baixar);
    };
    // O erro de um <source> dispara nele, e não no <audio>.
    fonte?.addEventListener("error", falhou);
    audio.addEventListener("error", falhou);
    audio.addEventListener("waiting", () => carregando(true));
    audio.addEventListener("playing", () => { aviso.textContent = ""; carregando(false); });

    audio.removeAttribute("controls");

    const pintar = () => {
      const max = Number(barra.max) || 1;
      barra.style.setProperty("--progresso", `${(Number(barra.value) / max) * 100}%`);
      barra.setAttribute("aria-valuetext", `${formatar(barra.value)} de ${formatar(barra.max)}`);
    };
    pintar();

    play.addEventListener("click", () => {
      if (audio.paused) {
        players.forEach((outro) => outro !== player && outro.querySelector("audio").pause());
        if (audio.readyState < 3) carregando(true);
        audio.play().catch((erro) => { if (erro.name !== "AbortError") falhou(); });
      } else {
        audio.pause();
      }
    });

    audio.addEventListener("play", () => { player.classList.add("player--tocando"); play.setAttribute("aria-label", "Pausar"); });
    // Conta uma audição por episódio e visita no GoatCounter, quando o analytics está ligado.
    audio.addEventListener("play", () => {
      window.goatcounter?.count?.({ path: `ouviu/${player.dataset.episodio}`, title: "Play no site", event: true });
    }, { once: true });
    audio.addEventListener("pause", () => {
      player.classList.remove("player--tocando", "player--carregando");
      play.setAttribute("aria-label", "Tocar");
    });
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
    const arquivo = document.querySelector(".arquivo");
    const lead = document.querySelector("[data-arquivo-lead]");
    const leadOriginal = lead?.textContent;

    // Com uma saga escolhida, a lista vai na ordem do currículo (do mais antigo ao mais novo), que é a ordem em
    // que se ouve uma saga. A ordem muda no DOM, e não só no CSS, para o Tab seguir o que se vê.
    const ordenar = (doCurriculo) => {
      const ordem = doCurriculo ? [...meses].reverse() : meses;
      ordem.forEach((mes) => {
        arquivo.append(mes);
        const lista = mes.querySelector(".mes__lista");
        const itens = [...lista.children].sort((a, b) => Number(a.dataset.ordem) - Number(b.dataset.ordem));
        (doCurriculo ? itens.reverse() : itens).forEach((item) => lista.append(item));
      });
      if (lead) lead.textContent = doCurriculo ? "Na ordem do currículo: do primeiro episódio ao mais recente." : leadOriginal;
    };
    meses.flatMap((mes) => [...mes.querySelectorAll(".item")]).forEach((item, indice) => { item.dataset.ordem = indice; });

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
      ordenar(Boolean(saga));
      opcoes.forEach((opcao) => opcao.setAttribute("aria-pressed", String(opcao.dataset.saga === saga)));
      // No celular a faixa de sagas rola de lado: traz a escolhida para o meio, em vez de deixá-la cortada.
      filtro.querySelector('.filtro__opcao[aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "center" });
      status.textContent = `${visiveis} ${visiveis === 1 ? "episódio" : "episódios"}`;
    };

    // O filtro mora em ?saga= porque o # já é do episódio. replaceState para "voltar" sair da página em vez de desfazer filtro.
    const comSaga = (saga) => {
      const url = new URL(location.href);
      if (saga) url.searchParams.set("saga", saga); else url.searchParams.delete("saga");
      return url;
    };

    opcoes.forEach((opcao) => opcao.addEventListener("click", () => {
      aplicar(opcao.dataset.saga);
      history.replaceState(history.state, "", comSaga(opcao.dataset.saga));
    }));

    const pedida = new URLSearchParams(location.search).get("saga");
    if (pedida && opcoes.some((opcao) => opcao.dataset.saga === pedida)) {
      aplicar(pedida);
      // A lista encolheu depois que o navegador rolou até a âncora: rola de novo para o episódio pedido.
      const alvo = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (alvo && !alvo.hidden) alvo.scrollIntoView();
    }
  }

  // Link para uma dobra (como .../episodios/sw-002/#transcricao): abre a dobra e rola até ela.
  const abrirDobraDaAncora = () => {
    const alvo = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (alvo instanceof HTMLDetailsElement) {
      alvo.open = true;
      alvo.scrollIntoView();
    }
  };
  abrirDobraDaAncora();
  window.addEventListener("hashchange", abrirDobraDaAncora);

  // Vozes no celular: a história fica em 3 linhas até a pessoa pedir para ler.
  document.querySelectorAll(".voz__mais").forEach((botao) => botao.addEventListener("click", () => {
    const aberta = botao.closest(".voz").toggleAttribute("data-aberta");
    botao.setAttribute("aria-expanded", String(aberta));
    botao.textContent = aberta ? "Fechar a história" : "Ler a história";
  }));

  // Curti / não curti. O voto vale por navegador: fica no localStorage para o botão lembrar, e o servidor guarda um por visitante.
  // O corpo vai como texto puro de propósito: é um pedido "simples" de CORS, sem a ida e volta do preflight.
  const guardado = {
    ler: (id) => { try { return localStorage.getItem(`pebacast:voto:${id}`); } catch { return null; } },
    gravar: (id, voto) => {
      try { voto ? localStorage.setItem(`pebacast:voto:${id}`, voto) : localStorage.removeItem(`pebacast:voto:${id}`); } catch { /* modo privado */ }
    },
  };

  document.querySelectorAll(".votos").forEach((bloco) => {
    const { episodio, api } = bloco.dataset;
    const opcoes = [...bloco.querySelectorAll(".votos__opcao[data-voto]")];
    const pergunta = bloco.querySelector(".votos__pergunta");
    const status = bloco.querySelector("[data-votos-status]");
    const textoDaPergunta = pergunta.textContent;
    const formulario = bloco.querySelector("[data-recado]");
    let atual = guardado.ler(episodio);
    let fila = Promise.resolve();

    const marcar = (voto) => opcoes.forEach((opcao) => opcao.setAttribute("aria-pressed", String(opcao.dataset.voto === voto)));
    marcar(atual);

    const enviar = (voto) => fetch(`${api}/votos`, { method: "POST", body: JSON.stringify({ episodio, voto }), keepalive: true })
      .then((resposta) => { if (!resposta.ok) throw new Error(String(resposta.status)); });

    opcoes.forEach((opcao) => opcao.addEventListener("click", () => {
      const anterior = atual;
      const voto = opcao.dataset.voto === atual ? null : opcao.dataset.voto;
      atual = voto;
      marcar(voto);
      pergunta.textContent = textoDaPergunta;
      // Cada pedido grava o estado inteiro; em fila, o último clique é o que fica no servidor.
      fila = fila.then(() => enviar(voto)).then(() => {
        guardado.gravar(episodio, voto);
        status.textContent = voto ? "Voto registrado. Valeu! Se quiser, conte o porquê no campo abaixo." : "Voto removido.";
        if (voto && formulario.dataset.enviado !== "sim") {
          formulario.hidden = false;
          bloco.querySelector("[data-abrir-recado]")?.setAttribute("aria-expanded", "true");
        }
      }).catch(() => {
        if (atual !== voto) return;
        atual = anterior;
        marcar(anterior);
        pergunta.textContent = "Não deu pra registrar. Tenta de novo?";
        status.textContent = "Não deu pra registrar o voto.";
      });
    }));
  });

  // O recado abre pelo botão "Deixar um recado" (sem precisar votar) ou depois de um voto.
  document.querySelectorAll("[data-abrir-recado]").forEach((botao) => {
    const formulario = botao.closest(".votos").querySelector("[data-recado]");
    botao.addEventListener("click", () => {
      formulario.hidden = !formulario.hidden;
      botao.setAttribute("aria-expanded", String(!formulario.hidden));
      if (!formulario.hidden) formulario.elements.texto.focus();
    });
  });

  // Se o servidor de recados falhar, o recado ainda pode ir como issue no GitHub, avisando que lá é público.
  const linkDeIssue = (episodio, texto) => {
    const repositorio = document.querySelector("[data-repositorio]")?.href.replace(/\/$/, "");
    if (!repositorio) return null;
    const parametros = new URLSearchParams({ title: `Recado sobre ${episodio}`, body: texto });
    return `${repositorio}/issues/new?${parametros}`;
  };

  const AVISOS_DO_RECADO = {
    400: "O recado precisa ter entre 3 e 1000 caracteres.",
    429: "Você já mandou recados demais hoje. Tenta amanhã?",
  };

  document.querySelectorAll("[data-recado]").forEach((formulario) => {
    const { episodio, api } = formulario.closest(".votos").dataset;
    const aviso = formulario.querySelector("[data-recado-aviso]");
    const enviar = formulario.querySelector('button[type="submit"]');

    formulario.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const texto = formulario.elements.texto.value.trim();
      if (texto.length < 3) {
        aviso.textContent = AVISOS_DO_RECADO[400];
        formulario.elements.texto.focus();
        return;
      }
      enviar.disabled = true;
      aviso.textContent = "Enviando…";
      try {
        const resposta = await fetch(`${api}/recados`, {
          method: "POST",
          body: JSON.stringify({ episodio, texto, site: formulario.elements.site.value }),
        });
        if (!resposta.ok) throw resposta.status;
        formulario.dataset.enviado = "sim";
        formulario.hidden = true;
        formulario.closest(".votos").querySelector("[data-abrir-recado]")?.setAttribute("aria-expanded", "false");
        formulario.reset();
        const status = formulario.closest(".votos").querySelector(".votos__pergunta");
        status.textContent = "Recado enviado. Valeu!";
        formulario.closest(".votos").querySelector("[data-votos-status]").textContent = "Recado enviado. Valeu!";
      } catch (status) {
        aviso.textContent = AVISOS_DO_RECADO[status] ?? "Não deu pra enviar agora. Tenta de novo?";
        const issue = AVISOS_DO_RECADO[status] ? null : linkDeIssue(episodio, texto);
        if (issue) {
          const link = document.createElement("a");
          link.href = issue;
          link.rel = "noopener";
          link.textContent = "Ou mande pelo GitHub (lá fica público)";
          aviso.append(" ", link);
        }
      } finally {
        enviar.disabled = false;
      }
    });
  });

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

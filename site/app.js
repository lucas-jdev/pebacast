// TEMPORÁRIO (#136): trava o renderer ao rolar, para conferir o teto e o artefato de diagnóstico no CI.
addEventListener("scroll", () => { while (true) {} });
// Player dos episódios, filtro do arquivo e botão de copiar o feed. Sem JS, o <audio controls> nativo continua lá e o arquivo mostra tudo.
(() => {
  const VELOCIDADES = [1, 1.25, 1.5, 1.75, 2, 0.75];

  const formatar = (s) => {
    s = Math.max(0, Math.floor(s || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), seg = String(s % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${seg}` : `${m}:${seg}`;
  };

  const players = [...document.querySelectorAll(".player")];

  // O minuto de um link compartilhado (?t=90) vale uma vez: sai do endereço assim que é lido. Senão, reabrir a
  // mesma mensagem ou restaurar a aba voltaria sempre a ele, por cima de onde a pessoa parou depois.
  // Ele fica no history.state, que sobrevive a um recarregamento (o navegador do WhatsApp recarrega, o Android
  // descarta a aba) mas não a uma nova abertura, até a pessoa tocar.
  const MINUTO_DO_LINK = (() => {
    const url = new URL(location.href);
    const pedido = url.searchParams.has("t") ? Number(url.searchParams.get("t")) : Number(history.state?.minutoDoLink);
    const valido = Number.isInteger(pedido) && pedido > 0 ? pedido : 0;
    url.searchParams.delete("t");
    history.replaceState({ ...history.state, minutoDoLink: valido || undefined }, "", url);
    return valido;
  })();
  const esquecerMinutoDoLink = () => {
    if (history.state?.minutoDoLink) history.replaceState({ ...history.state, minutoDoLink: undefined }, "", location.href);
  };
  const segundosDoLink = (duracao) => (MINUTO_DO_LINK && (!duracao || MINUTO_DO_LINK < duracao) ? MINUTO_DO_LINK : 0);
  const CAPA = new URL("capa-512.jpg", document.currentScript.src).href;
  const SETAS = { ArrowLeft: -5, ArrowDown: -5, ArrowRight: 5, ArrowUp: 5 };

  // Em aba anônima ou com o armazenamento bloqueado, o localStorage lança: o site segue como se nada estivesse salvo.
  const armazenamento = {
    ler: (chave) => { try { return localStorage.getItem(chave); } catch { return null; } },
    gravar: (chave, valor) => { try { localStorage.setItem(chave, valor); } catch { /* modo privado */ } },
    apagar: (chave) => { try { localStorage.removeItem(chave); } catch { /* modo privado */ } },
  };

  // Onde o ouvinte parou, só neste navegador (decidido em 24/11: sem sincronizar entre aparelhos).
  // Passar dos 90% tocando conta como ouvido: quase ninguém espera a vinheta final. Um salto longo para lá não
  // conta, senão um toque errado na trilha (ela fica logo abaixo do volume no celular) marcava o que não foi
  // ouvido. Um +30, na tela ou na de bloqueio, ainda é escuta: quem pula a despedida ouviu o episódio.
  const FRACAO_OUVIDA = 0.9;
  const SALTO_DE_ESCUTA_S = 31;
  const AVISO_SOME_MS = 6000;
  const progresso = {
    posicao: (id) => Number(armazenamento.ler(`pebacast:posicao:${id}`)) || 0,
    ouvido: (id) => armazenamento.ler(`pebacast:ouvido:${id}`) !== null,
    gravarPosicao: (id, segundos) => armazenamento.gravar(`pebacast:posicao:${id}`, String(Math.floor(segundos))),
    esquecerPosicao: (id) => armazenamento.apagar(`pebacast:posicao:${id}`),
    marcarOuvido: (id) => {
      armazenamento.gravar(`pebacast:ouvido:${id}`, new Date().toISOString());
      progresso.esquecerPosicao(id);
    },
  };

  // Na página do episódio o próprio player já diz onde parou: ali o selo diz só se foi ouvido.
  const mostrarProgresso = (id) => document.querySelectorAll(`[data-progresso="${CSS.escape(id)}"]`).forEach((selo) => {
    const posicao = selo.closest(".episodio--pagina") ? 0 : progresso.posicao(id);
    const parou = posicao ? `parou em ${formatar(posicao)}` : "";
    selo.textContent = progresso.ouvido(id) ? ["Ouvido", parou].filter(Boolean).join(" · ") : parou && `P${parou.slice(1)}`;
    selo.hidden = !selo.textContent;
    selo.classList.toggle("progresso--ouvido", progresso.ouvido(id));
  });
  document.querySelectorAll("[data-progresso]").forEach((selo) => mostrarProgresso(selo.dataset.progresso));

  // Volume: um só para o site, lembrado entre visitas. No iOS o audio.volume é só leitura (manda o botão físico),
  // então lá o botão vira "Silenciar" em vez de abrir uma barra que não faria nada.
  const CHAVE_DO_VOLUME = "pebacast:volume";
  const volumeAjustavel = (() => { const teste = new Audio(); teste.volume = 0.5; return teste.volume === 0.5; })();
  const lerVolume = () => {
    const guardado = armazenamento.ler(CHAVE_DO_VOLUME);
    const valor = Number(guardado);
    return guardado !== null && valor >= 0 && valor <= 1 ? valor : 1;
  };
  const gravarVolume = (valor) => armazenamento.gravar(CHAVE_DO_VOLUME, String(valor));
  const estadoDoVolume = (valor) => (valor === 0 ? "mudo" : valor < 0.5 ? "baixo" : "alto");

  const aplicarVolume = (valor) => players.forEach((player) => {
    const nivel = player.querySelector(".player__nivel");
    player.querySelector("audio").volume = valor;
    player.dataset.volume = estadoDoVolume(valor);
    nivel.value = Math.round(valor * 100);
    nivel.style.setProperty("--nivel", `${nivel.value}%`);
    nivel.setAttribute("aria-valuetext", valor === 0 ? "Mudo" : `${nivel.value}%`);
  });

  const aplicarMudo = (mudo) => players.forEach((player) => {
    player.querySelector("audio").muted = mudo;
    player.dataset.volume = mudo ? "mudo" : "alto";
    player.querySelector(".player__volume-botao").setAttribute("aria-pressed", String(mudo));
  });

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
      play.setAttribute("aria-label", sim ? "Carregando" : audio.paused ? rotuloDoPlay() : "Pausar");
    };
    // Erro: volta para "Tocar" e oferece o arquivo, em vez de ficar parado em "Pausar" no 0:00.
    const falhou = () => {
      carregando(false);
      player.classList.remove("player--tocando");
      play.setAttribute("aria-label", "Tocar");
      aviso.textContent = "Não deu pra carregar o áudio. ";
      aviso.dataset.erro = "";
      const baixar = document.createElement("a");
      baixar.href = fonte?.src || audio.currentSrc;
      baixar.textContent = "Baixar o MP3";
      aviso.append(baixar);
    };
    // O erro de um <source> dispara nele, e não no <audio>.
    fonte?.addEventListener("error", falhou);
    audio.addEventListener("error", falhou);
    audio.addEventListener("waiting", () => carregando(true));
    // Tocar de novo limpa o erro, mas não outros avisos, como o de episódio ouvido.
    audio.addEventListener("playing", () => {
      if ("erro" in aviso.dataset) { aviso.textContent = ""; delete aviso.dataset.erro; }
      carregando(false);
    });

    audio.removeAttribute("controls");

    const pintar = () => {
      const max = Number(barra.max) || 1;
      barra.style.setProperty("--progresso", `${(Number(barra.value) / max) * 100}%`);
      barra.setAttribute("aria-valuetext", `${formatar(barra.value)} de ${formatar(barra.max)}`);
    };

    const id = player.dataset.episodio;
    const retomar = player.querySelector("[data-retomar]");
    const doComeco = retomar.querySelector(".player__do-comeco");
    // Com preload="none" o áudio ainda não carregou: a posição salva só vale depois do loadedmetadata.
    // Um link com o minuto (?t=90) começa ali, porque quem mandou quer mostrar aquele trecho; mas, se a pessoa
    // tinha parado em outro ponto, o player oferece voltar para lá, e "Do começo" não apaga esse lugar.
    const doLink = player.closest(".episodio--pagina") ? segundosDoLink(Number(player.dataset.duracao)) : 0;
    const salvo = progresso.posicao(id);
    let retomarEm = doLink || salvo;
    let peloLink = Boolean(doLink);
    // Ouvindo o trecho de um link, com outro lugar salvo, a pessoa está de visita: nada é gravado por cima do
    // lugar dela, e "Voltar a 1:40" fica à mão enquanto toca, até ela escolher voltar ou ouvir do começo.
    let deVisita = Boolean(doLink && salvo && Math.abs(salvo - doLink) >= 5);
    let gravadoEm = 0;
    let tocandoEm = null;
    const motivo = player.querySelector("[data-retomar-motivo]");
    const ondeParei = retomar.querySelector(".player__onde-parei");

    const rotuloDoPlay = () => (!retomarEm ? "Tocar" : peloLink ? `Tocar a partir de ${formatar(retomarEm)}` : `Continuar de ${formatar(retomarEm)}`);
    const posicionar = (segundos) => {
      barra.value = Math.floor(segundos);
      atual.textContent = formatar(segundos);
      pintar();
    };
    const oferecerRetomada = () => {
      retomar.hidden = !retomarEm && !deVisita;
      motivo.parentElement.hidden = !retomarEm;
      doComeco.hidden = !retomarEm;
      motivo.textContent = peloLink ? "O link começa em" : "Você parou em";
      retomar.querySelector("[data-retomar-tempo]").textContent = formatar(retomarEm);
      ondeParei.hidden = !deVisita;
      ondeParei.textContent = `Voltar a ${formatar(salvo)}`;
      ondeParei.setAttribute("aria-label", `Voltar a ${formatar(salvo)}, onde você parou`);
      if (audio.paused) play.setAttribute("aria-label", rotuloDoPlay());
    };
    const desistirDaRetomada = () => { retomarEm = 0; peloLink = false; oferecerRetomada(); };

    const finalDoEpisodio = () => (Number.isFinite(audio.duration) ? audio.duration : Number(player.dataset.duracao)) * FRACAO_OUVIDA;
    // O selo do card só muda quando a pessoa para (pause, sair da página): "parou em" com o áudio tocando confunde.
    const gravarPosicao = ({ atualizarSelo = false } = {}) => {
      if (audio.currentTime < 1 || deVisita) return;
      if (audio.currentTime >= finalDoEpisodio()) progresso.esquecerPosicao(id);
      else progresso.gravarPosicao(id, audio.currentTime);
      gravadoEm = audio.currentTime;
      if (atualizarSelo) mostrarProgresso(id);
    };
    const avisar = (texto) => {
      aviso.textContent = texto;
      setTimeout(() => { if (aviso.textContent === texto) aviso.textContent = ""; }, AVISO_SOME_MS);
    };
    const conferirSeOuviu = () => {
      const agora = audio.currentTime, antes = tocandoEm, limite = finalDoEpisodio();
      tocandoEm = audio.paused ? null : agora;
      const cruzouTocando = antes !== null && antes < limite && agora >= limite && agora - antes <= SALTO_DE_ESCUTA_S;
      if (!cruzouTocando || progresso.ouvido(id)) return;
      progresso.marcarOuvido(id);
      mostrarProgresso(id);
      avisar("Episódio marcado como ouvido.");
    };

    posicionar(retomarEm);
    oferecerRetomada();

    ondeParei.addEventListener("click", () => {
      retomarEm = salvo;
      peloLink = false;
      deVisita = false;
      esquecerMinutoDoLink();
      if (audio.readyState > 0) audio.currentTime = salvo;
      posicionar(salvo);
      oferecerRetomada();
      play.focus();
    });

    doComeco.addEventListener("click", () => {
      const eraDoLink = peloLink;
      deVisita = false;
      esquecerMinutoDoLink();
      desistirDaRetomada();
      if (!eraDoLink) {
        progresso.esquecerPosicao(id);
        mostrarProgresso(id);
      }
      if (audio.readyState > 0) audio.currentTime = 0;
      posicionar(0);
      if (audio.paused) play.click();
      play.focus();
    });

    play.addEventListener("click", () => {
      if (audio.paused) {
        players.forEach((outro) => outro !== player && outro.querySelector("audio").pause());
        if (audio.readyState < 3) carregando(true);
        audio.play().catch((erro) => { if (erro.name !== "AbortError") falhou(); });
      } else {
        audio.pause();
      }
    });

    audio.addEventListener("play", () => {
      player.classList.add("player--tocando");
      play.setAttribute("aria-label", "Pausar");
      esquecerMinutoDoLink();
    });
    // Conta uma audição por episódio e visita no GoatCounter, quando o analytics está ligado.
    audio.addEventListener("play", () => {
      window.goatcounter?.count?.({ path: `ouviu/${player.dataset.episodio}`, title: "Play no site", event: true });
    }, { once: true });
    audio.addEventListener("pause", () => {
      player.classList.remove("player--tocando", "player--carregando");
      play.setAttribute("aria-label", "Tocar");
      gravarPosicao({ atualizarSelo: true });
    });
    audio.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(audio.duration)) barra.max = Math.round(audio.duration);
      if (retomarEm) audio.currentTime = retomarEm;
      pintar();
    });
    audio.addEventListener("timeupdate", () => {
      if (arrastando || (retomarEm && audio.currentTime < 1)) return;
      if (retomarEm) desistirDaRetomada();
      posicionar(audio.currentTime);
      if (!audio.paused && Math.abs(audio.currentTime - gravadoEm) >= 5) gravarPosicao();
      conferirSeOuviu();
    });
    // Fechar a aba no meio do áudio não dispara pause: o pagehide é o último momento garantido para gravar.
    window.addEventListener("pagehide", () => { if (!audio.paused) gravarPosicao({ atualizarSelo: true }); });

    const irPara = (segundos) => {
      const fim = Number.isFinite(audio.duration) ? audio.duration : Number(barra.max);
      const destino = Math.min(Math.max(0, segundos), fim);
      desistirDaRetomada();
      if (audio.readyState === 0) audio.load();
      audio.currentTime = destino;
      posicionar(destino);
    };
    const pular = (segundos) => irPara((audio.readyState ? audio.currentTime : Number(barra.value)) + segundos);

    barra.addEventListener("input", () => { arrastando = true; atual.textContent = formatar(barra.value); pintar(); });
    barra.addEventListener("change", () => { arrastando = false; irPara(Number(barra.value)); });
    // A seta nativa anda 1 s, o que não serve num áudio de 18 min.
    barra.addEventListener("keydown", (evento) => {
      if (!(evento.key in SETAS)) return;
      evento.preventDefault();
      pular(SETAS[evento.key]);
    });
    player.querySelectorAll("[data-pular]").forEach((botao) => botao.addEventListener("click", () => pular(Number(botao.dataset.pular))));

    // Tela de bloqueio e notificação de mídia: capa, título e botões de pular para quem ouve com o celular no bolso.
    const sessao = navigator.mediaSession;
    const atualizarPosicaoNaSessao = () => {
      if (!sessao?.setPositionState || sessao.metadata?.title !== player.dataset.titulo || !Number.isFinite(audio.duration)) return;
      try {
        sessao.setPositionState({ duration: audio.duration, position: Math.min(audio.currentTime, audio.duration), playbackRate: audio.playbackRate });
      } catch { /* posição fora da duração durante um seek */ }
    };
    audio.addEventListener("play", () => {
      if (!sessao) return;
      sessao.metadata = new MediaMetadata({
        title: player.dataset.titulo, artist: "Pebacast", album: player.dataset.rotulo,
        artwork: [{ src: CAPA, sizes: "512x512", type: "image/jpeg" }],
      });
      const acoes = {
        play: () => audio.paused && play.click(),
        pause: () => audio.pause(),
        seekbackward: (detalhes) => pular(-(detalhes.seekOffset || 15)),
        seekforward: (detalhes) => pular(detalhes.seekOffset || 30),
        seekto: (detalhes) => irPara(detalhes.seekTime),
      };
      Object.entries(acoes).forEach(([acao, tratar]) => { try { sessao.setActionHandler(acao, tratar); } catch { /* ação não suportada */ } });
      atualizarPosicaoNaSessao();
    });
    ["loadedmetadata", "seeked", "ratechange"].forEach((evento) => audio.addEventListener(evento, atualizarPosicaoNaSessao));

    velocidade.addEventListener("click", () => {
      const proxima = VELOCIDADES[(VELOCIDADES.indexOf(audio.playbackRate) + 1) % VELOCIDADES.length];
      audio.playbackRate = proxima;
      valorDaVelocidade.textContent = `${String(proxima).replace(".", ",")}×`;
    });

    const volume = player.querySelector(".player__volume");
    const botaoDoVolume = volume.querySelector(".player__volume-botao");
    const painel = volume.querySelector(".player__volume-painel");
    const nivel = painel.querySelector(".player__nivel");

    if (!volumeAjustavel) {
      botaoDoVolume.removeAttribute("aria-expanded");
      botaoDoVolume.removeAttribute("aria-controls");
      botaoDoVolume.setAttribute("aria-label", "Silenciar");
      botaoDoVolume.setAttribute("aria-pressed", "false");
      botaoDoVolume.addEventListener("click", () => aplicarMudo(!audio.muted));
      return;
    }

    // O painel abre para cima; se ali ele ficaria cortado pela tela ou escondido sob o cabeçalho fixo, abre para baixo.
    const abrirVolume = (aberto) => {
      painel.hidden = !aberto;
      botaoDoVolume.setAttribute("aria-expanded", String(aberto));
      if (!aberto) return;
      painel.classList.remove("player__volume-painel--abaixo");
      const limite = document.querySelector(".topo")?.getBoundingClientRect().bottom ?? 0;
      if (painel.getBoundingClientRect().top < Math.max(0, limite)) painel.classList.add("player__volume-painel--abaixo");
    };
    botaoDoVolume.addEventListener("click", () => {
      const abrir = painel.hidden;
      abrirVolume(abrir);
      if (abrir) nivel.focus();
    });
    nivel.addEventListener("input", () => {
      const valor = Number(nivel.value) / 100;
      aplicarVolume(valor);
      gravarVolume(valor);
    });
    volume.addEventListener("keydown", (evento) => {
      if (evento.key !== "Escape" || painel.hidden) return;
      abrirVolume(false);
      botaoDoVolume.focus();
    });
    // Fecha ao sair com Tab ou ao tocar fora. O Safari não dá foco a botão clicado, por isso o focusout
    // sem destino é ignorado: quem cuida do clique fora é o pointerdown.
    volume.addEventListener("focusout", (evento) => {
      if (evento.relatedTarget && !volume.contains(evento.relatedTarget)) abrirVolume(false);
    });
    document.addEventListener("pointerdown", (evento) => {
      if (!painel.hidden && !volume.contains(evento.target)) abrirVolume(false);
    });
  });

  if (volumeAjustavel) aplicarVolume(lerVolume());

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
    const titulo = document.querySelector("[data-arquivo-titulo]");
    const tituloOriginal = titulo?.textContent;
    const tituloDaAba = document.title;
    const proximos = [...document.querySelectorAll("[data-proximo-da-saga]")];

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
      // Com uma saga escolhida, a página é a da saga: o título diz isso, e o fim da lista aponta o próximo dela.
      const nome = opcoes.find((opcao) => opcao.dataset.saga === saga)?.dataset.nome;
      if (titulo) titulo.textContent = saga ? `Saga ${nome}` : tituloOriginal;
      document.title = saga ? `Saga ${nome} · ${tituloDaAba}` : tituloDaAba;
      proximos.forEach((nota) => { nota.hidden = nota.dataset.proximoDaSaga !== saga; });
      // No celular a faixa de sagas rola de lado: traz a escolhida para o meio, em vez de deixá-la cortada.
      filtro.querySelector('.filtro__opcao[aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "center" });
      const quantos = `${visiveis} ${visiveis === 1 ? "episódio" : "episódios"}`;
      status.textContent = saga ? `Saga ${opcoes.find((opcao) => opcao.dataset.saga === saga)?.dataset.nome}: ${quantos}` : quantos;
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
    ler: (id) => armazenamento.ler(`pebacast:voto:${id}`),
    gravar: (id, voto) => (voto ? armazenamento.gravar(`pebacast:voto:${id}`, voto) : armazenamento.apagar(`pebacast:voto:${id}`)),
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

  // Compartilhar sem recarregar (#118): o compartilhar do aparelho quando existe; senão, copia o endereço.
  // Com JS, o link do rodapé do card vira uma linha própria logo abaixo do player e dos votos, com um botão
  // (é uma ação, e não navegação) e, antes dele, a opção de mandar o link já no minuto em que a pessoa está.
  document.querySelectorAll("[data-compartilhar]").forEach((link) => {
    const cartao = link.closest(".episodio, .item");
    const player = cartao?.querySelector(`.player[data-episodio="${CSS.escape(link.dataset.compartilhar)}"]`);
    const audio = player?.querySelector("audio");
    const barra = player?.querySelector(".player__barra");
    const endereco = link.href;

    const linha = document.createElement("p");
    linha.className = "compartilhar";
    linha.innerHTML = '<label class="compartilhar__minuto" hidden><input type="checkbox"><span></span></label>'
      + '<button class="compartilhar__botao" type="button"><svg aria-hidden="true" viewBox="0 0 24 24"><use href="#i-compartilhar"/></svg>Compartilhar</button>'
      + '<span class="compartilhar__aviso" role="status"></span>';
    const minuto = linha.querySelector(".compartilhar__minuto");
    const caixa = minuto.querySelector("input");
    const botao = linha.querySelector("button");
    const status = linha.querySelector(".compartilhar__aviso");
    (cartao.querySelector(".votos") || player?.closest(".player-caixa") || link.closest("p")).after(linha);
    link.previousElementSibling?.matches('[aria-hidden="true"]') && link.previousElementSibling.remove();
    link.remove();

    // Marcada, a caixa guarda o minuto daquele instante: o áudio segue tocando enquanto a pessoa compartilha.
    let congelado = 0;
    const posicao = () => Math.floor(audio ? (audio.currentTime || Number(barra.value)) : 0);
    const minutoDoLink = () => (caixa.checked ? congelado : posicao());
    // O rótulo nomeia a opção ("Incluir o minuto 1:30"), e não a ação: o leitor de tela não ouve
    // "Compartilhar" duas vezes seguidas, na caixa e no botão.
    const escreverMinuto = (segundos) => { minuto.querySelector("span").textContent = `Incluir o minuto ${formatar(segundos)}`; };
    const atualizarMinuto = () => {
      if (caixa.checked) return;
      minuto.hidden = posicao() < 1;
      escreverMinuto(posicao());
    };
    caixa.addEventListener("change", () => {
      congelado = posicao();
      if (caixa.checked) escreverMinuto(congelado);
      else atualizarMinuto();
    });
    audio?.addEventListener("timeupdate", atualizarMinuto);
    audio?.addEventListener("pause", atualizarMinuto);
    atualizarMinuto();

    botao.addEventListener("click", async () => {
      const url = new URL(endereco);
      if (!minuto.hidden && caixa.checked && minutoDoLink() >= 1) url.searchParams.set("t", String(minutoDoLink()));
      const titulo = player?.dataset.titulo || document.title;
      if (navigator.share) {
        try { await navigator.share({ title: titulo, url: url.href }); } catch { /* a pessoa desistiu */ }
        return;
      }
      try {
        await navigator.clipboard.writeText(url.href);
        status.textContent = "Link copiado.";
        setTimeout(() => { status.textContent = ""; }, 2500);
      } catch {
        status.textContent = `Copie o endereço: ${url.href}`;
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
        await navigator.clipboard.writeText(campo.textContent);
      } catch {
        getSelection().selectAllChildren(campo);
        document.execCommand("copy");
      }
      const original = botao.textContent;
      botao.textContent = "Copiado!";
      aviso.textContent = "Endereço do feed copiado.";
      setTimeout(() => { botao.textContent = original; aviso.textContent = ""; }, 1800);
    });
  });
})();

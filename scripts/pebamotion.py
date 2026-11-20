"""Pebamotion: trailers animados dos episódios (ADR 0010).

    python scripts/pebamotion.py transcrever <ep>                 tempo de cada palavra do episódio
    python scripts/pebamotion.py sugerir-cortes <ep>              aproxima entrada e saída de cada recorte do silêncio
    python scripts/pebamotion.py linha <ep>                       monta a voz e grava pebamotion/episodios/<ep>/linha.json
    python scripts/pebamotion.py quadros <ep> -t 3.2 10 [--formato horizontal] [--param nomes=0] [--so-fim]
    python scripts/pebamotion.py produzir <ep> [--refazer]        renderiza as variantes, mixa e junta os MP4

Precisa do extra `motion` (`pip install -e ".[motion]"` e `python -m playwright install chromium`) e do ffmpeg
no PATH. `CHROME=<caminho>` usa outro Chromium. A trilha é a faixa inteira em `assets/vinheta.mp3`
(docs/vinheta.md); o áudio do episódio é baixado do Release. Intermediários ficam em `pebamotion/.cache/<ep>/`
e os vídeos em `pebamotion/saida/<ep>/`, ambos fora do Git.

Tudo que é cálculo (alinhamento, corte no silêncio, ducking, posição da trilha, efeitos) fica em funções puras,
testadas em tests/test_pebamotion.py sem navegador nem ffmpeg.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "pebamotion"
TRILHA = RAIZ / "assets" / "vinheta.mp3"

FPS = 30
SR = 48_000
SR_TRANSCRICAO = 16_000
LUFS_REDES = -14
TETO_DBTP = -1.5
PERSONAS = {"davi", "camila"}
FORMATOS = {"vertical": ((1080, 1920), "9x16"), "horizontal": ((1920, 1080), "16x9")}
DURACAO_ENCERRAMENTO = 6.0
ENCODER = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS)]


# ---------------------------------------------------------------- configuração do episódio

def validar_episodio(dados: dict[str, Any]) -> dict[str, Any]:
    """Confere o episodio.json antes de gastar render. Devolve o próprio dicionário."""
    for chave in ("episodio", "duracao", "inicio", "cortes", "trilha", "encerramento", "limites_de_render", "variantes"):
        if chave not in dados:
            raise ValueError(f"episodio.json sem a chave {chave!r}")
    ids = set()
    for corte in dados["cortes"]:
        if corte["id"] in ids:
            raise ValueError(f"recorte repetido: {corte['id']}")
        ids.add(corte["id"])
        if corte["persona"] not in PERSONAS:
            raise ValueError(f"persona desconhecida no recorte {corte['id']}: {corte['persona']}")
        if not corte["entrada"] < corte["saida"]:
            raise ValueError(f"recorte {corte['id']} com entrada depois da saída")
        if not corte["texto"].strip():
            raise ValueError(f"recorte {corte['id']} sem texto")
    voz = dados["inicio"] + sum(c["respiro"] for c in dados["cortes"][1:]) + sum(c["saida"] - c["entrada"] for c in dados["cortes"])
    if voz > dados["duracao"]:
        raise ValueError(f"a voz ({voz:.2f} s) não cabe em {dados['duracao']} s")
    limites = dados["limites_de_render"]
    if limites != sorted(limites) or any(not 0 < x < dados["duracao"] for x in limites):
        raise ValueError("limites_de_render precisam ser crescentes e dentro da duração")
    return dados


def carregar_episodio(ep: str) -> dict[str, Any]:
    return validar_episodio(json.loads((MODULO / "episodios" / ep / "episodio.json").read_text(encoding="utf-8")))


# ---------------------------------------------------------------- linha do tempo

Palavra = list  # [texto, início, fim]


def palavras_no_intervalo(palavras: Sequence[Palavra], entrada: float, saida: float) -> list[Palavra]:
    """Palavras ouvidas dentro do recorte, com uma folga para o arredondamento do reconhecedor."""
    return [p for p in palavras if p[1] >= entrada - 0.05 and p[2] <= saida + 0.15]


def alinhar(texto: str, ouvidas: Sequence[Palavra]) -> list[Palavra]:
    """Põe o texto do roteiro sobre os tempos ouvidos.

    A legenda mostra o roteiro, não a transcrição ("pro", não "para o"). Com o mesmo número de palavras, cada
    uma herda o tempo da ouvida; senão, o intervalo ouvido é repartido pelo tamanho de cada palavra.
    """
    alvo = texto.split()
    if not alvo or not ouvidas:
        raise ValueError("nada para alinhar")
    if len(alvo) == len(ouvidas):
        return [[p, w[1], w[2]] for p, w in zip(alvo, ouvidas)]
    ini, fim = ouvidas[0][1], ouvidas[-1][2]
    pesos = [len(p) + 2 for p in alvo]
    total, acumulado, saida = sum(pesos), 0, []
    for palavra, peso in zip(alvo, pesos):
        a = ini + (fim - ini) * acumulado / total
        acumulado += peso
        saida.append([palavra, a, ini + (fim - ini) * acumulado / total])
    return saida


def montar_linha(dados: dict[str, Any], palavras: Sequence[Palavra]) -> dict[str, Any]:
    """Posiciona cada recorte no tempo do trailer e leva junto o tempo de cada palavra."""
    cursor, clipes = dados["inicio"], []
    for corte in dados["cortes"]:
        if clipes:
            cursor += corte["respiro"]
        a, b = corte["entrada"], corte["saida"]
        ouvidas = palavras_no_intervalo(palavras, a, b)
        alinhadas = [[p, round(s - a + cursor, 3), round(e - a + cursor, 3)] for p, s, e in alinhar(corte["texto"], ouvidas)]
        clipes.append({"id": corte["id"], "persona": corte["persona"], "entrada": a, "saida": b, "inicio": round(cursor, 3),
                       "fim": round(cursor + b - a, 3), "texto": corte["texto"], "palavras": alinhadas})
        cursor += b - a
    return {"duracao": dados["duracao"], "clipes": clipes, "fim_da_voz": round(cursor, 3)}


def energia_db(sinal: np.ndarray, sr: int, janela_s: float = 0.03, passo_s: float = 0.01) -> np.ndarray:
    janela = max(1, int(janela_s * sr))
    rms = np.sqrt(np.convolve(sinal.astype(np.float64) ** 2, np.ones(janela) / janela, "same"))
    return 20 * np.log10(rms[:: max(1, int(passo_s * sr))] + 1e-6)


def vale_de_energia(db: np.ndarray, t: float, antes: float, depois: float, passo_s: float = 0.01) -> float:
    """Instante mais silencioso em [t - antes, t + depois]: onde cortar sem comer sílaba."""
    a = max(0, int(round((t - antes) / passo_s)))
    b = min(len(db), int(round((t + depois) / passo_s)) + 1)
    return round((a + int(np.argmin(db[a:b]))) * passo_s, 2)


# ---------------------------------------------------------------- som

def _t(d: float) -> np.ndarray:
    return np.arange(int(d * SR)) / SR


def _env(d: float, ataque: float, queda: float) -> np.ndarray:
    x = _t(d)
    return np.minimum(1, x / max(ataque, 1e-4)) * np.exp(-np.maximum(0, x - ataque) / queda)


def _varredura(d: float, f0: float, f1: float) -> np.ndarray:
    x = _t(d)
    return np.sin(2 * np.pi * np.cumsum(f0 * (f1 / f0) ** (x / d)) / SR)


def _norm(x: np.ndarray, pico: float) -> np.ndarray:
    return x / (np.max(np.abs(x)) + 1e-9) * pico


def sintetizar_efeito(nome: str, rng: np.random.Generator) -> np.ndarray:
    """Efeitos da linguagem: prensa, papel, sisal, pregador... sintetizados, sem amostra de terceiros."""
    from scipy.signal import butter, sosfilt

    def banda(x, lo, hi):
        return sosfilt(butter(2, [lo, hi], btype="band", fs=SR, output="sos"), x)

    def baixa(x, f):
        return sosfilt(butter(2, f, btype="low", fs=SR, output="sos"), x)

    def ruido(d):
        return rng.standard_normal(int(d * SR))

    def varrer_banda(d, de, ate, pedacos):
        x, out = ruido(d), np.zeros(int(d * SR))
        for i, (lo, hi) in enumerate(zip(np.linspace(de[0], ate[0], pedacos), np.linspace(de[1], ate[1], pedacos))):
            trecho = slice(int(i * len(x) / pedacos), int((i + 1) * len(x) / pedacos))
            out[trecho] = banda(x, lo, hi)[trecho]
        return out

    if nome == "carimbo":
        d = 0.32
        return _norm(_varredura(d, 120, 46) * _env(d, 0.002, 0.07) + banda(ruido(d), 900, 4500) * _env(d, 0.001, 0.012) * 0.5
                     + np.sin(2 * np.pi * 230 * _t(d)) * _env(d, 0.001, 0.03) * 0.35, 0.55)
    if nome == "prensa":
        d = 0.5
        toque = (np.sin(2 * np.pi * 180 * _t(d)) + 0.6 * np.sin(2 * np.pi * 410 * _t(d))) * _env(d, 0.001, 0.05)
        return _norm(_varredura(d, 90, 38) * _env(d, 0.002, 0.12) + toque * 0.6 + banda(ruido(d), 700, 5000) * _env(d, 0.001, 0.02) * 0.5, 0.7)
    if nome == "tique":
        d = 0.05
        return _norm(banda(ruido(d), 2500, 7000) * _env(d, 0.0005, 0.004) + np.sin(2 * np.pi * 1700 * _t(d)) * _env(d, 0.0005, 0.01) * 0.5, 0.25)
    if nome == "papel":
        d = 0.32
        tremor = np.clip(0.6 + 0.4 * np.abs(baixa(ruido(d), 40)) * 4, 0, 1.5)
        return _norm(banda(ruido(d), 900, 6000) * _env(d, 0.05, 0.08) * tremor, 0.28)
    if nome == "sisal":
        d = 0.45
        return _norm(banda(ruido(d), 250, 1400) * np.clip(baixa(ruido(d), 35) * 6, 0, 1) * _env(d, 0.03, 0.18), 0.22)
    if nome == "pregador":
        d = 0.09

        def estalo():
            return banda(ruido(d), 1500, 6000) * _env(d, 0.0005, 0.006) + np.sin(2 * np.pi * 1150 * _t(d)) * _env(d, 0.0005, 0.012)
        return _norm(estalo() + np.roll(estalo(), int(0.028 * SR)) * 0.7, 0.35)
    if nome == "rabisco":
        d = 0.55
        return _norm(banda(ruido(d), 2000, 7000) * np.abs(np.sin(2 * np.pi * 11 * _t(d))) ** 0.5 * _env(d, 0.02, 0.3), 0.18)
    if nome == "rasgo":
        d = 0.35
        estalos = (rng.random(int(d * SR)) > 0.985) * rng.standard_normal(int(d * SR))
        return _norm(banda(ruido(d) * 0.4 + estalos * 3, 600, 6000) * _env(d, 0.01, 0.15), 0.25)
    if nome == "queda":
        return _norm(varrer_banda(0.6, (2400, 4200), (300, 700), 6) * _env(0.6, 0.05, 0.25), 0.25)
    if nome == "puxao":
        return _norm(varrer_banda(0.5, (250, 700), (2500, 5500), 8) * _env(0.5, 0.25, 0.1), 0.4)
    if nome == "engole":
        return _norm(_varredura(0.18, 170, 80) * _env(0.18, 0.005, 0.05), 0.3)
    if nome == "corte":
        d = 1.2
        return _norm(_varredura(d, 70, 32) * _env(d, 0.002, 0.35) + banda(ruido(d), 500, 5000) * _env(d, 0.001, 0.03) * 0.6, 0.8)
    if nome == "risco":
        return _norm(banda(ruido(0.32), 1400, 4500) * _env(0.32, 0.01, 0.16), 0.25)
    if nome == "passo":
        return _norm(banda(ruido(0.03), 3000, 8000) * _env(0.03, 0.0003, 0.003), 0.12)
    if nome == "cava":
        d, x = 1.3, np.zeros(int(1.3 * SR))
        for _ in range(26):
            p = int(rng.random() * (len(x) - 0.12 * SR))
            grao = baixa(ruido(0.1), 1800) * _env(0.1, 0.004, 0.025) * (0.4 + rng.random())
            x[p:p + len(grao)] += grao
        return _norm(x, 0.35)
    if nome == "brilho":
        d = 0.9
        s = sum(np.sin(2 * np.pi * f * _t(d)) * _env(d, 0.002, 0.25) for f in (1568, 2093, 2637))
        return _norm(s + np.roll(s, int(0.07 * SR)) * 0.6, 0.14)
    raise ValueError(f"efeito desconhecido: {nome}")


def camada_de_efeitos(eventos: Iterable[dict[str, Any]], duracao: float,
                      sintetizar: Callable[[str, int], np.ndarray]) -> np.ndarray:
    """Soma cada efeito no instante do evento. `sintetizar(nome, variacao)` dá uma de três variações,
    escolhida pelo tempo, para a mesma batida não soar idêntica duas vezes seguidas."""
    pista = np.zeros(int(duracao * SR))
    for ev in eventos:
        i = int(round(ev["t"] * SR))
        if not 0 <= i < len(pista):
            continue
        som = sintetizar(ev["tipo"], int(ev["t"] * 100) % 3) * ev["ganho"]
        fim = min(len(pista), i + len(som))
        pista[i:fim] += som[: fim - i]
    return pista


def envelope_de_voz(voz: np.ndarray, sr: int = SR, limiar: float = 0.01, subida_s: float = 0.04,
                    descida_s: float = 0.35, bloco: int = 240) -> np.ndarray:
    """De 0 a 1: quanto a voz está presente. Sobe rápido e solta devagar, para a trilha não pular entre palavras."""
    janela = max(1, int(0.03 * sr))
    rms = np.sqrt(np.convolve(voz.astype(np.float64) ** 2, np.ones(janela) / janela, "same"))
    alvo = (rms > limiar).astype(float)
    sobe, desce = np.exp(-bloco / (subida_s * sr)), np.exp(-bloco / (descida_s * sr))
    saida, v = np.zeros_like(alvo), 0.0
    for i in range(0, len(alvo), bloco):
        x = alvo[i:i + bloco].max()
        v = x + (v - x) * (sobe if x > v else desce)
        saida[i:i + bloco] = v
    return saida


def colocar(pista: np.ndarray, trecho: np.ndarray, em: float, fade_in: float, fade_out: float, sr: int = SR) -> None:
    """Soma `trecho` (amostras × canais) na `pista` a partir de `em` segundos, com rampas lineares."""
    trecho = trecho.astype(np.float64).copy()
    ni, no = int(fade_in * sr), int(fade_out * sr)
    if ni:
        trecho[:ni] *= np.linspace(0, 1, ni)[:, None]
    if no:
        trecho[-no:] *= np.linspace(1, 0, no)[:, None]
    i = int(round(em * sr))
    n = max(0, min(len(trecho), len(pista) - i))
    pista[i:i + n] += trecho[:n]


def mixar(voz: np.ndarray, musica: np.ndarray, efeitos: np.ndarray, nivel_musica: float, ducking: float,
          nivel_efeitos: float) -> tuple[np.ndarray, np.ndarray]:
    """Devolve (com trilha, sem trilha), estéreo. A trilha abaixa `ducking` (0 a 1) quando há voz."""
    ganho = nivel_musica * (1 - ducking * envelope_de_voz(voz))
    base = np.stack([voz, voz], axis=1) + np.stack([efeitos, efeitos], axis=1) * nivel_efeitos
    return base + musica * ganho[:, None], base


# ---------------------------------------------------------------- ffmpeg

def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def ler_audio(caminho: Path, inicio: float, duracao: float | None, canais: int, sr: int) -> np.ndarray:
    corte = ["-ss", f"{inicio}"] + (["-t", f"{duracao}"] if duracao else [])
    r = subprocess.run(["ffmpeg", "-v", "error", *corte, "-i", str(caminho), "-ac", str(canais), "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    x = np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)
    return x.reshape(-1, canais) if canais > 1 else x


def gravar_wav(caminho: Path, x: np.ndarray, sr: int = SR) -> None:
    canais = 1 if x.ndim == 1 else x.shape[1]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ac", str(canais), "-ar", str(sr), "-i", "-", str(caminho)],
                         stdin=subprocess.PIPE)
    p.communicate(x.astype(np.float32).tobytes())
    if p.returncode:
        raise RuntimeError(f"ffmpeg não gravou {caminho}")


def normalizar(entrada: Path, saida: Path) -> None:
    """Loudness das redes em duas passadas, linear (sem compressão dinâmica)."""
    filtro = f"loudnorm=I={LUFS_REDES}:TP={TETO_DBTP}:LRA=11"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(entrada), "-af", filtro + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"): r.stderr.rindex("}") + 1])
    _ffmpeg("-i", str(entrada), "-af", f"{filtro}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true", "-ar", str(SR), str(saida))


# ---------------------------------------------------------------- navegador

class _Servidor:
    """Serve a raiz do repositório numa porta livre: o palco lê site/ e pebamotion/ pelo mesmo endereço."""

    def __enter__(self) -> str:
        manipulador = functools.partial(_Silencioso, directory=str(RAIZ))
        self._http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manipulador)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._http.server_address[1]}/pebamotion/palco.html"

    def __exit__(self, *_: object) -> None:
        self._http.shutdown()


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass


def _consulta(ep: str, formato: str, parametros: dict[str, str]) -> str:
    return "&".join(f"{k}={v}" for k, v in {"ep": ep, "f": formato, **parametros}.items())


def _abrir(playwright, url: str, formato: str):
    (largura, altura), _ = FORMATOS[formato]
    navegador = playwright.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--no-sandbox"])
    pagina = navegador.new_page(viewport={"width": largura, "height": altura})
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.goto(url)
    pagina.evaluate("window.pronto")
    if erros:
        raise RuntimeError("erro no palco: " + "; ".join(erros))
    return navegador, pagina


def renderizar(ep: str, formato: str, parametros: dict[str, str], destino: Path, limites: Sequence[float]) -> list[dict[str, Any]]:
    """Grava o vídeo sem áudio e devolve os eventos sonoros. Um MP4 por trecho (reaproveitado se já existe),
    juntados com concat; cada trecho nasce com nome temporário e só é renomeado quando o ffmpeg termina."""
    from playwright.sync_api import sync_playwright

    with _Servidor() as base, sync_playwright() as pw:
        navegador, pagina = _abrir(pw, f"{base}?{_consulta(ep, formato, parametros)}", formato)
        duracao, eventos = pagina.evaluate("window.duracao"), pagina.evaluate("window.eventos")
        total = round(duracao * FPS)
        quadros = [0, *[round(x * FPS) for x in limites if 0 < x < duracao], total]
        partes = []
        for n, (a, b) in enumerate(zip(quadros, quadros[1:])):
            parte = destino.with_name(f"{destino.stem}.{n:02d}.mp4")
            partes.append(parte)
            if parte.exists():
                continue
            temporario = parte.with_name(parte.stem + ".tmp.mp4")
            ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                                   *ENCODER, str(temporario)], stdin=subprocess.PIPE)
            inicio = time.time()
            for i in range(a, b):
                pagina.evaluate(f"window.desenhar({i / FPS})")
                ff.stdin.write(pagina.screenshot(type="jpeg", quality=92))
            ff.stdin.close()
            if ff.wait():
                raise RuntimeError(f"ffmpeg falhou no trecho {n} de {destino.name}")
            temporario.rename(parte)
            print(f"  {destino.stem} trecho {n}: {b - a} quadros em {time.time() - inicio:.0f} s", flush=True)
        navegador.close()
    lista = destino.with_suffix(".txt")
    lista.write_text("".join(f"file '{p.resolve()}'\n" for p in partes))
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(destino))
    return eventos


# ---------------------------------------------------------------- comandos

def _cache(ep: str) -> Path:
    pasta = MODULO / ".cache" / ep
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def audio_do_episodio(ep: str) -> Path:
    destino = _cache(ep) / "episodio.mp3"
    if not destino.exists():
        url = json.loads((RAIZ / "episodios" / ep / "publicacao.json").read_text())["url_audio"]
        print(f"baixando {url}")
        with urllib.request.urlopen(url) as r, open(destino.with_suffix(".tmp"), "wb") as f:
            shutil.copyfileobj(r, f)
        destino.with_suffix(".tmp").rename(destino)
    return destino


def cmd_transcrever(ep: str, modelo: str) -> None:
    from faster_whisper import WhisperModel

    audio = ler_audio(audio_do_episodio(ep), 0, None, 1, SR_TRANSCRICAO).astype(np.float32)
    segmentos, _ = WhisperModel(modelo, device="cpu", compute_type="int8").transcribe(audio, language="pt", word_timestamps=True)
    palavras = []
    for s in segmentos:
        palavras += [[w.word.strip(), round(w.start, 2), round(w.end, 2)] for w in s.words]
        print(f"{s.start:7.2f} {s.text}", flush=True)
    (_cache(ep) / "palavras.json").write_text(json.dumps(palavras, ensure_ascii=False))


def _palavras(ep: str) -> list[Palavra]:
    arquivo = _cache(ep) / "palavras.json"
    if not arquivo.exists():
        raise SystemExit(f"rode antes: python scripts/pebamotion.py transcrever {ep}")
    return json.loads(arquivo.read_text())


def cmd_sugerir_cortes(ep: str) -> None:
    dados, palavras = carregar_episodio(ep), _palavras(ep)
    db = energia_db(ler_audio(audio_do_episodio(ep), 0, None, 1, SR_TRANSCRICAO), SR_TRANSCRICAO)
    for corte in dados["cortes"]:
        ouvidas = palavras_no_intervalo(palavras, corte["entrada"], corte["saida"])
        entrada = vale_de_energia(db, ouvidas[0][1], 0.35, 0.02)
        saida = vale_de_energia(db, ouvidas[-1][2], 0.02, 0.4)
        print(f"{corte['id']:12s} entrada {corte['entrada']:8.2f} → {entrada:8.2f}   saída {corte['saida']:8.2f} → {saida:8.2f}")


def _voz(ep: str, linha: dict[str, Any]) -> np.ndarray:
    episodio = audio_do_episodio(ep)
    voz = np.zeros(int(linha["duracao"] * SR))
    borda_in, borda_out = int(0.02 * SR), int(0.04 * SR)
    for c in linha["clipes"]:
        x = ler_audio(episodio, c["entrada"], c["saida"] - c["entrada"], 1, SR)
        x[:borda_in] *= np.linspace(0, 1, borda_in)
        x[-borda_out:] *= np.linspace(1, 0, borda_out)
        colocar(voz[:, None], x[:, None], c["inicio"], 0, 0)
    return voz


def cmd_linha(ep: str) -> None:
    linha = montar_linha(carregar_episodio(ep), _palavras(ep))
    (MODULO / "episodios" / ep / "linha.json").write_text(json.dumps(linha, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in linha["clipes"]:
        print(f"{c['id']:12s} {c['inicio']:6.2f} → {c['fim']:6.2f}  {c['texto'][:60]}")
    print(f"voz termina em {linha['fim_da_voz']:.2f} s de {linha['duracao']} s")


def cmd_quadros(ep: str, tempos: Sequence[float], formato: str, parametros: dict[str, str], so_fim: bool) -> None:
    from playwright.sync_api import sync_playwright

    pasta = _cache(ep) / "quadros"
    pasta.mkdir(exist_ok=True)
    if so_fim:
        parametros = {**parametros, "so": "fim"}
    with _Servidor() as base, sync_playwright() as pw:
        navegador, pagina = _abrir(pw, f"{base}?{_consulta(ep, formato, parametros)}", formato)
        for t in tempos:
            pagina.evaluate(f"window.desenhar({t})")
            arquivo = pasta / f"{formato}-{t:06.2f}.png"
            pagina.screenshot(path=str(arquivo))
            print(arquivo.relative_to(RAIZ))
        navegador.close()


def _mixar_e_gravar(eventos, voz: np.ndarray, plano: dict[str, Any], duracao: float, prefixo: Path) -> dict[str, Path]:
    if not TRILHA.exists():
        raise SystemExit("falta assets/vinheta.mp3 (a faixa inteira; ver docs/vinheta.md)")
    n = int(duracao * SR)
    musica = np.zeros((n, 2))
    for t in plano["trechos"]:
        colocar(musica, ler_audio(TRILHA, t["de"], t["dur"], 2, SR), t["em"], t["fade_in"], t["fade_out"])
    variacoes: dict[tuple[str, int], np.ndarray] = {}

    def sintetizar(nome: str, variacao: int) -> np.ndarray:
        if (nome, variacao) not in variacoes:
            variacoes[(nome, variacao)] = sintetizar_efeito(nome, np.random.default_rng(zlib.crc32(nome.encode()) + variacao))
        return variacoes[(nome, variacao)]

    efeitos = camada_de_efeitos(eventos, duracao, sintetizar)
    voz = np.pad(voz, (0, max(0, n - len(voz))))[:n]
    com, sem = mixar(voz, musica, efeitos, plano["nivel"], plano.get("ducking", 0.6), plano["efeitos"])
    saidas = {}
    for nome, mix in (("trilha", com), ("sem-trilha", sem)):
        bruto, final = prefixo.with_name(f"{prefixo.name}-{nome}.bruto.wav"), prefixo.with_name(f"{prefixo.name}-{nome}.wav")
        gravar_wav(bruto, mix)
        normalizar(bruto, final)
        saidas[nome] = final
    return saidas


def _juntar(video: Path, audio: Path, saida: Path) -> None:
    _ffmpeg("-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-shortest", str(saida))
    print("  →", saida.relative_to(RAIZ))


def cmd_produzir(ep: str, refazer: bool) -> None:
    dados = carregar_episodio(ep)
    linha = json.loads((MODULO / "episodios" / ep / "linha.json").read_text(encoding="utf-8"))
    cache, saida = _cache(ep), MODULO / "saida" / ep
    if refazer:
        for arquivo in cache.glob("*.mp4"):
            arquivo.unlink()
    saida.mkdir(parents=True, exist_ok=True)
    voz = _voz(ep, linha)
    nome = f"pebacast-{ep}"
    trailer: dict[str, Path] = {}
    encerramento: dict[str, Path] = {}
    # A variante "" é o trailer principal; só ela ganha a versão sem trilha. O som é o mesmo em todas.
    for formato, (_, proporcao) in FORMATOS.items():
        for variante, parametros in dados["variantes"].items():
            sufixo = f"-{variante}" if variante else ""
            video = cache / f"trailer-{proporcao}{sufixo}.mp4"
            eventos = renderizar(ep, formato, parametros, video, dados["limites_de_render"])
            if not trailer:
                trailer = _mixar_e_gravar(eventos, voz, dados["trilha"], dados["duracao"], cache / "trailer")
            _juntar(video, trailer["trilha"], saida / f"{nome}-trailer-{proporcao}{sufixo}.mp4")
            if not variante:
                _juntar(video, trailer["sem-trilha"], saida / f"{nome}-trailer-{proporcao}-sem-trilha.mp4")
        video = cache / f"encerramento-{proporcao}.mp4"
        eventos_fim = renderizar(ep, formato, {"so": "fim"}, video, [DURACAO_ENCERRAMENTO / 2])
        if not encerramento:
            encerramento = _mixar_e_gravar(eventos_fim, np.zeros(int(DURACAO_ENCERRAMENTO * SR)), dados["encerramento"],
                                           DURACAO_ENCERRAMENTO, cache / "encerramento")
        _juntar(video, encerramento["trilha"], saida / f"pebacast-encerramento-{ep}-{proporcao}.mp4")


def _parametros(itens: Sequence[str]) -> dict[str, str]:
    saida = {}
    for item in itens:
        chave, sep, valor = item.partition("=")
        if not sep:
            raise SystemExit(f"--param espera chave=valor, veio {item!r}")
        saida[chave] = valor
    return saida


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="pebamotion", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="comando", required=True)
    t = sub.add_parser("transcrever")
    t.add_argument("ep")
    t.add_argument("--modelo", default=os.environ.get("WHISPER_MODELO", "small"))
    for nome in ("sugerir-cortes", "linha"):
        sub.add_parser(nome).add_argument("ep")
    q = sub.add_parser("quadros")
    q.add_argument("ep")
    q.add_argument("-t", "--tempos", type=float, nargs="+", required=True)
    q.add_argument("--formato", choices=FORMATOS, default="vertical")
    q.add_argument("--param", action="append", default=[])
    q.add_argument("--so-fim", action="store_true")
    r = sub.add_parser("produzir")
    r.add_argument("ep")
    r.add_argument("--refazer", action="store_true", help="descarta os trechos já renderizados")
    a = p.parse_args(argv)
    if a.comando == "transcrever":
        cmd_transcrever(a.ep, a.modelo)
    elif a.comando == "sugerir-cortes":
        cmd_sugerir_cortes(a.ep)
    elif a.comando == "linha":
        cmd_linha(a.ep)
    elif a.comando == "quadros":
        cmd_quadros(a.ep, a.tempos, a.formato, _parametros(a.param), a.so_fim)
    else:
        cmd_produzir(a.ep, a.refazer)


if __name__ == "__main__":
    main(sys.argv[1:])

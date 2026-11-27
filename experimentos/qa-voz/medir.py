"""Mede cada miolo: embedding de locutor (ONNX, sem torch) e F0 por YIN em numpy.

Grava `<id>.medidas.npz` com, por miolo: índice do turno, persona, bloco, embedding de cada modelo
(normalizado) e a mediana de F0.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from segmentacao import TAXA, decodificar, segmentar, turnos_do_roteiro  # noqa: E402

MAX_MIOLO_S = 12.0  # miolo longo: só o centro, para o custo não crescer com o turno

# (arquivo, escala da amostra): o WeSpeaker espera amostras na faixa do int16; o CAM++, em [-1, 1].
MODELOS = {
    "wespeaker_resnet34_lm": ("wespeaker_en_voxceleb_resnet34_LM.onnx", 32768.0),
    "campplus_voxceleb": ("3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx", 1.0),
}


def fbank(x: np.ndarray, escala: float) -> np.ndarray:
    import kaldi_native_fbank as knf

    opcoes = knf.FbankOptions()
    opcoes.frame_opts.dither = 0
    opcoes.frame_opts.samp_freq = TAXA
    opcoes.mel_opts.num_bins = 80
    extrator = knf.OnlineFbank(opcoes)
    extrator.accept_waveform(TAXA, (x * escala).tolist())
    extrator.input_finished()
    feats = np.array([extrator.get_frame(i) for i in range(extrator.num_frames_ready)], dtype=np.float32)
    return feats - feats.mean(axis=0, keepdims=True)


class Embedder:
    def __init__(self, pasta: Path, nome: str) -> None:
        import onnxruntime as ort

        arquivo, self.escala = MODELOS[nome]
        opcoes = ort.SessionOptions()
        opcoes.intra_op_num_threads = 2  # o ubuntu-latest tem 4 vCPUs; deixa folga
        self.sessao = ort.InferenceSession(str(pasta / arquivo), opcoes, providers=["CPUExecutionProvider"])
        self.entrada = self.sessao.get_inputs()[0].name

    def __call__(self, x: np.ndarray) -> np.ndarray:
        feats = fbank(x, self.escala)[None]
        emb = self.sessao.run(None, {self.entrada: feats})[0][0]
        return emb / np.linalg.norm(emb)


def f0_yin(x: np.ndarray, fmin: float = 60, fmax: float = 400, limiar: float = 0.15) -> np.ndarray:
    """F0 por quadro (Hz; 0 quando não vozeado), YIN com a diferença calculada por FFT."""
    janela, passo = 512, 160
    tau_max, tau_min = int(TAXA / fmin), int(TAXA / fmax)
    tamanho = janela + tau_max
    if len(x) < tamanho:
        return np.zeros(0)
    quadros = np.lib.stride_tricks.sliding_window_view(x.astype(np.float64), tamanho)[::passo]
    n = 1 << int(np.ceil(np.log2(tamanho + janela)))
    a = np.fft.rfft(quadros[:, :janela], n)
    b = np.fft.rfft(quadros, n)
    corr = np.fft.irfft(np.conj(a) * b, n)[:, :tau_max + 1]
    quad = np.cumsum(np.pad(quadros ** 2, ((0, 0), (1, 0))), axis=1)
    taus = np.arange(tau_max + 1)
    e_tau = quad[:, taus + janela] - quad[:, taus]
    d = quad[:, janela][:, None] + e_tau - 2 * corr
    d[:, 0] = 0
    acumulado = np.cumsum(d[:, 1:], axis=1)
    cmnd = np.ones_like(d)
    cmnd[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(acumulado, 1e-12)
    abaixo = cmnd[:, tau_min:] < limiar
    tem = abaixo.any(axis=1)
    primeiro = np.argmax(abaixo, axis=1) + tau_min
    # Desce até o mínimo local depois do primeiro ponto abaixo do limiar.
    for _ in range(8):
        proximo = np.minimum(primeiro + 1, tau_max)
        desce = cmnd[np.arange(len(cmnd)), proximo] < cmnd[np.arange(len(cmnd)), primeiro]
        primeiro = np.where(desce, proximo, primeiro)
    return np.where(tem, TAXA / primeiro, 0.0)


def medir(x: np.ndarray, turnos, embedders: dict) -> dict:
    linhas = {"turno": [], "persona": [], "bloco": [], "f0": [], "inicio": [], "fim": []}
    embs = {nome: [] for nome in embedders}
    tempos = {nome: 0.0 for nome in embedders} | {"f0": 0.0}
    for t in turnos:
        if not t.miolo:
            continue
        a, b = t.miolo
        if b - a > MAX_MIOLO_S:
            meio = (a + b) / 2
            a, b = meio - MAX_MIOLO_S / 2, meio + MAX_MIOLO_S / 2
        trecho = x[int(a * TAXA):int(b * TAXA)]
        for nome, embedder in embedders.items():
            comeco = time.perf_counter()
            embs[nome].append(embedder(trecho))
            tempos[nome] += time.perf_counter() - comeco
        comeco = time.perf_counter()
        f0 = f0_yin(trecho)
        tempos["f0"] += time.perf_counter() - comeco
        vozeado = f0[f0 > 0]
        for chave, valor in (("turno", t.indice), ("persona", t.persona), ("bloco", t.bloco),
                             ("f0", float(np.median(vozeado)) if len(vozeado) else 0.0), ("inicio", a), ("fim", b)):
            linhas[chave].append(valor)
    return {**{k: np.array(v) for k, v in linhas.items()},
            **{f"emb_{nome}": np.array(v, dtype=np.float32) for nome, v in embs.items()}}, tempos


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("raiz", type=Path)
    p.add_argument("audio", type=Path)
    p.add_argument("modelos", type=Path)
    p.add_argument("saida", type=Path)
    p.add_argument("episodios", nargs="+")
    p.add_argument("--modelo", action="append", choices=sorted(MODELOS), help="padrão: todos")
    a = p.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)
    comeco = time.perf_counter()
    embedders = {nome: Embedder(a.modelos, nome) for nome in (a.modelo or MODELOS)}
    carga = time.perf_counter() - comeco
    relatorio = {"carga_modelos_s": carga, "episodios": {}}
    for ep in a.episodios:
        t = {"inicio": time.perf_counter()}
        x = decodificar(a.audio / f"pebacast-{ep}.mp3")
        t["decodificar"] = time.perf_counter()
        # A segmentação usa o primeiro modelo da lista como evidência de voz (o QA terá um só).
        turnos, info = segmentar(x, turnos_do_roteiro(a.raiz, ep), embedder=next(iter(embedders.values())))
        t["segmentar"] = time.perf_counter()
        medidas, tempos = medir(x, turnos, embedders)
        np.savez(a.saida / f"{ep}.medidas.npz", **medidas)
        fim = time.perf_counter()
        rel = {"audio_s": info["duracao"], "miolos": int(len(medidas["turno"])),
               "decodificar_s": t["decodificar"] - t["inicio"], "segmentar_s": t["segmentar"] - t["decodificar"],
               **{f"{k}_s": v for k, v in tempos.items()}, "total_s": fim - t["inicio"]}
        relatorio["episodios"][ep] = rel
        print(ep, {k: round(v, 1) if isinstance(v, float) else v for k, v in rel.items()}, flush=True)
    (a.saida / "tempos.json").write_text(json.dumps(relatorio, indent=1), encoding="utf-8")

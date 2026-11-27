"""QA de voz (#21, ADR 0012): cada persona soa como ela mesma, e o Davi não soa como a convidada?

O TTS às vezes muda o timbre de uma voz no meio do episódio ou deixa duas vozes parecidas demais.
Depois de publicar, os turnos de cada persona são separados pelo roteiro (sem modelo de fala) e o
timbre de cada trecho é medido por um embedding de locutor em ONNX (WeSpeaker ResNet34-LM), sem torch.
O spike #27 (`docs/spikes/qa-de-voz.md`, no branch `spike/qa-de-voz`) provou a abordagem.

1. **Turnos:** as falas que foram ao TTS e os blocos de `agrupar_em_blocos` dão a persona, o bloco e
   o tamanho de cada turno. Um VAD de energia acha as pausas, e uma programação dinâmica escolhe onde
   cortar, com a duração de cada turno proporcional aos caracteres. Uma passada final soma a
   evidência de voz: quanto cada trecho entre pausas parece cada persona.
2. **Medida:** só o miolo de cada turno (sem 20 % de cada borda, com pelo menos 2 s), sem o primeiro
   turno, que fica sob a vinheta. Um embedding por miolo e, para o laudo, o F0 (YIN).
3. **Regras** (`qa_voz.limites`): a persona num bloco contra o resto do episódio e contra a
   impressão de voz de referência; a persona no episódio inteiro contra a referência; e cada par
   de personas do episódio, que não pode soar como a mesma voz.

Em modo aviso, só abre a issue `incidente`. Em modo regravar, a publicação também dispara o
`regravar.yml` (no máximo uma vez por execução). Nunca segura a publicação.

    python -m podcast.qualidade_voz referencia --repo dono/repo --episodios sw-002 in-001
    python -m podcast.qualidade_voz avaliar --repo dono/repo sw-002
"""

import argparse
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from podcast.audio import Trechos, Vinheta, duracao_mp3
from podcast.dominio import Fala, Persona
from podcast.issues import IssuesDeIncidente
from podcast.tts.gemini import agrupar_em_blocos

log = logging.getLogger(__name__)

TAXA = 16_000
# O WeSpeaker espera as amostras na escala do int16.
ESCALA_DA_AMOSTRA = 32768.0
QUADRO_S = 0.010
JANELA_S = 0.025
PAUSA_MIN_S = 0.12
# Trecho silencioso: 35 dB abaixo do percentil 95 da energia da fala.
PAUSA_ABAIXO_DB = 35
# Miolo longo: só o centro, para o custo não crescer com o turno.
MAX_MIOLO_S = 12.0
# Evidência de voz: trecho entre pausas mais curto que isso não diz quem fala.
TRECHO_DE_VOZ_MIN_S = 0.6
TRECHO_DE_VOZ_MAX_S = 6.0
PASSADAS_DE_DURACAO = 2
PADRAO_DE_ID = re.compile(r"^[a-z]{2}-\d{3}$")
CACHE_DE_MODELOS = Path.home() / ".cache" / "pebacast" / "modelos"
REFERENCIA = Path("config/vozes-referencia.json")
MODOS = ("aviso", "regravar")


class ModeloIndisponivel(Exception):
    """O modelo não baixou ou não confere com o SHA-256: o QA de voz não roda."""


# --- Configuração -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Modelo:
    url: str
    sha256: str


@dataclass(frozen=True)
class ParametrosDeSegmentacao:
    folga_caracteres: float = 12
    peso_da_pausa: float = 0.2
    peso_da_voz: float = 0.1
    borda_do_miolo: float = 0.2
    miolo_min_s: float = 2.0


@dataclass(frozen=True)
class LimitesDeVoz:
    miolos_min_no_bloco: int = 2
    timbre_bloco_min: float = 0.75
    timbre_referencia_min: float = 0.73
    persona_referencia_min: float = 0.92
    vozes_confundiveis_max: float = 0.61


# --- Modelo -------------------------------------------------------------------------------------


def sha256_de(arquivo: Path) -> str:
    resumo = hashlib.sha256()
    with arquivo.open("rb") as entrada:
        for pedaco in iter(lambda: entrada.read(1 << 20), b""):
            resumo.update(pedaco)
    return resumo.hexdigest()


def _baixar_url(url: str, destino: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as resposta, destino.open("wb") as saida:  # noqa: S310 (URL fixa da config)
        shutil.copyfileobj(resposta, saida)


def obter_modelo(modelo: Modelo, cache: Path = CACHE_DE_MODELOS,
                 baixar: Callable[[str, Path], None] = _baixar_url) -> Path:
    """O caminho do modelo, já conferido pelo SHA-256. Nada é carregado antes da conferência.

    O download vai para um arquivo temporário e só vira `<sha>.onnx` no cache se o hash bater.
    Um arquivo do cache que não bate (corrompido ou adulterado) é apagado e baixado de novo.
    """
    destino = cache / f"{modelo.sha256}.onnx"
    if destino.exists():
        if sha256_de(destino) == modelo.sha256:
            return destino
        log.warning("O modelo em cache não confere com o SHA-256; baixando de novo.")
        destino.unlink()
    cache.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".parcial")
    try:
        baixar(modelo.url, parcial)
    except Exception as erro:
        parcial.unlink(missing_ok=True)
        raise ModeloIndisponivel(f"o modelo não baixou de {modelo.url}: {type(erro).__name__}: {erro}") from erro
    obtido = sha256_de(parcial)
    if obtido != modelo.sha256:
        parcial.unlink()
        raise ModeloIndisponivel(f"o modelo baixado tem SHA-256 {obtido}, e a config pede {modelo.sha256}")
    parcial.replace(destino)
    return destino


def fbank(trecho: np.ndarray) -> np.ndarray:
    import kaldi_native_fbank as knf

    opcoes = knf.FbankOptions()
    opcoes.frame_opts.dither = 0
    opcoes.frame_opts.samp_freq = TAXA
    opcoes.mel_opts.num_bins = 80
    extrator = knf.OnlineFbank(opcoes)
    extrator.accept_waveform(TAXA, (trecho * ESCALA_DA_AMOSTRA).tolist())
    extrator.input_finished()
    quadros = np.array([extrator.get_frame(i) for i in range(extrator.num_frames_ready)], dtype=np.float32)
    return quadros - quadros.mean(axis=0, keepdims=True)


class Embedder:
    """Embedding de locutor normalizado de um trecho a 16 kHz, pelo onnxruntime."""

    def __init__(self, arquivo: Path) -> None:
        import onnxruntime as ort

        opcoes = ort.SessionOptions()
        opcoes.intra_op_num_threads = 2  # o ubuntu-latest tem 4 vCPUs
        self.sessao = ort.InferenceSession(str(arquivo), opcoes, providers=["CPUExecutionProvider"])
        self.entrada = self.sessao.get_inputs()[0].name

    def __call__(self, trecho: np.ndarray) -> np.ndarray:
        vetor = self.sessao.run(None, {self.entrada: fbank(trecho)[None]})[0][0]
        return vetor / np.linalg.norm(vetor)


# --- Turnos e segmentação -----------------------------------------------------------------------


@dataclass
class Turno:
    indice: int
    persona: str
    bloco: int
    caracteres: int
    inicio: float = 0.0
    fim: float = 0.0
    miolo: tuple[float, float] | None = None


def turnos_das_falas(falas: Sequence[Fala], max_caracteres_por_bloco: int) -> list[Turno]:
    """Os turnos como foram ao TTS: a mesma divisão em blocos que a síntese usou."""
    turnos = []
    for numero, bloco in enumerate(agrupar_em_blocos(falas, max_caracteres_por_bloco)):
        for fala in bloco:
            turnos.append(Turno(len(turnos), fala.persona.id, numero, len(fala.texto)))
    return turnos


def decodificar(mp3: Path) -> np.ndarray:
    saida = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(mp3), "-ac", "1", "-ar", str(TAXA), "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(saida, dtype=np.float32).copy()


def _energia_db(x: np.ndarray) -> np.ndarray:
    passo, janela = int(QUADRO_S * TAXA), int(JANELA_S * TAXA)
    quadros = np.lib.stride_tricks.sliding_window_view(x, janela)[::passo]
    return 10 * np.log10(np.mean(quadros.astype(np.float64) ** 2, axis=1) + 1e-12)


def pausas(db: np.ndarray, inicio_s: float) -> list[tuple[float, float]]:
    """Trechos silenciosos de pelo menos PAUSA_MIN_S, em segundos do episódio."""
    silencio = db < np.percentile(db, 95) - PAUSA_ABAIXO_DB
    trechos, comeco = [], None
    for i, quieto in enumerate(np.append(silencio, False)):
        if quieto and comeco is None:
            comeco = i
        elif not quieto and comeco is not None:
            if (i - comeco) * QUADRO_S >= PAUSA_MIN_S:
                trechos.append((inicio_s + comeco * QUADRO_S, inicio_s + i * QUADRO_S))
            comeco = None
    return trechos


def _programacao_dinamica(esperado, log_dur, valido, bonus, voz=None, personas=None) -> list[int]:
    """Os K+1 pontos de corte de menor custo. `voz[p]`: custo acumulado de pôr a fala até cada ponto na persona p."""
    k, n = len(esperado), len(log_dur)
    custo = np.full(n, np.inf)
    custo[0] = 0.0
    anterior = np.zeros((k, n), dtype=np.int32)
    for t in range(k):
        termo = (log_dur - np.log(esperado[t])) ** 2
        if voz is not None:
            acumulado = voz[personas[t]]
            termo = termo + (acumulado[None, :] - acumulado[:, None])
        total = np.where(valido, custo[:, None] + termo, np.inf) - bonus[None, :]
        anterior[t] = np.argmin(total, axis=0)
        custo = total[anterior[t], np.arange(n)]
    cortes, j = [n - 1], n - 1
    for t in range(k - 1, -1, -1):
        j = int(anterior[t, j])
        cortes.append(j)
    return cortes[::-1]


def _centroide(vetores: np.ndarray) -> np.ndarray:
    media = np.mean(vetores, axis=0)
    return media / np.linalg.norm(media)


def _custo_de_voz(x, pontos, turnos, cortes, embedder, parametros) -> dict[str, np.ndarray] | None:
    """Quanto cada trecho entre pausas parece cada uma das duas personas, pelos centróides da passada anterior.

    Se o TTS emenda dois turnos sem pausa, a duração sozinha erra a fronteira, e o erro se propaga
    (si-001 no spike). Quando as duas vozes se parecem, a diferença some e a divisão volta a depender
    só da duração, sem esconder o defeito: os miolos misturados deixam os centróides mais parecidos.
    """
    personas = sorted({turno.persona for turno in turnos})
    if len(personas) != 2:
        return None
    embs: dict[str, list] = {p: [] for p in personas}
    for t, turno in enumerate(turnos):
        a, b = pontos[cortes[t]], pontos[cortes[t + 1]]
        borda = (b - a) * parametros.borda_do_miolo
        if t > 0 and b - a - 2 * borda >= parametros.miolo_min_s:
            embs[turno.persona].append(embedder(x[int((a + borda) * TAXA):int((b - borda) * TAXA)]))
    if not all(embs.values()):
        return None
    primeira, segunda = (_centroide(np.array(embs[p])) for p in personas)
    nota = np.zeros(len(pontos) - 1)  # por trecho: parece a primeira − parece a segunda, vezes a duração
    for i in range(len(pontos) - 1):
        a, b = pontos[i], pontos[i + 1]
        if b - a < TRECHO_DE_VOZ_MIN_S:
            continue
        meio, metade = (a + b) / 2, min((b - a) / 2, TRECHO_DE_VOZ_MAX_S / 2)
        vetor = embedder(x[int((meio - metade) * TAXA):int((meio + metade) * TAXA)])
        nota[i] = (vetor @ primeira - vetor @ segunda) * (b - a)
    acumulado = np.concatenate([[0.0], np.cumsum(nota)])
    # Pôr um trecho com cara da primeira no turno da segunda custa; no turno da primeira, rende.
    return {personas[0]: -parametros.peso_da_voz * acumulado, personas[1]: parametros.peso_da_voz * acumulado}


def segmentar(x: np.ndarray, turnos: list[Turno], fala: tuple[float, float], embedder: Callable | None,
              parametros: ParametrosDeSegmentacao = ParametrosDeSegmentacao()) -> list[Turno]:
    """Preenche o início, o fim e o miolo de cada turno dentro do trecho `fala` (segundos do episódio)."""
    t0, t1 = fala
    db = _energia_db(x[int(t0 * TAXA):int(t1 * TAXA)])
    candidatas = pausas(db, t0)
    # Pontos de corte possíveis: o início, o meio de cada pausa e o fim.
    pontos = np.array([t0] + [(a + b) / 2 for a, b in candidatas] + [t1])
    largura = np.array([1.0] + [b - a for a, b in candidatas] + [1.0])
    pesos = np.array([turno.caracteres + parametros.folga_caracteres for turno in turnos], dtype=float)
    esperado = (t1 - t0) * pesos / pesos.sum()
    duracao = pontos[None, :] - pontos[:, None]
    valido = duracao > 0.2
    log_dur = np.log(np.where(valido, duracao, 1.0))
    # Pausa longa é corte mais provável: bônus pela largura da pausa no ponto de chegada.
    bonus = parametros.peso_da_pausa * np.log(largura / PAUSA_MIN_S)

    for passada in range(PASSADAS_DE_DURACAO):
        cortes = _programacao_dinamica(esperado, log_dur, valido, bonus)
        if passada == PASSADAS_DE_DURACAO - 1:
            break
        # Cada bloco é uma chamada ao TTS, e a velocidade muda de uma para outra e de voz para voz:
        # reestima a duração esperada com a velocidade por bloco e por persona da passada anterior.
        obtido = np.diff(pontos[cortes])
        fator = np.ones(len(turnos))
        for grupo in (np.array([t.bloco for t in turnos]), np.array([t.persona for t in turnos])):
            for valor in np.unique(grupo):
                mesmo = grupo == valor
                fator[mesmo] *= obtido[mesmo].sum() / (esperado[mesmo] * fator[mesmo]).sum()
        esperado = esperado * fator
        esperado *= (t1 - t0) / esperado.sum()
    if embedder is not None:
        voz = _custo_de_voz(x, pontos, turnos, cortes, embedder, parametros)
        if voz is not None:
            cortes = _programacao_dinamica(esperado, log_dur, valido, bonus, voz, [t.persona for t in turnos])
    for t, turno in enumerate(turnos):
        turno.inicio, turno.fim = float(pontos[cortes[t]]), float(pontos[cortes[t + 1]])
        borda = (turno.fim - turno.inicio) * parametros.borda_do_miolo
        a, b = turno.inicio + borda, turno.fim - borda
        turno.miolo = (a, b) if t > 0 and b - a >= parametros.miolo_min_s else None
    return turnos


# --- Medida -------------------------------------------------------------------------------------


def f0_yin(x: np.ndarray, fmin: float = 60, fmax: float = 400, limiar: float = 0.15) -> np.ndarray:
    """F0 por quadro (Hz; 0 quando não vozeado), YIN com a diferença calculada por FFT."""
    janela, passo = 512, 160
    tau_max, tau_min = int(TAXA / fmin), int(TAXA / fmax)
    tamanho = janela + tau_max
    if len(x) < tamanho:
        return np.zeros(0)
    quadros = np.lib.stride_tricks.sliding_window_view(x.astype(np.float64), tamanho)[::passo]
    n = 1 << int(np.ceil(np.log2(tamanho + janela)))
    corr = np.fft.irfft(np.conj(np.fft.rfft(quadros[:, :janela], n)) * np.fft.rfft(quadros, n), n)[:, :tau_max + 1]
    quad = np.cumsum(np.pad(quadros ** 2, ((0, 0), (1, 0))), axis=1)
    taus = np.arange(tau_max + 1)
    d = quad[:, janela][:, None] + quad[:, taus + janela] - quad[:, taus] - 2 * corr
    d[:, 0] = 0
    cmnd = np.ones_like(d)
    cmnd[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(np.cumsum(d[:, 1:], axis=1), 1e-12)
    abaixo = cmnd[:, tau_min:] < limiar
    primeiro = np.argmax(abaixo, axis=1) + tau_min
    linhas = np.arange(len(cmnd))
    for _ in range(8):  # desce até o mínimo local depois do primeiro ponto abaixo do limiar
        proximo = np.minimum(primeiro + 1, tau_max)
        primeiro = np.where(cmnd[linhas, proximo] < cmnd[linhas, primeiro], proximo, primeiro)
    return np.where(abaixo.any(axis=1), TAXA / primeiro, 0.0)


@dataclass(frozen=True)
class Medidas:
    """Um embedding e um F0 por miolo medido, com a persona e o bloco do turno."""

    persona: np.ndarray
    bloco: np.ndarray
    vetores: np.ndarray
    f0: np.ndarray

    def da_persona(self, persona: str) -> np.ndarray:
        return self.vetores[self.persona == persona]

    def centroide(self, persona: str) -> np.ndarray:
        return _centroide(self.da_persona(persona))

    @property
    def personas(self) -> list[str]:
        return sorted(set(self.persona.tolist()))


def medir_miolos(x: np.ndarray, turnos: Sequence[Turno], embedder: Callable[[np.ndarray], np.ndarray]) -> Medidas:
    persona, bloco, vetores, f0 = [], [], [], []
    for turno in turnos:
        if not turno.miolo:
            continue
        a, b = turno.miolo
        if b - a > MAX_MIOLO_S:
            meio = (a + b) / 2
            a, b = meio - MAX_MIOLO_S / 2, meio + MAX_MIOLO_S / 2
        trecho = x[int(a * TAXA):int(b * TAXA)]
        vozeado = (quadros := f0_yin(trecho))[quadros > 0]
        persona.append(turno.persona)
        bloco.append(turno.bloco)
        vetores.append(embedder(trecho))
        f0.append(float(np.median(vozeado)) if len(vozeado) else 0.0)
    return Medidas(np.array(persona, dtype=object), np.array(bloco), np.array(vetores, dtype=np.float32), np.array(f0))


# --- Impressão de voz de referência ---------------------------------------------------------------


@dataclass(frozen=True)
class ImpressaoDeVoz:
    voz: str
    vetor: tuple[float, ...]
    episodios: tuple[str, ...]
    data: str


@dataclass(frozen=True)
class Referencia:
    """`config/vozes-referencia.json`: só muda por PR, gerado pelo comando `referencia` (ADR 0012)."""

    modelo_sha256: str
    personas: Mapping[str, ImpressaoDeVoz]

    @classmethod
    def ler(cls, arquivo: Path) -> "Referencia":
        if not arquivo.exists():
            return cls("", {})
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return cls(dados["modelo_sha256"], {
            persona: ImpressaoDeVoz(item["voz"], tuple(item["vetor"]), tuple(item["episodios"]), item["data"])
            for persona, item in dados["personas"].items()
        })

    def gravar(self, arquivo: Path) -> None:
        dados = {
            "modelo_sha256": self.modelo_sha256,
            "personas": {
                persona: {"voz": item.voz, "episodios": list(item.episodios), "data": item.data,
                          "vetor": [round(valor, 5) for valor in item.vetor]}
                for persona, item in sorted(self.personas.items())
            },
        }
        arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def valida(self, persona: Persona, modelo_sha256: str) -> tuple[np.ndarray | None, str | None]:
        """O vetor da persona, ou None e o motivo de não haver referência válida."""
        item = self.personas.get(persona.id)
        if item is None:
            return None, "sem referência (estreia: só as medidas de dentro do episódio)"
        if self.modelo_sha256 != modelo_sha256:
            return None, "sem referência válida: a referência foi medida com outro modelo"
        if item.voz != persona.voz.gemini:
            return None, f"sem referência válida: a voz do Gemini mudou ({item.voz} → {persona.voz.gemini})"
        return np.array(item.vetor), None


def referencia_de(medidas: Mapping[str, Medidas], personas: Mapping[str, Persona], modelo_sha256: str,
                  hoje: str | None = None) -> Referencia:
    """A média dos centróides de cada persona, um por episódio."""
    hoje = hoje or date.today().isoformat()
    por_persona: dict[str, list[tuple[str, np.ndarray]]] = {}
    for episodio_id, medida in sorted(medidas.items()):
        for persona in medida.personas:
            por_persona.setdefault(persona, []).append((episodio_id, medida.centroide(persona)))
    return Referencia(modelo_sha256, {
        persona: ImpressaoDeVoz(personas[persona].voz.gemini,
                                tuple(float(v) for v in _centroide(np.array([c for _, c in itens]))),
                                tuple(e for e, _ in itens), hoje)
        for persona, itens in por_persona.items()
    })


# --- Regras e laudo -----------------------------------------------------------------------------


@dataclass(frozen=True)
class MedidaDeBloco:
    persona: str
    bloco: int
    miolos: int
    contra_o_episodio: float | None
    contra_a_referencia: float | None


@dataclass(frozen=True)
class MedidaDePersona:
    persona: str
    nome: str
    voz: str
    miolos: int
    f0_hz: float
    contra_a_referencia: float | None
    sem_referencia: str | None = None


@dataclass(frozen=True)
class Par:
    primeira: str
    segunda: str
    semelhanca: float


@dataclass(frozen=True)
class LaudoDeVoz:
    limites: LimitesDeVoz = field(default_factory=LimitesDeVoz)
    personas: tuple[MedidaDePersona, ...] = ()
    blocos: tuple[MedidaDeBloco, ...] = ()
    pares: tuple[Par, ...] = ()
    problemas: tuple[str, ...] = ()
    nao_aplicavel: str | None = None

    @property
    def aplicavel(self) -> bool:
        return self.nao_aplicavel is None

    @property
    def aprovado(self) -> bool:
        return self.aplicavel and not self.problemas

    def markdown(self, titulo: str) -> str:
        if not self.aplicavel:
            return f"### {titulo}: não aplicável\n\n{self.nao_aplicavel}\n"
        lim = self.limites
        linhas = [f"### {titulo}: {'aprovado' if self.aprovado else 'reprovado'}", ""]
        linhas += [f"- {problema}" for problema in self.problemas] + ([""] if self.problemas else [])
        linhas += [
            "Semelhança de timbre (cosseno de 0 a 1; a mesma voz dá 0,9 ou mais).",
            "",
            f"| Persona | Voz | Trechos | F0 | Contra a referência (mín. {_numero(lim.persona_referencia_min)}) |",
            "|---|---|---|---|---|",
        ]
        for p in self.personas:
            referencia = _numero(p.contra_a_referencia) if p.contra_a_referencia is not None else p.sem_referencia
            linhas.append(f"| {p.nome} | {p.voz} | {p.miolos} | {p.f0_hz:.0f} Hz | {referencia} |")
        linhas += ["", f"| Par de vozes | Semelhança (máx. {_numero(lim.vozes_confundiveis_max)}) |", "|---|---|"]
        linhas += [f"| {par.primeira} × {par.segunda} | {_numero(par.semelhanca)} |" for par in self.pares]
        linhas += [
            "",
            f"| Persona | Bloco | Trechos | Contra o resto do episódio (mín. {_numero(lim.timbre_bloco_min)}) "
            f"| Contra a referência (mín. {_numero(lim.timbre_referencia_min)}) |",
            "|---|---|---|---|---|",
        ]
        for b in self.blocos:
            if b.contra_o_episodio is None:
                linhas.append(f"| {b.persona} | {b.bloco + 1} | {b.miolos} | não julgado: menos de "
                              f"{lim.miolos_min_no_bloco} trechos no bloco ou no resto | |")
                continue
            referencia = _numero(b.contra_a_referencia) if b.contra_a_referencia is not None else "—"
            linhas.append(f"| {b.persona} | {b.bloco + 1} | {b.miolos} | {_numero(b.contra_o_episodio)} | {referencia} |")
        return "\n".join(linhas) + "\n"

    def para_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def de_json(cls, texto: str) -> "LaudoDeVoz":
        dados = json.loads(texto)
        return cls(
            LimitesDeVoz(**dados["limites"]),
            tuple(MedidaDePersona(**p) for p in dados["personas"]),
            tuple(MedidaDeBloco(**b) for b in dados["blocos"]),
            tuple(Par(**p) for p in dados["pares"]),
            tuple(dados["problemas"]),
            dados["nao_aplicavel"],
        )


def avaliar(medidas: Medidas, personas: Mapping[str, Persona], referencias: Mapping[str, np.ndarray],
            sem_referencia: Mapping[str, str], limites: LimitesDeVoz) -> LaudoDeVoz:
    """Aplica as regras. `referencias`: o vetor válido de cada persona que tem um; `sem_referencia`: o motivo das outras."""
    nomes = {pid: personas[pid].nome if pid in personas else pid for pid in medidas.personas}
    problemas, por_persona, por_bloco, pares = [], [], [], []
    for pid in medidas.personas:
        centroide = medidas.centroide(pid)
        da_persona = medidas.persona == pid
        f0 = medidas.f0[da_persona & (medidas.f0 > 0)]
        referencia = referencias.get(pid)
        contra = float(centroide @ referencia) if referencia is not None else None
        if contra is not None and contra < limites.persona_referencia_min:
            problemas.append(f"{nomes[pid]} no episódio inteiro não soa como a própria referência: {_numero(contra)} "
                             f"(mín. {_numero(limites.persona_referencia_min)}).")
        por_persona.append(MedidaDePersona(
            pid, nomes[pid], personas[pid].voz.gemini if pid in personas else "?", int(da_persona.sum()),
            float(np.median(f0)) if len(f0) else 0.0, contra, None if referencia is not None else sem_referencia.get(pid)))
        for bloco in sorted(set(medidas.bloco[da_persona].tolist())):
            no_bloco = da_persona & (medidas.bloco == bloco)
            resto = da_persona & (medidas.bloco != bloco)
            if no_bloco.sum() < limites.miolos_min_no_bloco or resto.sum() < limites.miolos_min_no_bloco:
                por_bloco.append(MedidaDeBloco(pid, int(bloco), int(no_bloco.sum()), None, None))
                continue
            do_bloco = _centroide(medidas.vetores[no_bloco])
            interno = float(do_bloco @ _centroide(medidas.vetores[resto]))
            externo = float(do_bloco @ referencia) if referencia is not None else None
            if interno < limites.timbre_bloco_min:
                problemas.append(f"{nomes[pid]} muda de timbre no bloco {bloco + 1}: {_numero(interno)} contra o resto "
                                 f"do episódio (mín. {_numero(limites.timbre_bloco_min)}).")
            if externo is not None and externo < limites.timbre_referencia_min:
                problemas.append(f"{nomes[pid]} no bloco {bloco + 1} não soa como a referência: {_numero(externo)} "
                                 f"(mín. {_numero(limites.timbre_referencia_min)}).")
            por_bloco.append(MedidaDeBloco(pid, int(bloco), int(no_bloco.sum()), interno, externo))
    ids = medidas.personas
    for i, primeira in enumerate(ids):
        for segunda in ids[i + 1:]:
            semelhanca = float(medidas.centroide(primeira) @ medidas.centroide(segunda))
            pares.append(Par(nomes[primeira], nomes[segunda], semelhanca))
            if semelhanca > limites.vozes_confundiveis_max:
                f0 = {p.persona: p.f0_hz for p in por_persona}
                problemas.append(f"{nomes[primeira]} e {nomes[segunda]} soam como a mesma voz: {_numero(semelhanca)} "
                                 f"(máx. {_numero(limites.vozes_confundiveis_max)}; {nomes[primeira]} em "
                                 f"{f0[primeira]:.0f} Hz, {nomes[segunda]} em {f0[segunda]:.0f} Hz).")
    return LaudoDeVoz(limites, tuple(por_persona), tuple(por_bloco), tuple(pares), tuple(problemas))


# --- Incidentes ---------------------------------------------------------------------------------


class RegistroDeVoz(Protocol):
    def registrar(self, episodio_id: str, laudo: LaudoDeVoz) -> None: ...

    def comentar_candidata(self, episodio_id: str, laudo: LaudoDeVoz) -> None: ...

    def comentar(self, episodio_id: str, texto: str) -> None: ...


@dataclass(frozen=True)
class IncidentesDeVoz:
    """Uma issue `incidente` por episódio reprovado, que fecha quando a voz dele passa (padrão do QA do áudio)."""

    repositorio: str
    execucao: str | None = None
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def registrar(self, episodio_id: str, laudo: LaudoDeVoz) -> None:
        if not laudo.aplicavel:
            return
        titulo, relatorio = self.titulo(episodio_id), laudo.markdown(f"Voz do {episodio_id}")
        if laudo.aprovado:
            self._issues.fechar(titulo, f"A voz do {episodio_id} passou no QA.\n\n{relatorio}")
            return
        self._issues.abrir_ou_comentar(titulo, "\n".join([
            f"O {episodio_id} foi publicado, mas a voz não passou no QA de voz (ADR 0012).",
            "",
            relatorio,
            "Ouça o trecho e comente aqui se o aviso **acertou** ou foi **alarme falso**: é o que calibra os "
            "limites antes de ligar o modo regravar. Se acertou, regrave (workflow Regravar áudio). A issue fecha "
            "sozinha quando a voz do episódio passar, por exemplo depois de regravar e substituir.",
        ]), f"Nova verificação da voz do {episodio_id}.\n\n{relatorio}")

    def comentar_candidata(self, episodio_id: str, laudo: LaudoDeVoz) -> None:
        """Na issue aberta do episódio, se houver: a candidata passou ou não."""
        if not laudo.aplicavel:
            return
        veredito = ("Candidata **aprovada** no QA de voz: ouça e, se ficou melhor, substitua (workflow Regravar "
                    "áudio, ação substituir)." if laudo.aprovado else
                    "A candidata **também reprovou** no QA de voz. A próxima regravação é manual.")
        self.comentar(episodio_id, f"{veredito}\n\n{laudo.markdown(f'Voz da candidata do {episodio_id}')}")

    def comentar(self, episodio_id: str, texto: str) -> None:
        self._issues.comentar(self.titulo(episodio_id), texto)

    @staticmethod
    def titulo(episodio_id: str) -> str:
        return f"Voz do {episodio_id} fora do padrão"

    @property
    def _issues(self) -> IssuesDeIncidente:
        return IssuesDeIncidente(self.repositorio, self.execucao, self.executar)


# --- O QA ---------------------------------------------------------------------------------------


@dataclass
class QaDeVoz:
    modelo: Modelo
    personas: Mapping[str, Persona]
    max_caracteres_por_bloco: int
    referencia: Referencia
    limites: LimitesDeVoz = field(default_factory=LimitesDeVoz)
    segmentacao: ParametrosDeSegmentacao = field(default_factory=ParametrosDeSegmentacao)
    modo: str = "aviso"
    incidentes: RegistroDeVoz | None = None
    obter: Callable[[Modelo], Path] = obter_modelo
    criar_embedder: Callable[[Path], Callable[[np.ndarray], np.ndarray]] = Embedder
    _embedder: Callable[[np.ndarray], np.ndarray] | None = field(default=None, init=False, repr=False)

    @classmethod
    def de_config(cls, config: Mapping[str, Any], config_tts: Mapping[str, Any], personas: Mapping[str, Persona],
                  referencia: Path, incidentes: RegistroDeVoz | None = None) -> "QaDeVoz":
        modo = config.get("modo", "aviso")
        if modo not in MODOS:
            raise ValueError(f"qa_voz.modo precisa ser um de {MODOS}, não {modo!r}")
        return cls(
            Modelo(**config["modelo"]), personas, config_tts["max_caracteres_por_bloco"], Referencia.ler(referencia),
            LimitesDeVoz(**(config.get("limites") or {})), ParametrosDeSegmentacao(**(config.get("segmentacao") or {})),
            modo, incidentes,
        )

    @property
    def embedder(self) -> Callable[[np.ndarray], np.ndarray]:
        """Baixa (ou acha no cache) e confere o modelo na primeira vez; só então o carrega."""
        if self._embedder is None:
            self._embedder = self.criar_embedder(self.obter(self.modelo))
        return self._embedder

    def rodar(self, episodio_id: str, mp3: Path, trechos: Trechos, falas: Sequence[Fala],
              fallback: bool = False) -> LaudoDeVoz:
        """`falas`: as que foram ao TTS (com o dicionário de pronúncia), porque o tamanho de cada turno conta."""
        if fallback:
            return LaudoDeVoz(nao_aplicavel="Narrado no fallback (Kokoro), em que as personas dividem vozes: o QA "
                                            "de voz só vale para o TTS principal (#28).")
        laudo = self.medir(mp3, trechos, falas)
        if self.incidentes is not None:
            self.incidentes.registrar(episodio_id, laudo)
        return laudo

    def medidas(self, mp3: Path, trechos: Trechos, falas: Sequence[Fala]) -> Medidas:
        x = decodificar(mp3)
        turnos = segmentar(x, turnos_das_falas(falas, self.max_caracteres_por_bloco), trechos.fala, self.embedder,
                           self.segmentacao)
        return medir_miolos(x, turnos, self.embedder)

    def medir(self, mp3: Path, trechos: Trechos, falas: Sequence[Fala]) -> LaudoDeVoz:
        return self.avaliar(self.medidas(mp3, trechos, falas))

    def avaliar(self, medidas: Medidas, referencia: Referencia | None = None) -> LaudoDeVoz:
        referencia = referencia or self.referencia
        validas, motivos = {}, {}
        for pid in medidas.personas:
            persona = self.personas.get(pid)
            vetor, motivo = referencia.valida(persona, self.modelo.sha256) if persona else (None, "persona desconhecida")
            if vetor is not None:
                validas[pid] = vetor
            else:
                motivos[pid] = motivo
        return avaliar(medidas, self.personas, validas, motivos, self.limites)


# --- Modo regravar ------------------------------------------------------------------------------


def a_regravar(modo: str, publicados: Sequence[str], aguardando: Sequence[str],
               laudos: Mapping[str, LaudoDeVoz]) -> list[str]:
    """Quem a publicação manda regravar sozinha: no máximo um, e nunca gastando a cota de quem espera por ela.

    Só a publicação chama isto, e um episódio só é publicado uma vez: daí sai o "no máximo uma candidata
    automática por episódio" (ADR 0012). A candidata gasta de 4 a 5 requisições, de 10 por dia (ADR 0011).
    """
    if modo != "regravar" or aguardando or len(publicados) != 1:
        return []
    [episodio_id] = publicados
    laudo = laudos.get(episodio_id)
    return [episodio_id] if laudo is not None and laudo.aplicavel and not laudo.aprovado else []


def disparar_regravacao(episodios: Sequence[str], repositorio: str, incidentes: RegistroDeVoz,
                        executar: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> list[str]:
    """Dispara o `regravar.yml` para cada id (a publicação passa no máximo um) e comenta na issue de voz."""
    disparados = []
    for episodio_id in episodios:
        if not PADRAO_DE_ID.match(episodio_id):
            raise ValueError(f"id de episódio inválido: {episodio_id!r}")
        executar(["gh", "workflow", "run", "regravar.yml", "-f", f"episodio={episodio_id}", "-f", "acao=regravar",
                  "--repo", repositorio], check=True)
        incidentes.comentar(episodio_id, "O modo regravar do QA de voz disparou uma candidata (workflow Regravar "
                                         "áudio). O laudo dela vem aqui quando sair.")
        disparados.append(episodio_id)
    return disparados


# --- Episódios publicados (referência e conferência) ----------------------------------------------


def trechos_publicados(mp3: Path, config_audio: Mapping[str, Any], com_vinheta: bool) -> Trechos:
    """Onde fica a fala num MP3 já publicado: sai da config da vinheta, sem metadado novo."""
    duracao = duracao_mp3(mp3)
    dados = config_audio.get("vinheta")
    if not (com_vinheta and dados):
        return Trechos(fala=(0.0, duracao))
    vinheta = Vinheta.de_config(Path(dados["arquivo"]), dados)
    fim = duracao - (vinheta.encerramento.duracao_s if vinheta.encerramento else 0.0)
    return Trechos(fala=(vinheta.entrada_da_fala_s, fim))


def medir_publicado(qa: QaDeVoz, raiz: Path, episodio_id: str, mp3: Path) -> Medidas:
    from podcast.publicacao import falas_do_episodio
    from podcast.roteiro import Projeto

    projeto = Projeto(raiz)
    config = projeto.config()
    pasta = projeto.episodios / episodio_id
    publicacao = json.loads((pasta / "publicacao.json").read_text(encoding="utf-8"))
    if publicacao["tts"]["fallback"]:
        raise ValueError(f"{episodio_id} foi narrado no fallback: não entra na referência de voz")
    falas = falas_do_episodio(pasta, qa.personas, config["tts"])
    return qa.medidas(mp3, trechos_publicados(mp3, config["audio"], publicacao.get("vinheta", False)), falas)


def baixar_publicado(repositorio: str, episodio_id: str, pasta: Path,
                     executar: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Path:
    nome = f"pebacast-{episodio_id}.mp3"
    executar(["gh", "release", "download", f"episodio-{episodio_id}", "--pattern", nome, "--dir", str(pasta),
              "--clobber", "--repo", repositorio], check=True)
    return pasta / nome


def _id(valor: str) -> str:
    if not PADRAO_DE_ID.match(valor):
        raise argparse.ArgumentTypeError(f"id de episódio inválido: {valor!r}")
    return valor


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qualidade_voz", description="QA de voz (ADR 0012).")
    parser.add_argument("--raiz", type=Path, default=Path.cwd())
    comandos = parser.add_subparsers(dest="comando", required=True)
    referencia = comandos.add_parser("referencia", help="Mede os episódios indicados e reescreve a referência de voz.")
    referencia.add_argument("--repo", required=True, help="dono/repositorio dos releases com os MP3.")
    referencia.add_argument("--episodios", nargs="+", type=_id, required=True)
    referencia.add_argument("--saida", type=Path, help="Padrão: config/vozes-referencia.json na raiz.")
    avaliar_ = comandos.add_parser("avaliar", help="Roda o QA de voz em episódios publicados, sem abrir issue.")
    avaliar_.add_argument("--repo", required=True)
    avaliar_.add_argument("episodios", nargs="+", type=_id)
    disparar = comandos.add_parser("disparar", help="Modo regravar: dispara o regravar.yml que o relatório pede.")
    disparar.add_argument("--repo", required=True)
    disparar.add_argument("--relatorio", type=Path, default=Path("relatorio.json"))
    disparar.add_argument("--execucao")
    return parser


def _qa(raiz: Path) -> QaDeVoz:
    from podcast.personas import carregar_personas
    from podcast.roteiro import Projeto

    config = Projeto(raiz).config()
    return QaDeVoz.de_config(config["qa_voz"], config["tts"], carregar_personas(raiz / "curriculum" / "personas"),
                             raiz / REFERENCIA)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _criar_parser().parse_args(argv)
    if args.comando == "disparar":
        relatorio = json.loads(args.relatorio.read_text(encoding="utf-8")) if args.relatorio.exists() else {}
        ids = relatorio.get("regravar_automatico", [])
        disparados = disparar_regravacao(ids, args.repo, IncidentesDeVoz(args.repo, args.execucao))
        print(f"Regravação disparada: {', '.join(disparados) or 'nenhuma'}")
        return 0

    qa = _qa(args.raiz)
    with tempfile.TemporaryDirectory() as pasta:
        medidas = {}
        for episodio_id in args.episodios:
            mp3 = baixar_publicado(args.repo, episodio_id, Path(pasta))
            medidas[episodio_id] = medir_publicado(qa, args.raiz, episodio_id, mp3)
            mp3.unlink()
    if args.comando == "referencia":
        destino = args.saida or args.raiz / REFERENCIA
        referencia_de(medidas, qa.personas, qa.modelo.sha256).gravar(destino)
        print(f"Referência gravada em {destino}, com {', '.join(args.episodios)}.")
        return 0
    for episodio_id, medida in medidas.items():
        print(qa.avaliar(medida).markdown(f"Voz do {episodio_id}"))
    return 0


def _numero(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


if __name__ == "__main__":
    raise SystemExit(main())

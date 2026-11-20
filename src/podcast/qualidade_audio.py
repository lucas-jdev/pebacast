"""QA do MP3 montado: mede o que dá para medir sem ouvir.

O QA não segura a publicação: o episódio sai mesmo reprovado, e a reprovação vira uma issue
`incidente` que fecha sozinha quando o áudio daquele episódio passar.
"""

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from podcast.audio import ALVO_LOUDNESS_LUFS, Loudness, Trechos, medir_loudness

# Folga para o meio da pausa cair dentro do silêncio detectado mesmo com o atraso do limitador.
TOLERANCIA_TROCA_S = 0.05


@dataclass(frozen=True)
class Limites:
    """Limites do QA. Partem do alvo da montagem e podem ser ajustados em `audio.qualidade`."""

    loudness_lufs: float = ALVO_LOUDNESS_LUFS
    tolerancia_lu: float = 1.0
    pico_maximo_dbtp: float = -1.0
    musica_acima_da_fala_lu: float = 0.0
    pausa_maxima_s: float = 0.6
    silencio_dbfs: float = -50.0

    @classmethod
    def de_config(cls, config_audio: Mapping[str, Any]) -> "Limites":
        return cls(**(config_audio.get("qualidade") or {}))


@dataclass(frozen=True)
class Medicao:
    pico_real_dbtp: float
    loudness_lufs: float
    fala_lufs: float
    abertura_lufs: float | None
    encerramento_lufs: float | None
    maior_pausa_s: float
    trocas: int

    def para_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def de_json(cls, texto: str) -> "Medicao":
        return cls(**json.loads(texto))


@dataclass(frozen=True)
class Medida:
    nome: str
    valor: str
    limite: str
    aprovada: bool


@dataclass(frozen=True)
class Laudo:
    medidas: tuple[Medida, ...]

    @property
    def aprovado(self) -> bool:
        return all(medida.aprovada for medida in self.medidas)

    def markdown(self, titulo: str) -> str:
        linhas = [
            f"### {titulo}: {_resultado(self.aprovado)}",
            "",
            "| Medida | Valor | Limite | Resultado |",
            "|---|---|---|---|",
            *[f"| {m.nome} | {m.valor} | {m.limite} | {_resultado(m.aprovada)} |" for m in self.medidas],
        ]
        return "\n".join(linhas) + "\n"


def medir(mp3: Path, trechos: Trechos, limites: Limites) -> Medicao:
    total = _loudness(mp3)
    fala = _loudness(mp3, trechos.fala)
    return Medicao(
        pico_real_dbtp=total.pico_real_dbtp,
        loudness_lufs=total.integrada_lufs,
        fala_lufs=fala.integrada_lufs,
        abertura_lufs=_loudness(mp3, trechos.abertura).integrada_lufs if trechos.abertura else None,
        encerramento_lufs=_loudness(mp3, trechos.encerramento).integrada_lufs if trechos.encerramento else None,
        maior_pausa_s=maior_pausa(trechos.trocas_s, silencios(mp3, trechos.fala, limites.silencio_dbfs)),
        trocas=len(trechos.trocas_s),
    )


def avaliar(medicao: Medicao, limites: Limites) -> Laudo:
    musicas = {nome: lufs for nome, lufs in (("abertura", medicao.abertura_lufs),
                                              ("encerramento", medicao.encerramento_lufs)) if lufs is not None}
    limite_musica = (f"até {_numero(limites.musica_acima_da_fala_lu)} LU acima da fala"
                     if limites.musica_acima_da_fala_lu else "não passa a fala")
    return Laudo((
        Medida(
            "Pico real", f"{_numero(medicao.pico_real_dbtp)} dBTP", f"≤ {_numero(limites.pico_maximo_dbtp)} dBTP",
            medicao.pico_real_dbtp <= limites.pico_maximo_dbtp,
        ),
        Medida(
            "Loudness integrada", f"{_numero(medicao.loudness_lufs)} LUFS",
            f"{_numero(limites.loudness_lufs)} ± {_numero(limites.tolerancia_lu)} LUFS",
            abs(medicao.loudness_lufs - limites.loudness_lufs) <= limites.tolerancia_lu,
        ),
        Medida(
            "Música (abertura e encerramento)",
            " · ".join([*(f"{nome} {_numero(lufs)}" for nome, lufs in musicas.items()),
                        f"fala {_numero(medicao.fala_lufs)} LUFS"]) if musicas else "sem vinheta",
            limite_musica,
            all(lufs - medicao.fala_lufs <= limites.musica_acima_da_fala_lu for lufs in musicas.values()),
        ),
        Medida(
            "Pausa na troca de blocos",
            f"{_numero(medicao.maior_pausa_s, 2)} s ({medicao.trocas} trocas)",
            f"≤ {_numero(limites.pausa_maxima_s, 2)} s",
            medicao.maior_pausa_s <= limites.pausa_maxima_s,
        ),
    ))


def silencios(mp3: Path, trecho: tuple[float, float], limiar_dbfs: float) -> list[tuple[float, float]]:
    """Intervalos de silêncio dentro do trecho, em segundos do episódio."""
    inicio, fim = trecho
    resultado = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-ss", f"{inicio:.3f}", "-to", f"{fim:.3f}", "-i", str(mp3),
         "-af", f"silencedetect=noise={limiar_dbfs}dB:d=0.05", "-f", "null", "-"],
        capture_output=True, check=True,
    )
    log = resultado.stderr.decode("utf-8", "replace")
    comecos = [float(valor) for valor in re.findall(r"silence_start: (\S+)", log)]
    finais = [float(valor) for valor in re.findall(r"silence_end: (\S+)", log)]
    finais += [fim - inicio] * (len(comecos) - len(finais))
    return [(inicio + comeco, inicio + final) for comeco, final in zip(comecos, finais)]


def maior_pausa(trocas_s: Sequence[float], intervalos: Sequence[tuple[float, float]]) -> float:
    """A maior pausa que contém uma troca de blocos. As pausas no meio de um bloco são do TTS, não da montagem."""
    pausas = [
        fim - comeco
        for troca in trocas_s
        for comeco, fim in intervalos
        if comeco - TOLERANCIA_TROCA_S <= troca <= fim + TOLERANCIA_TROCA_S
    ]
    return max(pausas, default=0.0)


class RegistroDeIncidentes(Protocol):
    def registrar(self, episodio_id: str, laudo: Laudo) -> None:
        """Abre (ou comenta) a issue do episódio reprovado e fecha a do aprovado."""
        ...


@dataclass(frozen=True)
class IncidentesDeAudio:
    """Uma issue `incidente` por episódio, no padrão das outras issues abertas pelos workflows."""

    repositorio: str
    execucao: str | None = None
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def registrar(self, episodio_id: str, laudo: Laudo) -> None:
        abertas = self._abertas(episodio_id)
        if laudo.aprovado:
            for numero in abertas:
                self._gh("issue", "close", str(numero), "--reason", "completed", "--comment",
                         self._corpo(f"O áudio do {episodio_id} passou no QA.", episodio_id, laudo))
            return
        corpo = self._corpo(f"O áudio do {episodio_id} foi publicado, mas não passou no QA.", episodio_id, laudo)
        if abertas:
            self._gh("issue", "comment", str(abertas[0]), "--body", corpo)
        else:
            self._gh("issue", "create", "--title", self.titulo(episodio_id), "--label", "incidente", "--body", corpo)

    @staticmethod
    def titulo(episodio_id: str) -> str:
        # Sem terminar em ": <id>": esse é o padrão das issues de roteiro, que a publicação fecha.
        return f"Áudio do {episodio_id} fora do padrão"

    def _abertas(self, episodio_id: str) -> list[int]:
        titulo = self.titulo(episodio_id)
        saida = self._gh("issue", "list", "--state", "open", "--label", "incidente",
                         "--search", f'"{titulo}" in:title', "--json", "number,title", capture_output=True, text=True)
        return [issue["number"] for issue in json.loads(saida.stdout or "[]") if issue["title"] == titulo]

    def _corpo(self, abertura: str, episodio_id: str, laudo: Laudo) -> str:
        partes = [abertura, "", laudo.markdown(f"Qualidade do áudio do {episodio_id}")]
        if not laudo.aprovado:
            partes.append("A issue fecha sozinha quando o áudio do episódio passar no QA, por exemplo depois de "
                          "regravar e substituir (`regravar.yml`).")
        if self.execucao:
            partes += ["", f"Execução: {self.execucao}"]
        return "\n".join(partes)

    def _gh(self, *argumentos: str, **opcoes: Any) -> subprocess.CompletedProcess:
        return self.executar(["gh", *argumentos, "--repo", self.repositorio], check=True, **opcoes)


def _loudness(mp3: Path, trecho: tuple[float, float] | None = None) -> Loudness:
    corte = ["-ss", f"{trecho[0]:.3f}", "-to", f"{trecho[1]:.3f}"] if trecho else []
    return medir_loudness([*corte, "-i", str(mp3)], "[0:a]anull[medir]")


def _numero(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def _resultado(aprovado: bool) -> str:
    return "aprovado" if aprovado else "reprovado"

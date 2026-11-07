import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

AMOSTRA_BYTES = 2
LOUDNESS_PODCAST = "loudnorm=I=-16:TP=-1.5:LRA=11"


@dataclass(frozen=True)
class Audio:
    """PCM 16 bits mono little-endian."""

    pcm: bytes
    taxa_amostragem: int

    @classmethod
    def silencio(cls, duracao_ms: int, taxa_amostragem: int) -> "Audio":
        amostras = taxa_amostragem * duracao_ms // 1000
        return cls(bytes(amostras * AMOSTRA_BYTES), taxa_amostragem)

    @classmethod
    def de_float(cls, amostras: np.ndarray, taxa_amostragem: int) -> "Audio":
        pcm16 = (np.clip(amostras, -1.0, 1.0) * np.iinfo(np.int16).max).astype("<i2")
        return cls(pcm16.tobytes(), taxa_amostragem)

    @property
    def duracao_segundos(self) -> float:
        return len(self.pcm) / AMOSTRA_BYTES / self.taxa_amostragem


def concatenar(partes: Sequence[Audio], pausa_ms: int = 0) -> Audio:
    if not partes:
        raise ValueError("Nada para concatenar.")

    taxas = {parte.taxa_amostragem for parte in partes}
    if len(taxas) > 1:
        raise ValueError(f"Taxas de amostragem diferentes: {sorted(taxas)}.")

    taxa = taxas.pop()
    pausa = Audio.silencio(pausa_ms, taxa).pcm
    return Audio(pausa.join(parte.pcm for parte in partes), taxa)


@dataclass(frozen=True)
class Vinheta:
    """Recorte de uma faixa musical tocado na abertura e, opcionalmente, no encerramento.

    A primeira fala entra `sobreposicao_s` segundos antes do fim do recorte, por cima do fade-out.
    """

    arquivo: Path
    inicio_s: float
    duracao_s: float
    fade_entrada_s: float = 0.5
    fade_saida_s: float = 3.0
    sobreposicao_s: float = 1.5
    volume: float = 0.7
    encerramento: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.sobreposicao_s <= self.fade_saida_s <= self.duracao_s:
            raise ValueError("A vinheta precisa de 0 <= sobreposicao_s <= fade_saida_s <= duracao_s.")

    def filtro(self, entrada_fala: str, entrada_musica: str, taxa: int) -> str:
        """Grafo do ffmpeg que mistura a vinheta com a fala e entrega o rótulo [episodio]."""
        fade_saida_inicio = self.duracao_s - self.fade_saida_s
        recorte = (
            f"atrim=start={self.inicio_s}:duration={self.duracao_s},asetpts=PTS-STARTPTS,"
            f"aformat=sample_rates={taxa}:channel_layouts=mono,volume={self.volume},"
            f"afade=t=in:d={self.fade_entrada_s},afade=t=out:st={fade_saida_inicio}:d={self.fade_saida_s}"
        )
        atraso_ms = round((self.duracao_s - self.sobreposicao_s) * 1000)
        fala = f"[{entrada_fala}]adelay={atraso_ms}[fala]"
        if not self.encerramento:
            return ";".join([
                f"[{entrada_musica}]{recorte}[abertura]",
                fala,
                "[abertura][fala]amix=inputs=2:duration=longest:normalize=0[episodio]",
            ])
        return ";".join([
            f"[{entrada_musica}]{recorte},asplit=2[abertura][fecho]",
            fala,
            "[abertura][fala]amix=inputs=2:duration=longest:normalize=0[corpo]",
            "[corpo][fecho]concat=n=2:v=0:a=1[episodio]",
        ])


def exportar_mp3(
    audio: Audio,
    destino: Path,
    bitrate_kbps: int,
    taxa_saida: int = 24_000,
    vinheta: Vinheta | None = None,
) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    entrada_fala = ["-f", "s16le", "-ar", str(audio.taxa_amostragem), "-ac", "1", "-i", "pipe:0"]
    if vinheta is None:
        entradas, filtro = entrada_fala, ["-af", LOUDNESS_PODCAST]
    else:
        entradas = [*entrada_fala, "-i", str(vinheta.arquivo)]
        grafo = f"{vinheta.filtro('0:a', '1:a', audio.taxa_amostragem)};[episodio]{LOUDNESS_PODCAST}[saida]"
        filtro = ["-filter_complex", grafo, "-map", "[saida]"]
    comando = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *entradas, *filtro,
        "-ar", str(taxa_saida), "-ac", "1", "-b:a", f"{bitrate_kbps}k",
        str(destino),
    ]
    subprocess.run(comando, input=audio.pcm, check=True)


def duracao_mp3(arquivo: Path) -> float:
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arquivo)],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())

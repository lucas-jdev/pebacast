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


def exportar_mp3(audio: Audio, destino: Path, bitrate_kbps: int, taxa_saida: int = 24_000) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    comando = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "s16le", "-ar", str(audio.taxa_amostragem), "-ac", "1", "-i", "pipe:0",
        "-af", LOUDNESS_PODCAST,
        "-ar", str(taxa_saida), "-ac", "1", "-b:a", f"{bitrate_kbps}k",
        str(destino),
    ]
    subprocess.run(comando, input=audio.pcm, check=True)

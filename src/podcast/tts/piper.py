from collections.abc import Sequence
from pathlib import Path
from typing import Any

from podcast.audio import Audio
from podcast.dominio import Fala
from podcast.tts.provedor import sintetizar_fala_a_fala


class PiperTts:
    nome = "piper"

    def __init__(self, diretorio_vozes: Path, pausa_entre_falas_ms: int = 350) -> None:
        self._diretorio = diretorio_vozes
        self._pausa_ms = pausa_entre_falas_ms
        self._vozes: dict[str, Any] = {}

    def sintetizar(self, falas: Sequence[Fala]) -> Audio:
        return sintetizar_fala_a_fala(falas, self._sintetizar_fala, self._pausa_ms)

    def _sintetizar_fala(self, fala: Fala) -> Audio:
        trechos = list(self._carregar_voz(fala.persona.voz.piper).synthesize(fala.texto))
        if not trechos:
            raise RuntimeError(f"Piper não gerou áudio para a fala: {fala.texto[:60]}")
        return Audio(b"".join(trecho.audio_int16_bytes for trecho in trechos), trechos[0].sample_rate)

    def _carregar_voz(self, nome: str) -> Any:
        if nome not in self._vozes:
            self._vozes[nome] = self._ler_modelo(nome)
        return self._vozes[nome]

    def _ler_modelo(self, nome: str) -> Any:
        from piper import PiperVoice

        modelo = self._diretorio / f"{nome}.onnx"
        if not modelo.exists():
            raise FileNotFoundError(
                f"Voz {nome} não encontrada em {self._diretorio}. "
                f"Baixe com: python -m piper.download_voices {nome} --download-dir {self._diretorio}"
            )
        return PiperVoice.load(modelo)

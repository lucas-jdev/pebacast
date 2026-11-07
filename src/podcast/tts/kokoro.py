from collections.abc import Sequence

import numpy as np

from podcast.audio import Audio
from podcast.dominio import Fala
from podcast.tts.provedor import sintetizar_fala_a_fala

TAXA_AMOSTRAGEM = 24_000
PORTUGUES_BRASILEIRO = "p"


class KokoroTts:
    nome = "kokoro"

    def __init__(self, pausa_entre_falas_ms: int = 350) -> None:
        from kokoro import KPipeline

        self._pipeline = KPipeline(lang_code=PORTUGUES_BRASILEIRO, repo_id="hexgrad/Kokoro-82M")
        self._pausa_ms = pausa_entre_falas_ms

    def sintetizar(self, falas: Sequence[Fala]) -> Audio:
        return sintetizar_fala_a_fala(falas, self._sintetizar_fala, self._pausa_ms)

    def _sintetizar_fala(self, fala: Fala) -> Audio:
        segmentos = [
            resultado.audio.numpy()
            for resultado in self._pipeline(fala.texto, voice=fala.persona.voz.kokoro)
            if resultado.audio is not None
        ]
        if not segmentos:
            raise RuntimeError(f"Kokoro não gerou áudio para a fala: {fala.texto[:60]}")
        return Audio.de_float(np.concatenate(segmentos), TAXA_AMOSTRAGEM)

from collections.abc import Callable, Sequence
from typing import Protocol

from podcast.audio import Audio, concatenar
from podcast.dominio import Fala


class TtsProvider(Protocol):
    nome: str

    def sintetizar(self, falas: Sequence[Fala]) -> Audio: ...


def sintetizar_fala_a_fala(
    falas: Sequence[Fala],
    sintetizar_fala: Callable[[Fala], Audio],
    pausa_ms: int,
) -> Audio:
    return concatenar([sintetizar_fala(fala) for fala in falas], pausa_ms)

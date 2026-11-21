from collections.abc import Callable, Sequence
from typing import Protocol

from podcast.audio import Audio, concatenar
from podcast.dominio import Fala


class RequisicaoRecusada(Exception):
    """O provedor recusou o pedido em si: voz, modelo ou texto inválidos.

    Repetir não adianta e cair no fallback só esconderia um erro de configuração.
    """


class CotaDiariaEsgotada(Exception):
    """A cota diária de requisições do provedor acabou.

    Só renova no dia seguinte: repetir com espera de segundos gasta tempo sem chance de passar.
    """


class TtsProvider(Protocol):
    nome: str

    def sintetizar(self, falas: Sequence[Fala]) -> Audio: ...


def sintetizar_fala_a_fala(
    falas: Sequence[Fala],
    sintetizar_fala: Callable[[Fala], Audio],
    pausa_ms: int,
) -> Audio:
    return concatenar([sintetizar_fala(fala) for fala in falas], pausa_ms, aparar=True)

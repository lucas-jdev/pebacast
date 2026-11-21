"""A única camada de retentativa das chamadas ao Gemini (#36): cada tentativa fica no log."""

import logging
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def tentar(
    chamada: Callable[[], T],
    *,
    rotulo: str,
    tentativas: int,
    espera_inicial_s: float,
    dormir: Callable[[float], None],
    desistir: Callable[[Exception], Exception | None] = lambda _: None,
) -> T:
    """Chama até `tentativas` vezes, com espera exponencial entre elas.

    `desistir` decide o que não vale repetir: devolve a exceção a lançar na hora (a própria
    exceção, para subir como veio) ou None para seguir tentando.
    """
    for tentativa in range(1, tentativas + 1):
        try:
            return chamada()
        except Exception as erro:
            substituta = desistir(erro)
            if substituta is not None and substituta is not erro:
                raise substituta from erro
            if substituta is erro or tentativa == tentativas:
                log.warning("%s falhou (tentativa %d de %d): %s. Sem nova tentativa.", rotulo, tentativa, tentativas, erro)
                raise
            espera = espera_inicial_s * 2 ** (tentativa - 1)
            log.warning("%s falhou (tentativa %d de %d): %s. Nova tentativa em %.0f s.",
                        rotulo, tentativa, tentativas, erro, espera)
            dormir(espera)
    raise AssertionError("inalcançável")

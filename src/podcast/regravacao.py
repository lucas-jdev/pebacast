"""Regravação do áudio de um episódio já publicado, em dois passos (ADR 0008).

`regravar` narra de novo o mesmo roteiro e anexa uma candidata ao release do episódio,
sem tocar no feed. Depois de ouvir, `substituir` troca o áudio publicado pela candidata:
a URL, o GUID e a data de publicação continuam os mesmos.

    python -m podcast.regravacao regravar sw-002 --repo dono/repo
    python -m podcast.regravacao --site _site substituir sw-002 --repo dono/repo
"""

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from podcast.audio import exportar_mp3
from podcast.personas import carregar_personas
from podcast.publicacao import (
    GitHubReleases,
    carregar_vinheta,
    escrever_site,
    falas_do_episodio,
    medir_mp3,
    saga_do_episodio,
)
from podcast.roteiro import Projeto, regras_para
from podcast.tts.provedor import TtsProvider
from podcast.validacao import PUBLICACAO, validar_episodio


class RegravacaoInvalida(Exception):
    """O pedido não pode ser atendido: o motivo vai para quem disparou."""


class StorageDeRegravacao(Protocol):
    def anexar(self, episodio_id: str, arquivo: Path) -> str:
        """Sobe o arquivo no lugar do asset de mesmo nome e devolve a URL."""
        ...

    def baixar(self, episodio_id: str, nome: str, pasta: Path) -> Path: ...

    def remover(self, episodio_id: str, nome: str) -> None: ...


def nome_publicado(episodio_id: str) -> str:
    return f"pebacast-{episodio_id}.mp3"


def nome_candidata(episodio_id: str) -> str:
    return f"pebacast-{episodio_id}-candidata.mp3"


def regravar(
    projeto: Projeto,
    episodio_id: str,
    storage: StorageDeRegravacao,
    criar_provedor: Callable[[str], TtsProvider],
    trabalho: Path,
) -> str:
    """Narra o episódio de novo e anexa a candidata. Devolve a URL para ouvir."""
    _exigir_publicado(projeto, episodio_id)
    config = projeto.config()
    pasta = projeto.episodios / episodio_id
    saga = saga_do_episodio(projeto.sagas(), episodio_id)
    problemas = validar_episodio(pasta, regras_para(projeto, saga, episodio_id))
    if problemas:
        raise RegravacaoInvalida("o roteiro não passa mais na validação: " + "; ".join(problemas))

    # Sem vinheta e sem fallback a regravação sairia pior que o áudio no ar: melhor falhar.
    # Assim a candidata tem vinheta sempre que a configuração pede, e o crédito no feed bate.
    vinheta, aviso = carregar_vinheta(projeto, config["audio"])
    if aviso:
        raise RegravacaoInvalida(aviso)

    personas = carregar_personas(projeto.raiz / "curriculum" / "personas")
    provedor = criar_provedor(config["tts"]["principal"])
    audio = provedor.sintetizar(falas_do_episodio(pasta, personas, config["tts"]))

    mp3 = trabalho / nome_candidata(episodio_id)
    exportar_mp3(audio, mp3, config["audio"]["bitrate_kbps"], vinheta=vinheta)
    return storage.anexar(episodio_id, mp3)


def substituir(
    projeto: Projeto,
    episodio_id: str,
    storage: StorageDeRegravacao,
    trabalho: Path,
    agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Troca o áudio publicado pela candidata e atualiza o `publicacao.json`."""
    arquivo = _exigir_publicado(projeto, episodio_id)
    publicacao = json.loads(arquivo.read_text(encoding="utf-8"))
    config = projeto.config()

    candidata = storage.baixar(episodio_id, nome_candidata(episodio_id), trabalho)
    definitivo = candidata.rename(candidata.with_name(nome_publicado(episodio_id)))
    # A candidata só sai depois de o definitivo subir: se o upload falhar, dá para tentar de novo.
    storage.anexar(episodio_id, definitivo)
    storage.remover(episodio_id, candidata.name)

    publicacao.update(
        medir_mp3(definitivo),
        tts={"provedor": config["tts"]["principal"], "fallback": False},
        vinheta=bool(config["audio"].get("vinheta")),
        regravado_em=agora().isoformat(timespec="seconds"),
    )
    arquivo.write_text(json.dumps(publicacao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return publicacao


def _exigir_publicado(projeto: Projeto, episodio_id: str) -> Path:
    if saga_do_episodio(projeto.sagas(), episodio_id) is None:
        raise RegravacaoInvalida(f"{episodio_id} não é um episódio do currículo")
    arquivo = projeto.episodios / episodio_id / PUBLICACAO
    if not arquivo.exists():
        raise RegravacaoInvalida(f"{episodio_id} ainda não foi publicado: quem narra a primeira vez é a publicação")
    return arquivo


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="regravacao", description="Regrava o áudio de um episódio já publicado.")
    parser.add_argument("--raiz", type=Path, default=Path.cwd())
    parser.add_argument("--site", type=Path, default=Path("_site"), help="Onde gravar o feed para o Pages.")
    parser.add_argument("--trabalho", type=Path, default=Path("_trabalho"), help="Pasta temporária dos MP3.")
    comandos = parser.add_subparsers(dest="comando", required=True)
    for nome, ajuda in (
        ("regravar", "Narra de novo e anexa uma candidata ao release, sem mexer no feed."),
        ("substituir", "Troca o áudio publicado pela candidata e regenera o feed."),
    ):
        comando = comandos.add_parser(nome, help=ajuda)
        comando.add_argument("episodio", help="Id do episódio, como sw-002.")
        comando.add_argument("--repo", required=True, help="dono/repositorio do GitHub Releases.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _criar_parser().parse_args(argv)
    projeto, storage = Projeto(args.raiz), GitHubReleases(args.repo)

    try:
        if args.comando == "regravar":
            from podcast.tts.fabrica import criar_provedor

            url = regravar(projeto, args.episodio, storage, criar_provedor, args.trabalho)
            print(f"Candidata para ouvir: {url}")
        else:
            publicacao = substituir(projeto, args.episodio, storage, args.trabalho)
            escrever_site(projeto, args.site)
            print(f"Áudio substituído: {publicacao['url_audio']} ({publicacao['duracao_segundos']} s)")
    except RegravacaoInvalida as erro:
        print(f"Não deu para {args.comando} {args.episodio}: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Regravação do áudio de um episódio já publicado, em dois passos (ADR 0008).

`regravar` narra de novo o mesmo roteiro e anexa uma candidata ao release do episódio,
sem tocar no feed, com as medidas do QA do áudio e o laudo de pronúncia ao lado. Depois de ouvir,
`substituir` troca o áudio publicado pela candidata: a URL, o GUID e a data de publicação continuam
os mesmos, e o áudio que sai do ar fica no release como `-anterior.mp3`.

    python -m podcast.regravacao regravar sw-002 --repo dono/repo
    python -m podcast.regravacao --site _site substituir sw-002 --repo dono/repo
"""

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from podcast.audio import exportar_mp3
from podcast.personas import carregar_personas
from podcast.publicacao import (
    GitHubReleases,
    carregar_falas,
    carregar_vinheta,
    escrever_site,
    falas_do_episodio,
    medir_mp3,
    saga_do_episodio,
)
from podcast.qualidade_audio import (
    IncidentesDeAudio,
    Laudo,
    Limites,
    Medicao,
    RegistroDeIncidentes,
    avaliar,
    medir,
)
from podcast.qualidade_pronuncia import LaudoDePronuncia, QaDePronuncia
from podcast.qualidade_voz import REFERENCIA, IncidentesDeVoz, LaudoDeVoz, QaDeVoz, RegistroDeVoz
from podcast.roteiro import Projeto, regras_para
from podcast.tts.provedor import CotaDiariaEsgotada, TtsProvider
from podcast.validacao import PUBLICACAO, ROTEIRO, validar_episodio


log = logging.getLogger(__name__)


class RegravacaoInvalida(Exception):
    """O pedido não pode ser atendido: o motivo vai para quem disparou."""


@dataclass(frozen=True)
class Candidata:
    url: str
    laudo: Laudo
    pronuncia: LaudoDePronuncia | None = None
    pronuncia_nao_rodou: str | None = None
    voz: LaudoDeVoz | None = None
    voz_nao_rodou: str | None = None

    def markdown(self, episodio_id: str) -> str:
        partes = [self.laudo.markdown(f"Qualidade da candidata do {episodio_id}")]
        if self.pronuncia is not None:
            partes.append(self.pronuncia.markdown(f"Pronúncia da candidata do {episodio_id}"))
        if self.pronuncia_nao_rodou:
            partes.append(f"### Pronúncia da candidata do {episodio_id}\n\n{self.pronuncia_nao_rodou}\n")
        if self.voz is not None:
            partes.append(self.voz.markdown(f"Voz da candidata do {episodio_id}"))
        if self.voz_nao_rodou:
            partes.append(f"### Voz da candidata do {episodio_id}\n\n{self.voz_nao_rodou}\n")
        return "\n".join(partes)


@dataclass(frozen=True)
class Substituicao:
    publicacao: dict[str, Any]
    laudo: Laudo | None
    voz: LaudoDeVoz | None = None


class StorageDeRegravacao(Protocol):
    def anexar(self, episodio_id: str, arquivo: Path) -> str:
        """Sobe o arquivo no lugar do asset de mesmo nome e devolve a URL."""
        ...

    def baixar(self, episodio_id: str, nome: str, pasta: Path) -> Path: ...

    def remover(self, episodio_id: str, nome: str) -> None: ...


def nome_publicado(episodio_id: str) -> str:
    return f"pebacast-{episodio_id}.mp3"


def nome_anterior(episodio_id: str) -> str:
    """O áudio que saiu do ar na última substituição: o caminho de volta, e o caso de calibração dos QAs."""
    return f"pebacast-{episodio_id}-anterior.mp3"


def nome_candidata(episodio_id: str) -> str:
    return f"pebacast-{episodio_id}-candidata.mp3"


def nome_medicao_candidata(episodio_id: str) -> str:
    """As medidas viajam com a candidata: só a montagem sabe onde ficam as trocas de bloco."""
    return f"pebacast-{episodio_id}-candidata.qualidade.json"


def nome_voz_candidata(episodio_id: str) -> str:
    """O laudo de voz da candidata: o substituir lê este, sem medir de novo (e sem o extra qa-voz)."""
    return f"pebacast-{episodio_id}-candidata.voz.json"


# Na issue de voz aberta: a candidata não saiu porque a cota diária acabou (ADR 0011).
COMENTARIO_DE_COTA = ("A candidata não saiu: a cota diária do Gemini esgotou. Rode o workflow Regravar áudio à mão "
                      "depois das 08:15 UTC, quando a cota já renovou.")


def regravar(
    projeto: Projeto,
    episodio_id: str,
    storage: StorageDeRegravacao,
    criar_provedor: Callable[[str], TtsProvider],
    trabalho: Path,
    qa_pronuncia: QaDePronuncia | None = None,
    qa_voz: QaDeVoz | None = None,
    incidentes_voz: RegistroDeVoz | None = None,
) -> Candidata:
    """Narra o episódio de novo e anexa a candidata, com as medidas do QA. Devolve a URL para ouvir."""
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
    falas_tts = falas_do_episodio(pasta, personas, config["tts"])
    try:
        audio = provedor.sintetizar(falas_tts)
    except CotaDiariaEsgotada as erro:
        # Sem fallback, como no ADR 0008; a issue de voz, se aberta, fica sabendo por que não veio a candidata.
        if incidentes_voz is not None:
            _sem_segurar("comentar a cota esgotada na issue de voz",
                         lambda: incidentes_voz.comentar(episodio_id, COMENTARIO_DE_COTA))
        raise RegravacaoInvalida(f"a cota diária do Gemini esgotou ({erro}); rode de novo depois das 08:15 UTC") from erro

    mp3 = trabalho / nome_candidata(episodio_id)
    trechos = exportar_mp3(audio, mp3, config["audio"]["bitrate_kbps"], vinheta=vinheta)
    url = storage.anexar(episodio_id, mp3)

    limites = Limites.de_config(config["audio"])
    medicao = medir(mp3, trechos, limites)
    arquivo_medicao = trabalho / nome_medicao_candidata(episodio_id)
    arquivo_medicao.write_text(medicao.para_json(), encoding="utf-8")
    storage.anexar(episodio_id, arquivo_medicao)
    laudo = avaliar(medicao, limites)
    # A candidata já está no release: uma falha de um QA vira motivo no resumo, não erro do passo.
    pronuncia = pronuncia_nao_rodou = voz = voz_nao_rodou = None
    if qa_pronuncia is not None:
        try:
            falas = carregar_falas(json.loads((pasta / ROTEIRO).read_text(encoding="utf-8")), personas)
            pronuncia = qa_pronuncia.rodar(episodio_id, mp3, trechos, falas)
        except Exception as erro:
            log.exception("O QA de pronúncia da candidata de %s não rodou.", episodio_id)
            pronuncia_nao_rodou = f"QA de pronúncia não rodou. {type(erro).__name__}: {erro}"
    if qa_voz is not None:
        try:
            voz = qa_voz.medir(mp3, trechos, falas_tts)
            arquivo_voz = trabalho / nome_voz_candidata(episodio_id)
            arquivo_voz.write_text(voz.para_json(), encoding="utf-8")
            storage.anexar(episodio_id, arquivo_voz)
        except Exception as erro:
            log.exception("O QA de voz da candidata de %s não rodou.", episodio_id)
            voz, voz_nao_rodou = None, f"QA de voz não rodou. {type(erro).__name__}: {erro}"
        if voz is not None and incidentes_voz is not None:
            laudo_voz = voz
            _sem_segurar("comentar a candidata na issue de voz",
                         lambda: incidentes_voz.comentar_candidata(episodio_id, laudo_voz))
    return Candidata(url, laudo, pronuncia, pronuncia_nao_rodou, voz, voz_nao_rodou)


def _sem_segurar(acao: str, executar: Callable[[], object]) -> None:
    """Conversa com a issue depois que a candidata já existe: uma falha no GitHub não derruba o passo."""
    try:
        executar()
    except Exception:
        log.exception("Não deu para %s.", acao)


def substituir(
    projeto: Projeto,
    episodio_id: str,
    storage: StorageDeRegravacao,
    trabalho: Path,
    agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    incidentes: RegistroDeIncidentes | None = None,
    incidentes_voz: RegistroDeVoz | None = None,
) -> Substituicao:
    """Troca o áudio publicado pela candidata, atualiza o `publicacao.json` e o incidente de QA do episódio."""
    arquivo = _exigir_publicado(projeto, episodio_id)
    publicacao = json.loads(arquivo.read_text(encoding="utf-8"))
    config = projeto.config()

    candidata = storage.baixar(episodio_id, nome_candidata(episodio_id), trabalho)
    medicao = _baixar_medicao(storage, episodio_id, trabalho)
    voz = _baixar_voz(storage, episodio_id, trabalho)
    # Antes de sobrescrever: sem isso, o --clobber apagava o áudio que sai do ar para sempre.
    no_ar = storage.baixar(episodio_id, nome_publicado(episodio_id), trabalho / "no-ar")
    storage.anexar(episodio_id, no_ar.rename(no_ar.with_name(nome_anterior(episodio_id))))
    definitivo = candidata.rename(candidata.with_name(nome_publicado(episodio_id)))
    # A candidata só sai depois de o definitivo subir: se o upload falhar, dá para tentar de novo.
    storage.anexar(episodio_id, definitivo)
    storage.remover(episodio_id, candidata.name)
    if medicao is not None:
        storage.remover(episodio_id, nome_medicao_candidata(episodio_id))
    if voz is not None:
        storage.remover(episodio_id, nome_voz_candidata(episodio_id))

    publicacao.update(
        medir_mp3(definitivo),
        tts={"provedor": config["tts"]["principal"], "fallback": False},
        vinheta=bool(config["audio"].get("vinheta")),
        regravado_em=agora().isoformat(timespec="seconds"),
    )
    arquivo.write_text(json.dumps(publicacao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    limites = Limites.de_config(config["audio"])
    laudo = avaliar(medicao, limites) if medicao is not None else None
    if laudo is not None and incidentes is not None:
        # O áudio já trocou: uma falha no GitHub não pode impedir o registro no repositório.
        try:
            incidentes.registrar(episodio_id, laudo)
        except Exception:
            log.exception("Não deu para atualizar a issue de QA de %s.", episodio_id)
    if voz is not None and incidentes_voz is not None:
        # A voz no ar agora é a da candidata: se passou, fecha a issue de voz; se não, comenta nela.
        _sem_segurar("atualizar a issue de voz", lambda: incidentes_voz.registrar(episodio_id, voz))
    return Substituicao(publicacao, laudo, voz)


def _baixar_medicao(storage: StorageDeRegravacao, episodio_id: str, trabalho: Path) -> Medicao | None:
    try:
        arquivo = storage.baixar(episodio_id, nome_medicao_candidata(episodio_id), trabalho)
        return Medicao.de_json(arquivo.read_text(encoding="utf-8"))
    except Exception:
        # Candidata gerada antes do QA existir: substitui do mesmo jeito, só sem o laudo.
        log.warning("A candidata de %s não tem as medidas do QA.", episodio_id, exc_info=True)
        return None


def _baixar_voz(storage: StorageDeRegravacao, episodio_id: str, trabalho: Path) -> LaudoDeVoz | None:
    try:
        arquivo = storage.baixar(episodio_id, nome_voz_candidata(episodio_id), trabalho)
        return LaudoDeVoz.de_json(arquivo.read_text(encoding="utf-8"))
    except Exception:
        # Candidata gerada antes do QA de voz, ou o QA de voz não rodou nela.
        log.warning("A candidata de %s não tem o laudo de voz.", episodio_id, exc_info=True)
        return None


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
    parser.add_argument("--qualidade", type=Path, default=Path("qualidade.md"),
                        help="Medidas do QA do áudio, para o resumo da execução.")
    parser.add_argument("--execucao", help="URL da execução, citada nas issues de incidente.")
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
            from podcast.tts.fabrica import fabrica_da_config

            config = projeto.config()
            criar_provedor = fabrica_da_config(config["tts"])
            # Sem incidentes: o laudo da candidata é para decidir se vale substituir, não um aviso do episódio no ar.
            qa_pronuncia = (QaDePronuncia.de_config(config["qualidade_pronuncia"], config["tts"])
                            if config.get("qualidade_pronuncia") else None)
            # O QA de voz também vai sem incidentes: só comenta na issue de voz que já estiver aberta.
            qa_voz = (QaDeVoz.de_config(config["qa_voz"], config["tts"],
                                        carregar_personas(projeto.raiz / "curriculum" / "personas"),
                                        projeto.raiz / REFERENCIA)
                      if config.get("qa_voz") else None)
            candidata = regravar(projeto, args.episodio, storage, criar_provedor, args.trabalho, qa_pronuncia,
                                 qa_voz, IncidentesDeVoz(args.repo, args.execucao))
            print(f"Candidata para ouvir: {candidata.url}")
            args.qualidade.write_text(candidata.markdown(args.episodio), encoding="utf-8")
        else:
            incidentes = IncidentesDeAudio(args.repo, args.execucao)
            substituicao = substituir(projeto, args.episodio, storage, args.trabalho, incidentes=incidentes,
                                      incidentes_voz=IncidentesDeVoz(args.repo, args.execucao))
            escrever_site(projeto, args.site)
            publicacao = substituicao.publicacao
            print(f"Áudio substituído: {publicacao['url_audio']} ({publicacao['duracao_segundos']} s)")
            partes = [laudo.markdown(titulo) for laudo, titulo in (
                (substituicao.laudo, f"Qualidade do áudio do {args.episodio}"),
                (substituicao.voz, f"Voz do {args.episodio}")) if laudo is not None]
            if partes:
                args.qualidade.write_text("\n".join(partes), encoding="utf-8")
    except RegravacaoInvalida as erro:
        print(f"Não deu para {args.comando} {args.episodio}: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Ponte entre o repositório e a rotina do roteirista.

A rotina agendada (Claude Code na nuvem) chama este módulo para saber o que escrever e para
conferir o que escreveu. Ver docs/adr/0006-roteiro-por-rotina-claude.md.

    python -m podcast.roteiro contexto [--data AAAA-MM-DD]
    python -m podcast.roteiro hash <episodio>
    python -m podcast.roteiro validar <episodio>
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from podcast.curriculo import Episodio, Saga, carregar_sagas
from podcast.validacao import (
    NOTICIA,
    PUBLICACAO,
    ROTEIRO,
    Regras,
    hash_do_roteiro,
    roteiro_aprovado,
    validar_episodio,
)

FUSO_BRASILIA = timezone(timedelta(hours=-3))
DIAS_DA_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")

PENDENTE = "pendente"
AGUARDANDO_PUBLICACAO = "aguardando_publicacao"
PUBLICADO = "publicado"

SAIDA_SEM_EPISODIO = 3


class SemEpisodio(Exception):
    """Nenhum episódio pode ser roteirizado hoje. Não é erro da rotina: ela só deve parar."""


@dataclass(frozen=True)
class Projeto:
    raiz: Path

    @property
    def episodios(self) -> Path:
        return self.raiz / "episodios"

    def config(self) -> dict[str, Any]:
        return _ler_yaml(self.raiz / "config" / "pipeline.yaml")

    def sagas(self) -> dict[str, Saga]:
        return carregar_sagas(self.raiz / "curriculum" / "sagas")

    def personas(self) -> dict[str, dict[str, Any]]:
        arquivos = sorted((self.raiz / "curriculum" / "personas").glob("*.yaml"))
        personas = (_ler_yaml(arquivo) for arquivo in arquivos)
        return {persona["id"]: persona for persona in personas}

    def feedbacks_recentes(self, saga: str, quantidade: int) -> list[dict[str, Any]]:
        arquivos = (self.raiz / "feedback" / saga).glob("*.yaml")
        feedbacks = [_ler_yaml(arquivo) for arquivo in arquivos]
        feedbacks.sort(key=lambda f: str(f.get("ouvido_em", "")), reverse=True)
        return feedbacks[:quantidade]


def data_de_publicacao(agora: datetime | None = None) -> date:
    """A rotina roda à noite e escreve o episódio do dia seguinte, no horário de Brasília."""
    agora = agora or datetime.now(FUSO_BRASILIA)
    return agora.astimezone(FUSO_BRASILIA).date() + timedelta(days=1)


def saga_do_dia(config: Mapping[str, Any], data: date) -> str:
    agenda = config["agenda"]
    if agenda["modo"] == "saga_unica":
        return agenda["saga_unica"]
    if agenda["modo"] == "rotacao_semanal":
        return agenda["rotacao_semanal"][DIAS_DA_SEMANA[data.weekday()]]
    raise ValueError(f"O modo de agenda {agenda['modo']} não tem saga do dia.")


def ultima_publicacao_por_saga(projeto: Projeto, sagas: Mapping[str, Saga]) -> dict[str, str]:
    saga_do_episodio = {episodio.id: saga.id for saga in sagas.values() for episodio in saga.episodios}
    ultimas: dict[str, str] = {}
    for arquivo in projeto.episodios.glob(f"*/{PUBLICACAO}"):
        saga = saga_do_episodio.get(arquivo.parent.name)
        if saga is None:
            continue
        publicado_em = str(json.loads(arquivo.read_text(encoding="utf-8")).get("publicado_em", ""))
        ultimas[saga] = max(ultimas.get(saga, ""), publicado_em)
    return ultimas


def ordem_da_fila(fila: Sequence[str], ultimas_publicacoes: Mapping[str, str]) -> list[str]:
    """Saga nunca publicada vem primeiro; depois, a publicada há mais tempo. Empates seguem a fila."""
    return sorted(fila, key=lambda saga: ultimas_publicacoes.get(saga, ""))


def apresentador(personas: Mapping[str, Mapping[str, Any]], saga: str) -> str:
    candidatos = [
        persona["id"]
        for persona in personas.values()
        if persona.get("papel") == "apresentador" and {"todas", saga} & set(persona.get("sagas", []))
    ]
    if len(candidatos) != 1:
        raise ValueError(f"Esperado um apresentador para a saga {saga}, encontrados: {candidatos}.")
    return candidatos[0]


def urls_ja_usadas(pasta_episodios: Path, exceto: str) -> frozenset[str]:
    """Notícias de episódios publicados. Só um episódio fica em produção por vez, então isso basta."""
    urls = set()
    for arquivo in pasta_episodios.glob(f"*/{NOTICIA}"):
        if arquivo.parent.name == exceto or not (arquivo.parent / PUBLICACAO).exists():
            continue
        noticia = json.loads(arquivo.read_text(encoding="utf-8"))
        if noticia.get("tipo") == "noticia" and noticia.get("url"):
            urls.add(noticia["url"])
    return frozenset(urls)


def regras_para(projeto: Projeto, saga: Saga, episodio_id: str) -> Regras:
    config = projeto.config()
    personas = projeto.personas()
    voz_principal = apresentador(personas, saga.id)
    return Regras(
        episodio_id=episodio_id,
        nome_podcast=config["feed"]["titulo"],
        apresentador=voz_principal,
        expert=saga.expert,
        nome_expert=personas[saga.expert]["nome"],
        personas_permitidas=frozenset({voz_principal, saga.expert}),
        palavras_min=config["episodio"]["palavras_alvo"]["min"],
        palavras_max=config["episodio"]["palavras_alvo"]["max"],
        max_ciclos=config["revisao"]["max_ciclos"],
        vereditos_reprovam=frozenset(config["revisao"]["vereditos_reprovam"]),
        nota_minima_relevancia=config["noticias"]["nota_minima_relevancia"],
        urls_ja_usadas=urls_ja_usadas(projeto.episodios, exceto=episodio_id),
    )


def estado_do_episodio(projeto: Projeto, saga: Saga, episodio_id: str) -> str:
    pasta = projeto.episodios / episodio_id
    if (pasta / PUBLICACAO).exists():
        return PUBLICADO
    if roteiro_aprovado(pasta, regras_para(projeto, saga, episodio_id)):
        return AGUARDANDO_PUBLICACAO
    return PENDENTE


def selecionar(saga: Saga, estados: Mapping[str, str], exigir_referencias_verificadas: bool) -> Episodio:
    """Escolhe o próximo episódio da saga, na ordem do currículo.

    Só um episódio fica em produção por vez: se algum já tem roteiro aprovado e ainda não foi
    publicado, nada novo é escrito. Isso evita acumular roteiros quando a publicação quebra.
    """
    _garantir_nada_aguardando(estados)

    motivos = []
    for episodio in saga.episodios:
        if estados.get(episodio.id) == PUBLICADO:
            continue
        faltando = [p for p in episodio.pre_requisitos if estados.get(p) != PUBLICADO]
        if faltando:
            motivos.append(f"{episodio.id}: pré-requisitos não publicados ({', '.join(faltando)})")
        elif exigir_referencias_verificadas and not episodio.referencias_verificadas:
            motivos.append(f"{episodio.id}: referências não verificadas")
        else:
            return episodio

    detalhe = "; ".join(motivos) if motivos else "todos os episódios já foram publicados"
    raise SemEpisodio(f"Nenhum episódio elegível na saga {saga.id}: {detalhe}.")


def selecionar_na_fila(
    sagas: Sequence[Saga], estados: Mapping[str, str], exigir_referencias_verificadas: bool
) -> tuple[Saga, Episodio]:
    """Devolve o primeiro episódio elegível percorrendo as sagas na ordem recebida."""
    _garantir_nada_aguardando(estados)

    motivos = []
    for saga in sagas:
        try:
            return saga, selecionar(saga, estados, exigir_referencias_verificadas)
        except SemEpisodio as motivo:
            motivos.append(str(motivo))
    raise SemEpisodio(" ".join(motivos))


def sagas_candidatas(projeto: Projeto, config: Mapping[str, Any], data: date) -> list[Saga]:
    sagas = projeto.sagas()
    agenda = config["agenda"]
    if agenda["modo"] == "fila":
        ordem = ordem_da_fila(agenda["fila"], ultima_publicacao_por_saga(projeto, sagas))
        return [sagas[saga] for saga in ordem]
    return [sagas[saga_do_dia(config, data)]]


def montar_contexto(projeto: Projeto, data: date) -> dict[str, Any]:
    config = projeto.config()
    candidatas = sagas_candidatas(projeto, config, data)
    estados = {
        episodio.id: estado_do_episodio(projeto, saga, episodio.id)
        for saga in candidatas
        for episodio in saga.episodios
    }
    saga, episodio = selecionar_na_fila(candidatas, estados, config["episodio"]["exigir_referencias_verificadas"])

    personas = projeto.personas()
    regras = regras_para(projeto, saga, episodio.id)
    return {
        "data_publicacao": data.isoformat(),
        "pasta": f"episodios/{episodio.id}",
        "saga": {chave: saga.dados[chave] for chave in ("id", "nome", "pergunta_central")},
        "episodio": episodio.dados,
        "referencias": saga.referencias_do(episodio),
        "personas": {
            "apresentador": personas[regras.apresentador],
            "expert": personas[saga.expert],
        },
        "regras": {
            "episodio": config["episodio"],
            "noticias": config["noticias"],
            "revisao": {**config["revisao"], "max_revisoes": regras.max_revisoes},
        },
        "noticias_ja_usadas": sorted(regras.urls_ja_usadas),
        "feedbacks_recentes": projeto.feedbacks_recentes(saga.id, config["feedback"]["ultimos_por_saga"]),
    }


def _garantir_nada_aguardando(estados: Mapping[str, str]) -> None:
    aguardando = [id_ for id_, estado in estados.items() if estado == AGUARDANDO_PUBLICACAO]
    if aguardando:
        raise SemEpisodio(f"{', '.join(aguardando)} já tem roteiro aprovado e aguarda publicação.")


def _saga_do_episodio(projeto: Projeto, episodio_id: str) -> Saga:
    for saga in projeto.sagas().values():
        if any(episodio.id == episodio_id for episodio in saga.episodios):
            return saga
    raise SystemExit(f"Episódio {episodio_id} não existe no currículo.")


def _ler_yaml(arquivo: Path) -> dict[str, Any]:
    return yaml.safe_load(arquivo.read_text(encoding="utf-8"))


def _imprimir_json(dados: Any) -> None:
    print(json.dumps(dados, ensure_ascii=False, indent=2, default=str))


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roteiro", description="Ponte entre o repositório e a rotina do roteirista.")
    parser.add_argument("--raiz", type=Path, default=Path.cwd(), help="Raiz do repositório.")
    comandos = parser.add_subparsers(dest="comando", required=True)

    contexto = comandos.add_parser("contexto", help="Seleciona o episódio e imprime tudo o que o roteirista precisa.")
    contexto.add_argument("--data", type=date.fromisoformat, help="Data de publicação (padrão: amanhã, em Brasília).")

    hash_cmd = comandos.add_parser("hash", help="Imprime o hash do roteiro, que o revisor grava no relatório.")
    hash_cmd.add_argument("episodio")

    validar = comandos.add_parser("validar", help="Confere roteiro, notícia e revisões. Sai com 1 se houver problema.")
    validar.add_argument("episodio")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _criar_parser().parse_args(argv)
    projeto = Projeto(args.raiz)

    if args.comando == "contexto":
        try:
            _imprimir_json(montar_contexto(projeto, args.data or data_de_publicacao()))
        except SemEpisodio as motivo:
            print(f"Sem episódio para roteirizar: {motivo}", file=sys.stderr)
            return SAIDA_SEM_EPISODIO
        return 0

    pasta = projeto.episodios / args.episodio
    if args.comando == "hash":
        print(hash_do_roteiro(json.loads((pasta / ROTEIRO).read_text(encoding="utf-8"))))
        return 0

    problemas = validar_episodio(pasta, regras_para(projeto, _saga_do_episodio(projeto, args.episodio), args.episodio))
    for problema in problemas:
        print(f"- {problema}")
    print("Roteiro aprovado." if not problemas else f"{len(problemas)} problema(s). Roteiro reprovado.")
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())

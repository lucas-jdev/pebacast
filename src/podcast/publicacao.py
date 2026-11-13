"""Etapas mecânicas da pipeline: voz, montagem e publicação.

Roda no GitHub Actions depois do push da rotina do roteirista. Antes de gastar qualquer
chamada de TTS, valida o roteiro de novo: a rotina não é a fonte de verdade da aprovação.

    python -m podcast.publicacao --site _site publicar --repo dono/repo
    python -m podcast.publicacao --site _site feed
"""

import argparse
import json
import logging
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree as ET

from podcast.audio import Audio, Vinheta, duracao_mp3, exportar_mp3
from podcast.dominio import Fala, Persona
from podcast.personas import carregar_personas
from podcast.pronuncia import aplicar_pronuncias, carregar_pronuncias
from podcast.roteiro import Projeto, regras_para
from podcast.site import escrever_pagina
from podcast.tts.provedor import RequisicaoRecusada, TtsProvider
from podcast.validacao import NOTICIA, PASTA_REVISOES, PUBLICACAO, ROTEIRO, validar_episodio

log = logging.getLogger(__name__)

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
ARQUIVO_FEED = "feed.xml"


class AudioStorage(Protocol):
    def publicar(self, episodio_id: str, titulo: str, arquivo: Path) -> str:
        """Publica o arquivo e devolve a URL pública e estável do áudio."""
        ...


@dataclass(frozen=True)
class GitHubReleases:
    """Um release por episódio, com o MP3 como asset (ADR 0002)."""

    repositorio: str
    executar: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def publicar(self, episodio_id: str, titulo: str, arquivo: Path) -> str:
        tag = f"episodio-{episodio_id}"
        repo = ["--repo", self.repositorio]
        ja_existe = self.executar(["gh", "release", "view", tag, *repo], capture_output=True).returncode == 0
        if ja_existe:
            # Republicação do mesmo episódio: a URL e o GUID continuam os mesmos.
            self.executar(["gh", "release", "upload", tag, str(arquivo), "--clobber", *repo], check=True)
        else:
            self.executar(
                ["gh", "release", "create", tag, str(arquivo), "--title", titulo,
                 "--notes", f"Áudio do episódio {episodio_id}.", *repo],
                check=True,
            )
        return f"https://github.com/{self.repositorio}/releases/download/{tag}/{arquivo.name}"


@dataclass(frozen=True)
class Resultado:
    publicados: list[str]
    reprovados: dict[str, list[str]]
    avisos: list[str]


def episodios_pendentes(projeto: Projeto) -> list[str]:
    """Pastas com roteiro e sem publicação: aprovadas, a publicar, ou reprovadas, a reportar."""
    if not projeto.episodios.is_dir():
        return []
    return sorted(
        pasta.name
        for pasta in projeto.episodios.iterdir()
        if (pasta / ROTEIRO).exists() and not (pasta / PUBLICACAO).exists()
    )


def carregar_falas(roteiro: Mapping[str, Any], personas: Mapping[str, Persona]) -> list[Fala]:
    return [
        Fala(persona=personas[fala["persona"]], texto=fala["texto"], estilo=fala.get("estilo"))
        for fala in roteiro["falas"]
    ]


def sintetizar_com_fallback(
    falas: Sequence[Fala],
    criar_principal: Callable[[], TtsProvider],
    criar_fallback: Callable[[], TtsProvider],
) -> tuple[Audio, str, str | None]:
    """Devolve o áudio, o provedor usado e, se houve fallback, o erro do principal."""
    try:
        principal = criar_principal()
        return principal.sintetizar(falas), principal.nome, None
    except RequisicaoRecusada:
        raise
    except Exception as erro:
        log.exception("Provedor principal falhou; usando o fallback.")
        fallback = criar_fallback()
        return fallback.sintetizar(falas), fallback.nome, f"{type(erro).__name__}: {erro}"


def carregar_vinheta(projeto: Projeto, config_audio: Mapping[str, Any]) -> tuple[Vinheta | None, str | None]:
    """Devolve a vinheta configurada ou, se o arquivo decifrado não estiver lá, um aviso."""
    dados = config_audio.get("vinheta")
    if not dados:
        return None, None
    arquivo = projeto.raiz / dados["arquivo"]
    if not arquivo.exists():
        return None, f"vinheta configurada, mas {dados['arquivo']} não existe (o secret VINHETA_SENHA está definido?)"
    return Vinheta.de_config(arquivo, dados), None


def publicar_pendentes(
    projeto: Projeto,
    storage: AudioStorage,
    criar_provedor: Callable[[str], TtsProvider],
    trabalho: Path,
    agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Resultado:
    config = projeto.config()
    personas = carregar_personas(projeto.raiz / "curriculum" / "personas")
    sagas = projeto.sagas()
    publicados, reprovados, avisos = [], {}, []

    for episodio_id in episodios_pendentes(projeto):
        saga = next((s for s in sagas.values() if any(e.id == episodio_id for e in s.episodios)), None)
        if saga is None:
            reprovados[episodio_id] = ["a pasta não corresponde a nenhum episódio do currículo"]
            continue
        pasta = projeto.episodios / episodio_id
        problemas = validar_episodio(pasta, regras_para(projeto, saga, episodio_id))
        if problemas:
            reprovados[episodio_id] = problemas
            continue

        roteiro = _ler_json(pasta / ROTEIRO)
        falas = aplicar_pronuncias(carregar_falas(roteiro, personas), carregar_pronuncias(config["tts"]))
        try:
            audio, provedor, erro_principal = sintetizar_com_fallback(
                falas,
                lambda: criar_provedor(config["tts"]["principal"]),
                lambda: criar_provedor(config["tts"]["fallback"]),
            )
        except RequisicaoRecusada as erro:
            reprovados[episodio_id] = [f"o TTS principal recusou o pedido (configuração?): {erro}"]
            continue
        if erro_principal:
            avisos.append(f"{episodio_id}: sintetizado com o fallback {provedor}. Erro do principal: {erro_principal}")

        vinheta, aviso_vinheta = carregar_vinheta(projeto, config["audio"])
        if aviso_vinheta:
            avisos.append(f"{episodio_id}: publicado sem vinheta. {aviso_vinheta}")

        mp3 = trabalho / f"pebacast-{episodio_id}.mp3"
        exportar_mp3(audio, mp3, config["audio"]["bitrate_kbps"], vinheta=vinheta)
        episodio = saga.episodio(episodio_id)
        url = storage.publicar(episodio_id, episodio.titulo, mp3)

        publicacao = {
            "guid": f"pebacast-{episodio_id}",
            "url_audio": url,
            "tamanho_bytes": mp3.stat().st_size,
            "duracao_segundos": round(duracao_mp3(mp3)),
            "publicado_em": agora().isoformat(timespec="seconds"),
            "tts": {"provedor": provedor, "fallback": erro_principal is not None},
            "vinheta": vinheta is not None,
        }
        (pasta / PUBLICACAO).write_text(json.dumps(publicacao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        publicados.append(episodio_id)

    return Resultado(publicados, reprovados, avisos)


def gerar_feed(projeto: Projeto) -> str:
    config = projeto.config()
    meta = config["feed"]
    url_site = meta["url_site"].rstrip("/") + "/"
    url_feed = url_site + ARQUIVO_FEED
    url_capa = url_site + meta["capa"]

    ET.register_namespace("itunes", ITUNES)
    ET.register_namespace("atom", ATOM)
    rss = ET.Element("rss", {"version": "2.0"})
    canal = ET.SubElement(rss, "channel")
    _sub(canal, "title", meta["titulo"])
    _sub(canal, "link", url_site)
    _sub(canal, "description", meta["descricao"].strip())
    _sub(canal, "language", meta["idioma"])
    _sub(canal, "copyright", f"{meta['autor']}, {meta['licenca']}")
    ET.SubElement(canal, f"{{{ATOM}}}link", {"href": url_feed, "rel": "self", "type": "application/rss+xml"})
    imagem = ET.SubElement(canal, "image")
    _sub(imagem, "url", url_capa)
    _sub(imagem, "title", meta["titulo"])
    _sub(imagem, "link", url_site)
    _sub(canal, f"{{{ITUNES}}}author", meta["autor"])
    dono = ET.SubElement(canal, f"{{{ITUNES}}}owner")
    _sub(dono, f"{{{ITUNES}}}name", meta["autor"])
    _sub(dono, f"{{{ITUNES}}}email", meta["email_dono"])
    ET.SubElement(canal, f"{{{ITUNES}}}image", {"href": url_capa})
    _sub(canal, f"{{{ITUNES}}}explicit", "false")
    ET.SubElement(canal, f"{{{ITUNES}}}category", {"text": meta["categoria"]})

    itens = sorted(_episodios_publicados(projeto), key=lambda item: item["publicacao"]["publicado_em"], reverse=True)
    for item in itens:
        _adicionar_item(canal, item)

    ET.indent(rss)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"


def escrever_site(projeto: Projeto, site: Path) -> None:
    site.mkdir(parents=True, exist_ok=True)
    (site / ARQUIVO_FEED).write_text(gerar_feed(projeto), encoding="utf-8")
    escrever_pagina(projeto, site, ARQUIVO_FEED)


def show_notes(episodio: Mapping[str, Any], roteiro: Mapping[str, Any], noticia: Mapping[str, Any],
               revisoes: Sequence[Mapping[str, Any]], credito_vinheta: str | None = None) -> str:
    linhas = [
        "Conteúdo gerado por inteligência artificial e revisado contra as fontes citadas.",
        "",
        "Objetivos:",
        *[f"- {objetivo}" for objetivo in episodio.get("objetivos", [])],
        "",
    ]
    if noticia.get("tipo") == "noticia":
        linhas += [f"Notícia: {noticia['titulo']} ({noticia['fonte']}, {noticia['data']}) {noticia['url']}", ""]
    else:
        linhas += ["Caso usado no episódio: cenário hipotético.", ""]
    linhas += [f"Desafio: {roteiro['desafio']}", "", "Fontes:", *[f"- {fonte}" for fonte in roteiro["fontes"]], ""]

    ultima = revisoes[-1] if revisoes else {"afirmacoes": []}
    linhas.append(
        f"Revisão: {len(ultima['afirmacoes'])} afirmações verificadas, "
        f"aprovado na revisão {len(revisoes)}."
    )
    if credito_vinheta:
        linhas += ["", credito_vinheta]
    return "\n".join(linhas)


def _episodios_publicados(projeto: Projeto) -> list[dict[str, Any]]:
    credito = (projeto.config()["audio"].get("vinheta") or {}).get("credito")
    itens = []
    for saga in projeto.sagas().values():
        for episodio in saga.episodios:
            pasta = projeto.episodios / episodio.id
            if not (pasta / PUBLICACAO).exists():
                continue
            publicacao = _ler_json(pasta / PUBLICACAO)
            revisoes = sorted((pasta / PASTA_REVISOES).glob("*.json"), key=lambda a: int(a.stem))
            itens.append({
                "episodio": episodio.dados,
                "publicacao": publicacao,
                "notas": show_notes(
                    episodio.dados,
                    _ler_json(pasta / ROTEIRO),
                    _ler_json(pasta / NOTICIA),
                    [_ler_json(arquivo) for arquivo in revisoes],
                    credito if publicacao.get("vinheta") else None,
                ),
            })
    return itens


def _adicionar_item(canal: ET.Element, item: Mapping[str, Any]) -> None:
    episodio, publicacao = item["episodio"], item["publicacao"]
    no = ET.SubElement(canal, "item")
    _sub(no, "title", episodio["titulo"])
    _sub(no, "description", item["notas"])
    ET.SubElement(no, "guid", {"isPermaLink": "false"}).text = publicacao["guid"]
    _sub(no, "pubDate", format_datetime(datetime.fromisoformat(publicacao["publicado_em"])))
    ET.SubElement(no, "enclosure", {
        "url": publicacao["url_audio"],
        "length": str(publicacao["tamanho_bytes"]),
        "type": "audio/mpeg",
    })
    _sub(no, f"{{{ITUNES}}}duration", str(publicacao["duracao_segundos"]))
    _sub(no, f"{{{ITUNES}}}explicit", "false")


def _sub(pai: ET.Element, tag: str, texto: str) -> ET.Element:
    no = ET.SubElement(pai, tag)
    no.text = texto
    return no


def _ler_json(arquivo: Path) -> Any:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def relatorio(resultado: Resultado) -> dict[str, Any]:
    """Uma entrada por episódio: o workflow abre (ou comenta) uma issue por reprovado e fecha as dos publicados."""
    return {
        "publicados": resultado.publicados,
        "reprovados": {
            episodio_id: "\n".join([
                "O roteiro não passou na validação e o episódio não foi publicado.",
                "",
                *[f"- {p}" for p in problemas],
                "",
                f"A rotina tenta de novo na próxima execução. Veja `episodios/{episodio_id}/revisoes/`.",
            ])
            for episodio_id, problemas in resultado.reprovados.items()
        },
    }


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publicacao", description="Voz, montagem e publicação dos episódios.")
    parser.add_argument("--raiz", type=Path, default=Path.cwd())
    parser.add_argument("--site", type=Path, default=Path("_site"), help="Onde gravar o feed para o Pages.")
    comandos = parser.add_subparsers(dest="comando", required=True)

    publicar = comandos.add_parser("publicar", help="Valida, sintetiza e publica os episódios pendentes.")
    publicar.add_argument("--repo", required=True, help="dono/repositorio do GitHub Releases.")
    publicar.add_argument("--trabalho", type=Path, default=Path("_trabalho"), help="Pasta temporária dos MP3.")
    publicar.add_argument("--relatorio", type=Path, default=Path("relatorio.json"), help="Publicados e reprovados, para as issues.")
    publicar.add_argument("--avisos", type=Path, default=Path("avisos.md"), help="Relatório gravado se houver fallback.")

    comandos.add_parser("feed", help="Só regenera o feed.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _criar_parser().parse_args(argv)
    projeto = Projeto(args.raiz)

    if args.comando == "feed":
        escrever_site(projeto, args.site)
        return 0

    from podcast.tts.fabrica import criar_provedor

    resultado = publicar_pendentes(projeto, GitHubReleases(args.repo), criar_provedor, args.trabalho)
    escrever_site(projeto, args.site)

    print(f"Publicados: {', '.join(resultado.publicados) or 'nenhum'}")
    args.relatorio.write_text(json.dumps(relatorio(resultado), ensure_ascii=False, indent=2), encoding="utf-8")
    if resultado.avisos:
        args.avisos.write_text("\n".join(f"- {aviso}" for aviso in resultado.avisos) + "\n", encoding="utf-8")
    if resultado.reprovados:
        print(f"Reprovados: {', '.join(resultado.reprovados)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Experimento cego de pronúncia de um termo no Gemini.

Cada variante do dicionário de pronúncia (grafia, instrução ou as duas) narra as mesmas frases
numa única requisição, para o teste caber na cota diária do free tier ao lado do episódio do dia.
As amostras saem anônimas, em ordem sorteada, e o gabarito fica num arquivo à parte.

    python -m podcast.teste_pronuncia gerar
    python -m podcast.teste_pronuncia revelar A=4 B=1 C=3
"""

import argparse
import json
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import ascii_uppercase

import yaml

from podcast.audio import exportar_mp3
from podcast.dominio import Fala, Persona
from podcast.personas import carregar_personas
from podcast.pronuncia import Pronuncia, aplicar_pronuncias
from podcast.tts.fabrica import fabrica_da_config
from podcast.tts.provedor import TtsProvider

ARQUIVO_GABARITO = "gabarito.json"
PASTA_AMOSTRAS = "amostras"


@dataclass(frozen=True)
class Experimento:
    falas: list[Fala]
    variantes: dict[str, Pronuncia]


def carregar_experimento(arquivo: Path, personas: Mapping[str, Persona]) -> Experimento:
    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    persona = personas[dados["persona"]]
    falas = [Fala(persona, frase.strip()) for frase in dados["frases"]]
    variantes = {nome: Pronuncia(termo=dados["termo"], **opcoes) for nome, opcoes in dados["variantes"].items()}
    return Experimento(falas, variantes)


def gerar(experimento: Experimento, provedor: TtsProvider, saida: Path, bitrate_kbps: int,
          sorteio: random.Random | None = None) -> None:
    if (saida / ARQUIVO_GABARITO).exists():
        raise FileExistsError(f"Já existe um teste em {saida}. Apague a pasta para gerar outro.")

    nomes = list(experimento.variantes)
    (sorteio or random.SystemRandom()).shuffle(nomes)
    gabarito = dict(zip(ascii_uppercase, nomes))
    for amostra, nome in gabarito.items():
        audio = provedor.sintetizar(aplicar_pronuncias(experimento.falas, [experimento.variantes[nome]]))
        exportar_mp3(audio, saida / PASTA_AMOSTRAS / f"{amostra}.mp3", bitrate_kbps)

    conteudo = {"frases": len(experimento.falas), "amostras": gabarito}
    (saida / ARQUIVO_GABARITO).write_text(json.dumps(conteudo, indent=2, ensure_ascii=False), encoding="utf-8")


def revelar(saida: Path, acertos: Mapping[str, int]) -> str:
    gabarito = json.loads((saida / ARQUIVO_GABARITO).read_text(encoding="utf-8"))
    total, amostras = gabarito["frases"], gabarito["amostras"]

    faltando = sorted(set(amostras) - set(acertos))
    fora_da_escala = sorted(amostra for amostra, nota in acertos.items() if not 0 <= nota <= total)
    if faltando or fora_da_escala or set(acertos) - set(amostras):
        raise ValueError(
            f"Informe de 0 a {total} acertos para cada amostra ({', '.join(amostras)}). "
            f"Faltando: {faltando or '-'}; fora da escala: {fora_da_escala or '-'}."
        )

    ordem = sorted(amostras, key=lambda amostra: acertos[amostra], reverse=True)
    return "\n".join(f"{amostra} = {amostras[amostra]}: {acertos[amostra]} de {total}" for amostra in ordem)


def _ler_acertos(pares: Sequence[str]) -> dict[str, int]:
    acertos = {}
    for par in pares:
        amostra, _, nota = par.partition("=")
        if not nota.strip().isdigit():
            raise ValueError(f"Use AMOSTRA=ACERTOS, como A=3. Recebido: {par!r}")
        acertos[amostra.strip().upper()] = int(nota)
    return acertos


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teste_pronuncia", description="Experimento cego de pronúncia no Gemini.")
    parser.add_argument("--saida", type=Path, default=Path("experimentos/teste-pronuncia/saida"))
    comandos = parser.add_subparsers(dest="comando", required=True)

    gerar_cmd = comandos.add_parser("gerar", help="narra cada variante e grava as amostras anônimas")
    gerar_cmd.add_argument("--teste", type=Path, default=Path("experimentos/teste-pronuncia/pebacast.yaml"))
    gerar_cmd.add_argument("--personas", type=Path, default=Path("curriculum/personas"))
    gerar_cmd.add_argument("--config", type=Path, default=Path("config/pipeline.yaml"))

    revelar_cmd = comandos.add_parser("revelar", help="mostra qual variante é cada amostra")
    revelar_cmd.add_argument("acertos", nargs="+", help="acertos por amostra, como A=4 B=1 C=3")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _criar_parser().parse_args(argv)
    try:
        if args.comando == "gerar":
            config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
            provedor = fabrica_da_config(config["tts"])(config["tts"]["principal"])
            experimento = carregar_experimento(args.teste, carregar_personas(args.personas))
            gerar(experimento, provedor, args.saida, config["audio"]["bitrate_kbps"])
            print(f"Amostras em {args.saida / PASTA_AMOSTRAS}. Não abra {args.saida / ARQUIVO_GABARITO}.")
        else:
            print(revelar(args.saida, _ler_acertos(args.acertos)))
    except (FileExistsError, ValueError) as erro:
        print(erro, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

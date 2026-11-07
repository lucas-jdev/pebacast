from pathlib import Path

import yaml

from podcast.dominio import Persona, Voz


def carregar_personas(diretorio: Path) -> dict[str, Persona]:
    personas = (_ler_persona(arquivo) for arquivo in sorted(diretorio.glob("*.yaml")))
    return {persona.id: persona for persona in personas}


def _ler_persona(arquivo: Path) -> Persona:
    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    voz = dados["voz"]
    return Persona(
        id=dados["id"],
        nome=dados["nome"],
        voz=Voz(
            gemini=voz["gemini"],
            kokoro=voz["kokoro"],
            piper=voz["piper"],
            estilo=voz["instrucao_de_estilo"].strip(),
        ),
    )

from dataclasses import dataclass


@dataclass(frozen=True)
class Voz:
    gemini: str
    kokoro: str
    piper: str
    estilo: str


@dataclass(frozen=True)
class Persona:
    id: str
    nome: str
    voz: Voz


@dataclass(frozen=True)
class Fala:
    persona: Persona
    texto: str
    estilo: str | None = None

    @property
    def estilo_efetivo(self) -> str:
        return self.estilo or self.persona.voz.estilo

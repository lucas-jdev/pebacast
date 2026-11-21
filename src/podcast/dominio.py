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
    instrucoes_de_pronuncia: tuple[str, ...] = ()

    @property
    def estilo_efetivo(self) -> str:
        """A instrução que vai ao TTS. Cada fonte fica no seu campo e só se junta aqui, uma vez.

        O estilo da fala complementa a voz da persona, que é o que separa duas vozes parecidas;
        substituí-la apagava essa diferença justamente nas falas com emoção marcada.
        """
        partes = [self.persona.voz.estilo]
        if self.estilo:
            partes.append(f"Nesta fala: {self.estilo.strip().rstrip('.')}.")
        partes.extend(self.instrucoes_de_pronuncia)
        return " ".join(parte.strip() for parte in partes if parte and parte.strip())

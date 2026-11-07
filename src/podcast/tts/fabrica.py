from pathlib import Path

from podcast.tts.provedor import TtsProvider


def criar_provedor(nome: str, diretorio_vozes_piper: Path | None = None) -> TtsProvider:
    """Cria o provedor pelo nome usado em config/pipeline.yaml. Importa a biblioteca só quando precisa."""
    if nome.startswith("gemini-"):
        from podcast.tts.gemini import GeminiTts

        return GeminiTts(modelo=nome)
    if nome == "kokoro":
        from podcast.tts.kokoro import KokoroTts

        return KokoroTts()
    if nome == "piper":
        if diretorio_vozes_piper is None:
            raise ValueError("O Piper precisa do diretório das vozes.")
        from podcast.tts.piper import PiperTts

        return PiperTts(diretorio_vozes_piper)
    raise ValueError(f"Provedor de voz desconhecido: {nome}")

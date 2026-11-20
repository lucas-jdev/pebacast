from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from podcast.tts.provedor import TtsProvider


def criar_provedor(nome: str, diretorio_vozes_piper: Path | None = None,
                   timeout_gemini_s: float | None = None) -> TtsProvider:
    """Cria o provedor pelo nome usado em config/pipeline.yaml. Importa a biblioteca só quando precisa."""
    if nome.startswith("gemini-"):
        from podcast.tts.gemini import TIMEOUT_PADRAO_S, GeminiTts

        return GeminiTts(modelo=nome, timeout_s=timeout_gemini_s or TIMEOUT_PADRAO_S)
    if nome == "kokoro":
        from podcast.tts.kokoro import KokoroTts

        return KokoroTts()
    if nome == "piper":
        if diretorio_vozes_piper is None:
            raise ValueError("O Piper precisa do diretório das vozes.")
        from podcast.tts.piper import PiperTts

        return PiperTts(diretorio_vozes_piper)
    raise ValueError(f"Provedor de voz desconhecido: {nome}")


def fabrica_da_config(config_tts: Mapping[str, Any]) -> Callable[[str], TtsProvider]:
    """Cria provedores com as opções de `tts` do config/pipeline.yaml."""
    timeout_s = (config_tts.get("gemini") or {}).get("timeout_s")
    return lambda nome: criar_provedor(nome, timeout_gemini_s=timeout_s)

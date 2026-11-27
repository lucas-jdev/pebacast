import re
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

AMOSTRA_BYTES = 2
ALVO_LOUDNESS_LUFS = -16.0
ALVO_PICO_DBTP = -1.5
# O limitador roda com a taxa quadruplicada para enxergar o pico entre amostras (true peak, BS.1770).
SOBREAMOSTRAGEM = 4
PASSADAS_DE_CODIFICACAO = 5
TOLERANCIA_DE_LOUDNESS_LU = 0.2
FOLGA_DO_TETO_DB = 0.2
TETO_MINIMO_DBTP = -12.0
# A música vale como nivelada entre `abaixo_da_fala_lu` e esta faixa abaixo disso, medida no MP3.
FAIXA_DA_MUSICA_LU = 0.5
# Abaixo disso a borda de um bloco é silêncio. A folga preserva o ataque e a cauda das consoantes.
LIMIAR_BORDA_DBFS = -50.0
FOLGA_BORDA_MS = 30
SEM_LOUDNESS = -70.0  # o ebur128 devolve -70 LUFS para silêncio
VOZ = "voz"  # rótulo, no grafo do ffmpeg, da fala já com o ganho e o limitador


@dataclass(frozen=True)
class Audio:
    """PCM 16 bits mono little-endian.

    `trocas_s` marca onde `concatenar` emendou uma parte na outra: o meio de cada pausa inserida.
    """

    pcm: bytes
    taxa_amostragem: int
    trocas_s: tuple[float, ...] = ()

    @classmethod
    def silencio(cls, duracao_ms: int, taxa_amostragem: int) -> "Audio":
        amostras = taxa_amostragem * duracao_ms // 1000
        return cls(bytes(amostras * AMOSTRA_BYTES), taxa_amostragem)

    @classmethod
    def de_float(cls, amostras: np.ndarray, taxa_amostragem: int) -> "Audio":
        pcm16 = (np.clip(amostras, -1.0, 1.0) * np.iinfo(np.int16).max).astype("<i2")
        return cls(pcm16.tobytes(), taxa_amostragem)

    @property
    def duracao_segundos(self) -> float:
        return len(self.pcm) / AMOSTRA_BYTES / self.taxa_amostragem


def aparar_bordas(audio: Audio, limiar_dbfs: float = LIMIAR_BORDA_DBFS, folga_ms: int = FOLGA_BORDA_MS) -> Audio:
    """Corta o silêncio do começo e do fim. Uma parte toda em silêncio volta como está."""
    amostras = np.frombuffer(audio.pcm, dtype="<i2")
    limiar = np.iinfo(np.int16).max * 10 ** (limiar_dbfs / 20)
    audiveis = np.flatnonzero(np.abs(amostras.astype(np.int32)) > limiar)
    if audiveis.size == 0:
        return audio
    folga = audio.taxa_amostragem * folga_ms // 1000
    inicio = max(int(audiveis[0]) - folga, 0)
    fim = min(int(audiveis[-1]) + 1 + folga, amostras.size)
    return Audio(amostras[inicio:fim].tobytes(), audio.taxa_amostragem)


def concatenar(partes: Sequence[Audio], pausa_ms: int = 0, aparar: bool = False) -> Audio:
    """Emenda as partes com uma pausa fixa entre elas.

    Com `aparar`, o silêncio que o TTS deixa nas bordas de cada parte sai antes, para que a pausa
    entre as partes seja só a `pausa_ms`.
    """
    if not partes:
        raise ValueError("Nada para concatenar.")

    taxas = {parte.taxa_amostragem for parte in partes}
    if len(taxas) > 1:
        raise ValueError(f"Taxas de amostragem diferentes: {sorted(taxas)}.")

    taxa = taxas.pop()
    if aparar:
        partes = [aparar_bordas(parte) for parte in partes]
    pausa = Audio.silencio(pausa_ms, taxa)
    trocas, inicio = [], 0.0
    for indice, parte in enumerate(partes):
        trocas.extend(inicio + troca for troca in parte.trocas_s)
        inicio += parte.duracao_segundos
        if indice < len(partes) - 1:
            trocas.append(inicio + pausa.duracao_segundos / 2)
            inicio += pausa.duracao_segundos
    return Audio(pausa.pcm.join(parte.pcm for parte in partes), taxa, tuple(trocas))


@dataclass(frozen=True)
class Loudness:
    integrada_lufs: float
    pico_real_dbtp: float


def medir_loudness(entradas: Sequence[str], grafo: str) -> Loudness:
    """Loudness integrada e pico real (EBU R128) do rótulo [medir] de um grafo do ffmpeg."""
    comando = [
        "ffmpeg", "-hide_banner", "-nostats", "-nostdin", *entradas,
        "-filter_complex", f"{grafo};[medir]ebur128=peak=true:framelog=verbose[medido]",
        "-map", "[medido]", "-f", "null", "-",
    ]
    resultado = subprocess.run(comando, capture_output=True, check=True)
    resumo = resultado.stderr.decode("utf-8", "replace").rsplit("Summary:", 1)[-1]
    integrada = re.search(r"I:\s+(\S+) LUFS", resumo)
    pico = re.search(r"Peak:\s+(\S+) dBFS", resumo)
    if not (integrada and pico):
        raise RuntimeError(f"O ebur128 não devolveu o resumo: {resumo[-500:]}")
    return Loudness(float(integrada.group(1)), float(pico.group(1)))


@dataclass(frozen=True)
class Recorte:
    """Trecho de uma faixa musical, com fade de entrada e de saída."""

    inicio_s: float
    duracao_s: float
    fade_entrada_s: float = 0.5
    fade_saida_s: float = 3.0

    def __post_init__(self) -> None:
        if not (self.inicio_s >= 0 and self.duracao_s > 0
                and 0 <= self.fade_entrada_s + self.fade_saida_s <= self.duracao_s):
            raise ValueError("Recorte inválido: os fades precisam caber na duração.")

    def filtro(self, taxa: int, volume: float) -> str:
        filtros = [
            f"atrim=start={self.inicio_s}:duration={self.duracao_s}",
            "asetpts=PTS-STARTPTS",
            f"aformat=sample_rates={taxa}:channel_layouts=mono",
            f"volume={volume}",
        ]
        if self.fade_entrada_s:
            filtros.append(f"afade=t=in:d={self.fade_entrada_s}")
        if self.fade_saida_s:
            filtros.append(f"afade=t=out:st={self.duracao_s - self.fade_saida_s}:d={self.fade_saida_s}")
        return ",".join(filtros)


@dataclass(frozen=True)
class Trechos:
    """Onde fica cada parte no episódio montado, em segundos. É o que o QA mede."""

    fala: tuple[float, float]
    trocas_s: tuple[float, ...] = ()
    abertura: tuple[float, float] | None = None
    encerramento: tuple[float, float] | None = None


@dataclass(frozen=True)
class Vinheta:
    """Recortes de uma faixa musical na abertura e, opcionalmente, no encerramento.

    A primeira fala entra `sobreposicao_s` segundos antes do fim da abertura, por cima do fade-out.
    O encerramento começa logo depois da última fala. No MP3, cada recorte fica `abaixo_da_fala_lu`
    abaixo da loudness da fala do episódio, seja qual for o volume da faixa.
    """

    arquivo: Path
    abertura: Recorte
    encerramento: Recorte | None = None
    sobreposicao_s: float = 1.5
    abaixo_da_fala_lu: float = 2.0

    def __post_init__(self) -> None:
        if not 0 <= self.sobreposicao_s <= self.abertura.fade_saida_s:
            raise ValueError("A vinheta precisa de 0 <= sobreposicao_s <= abertura.fade_saida_s.")
        if self.abaixo_da_fala_lu < 0:
            raise ValueError("A vinheta precisa de abaixo_da_fala_lu >= 0: a música não passa da fala.")

    @classmethod
    def de_config(cls, arquivo: Path, config: dict) -> "Vinheta":
        encerramento = config.get("encerramento")
        # "credito" e "arquivo" são metadados da config, não parâmetros de montagem.
        return cls(
            arquivo=arquivo,
            abertura=Recorte(**config["abertura"]),
            encerramento=Recorte(**encerramento) if encerramento else None,
            sobreposicao_s=config.get("sobreposicao_s", 1.5),
            abaixo_da_fala_lu=config.get("abaixo_da_fala_lu", 2.0),
        )

    @property
    def entrada_da_fala_s(self) -> float:
        return self.abertura.duracao_s - self.sobreposicao_s

    def volume_do_recorte(self, recorte: Recorte, fala_lufs: float, taxa: int) -> float:
        """Ganho linear que põe o recorte `abaixo_da_fala_lu` abaixo da fala."""
        musica = medir_loudness(["-i", str(self.arquivo)], f"[0:a]{recorte.filtro(taxa, 1.0)}[medir]").integrada_lufs
        if musica <= SEM_LOUDNESS or fala_lufs <= SEM_LOUDNESS:
            return 1.0
        return 10 ** ((fala_lufs - self.abaixo_da_fala_lu - musica) / 20)

    def filtro(self, entrada_fala: str, entrada_musica: str, taxa: int,
               volume_abertura: float = 1.0, volume_encerramento: float = 1.0) -> str:
        """Grafo do ffmpeg que mistura a vinheta com a fala e entrega o rótulo [episodio]."""
        atraso_ms = round(self.entrada_da_fala_s * 1000)
        fala = f"[{entrada_fala}]adelay={atraso_ms}[fala]"
        abertura = self.abertura.filtro(taxa, volume_abertura)
        if self.encerramento is None:
            return ";".join([
                f"[{entrada_musica}]{abertura}[abertura]",
                fala,
                "[abertura][fala]amix=inputs=2:duration=longest:normalize=0[episodio]",
            ])
        return ";".join([
            f"[{entrada_musica}]asplit=2[musica1][musica2]",
            f"[musica1]{abertura}[abertura]",
            f"[musica2]{self.encerramento.filtro(taxa, volume_encerramento)}[fecho]",
            fala,
            "[abertura][fala]amix=inputs=2:duration=longest:normalize=0[corpo]",
            "[corpo][fecho]concat=n=2:v=0:a=1[episodio]",
        ])

    def trechos(self, fala: Audio) -> Trechos:
        entrada = self.entrada_da_fala_s
        fim_da_fala = entrada + fala.duracao_segundos
        fim_do_corpo = max(fim_da_fala, self.abertura.duracao_s)
        return Trechos(
            fala=(entrada, fim_da_fala),
            trocas_s=tuple(entrada + troca for troca in fala.trocas_s),
            abertura=(0.0, entrada),
            encerramento=(fim_do_corpo, fim_do_corpo + self.encerramento.duracao_s) if self.encerramento else None,
        )


def exportar_mp3(
    audio: Audio,
    destino: Path,
    bitrate_kbps: int,
    taxa_saida: int = 24_000,
    vinheta: Vinheta | None = None,
) -> Trechos:
    """Monta o episódio no alvo de loudness, com o pico real limitado, e devolve onde ficou cada parte.

    O ganho é um só para a fala inteira, medido antes. Um normalizador dinâmico (loudnorm)
    puxaria a música do encerramento, mais baixa que a fala, para o alvo. A música entra depois do
    ganho e do limitador da fala, com o volume conferido no MP3.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    # A fala vai para um WAV temporário porque o ffmpeg a lê várias vezes (medir, codificar, corrigir).
    with tempfile.TemporaryDirectory() as pasta:
        fala = Path(pasta) / "fala.wav"
        _gravar_wav(audio, fala)
        return _montar(audio, fala, destino, bitrate_kbps, taxa_saida, vinheta)


def medir_trecho(arquivo: Path, trecho: tuple[float, float] | None = None) -> Loudness:
    """Loudness de um trecho do arquivo, em segundos. É a medida do QA, e a montagem confere com ela."""
    corte = ["-ss", f"{trecho[0]:.3f}", "-to", f"{trecho[1]:.3f}"] if trecho else []
    return medir_loudness([*corte, "-i", str(arquivo)], "[0:a]anull[medir]")


def correcao_da_musica(mp3: Path, trechos: Trechos, vinheta: Vinheta) -> tuple[float, float]:
    """Quantos dB mudar na abertura e no encerramento para ficarem `abaixo_da_fala_lu` abaixo da fala no MP3.

    Zero quando o recorte já está na faixa aceita, entre o alvo e `FAIXA_DA_MUSICA_LU` abaixo dele.
    """
    fala = medir_trecho(mp3, trechos.fala).integrada_lufs
    alvo = -vinheta.abaixo_da_fala_lu
    correcoes = []
    for trecho in (trechos.abertura, trechos.encerramento):
        musica = medir_trecho(mp3, trecho).integrada_lufs if trecho else SEM_LOUDNESS
        diferenca = musica - fala
        na_faixa = alvo - FAIXA_DA_MUSICA_LU <= diferenca <= alvo
        sem_som = musica <= SEM_LOUDNESS or fala <= SEM_LOUDNESS
        correcoes.append(0.0 if na_faixa or sem_som else alvo - FAIXA_DA_MUSICA_LU / 2 - diferenca)
    return correcoes[0], correcoes[1]


def _montar(audio: Audio, wav_da_fala: Path, destino: Path, bitrate_kbps: int, taxa_saida: int,
            vinheta: Vinheta | None) -> Trechos:
    taxa = audio.taxa_amostragem
    entradas = ["-i", str(wav_da_fala)]
    fala = medir_loudness(entradas, "[0:a]anull[medir]").integrada_lufs
    volumes = [1.0, 1.0]
    if vinheta is None:
        trechos = Trechos(fala=(0.0, audio.duracao_segundos), trocas_s=audio.trocas_s)
    else:
        # A música entra depois do ganho e do limitador da fala: o nível dela é o da fala já no alvo.
        volumes = [vinheta.volume_do_recorte(recorte, ALVO_LOUDNESS_LUFS, taxa) if recorte else 1.0
                   for recorte in (vinheta.abertura, vinheta.encerramento)]
        entradas = [*entradas, "-i", str(vinheta.arquivo)]
        trechos = vinheta.trechos(audio)

    def grafo() -> str:
        return vinheta.filtro(VOZ, "1:a", taxa, *volumes) if vinheta else f"[{VOZ}]anull[episodio]"

    ganho_db = ALVO_LOUDNESS_LUFS - fala if fala > SEM_LOUDNESS else 0.0
    teto_dbtp = ALVO_PICO_DBTP
    # O que sai do limitador ainda muda no MP3: o codificador corta os agudos e o pico real sobe
    # (mais de 1 dB no sw-002), e a loudness cai alguns décimos. Mede o MP3 e corrige o que passou.
    # A música é conferida no MP3 também, nos trechos que o QA mede (#142).
    for _ in range(PASSADAS_DE_CODIFICACAO):
        _codificar(entradas, grafo(), taxa, ganho_db, teto_dbtp, destino, bitrate_kbps, taxa_saida)
        if fala <= SEM_LOUDNESS:
            break
        medida = medir_trecho(destino)
        desvio = ALVO_LOUDNESS_LUFS - medida.integrada_lufs
        excesso = medida.pico_real_dbtp - ALVO_PICO_DBTP
        musica = correcao_da_musica(destino, trechos, vinheta) if vinheta else (0.0, 0.0)
        if abs(desvio) <= TOLERANCIA_DE_LOUDNESS_LU and excesso <= 0 and not any(musica):
            break
        ganho_db += desvio
        if excesso > 0:
            teto_dbtp = max(teto_dbtp - excesso - FOLGA_DO_TETO_DB, TETO_MINIMO_DBTP)
        # Se a fala vai baixar nesta passada, a música baixa junto, para não passar dela.
        volumes = [volume * 10 ** ((correcao + min(desvio, 0.0)) / 20) for volume, correcao in zip(volumes, musica)]
    return trechos


def _gravar_wav(audio: Audio, destino: Path) -> None:
    with wave.open(str(destino), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(AMOSTRA_BYTES)
        wav.setframerate(audio.taxa_amostragem)
        wav.writeframes(audio.pcm)


def _codificar(entradas: Sequence[str], grafo: str, taxa: int, ganho_db: float, teto_dbtp: float,
               destino: Path, bitrate_kbps: int, taxa_saida: int) -> None:
    """Ganho e limitador na fala, a mistura do `grafo` (que lê o rótulo VOZ) e de novo o limitador na soma.

    O ganho não passa pela música: o limitador baixa os picos da fala e não os da música, e o ganho
    que compensava isso na fala subia a música junto (si-003, #142). O segundo limitador só pega
    o pico da fala somada à música, na sobreposição da abertura.
    """
    limitador = (f"aresample={taxa * SOBREAMOSTRAGEM},"
                 f"alimiter=limit={10 ** (teto_dbtp / 20):.4f}:level=disabled")
    final = (
        f"[0:a]volume={ganho_db:.2f}dB,{limitador},aresample={taxa}[{VOZ}];"
        f"{grafo};[episodio]{limitador},aresample={taxa_saida}[saida]"
    )
    comando = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        *entradas, "-filter_complex", final, "-map", "[saida]",
        "-ar", str(taxa_saida), "-ac", "1", "-b:a", f"{bitrate_kbps}k",
        str(destino),
    ]
    subprocess.run(comando, check=True)


def duracao_mp3(arquivo: Path) -> float:
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arquivo)],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())

"""
Gerenciador de áudio, BGM (Background Music) e detecção de riscos sonoros.
- Provê biblioteca de trilhas sonoras royalty-free (ambient, lo-fi, suspense)
- Gera automaticamente loops harmônicos sintéticos se nenhuma faixa for fornecida
- Detecta tags de música do Whisper para evitar trechos com copyright
"""

import os
import re
import random
import subprocess
import logging
from pathlib import Path

try:
    import structlog
    logger = structlog.get_logger("audio_manager")
except ImportError:
    logger = logging.getLogger("audio_manager")

ASSETS_DIR = Path("assets/bgm")


def ensure_bgm_library() -> list[Path]:
    """
    Garante a existência do diretório assets/bgm e de ao menos 3 faixas livres de royalties.
    Caso o diretório esteja vazio, sintetiza faixas harmônicas estéreis via FFmpeg.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(ASSETS_DIR.glob("*.mp3")) + list(ASSETS_DIR.glob("*.wav"))
    if existing:
        return existing

    # Sintetiza loops neutros de ambientação caso não haja MP3s carregados
    default_tracks = [
        ("lofi_ambient.mp3", "sine=frequency=130:duration=40[b1]; sine=frequency=196:duration=40[b2]; sine=frequency=261.6:duration=40[b3]; [b1][b2][b3]amix=inputs=3,volume=0.25,lowpass=f=450"),
        ("tension_subtle.mp3", "sine=frequency=82.4:duration=40[b1]; sine=frequency=123.5:duration=40[b2]; [b1][b2]amix=inputs=2,volume=0.22,lowpass=f=350"),
        ("focus_drift.mp3", "sine=frequency=146.8:duration=40[b1]; sine=frequency=220:duration=40[b2]; sine=frequency=293.7:duration=40[b3]; [b1][b2][b3]amix=inputs=3,volume=0.25,lowpass=f=500"),
    ]

    created = []
    for filename, synth_filter in default_tracks:
        out_file = ASSETS_DIR / filename
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", synth_filter,
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(out_file),
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            created.append(out_file)
            logger.info("audio_manager.bgm_synth_created", file=str(out_file))
        except Exception as e:
            logger.warning("audio_manager.bgm_synth_failed", file=filename, error=str(e))

    return created or list(ASSETS_DIR.glob("*.mp3"))


def get_random_bgm() -> Path | None:
    """Retorna uma faixa BGM aleatória da biblioteca."""
    tracks = ensure_bgm_library()
    if not tracks:
        return None
    return random.choice(tracks)


def detect_music_risk(segments: list[dict], start: float, end: float) -> dict:
    """
    Analisa se o trecho [start, end] contém marcações de música que possam gerar strike por Content ID.
    Retorna flag de risco, contagem de tags e aviso.
    """
    if not segments:
        return {"has_music": False, "score_penalty": 0.0, "warning": None}

    music_patterns = [
        r"\[m[uú]sica\]",
        r"\(m[uú]sica\)",
        r"\[music\]",
        r"\(music\)",
        r"♪",
        r"🎵",
        r"🎶",
        r"\[can[cç][aã]o\]",
        r"\[tocando m[uú]sica\]",
    ]
    regex = re.compile("|".join(music_patterns), re.IGNORECASE)

    relevant = [s for s in segments if s.get("end", 0) > start and s.get("start", 0) < end]
    music_segs = 0
    total_segs = max(1, len(relevant))

    for s in relevant:
        txt = s.get("text", "")
        if regex.search(txt):
            music_segs += 1

    ratio = music_segs / total_segs
    has_risk = ratio > 0.25 or music_segs >= 3

    warning = None
    if has_risk:
        warning = f"Aviso de Copyright: Detectado áudio musical em {music_segs} segmentos deste trecho. Risco de Content ID."
        logger.warning("audio_manager.music_risk_detected", start=start, end=end, music_segments=music_segs, ratio=ratio)

    return {
        "has_music": has_risk,
        "music_ratio": ratio,
        "music_segments": music_segs,
        "warning": warning,
    }

import subprocess
import json
from pathlib import Path
import structlog

from config import settings

logger = structlog.get_logger()

OUT = Path(settings.VIDEO_OUTPUT_DIR)
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920  # 9:16 vertical


def _probe_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def cut_and_convert_to_vertical(
    video_path: Path,
    start: float,
    end: float,
    output_path: str,
    segments: list[dict] | None = None,  # segmentos Whisper para legendas
    subtitle_style: str = "none",        # "none" | "simple" | "karaoke"
    aspect_mode: str = "fill",           # "fill" (tela cheia 100%) | "blur" (fundo desfocado)
    hook_text: str | None = None,        # Texto de gancho nos primeiros 5s
) -> Path:
    """
    Corta start→end, converte para 9:16 (fill ou blur), legendas e gancho de retenção em PASSADA ÚNICA.
    - fill (padrão): zoom/crop 1080x1920 central preenchendo 100% da tela (sem barras).
    - blur: letterbox com fundo desfocado acima e abaixo.
    - hook_text: texto chamativo fixado no topo nos primeiros 4.5s com estilo viral.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_duration = end - start
    # Se o corte for ~60s, limita a 59s para garantir enquadramento do YouTube Shorts (evita 60.02s)
    duration = min(raw_duration, 59.0) if raw_duration >= 59.5 else raw_duration

    # 1. Prepara arquivo de legendas/gancho se necessário
    sub_filter = None
    has_sub = subtitle_style != "none" and bool(segments)
    has_hook = bool(hook_text and hook_text.strip())

    if has_sub or has_hook:
        from services.subtitle_generator import (
            generate_ass_hook_only,
            generate_ass_simple,
            generate_ass_karaoke,
        )

        sub_dir = OUT / "subs"
        sub_dir.mkdir(parents=True, exist_ok=True)
        sub_path = sub_dir / f"{out.stem}.ass"

        adjusted = []
        if has_sub and segments:
            adjusted = [
                {**s, "start": s["start"] - start, "end": s["end"] - start}
                for s in segments
                if s["end"] > start and s["start"] < end
            ]

        clean_hook = hook_text.strip() if has_hook else None

        if subtitle_style == "karaoke" and adjusted:
            generate_ass_karaoke(adjusted, sub_path, hook_text=clean_hook)
        elif subtitle_style == "simple" and adjusted:
            generate_ass_simple(adjusted, sub_path, hook_text=clean_hook)
        elif clean_hook:
            generate_ass_hook_only(sub_path, clean_hook)
        elif adjusted:
            generate_ass_simple(adjusted, sub_path)
        else:
            sub_path = None

        if sub_path and sub_path.exists():
            escaped_sub = str(sub_path).replace("\\", "/").replace(":", "\\:")
            sub_filter = f"ass='{escaped_sub}'"

    # 2. Constrói filter_complex conforme o enquadramento escolhido
    if aspect_mode == "blur":
        # Fundo: escala 270x480 -> crop 270x480 -> boxblur leve -> upscale para 1080x1920
        bg_filter = (
            f"[0:v]scale=270:480:force_original_aspect_ratio=increase,"
            f"crop=270:480,boxblur=10:2,scale={W}:{H}[bg];"
        )
        main_filter = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[main];"
        )
        if sub_filter:
            overlay_and_sub = (
                f"[bg][main]overlay=(W-w)/2:(H-h)/2[base];"
                f"[base]{sub_filter}[outv]"
            )
        else:
            overlay_and_sub = f"[bg][main]overlay=(W-w)/2:(H-h)/2[outv]"

        vf = f"{bg_filter}{main_filter}{overlay_and_sub}"
    else:
        # Preenchimento total 100% (crop central 9:16)
        scale_crop = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1"
        )
        if sub_filter:
            vf = f"{scale_crop}[base];[base]{sub_filter}[outv]"
        else:
            vf = f"{scale_crop}[outv]"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
        "-filter_complex", vf,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "fastdecode",
        "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        logger.error("video_processor.ffmpeg.failed", error=err_msg)
        raise RuntimeError(f"FFmpeg falhou ao processar vídeo: {err_msg[:400]}")

    return out


def split_into_parts(
    video_path: Path,
    job_id: str,
    part_duration: int = 60,
    segments: list[dict] | None = None,
    subtitle_style: str = "none",
    aspect_mode: str = "fill",
    hook_text: str | None = None,
    max_parts: int | None = None,
) -> list[Path]:
    """Divide o vídeo inteiro em partes iguais e converte cada uma para 9:16."""
    total   = _probe_duration(video_path)
    outputs = []
    start   = 0.0
    idx     = 1

    while start < total:
        if max_parts is not None and max_parts > 0 and idx > max_parts:
            break

        end = min(start + part_duration, total)
        out = OUT / f"{job_id}_part{idx:03d}.mp4"

        # Filtra segmentos Whisper relevantes para esta parte
        part_segs = None
        if segments:
            part_segs = [s for s in segments if s["end"] > start and s["start"] < end]

        part_hook = hook_text or f"PARTE {idx} 🔥" if hook_text is not False else None

        cut_and_convert_to_vertical(
            video_path, start, end, str(out),
            segments=part_segs,
            subtitle_style=subtitle_style,
            aspect_mode=aspect_mode,
            hook_text=part_hook,
        )
        outputs.append(out)
        start = end
        idx  += 1
    return outputs

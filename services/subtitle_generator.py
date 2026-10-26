"""
subtitle_generator.py
Gera legendas a partir de segmentos Whisper e queima no vídeo via FFmpeg.

Estilos:
  simple   — linha por linha, texto branco + fundo semi-transparente
  karaoke  — palavra por palavra destacada (amarelo bold), estilo TikTok viral
"""

import re
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Word:
    text:  str
    start: float  # segundos
    end:   float


# ── 1. Helpers de tempo ───────────────────────────────────────

def _srt_time(seconds: float) -> str:
    """Converte segundos → HH:MM:SS,mmm (formato SRT)."""
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
    """Converte segundos → H:MM:SS.cc (formato ASS)."""
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ── 2. Extrai palavras com timestamps do Whisper ──────────────

def extract_words(segments: list[dict]) -> list[Word]:
    """
    Tenta usar word-level timestamps do Whisper (whisper-timestamped).
    Fallback: divide o texto do segmento proporcionalmente pelo tempo.
    """
    words = []
    for seg in segments:
        if "words" in seg:
            # whisper-timestamped ou Whisper large-v3 com word_timestamps=True
            for w in seg["words"]:
                words.append(Word(
                    text  = w.get("word", w.get("text", "")).strip(),
                    start = float(w["start"]),
                    end   = float(w["end"]),
                ))
        else:
            # Fallback: divide palavras proporcionalmente
            raw   = seg["text"].strip()
            parts = raw.split()
            if not parts:
                continue
            dur  = (seg["end"] - seg["start"]) / len(parts)
            for i, p in enumerate(parts):
                words.append(Word(
                    text  = p,
                    start = seg["start"] + i * dur,
                    end   = seg["start"] + (i + 1) * dur,
                ))
    return words


# ── 3. Gera SRT (estilo simple) ───────────────────────────────

def generate_srt(segments: list[dict], output_path: Path, max_chars: int = 42) -> Path:
    """
    Gera arquivo .srt agrupando palavras em linhas de até max_chars caracteres.
    Ideal para legendas simples linha a linha.
    """
    words  = extract_words(segments)
    blocks = []
    buf    = []
    buf_start = buf_end = 0.0

    for w in words:
        candidate = " ".join([x.text for x in buf] + [w.text])
        if buf and len(candidate) > max_chars:
            blocks.append((buf_start, buf_end, " ".join(x.text for x in buf)))
            buf = []
        if not buf:
            buf_start = w.start
        buf.append(w)
        buf_end = w.end

    if buf:
        blocks.append((buf_start, buf_end, " ".join(x.text for x in buf)))

    srt_lines = []
    for i, (start, end, text) in enumerate(blocks, 1):
        srt_lines.append(
            f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n"
        )

    output_path.write_text("\n".join(srt_lines), encoding="utf-8")
    return output_path


# ── 4. Gera ASS (estilo karaoke — palavra por palavra + gancho) ─

def get_ass_header(middle_align: bool = False) -> str:
    """
    Gera cabeçalho ASS.
    Se middle_align=True (ex: split-screen / podcast), posiciona a legenda no centro vertical (Alignment 5)
    para não cobrir o rosto da pessoa de baixo.
    """
    default_align = 5 if middle_align else 2
    default_margin_v = 0 if middle_align else 480
    hook_margin_v = 220 if middle_align else 320

    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,66,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,2,0,1,4,2,{default_align},60,60,{default_margin_v},1\n"
        f"Style: Hook,Arial,58,&H0000FFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,3,16,0,8,70,70,{hook_margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

_ASS_HEADER = get_ass_header(False)


def format_hook_text(text: str, max_chars_per_line: int = 24) -> str:
    """Formata o texto do gancho em caixa alta e quebra em até 2 linhas usando \\N."""
    try:
        from services.ai_analyzer import sanitize_ptbr_text
        text = sanitize_ptbr_text(text)
    except Exception:
        pass
    # Remove caracteres de controle de injeção ASS e quebras de linha
    safe = re.sub(r"[\r\n\{\}\\]+", " ", text).strip()
    clean = re.sub(r"\s+", " ", safe).upper()
    if len(clean) <= max_chars_per_line:
        return clean
    words = clean.split()
    lines = []
    curr = []
    curr_len = 0
    for w in words:
        if curr and (curr_len + 1 + len(w)) > max_chars_per_line and len(lines) < 2:
            lines.append(" ".join(curr))
            curr = [w]
            curr_len = len(w)
        else:
            curr.append(w)
            curr_len += len(w) + (1 if curr else 0)
    if curr:
        lines.append(" ".join(curr))
    return "\\N".join(lines[:3])


def create_hook_event(hook_text: str, duration: float = 4.5) -> str:
    """Gera a linha Dialogue ASS para o gancho com fade suave nos primeiros segundos."""
    formatted = format_hook_text(hook_text)
    end_str = _ass_time(duration)
    return f"Dialogue: 1,0:00:00.00,{end_str},Hook,,0,0,0,,{{\\fad(250,300)}}{formatted}"


def generate_ass_hook_only(
    output_path: Path,
    hook_text: str,
    duration: float = 4.5,
    middle_align: bool = False,
) -> Path:
    """Gera arquivo .ass contendo apenas o gancho visual nos primeiros segundos."""
    events = [create_hook_event(hook_text, duration)]
    header = get_ass_header(middle_align)
    output_path.write_text(header + "\n".join(events), encoding="utf-8")
    return output_path


def generate_ass_simple(
    segments: list[dict],
    output_path: Path,
    max_chars: int = 42,
    hook_text: str | None = None,
    hook_duration: float = 4.5,
    middle_align: bool = False,
) -> Path:
    """Gera arquivo .ass para legendas simples linha a linha, com gancho opcional no topo."""
    words  = extract_words(segments)
    blocks = []
    buf    = []
    buf_start = buf_end = 0.0

    for w in words:
        candidate = " ".join([x.text for x in buf] + [w.text])
        if buf and len(candidate) > max_chars:
            blocks.append((buf_start, buf_end, " ".join(x.text for x in buf)))
            buf = []
        if not buf:
            buf_start = w.start
        buf.append(w)
        buf_end = w.end

    if buf:
        blocks.append((buf_start, buf_end, " ".join(x.text for x in buf)))

    events = []
    if hook_text and hook_text.strip():
        events.append(create_hook_event(hook_text.strip(), hook_duration))

    for start, end, text in blocks:
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
        )

    header = get_ass_header(middle_align)
    output_path.write_text(header + "\n".join(events), encoding="utf-8")
    return output_path


def generate_ass_karaoke(
    segments: list[dict],
    output_path: Path,
    words_per_line: int = 4,
    hook_text: str | None = None,
    hook_duration: float = 4.5,
    middle_align: bool = False,
) -> Path:
    """
    Gera arquivo .ass com efeito karaoke:
    linha com N palavras visíveis, palavra ativa em amarelo bold,
    mais gancho no topo nos primeiros segundos se fornecido.
    """
    words  = extract_words(segments)
    events = []

    if hook_text and hook_text.strip():
        events.append(create_hook_event(hook_text.strip(), hook_duration))

    # Agrupa em janelas de words_per_line
    for i in range(0, len(words), words_per_line):
        group = words[i: i + words_per_line]
        if not group:
            continue

        for active_idx, active in enumerate(group):
            # Monta linha: palavras antes (branco), ativa (amarelo bold), depois (branco dim)
            parts = []
            for j, w in enumerate(group):
                if j < active_idx:
                    parts.append(f"{{\\c&H00FFFFFF&}}{w.text}")
                elif j == active_idx:
                    parts.append(f"{{\\c&H00FFFF&\\b1}}{w.text}{{\\b0}}")
                else:
                    parts.append(f"{{\\c&H88FFFFFF&}}{w.text}")
            line_text = " ".join(parts)

            events.append(
                f"Dialogue: 0,{_ass_time(active.start)},{_ass_time(active.end)},"
                f"Default,,0,0,0,,{line_text}"
            )

    header = get_ass_header(middle_align)
    output_path.write_text(header + "\n".join(events), encoding="utf-8")
    return output_path


# ── 5. Queima legenda no vídeo ────────────────────────────────

def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    style: str = "simple",   # "simple" | "karaoke"
    clip_start: float = 0.0, # offset para sincronizar com o corte
) -> Path:
    """
    Queima as legendas no vídeo usando FFmpeg.
    clip_start: quando o segmento não começa em 0s, subtrai o offset do .srt/.ass.
    """
    sub_ext = subtitle_path.suffix.lower()

    if sub_ext == ".srt":
        # Estilo simples: força fonte grande, contorno preto, fundo semi-transparente
        sub_filter = (
            f"subtitles={str(subtitle_path).replace(chr(92), '/')}:"
            f"force_style='FontName=Arial,FontSize=68,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,Outline=3,Shadow=1,"
            f"Alignment=2,MarginV=480,Bold=1'"
        )
    else:
        # ASS: já tem estilos embutidos
        sub_filter = f"ass={str(subtitle_path).replace(chr(92), '/')}"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", sub_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path

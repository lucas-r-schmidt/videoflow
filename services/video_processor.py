import subprocess
import json
from pathlib import Path
from config import settings

try:
    import structlog
    logger = structlog.get_logger()
    log = logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    log = logger

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


def _probe_dimensions(video_path: Path) -> tuple[int, int]:
    """Obtém largura e altura do vídeo via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(video_path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(out.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except Exception:
        return 1920, 1080


def _probe_has_audio(video_path: Path) -> bool:
    """Verifica se o arquivo contém trilha de áudio."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "json",
        str(video_path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(out.stdout)
        return len(data.get("streams", [])) > 0
    except Exception:
        return True


def detect_speaker_face_x(video_path: Path, start: float, duration: float) -> float | None:
    """
    Detecta a posição horizontal média do rosto do falante (0.0 = esquerda, 1.0 = direita).
    Usa MediaPipe Face Detection ou OpenCV Haar Cascade com amostragem leve de frames.
    Retorna None se não houver rostos ou se as bibliotecas não estiverem instaladas.
    """
    if duration <= 0:
        return None

    sample_points = [
        start + (duration * 0.2),
        start + (duration * 0.5),
        start + (duration * 0.8),
    ]

    face_x_ratios = []

    # 1. Tentativa via MediaPipe (alta precisão)
    try:
        import mediapipe as mp
        import cv2

        mp_face = mp.solutions.face_detection
        with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as detector:
            cap = cv2.VideoCapture(str(video_path))
            for t in sample_points:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = detector.process(rgb)
                if res and res.detections:
                    best_det = max(
                        res.detections,
                        key=lambda d: d.location_data.relative_bounding_box.width * d.location_data.relative_bounding_box.height,
                    )
                    bb = best_det.location_data.relative_bounding_box
                    center_x = bb.xmin + (bb.width / 2.0)
                    face_x_ratios.append(center_x)
            cap.release()

        if face_x_ratios:
            import statistics
            return float(statistics.median(face_x_ratios))
    except Exception:
        pass

    # 2. Fallback via OpenCV Haar Cascade
    try:
        import cv2
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        cap = cv2.VideoCapture(str(video_path))
        for t in sample_points:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(60, 60))
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2] * f[3])
                center_x = (largest[0] + largest[2] / 2.0) / frame.shape[1]
                face_x_ratios.append(center_x)
        cap.release()

        if face_x_ratios:
            import statistics
            return float(statistics.median(face_x_ratios))
    except Exception:
        pass

    return None


def detect_dual_faces_x(video_path: Path, start: float, duration: float) -> tuple[float, float]:
    """
    Detecta duas posições horizontais médias de rostos (esquerda e direita) para layout split-screen.
    Retorna (left_x, right_x) onde 0.0 é esquerda total e 1.0 é direita total.
    Fallback: (0.25, 0.75).
    """
    if duration <= 0:
        return 0.25, 0.75

    sample_points = [
        start + (duration * 0.15),
        start + (duration * 0.35),
        start + (duration * 0.55),
        start + (duration * 0.75),
        start + (duration * 0.90),
    ]

    left_faces = []
    right_faces = []

    # 1. Tentativa via MediaPipe (alta precisão)
    try:
        import mediapipe as mp
        import cv2

        mp_face = mp.solutions.face_detection
        with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.45) as detector:
            cap = cv2.VideoCapture(str(video_path))
            for t in sample_points:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = detector.process(rgb)
                if res and res.detections:
                    for det in res.detections:
                        bb = det.location_data.relative_bounding_box
                        center_x = bb.xmin + (bb.width / 2.0)
                        if bb.width > 0.04 and bb.height > 0.04:
                            if center_x < 0.50:
                                left_faces.append(center_x)
                            else:
                                right_faces.append(center_x)
            cap.release()
    except Exception:
        pass

    # 2. Fallback via OpenCV Haar Cascade se MediaPipe não achar
    if not left_faces and not right_faces:
        try:
            import cv2
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            face_cascade = cv2.CascadeClassifier(cascade_path)
            cap = cv2.VideoCapture(str(video_path))
            for t in sample_points:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(60, 60))
                for (fx, fy, fw, fh) in faces:
                    cx = (fx + fw / 2.0) / frame.shape[1]
                    if cx < 0.50:
                        left_faces.append(cx)
                    else:
                        right_faces.append(cx)
            cap.release()
        except Exception:
            pass

    import statistics
    left_x = float(statistics.median(left_faces)) if left_faces else 0.25
    right_x = float(statistics.median(right_faces)) if right_faces else 0.75

    # Clamping de segurança para enquadramentos utilizáveis
    left_x = max(0.12, min(0.45, left_x))
    right_x = max(0.55, min(0.88, right_x))

    return left_x, right_x


def plan_jump_cut_intervals(
    start: float,
    end: float,
    segments: list[dict] | None,
    min_silence: float = 0.55,
    lead_in: float = 0.12,
    lead_out: float = 0.18,
) -> list[tuple[float, float]]:
    """
    Identifica sub-intervalos ativos de fala dentro de [start, end].
    Elimina pausas de silêncio mortas (> min_silence) mantendo margem natural de fala.
    """
    if not segments:
        return [(start, end)]

    clip_segs = [s for s in segments if float(s.get("end", 0)) > start and float(s.get("start", 0)) < end]
    if not clip_segs:
        return [(start, end)]

    # Constrói faixas de fala ativas limitadas a [start, end]
    speech_ranges = []
    for s in clip_segs:
        s_st = max(start, float(s.get("start", start)))
        s_en = min(end, float(s.get("end", end)))
        if s_en > s_st:
            speech_ranges.append((s_st, s_en))

    if not speech_ranges:
        return [(start, end)]

    # Une blocos de fala cuja pausa entre eles é menor ou igual a min_silence
    merged = []
    cur_s, cur_e = speech_ranges[0]
    for nxt_s, nxt_e in speech_ranges[1:]:
        if nxt_s - cur_e <= min_silence:
            cur_e = max(cur_e, nxt_e)
        else:
            merged.append((cur_s, cur_e))
            cur_s, cur_e = nxt_s, nxt_e
    merged.append((cur_s, cur_e))

    # Aplica margens de respiro natural (lead_in e lead_out)
    expanded = []
    for m_s, m_e in merged:
        ext_s = max(start, m_s - lead_in)
        ext_e = min(end, m_e + lead_out)
        if expanded and ext_s <= expanded[-1][1]:
            prev_s, _ = expanded.pop()
            expanded.append((prev_s, ext_e))
        else:
            expanded.append((ext_s, ext_e))

    # Se a diferença para as bordas for mínima (< 0.35s), mantém as bordas
    if expanded and (expanded[0][0] - start) < 0.35:
        expanded[0] = (start, expanded[0][1])
    if expanded and (end - expanded[-1][1]) < 0.35:
        expanded[-1] = (expanded[-1][0], end)

    total_kept = sum(e - s for s, e in expanded)
    # Se economizar menos de 0.6s no total, não justifica cortes extras
    if (end - start) - total_kept < 0.6:
        return [(start, end)]

    return expanded


def _remap_time_for_jump_cuts(t: float, intervals: list[tuple[float, float]]) -> float:
    """Mapeia o timestamp original do vídeo para a linha do tempo concatenada pós-corte de silêncios."""
    accum = 0.0
    for s, e in intervals:
        dur = e - s
        if t < s:
            return accum
        elif t <= e:
            return accum + (t - s)
        accum += dur
    return accum


def cut_and_convert_to_vertical(
    video_path: Path,
    start: float,
    end: float,
    output_path: str,
    segments: list[dict] | None = None,  # segmentos Whisper para legendas
    subtitle_style: str = "none",        # "none" | "simple" | "karaoke"
    aspect_mode: str = "fill",           # "fill" (com auto face tracking) | "blur" (fundo desfocado)
    hook_text: str | None = None,        # Texto de gancho nos primeiros 5s
    headline_text: str | None = None,    # Banner superior chamativo persistente
    jump_cut: bool = True,               # Remove pausas mortas de silêncio se ativo
    enable_bgm: bool = True,             # Trilha de fundo royalty-free para mascarar Content ID
    bgm_volume: float = 0.08,            # Volume sutil de BGM (0.05 - 0.12)
    speed_boost: float = 1.03,           # Leve aceleração (1.03x) para alterar pitch e tempo
    horizontal_flip: bool = False,       # Espelha horizontalmente o vídeo (anti-fingerprint óptico)
    watermark_text: str | None = None,   # Marca d'água / assinatura autoral no canto
) -> Path:
    """
    Corta start→end, converte para 9:16 com auto face tracking, legendas, gancho, headline, BGM e jump-cuts opcionais.
    - fill (padrão): zoom 1080x1920 centralizado no rosto do falante (ou centro se sem rosto).
    - blur: letterbox com fundo desfocado acima e abaixo.
    - hook_text: texto chamativo fixado no topo nos primeiros 4.5s.
    - headline_text: banner superior persistente durante todo o corte.
    - enable_bgm: mix de música neutra sutil para quebra de fingerprint de áudio.
    - speed_boost: aceleração 1.03x de vídeo e áudio contra Content ID.
    - horizontal_flip: espelhamento óptico que quebra hashes de imagem sem inverter legendas.
    - watermark_text: assinatura autoral do canal de cortes no canto inferior.
    - jump_cut: remove pausas mortas de respiração e silêncios mantendo sincronia perfeita.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_duration = end - start
    duration = min(raw_duration, 59.0) if 59.5 <= raw_duration <= 61.5 else raw_duration

    has_audio = _probe_has_audio(video_path)

    # 1. Planejamento de intervalos com jump-cuts se solicitado
    intervals = [(start, end)]
    if jump_cut and segments and has_audio:
        intervals = plan_jump_cut_intervals(start, end, segments)

    is_jump_cut = len(intervals) > 1 or (len(intervals) == 1 and (abs(intervals[0][0] - start) > 0.05 or abs(intervals[0][1] - end) > 0.05))
    final_target_duration = sum(e - s for s, e in intervals) if is_jump_cut else duration

    # 2. Prepara arquivo de legendas/gancho/headline/watermark se necessário
    sub_filter = None
    has_sub = subtitle_style != "none" and bool(segments)
    has_hook = bool(hook_text and hook_text.strip())
    has_headline = bool(headline_text and headline_text.strip())
    has_watermark = bool(watermark_text and watermark_text.strip())

    if has_sub or has_hook or has_headline or has_watermark:
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
            for s in segments:
                if s["end"] > start and s["start"] < end:
                    if is_jump_cut:
                        c_start = _remap_time_for_jump_cuts(float(s["start"]), intervals)
                        c_end = _remap_time_for_jump_cuts(float(s["end"]), intervals)
                    else:
                        c_start = max(0.0, s["start"] - start)
                        c_end = max(0.0, s["end"] - start)

                    if c_end > c_start:
                        item = {**s, "start": c_start, "end": c_end}
                        if "words" in s and s["words"]:
                            mapped_words = []
                            for w in s["words"]:
                                w_raw_end = float(w.get("end", s["end"]))
                                w_raw_start = float(w.get("start", s["start"]))
                                if w_raw_end > start and w_raw_start < end:
                                    if is_jump_cut:
                                        w_st = _remap_time_for_jump_cuts(w_raw_start, intervals)
                                        w_en = _remap_time_for_jump_cuts(w_raw_end, intervals)
                                    else:
                                        w_st = max(0.0, w_raw_start - start)
                                        w_en = max(0.0, w_raw_end - start)
                                    if w_en > w_st:
                                        mapped_words.append({**w, "start": w_st, "end": w_en})
                            item["words"] = mapped_words
                        adjusted.append(item)

        clean_hook = hook_text.strip() if has_hook else None
        clean_headline = headline_text.strip() if has_headline else None
        clean_watermark = watermark_text.strip() if has_watermark else None
        is_split = (aspect_mode == "split")

        if subtitle_style == "karaoke" and adjusted:
            generate_ass_karaoke(adjusted, sub_path, hook_text=clean_hook, headline_text=clean_headline, watermark_text=clean_watermark, total_duration=final_target_duration, middle_align=is_split)
        elif subtitle_style == "simple" and adjusted:
            generate_ass_simple(adjusted, sub_path, hook_text=clean_hook, headline_text=clean_headline, watermark_text=clean_watermark, total_duration=final_target_duration, middle_align=is_split)
        elif clean_hook or clean_headline or clean_watermark:
            generate_ass_hook_only(sub_path, hook_text=clean_hook, headline_text=clean_headline, watermark_text=clean_watermark, total_duration=final_target_duration, middle_align=is_split)
        elif adjusted:
            generate_ass_simple(adjusted, sub_path, headline_text=clean_headline, watermark_text=clean_watermark, total_duration=final_target_duration, middle_align=is_split)
        else:
            sub_path = None

        if sub_path and sub_path.exists():
            escaped_sub = str(sub_path).replace("\\", "/").replace(":", "\\:")
            sub_filter = f"ass='{escaped_sub}'"

    # 3. Constrói filter_complex conforme o enquadramento escolhido e jump-cuts
    pre_filter = ""
    v_src = "[0:v]"
    a_cut_label = None

    if is_jump_cut:
        rel_intervals = [(max(0.0, s - start), min(duration, e - start)) for s, e in intervals]
        trim_lines = []
        if has_audio:
            for idx, (s_rel, e_rel) in enumerate(rel_intervals):
                trim_lines.append(f"[0:v]trim=start={s_rel:.3f}:end={e_rel:.3f},setpts=PTS-STARTPTS[v{idx}];")
                trim_lines.append(f"[0:a]atrim=start={s_rel:.3f}:end={e_rel:.3f},asetpts=PTS-STARTPTS[a{idx}];")
            concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(rel_intervals)))
            trim_lines.append(f"{concat_inputs}concat=n={len(rel_intervals)}:v=1:a=1[v_cut][a_cut];")
            a_cut_label = "[a_cut]"
        else:
            for idx, (s_rel, e_rel) in enumerate(rel_intervals):
                trim_lines.append(f"[0:v]trim=start={s_rel:.3f}:end={e_rel:.3f},setpts=PTS-STARTPTS[v{idx}];")
            concat_inputs = "".join(f"[v{i}]" for i in range(len(rel_intervals)))
            trim_lines.append(f"{concat_inputs}concat=n={len(rel_intervals)}:v=1:a=0[v_cut];")

        pre_filter = "".join(trim_lines)
        v_src = "[v_cut]"

    if aspect_mode == "blur":
        bg_filter = (
            f"{v_src}scale=270:480:force_original_aspect_ratio=increase,"
            f"crop=270:480,boxblur=10:2,scale={W}:{H}[bg];"
        )
        main_filter = (
            f"{v_src}scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[main];"
        )
        vf_base = f"{pre_filter}{bg_filter}{main_filter}[bg][main]overlay=(W-w)/2:(H-h)/2[v_base];"
    elif aspect_mode == "split":
        # Modo Podcast / Duas Câmeras Empilhadas (Host em cima, Convidado embaixo)
        orig_w, orig_h = _probe_dimensions(video_path)

        crop_h = orig_h
        crop_w = int(orig_h * (W / 960))
        if crop_w > orig_w:
            crop_w = orig_w
            crop_h = int(crop_w * (960 / W))

        # Garante dimensões pares para compatibilidade estrita do codec x264
        crop_w = (crop_w // 2) * 2
        crop_h = (crop_h // 2) * 2

        left_x, right_x = detect_dual_faces_x(video_path, start, duration)

        ideal_c1 = int(left_x * orig_w)
        crop_x1 = max(0, min(orig_w - crop_w, ideal_c1 - (crop_w // 2)))
        crop_x1 = (crop_x1 // 2) * 2

        ideal_c2 = int(right_x * orig_w)
        crop_x2 = max(0, min(orig_w - crop_w, ideal_c2 - (crop_w // 2)))
        crop_x2 = (crop_x2 // 2) * 2

        crop_y = max(0, (orig_h - crop_h) // 2)
        crop_y = (crop_y // 2) * 2

        split_filter = (
            f"{v_src}split=2[v_top_in][v_bot_in];"
            f"[v_top_in]crop={crop_w}:{crop_h}:{crop_x1}:{crop_y},scale={W}:960,setsar=1[top];"
            f"[v_bot_in]crop={crop_w}:{crop_h}:{crop_x2}:{crop_y},scale={W}:960,setsar=1[bottom];"
            f"[top][bottom]vstack=inputs=2,drawbox=x=0:y=958:w={W}:h=4:color=black@0.9:t=fill[v_base];"
        )
        vf_base = f"{pre_filter}{split_filter}"
    else:
        # Preenchimento total 100% com reframe inteligente de rosto (se disponível)
        orig_w, orig_h = _probe_dimensions(video_path)

        # Se o vídeo de entrada JÁ É vertical 9:16 (ex: 2160x3840 ou 1080x1920), faz downscale direto
        is_already_vertical = orig_h > orig_w and abs((orig_w / orig_h) - (W / H)) < 0.05
        if is_already_vertical:
            scale_crop = f"{v_src}scale={W}:{H},setsar=1"
        else:
            scale_w = int(orig_w * (H / orig_h)) if orig_h > 0 else W
            pan_range = max(0, scale_w - W)

            face_x = None
            if pan_range > 0:
                face_x = detect_speaker_face_x(video_path, start, duration)

            if face_x is not None and pan_range > 0:
                ideal_center = int(face_x * scale_w)
                crop_x = max(0, min(pan_range, ideal_center - (W // 2)))
                scale_crop = f"{v_src}scale={scale_w}:{H},crop={W}:{H}:{crop_x}:0,setsar=1"
            else:
                scale_crop = (
                    f"{v_src}scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},setsar=1"
                )
        vf_base = f"{pre_filter}{scale_crop}[v_base];"

    # Aplica espelhamento horizontal (hflip) ANTES das legendas para que o texto não fique invertido
    if horizontal_flip:
        flip_line = "[v_base]hflip[v_flipped];"
        v_target = "[v_flipped]"
    else:
        flip_line = ""
        v_target = "[v_base]"

    if sub_filter:
        sub_line = f"{v_target}{sub_filter}[v_framed]"
    else:
        sub_line = f"{v_target}null[v_framed]"

    vf_core = f"{vf_base}{flip_line}{sub_line}"

    # Aplica speed_boost de vídeo
    speed_factor = max(1.0, min(1.25, float(speed_boost))) if speed_boost else 1.0
    if abs(speed_factor - 1.0) > 0.005:
        vf_full = f"{vf_core};[v_framed]setpts=PTS/{speed_factor:.4f}[outv]"
    else:
        vf_full = f"{vf_core};[v_framed]null[outv]"

    # 4. Processamento de áudio (speed_boost e amix com BGM)
    bgm_path = None
    if enable_bgm:
        from services.audio_manager import get_random_bgm
        bgm_path = get_random_bgm()

    filter_chains = [vf_full]
    a_out_label = None

    if has_audio:
        a_in = a_cut_label if is_jump_cut else "[0:a]"
        if abs(speed_factor - 1.0) > 0.005:
            filter_chains.append(f"{a_in}atempo={speed_factor:.4f}[maina]")
        else:
            filter_chains.append(f"{a_in}aresample=async=1[maina]")

        if bgm_path and bgm_path.exists():
            bgm_vol = max(0.01, min(0.35, float(bgm_volume)))
            filter_chains.append(f"[1:a]volume={bgm_vol:.3f}[bgma]")
            filter_chains.append(f"[maina][bgma]amix=inputs=2:duration=first:dropout_transition=2[outa]")
            a_out_label = "[outa]"
        else:
            filter_chains.append(f"[maina]null[outa]")
            a_out_label = "[outa]"
    elif bgm_path and bgm_path.exists():
        bgm_vol = max(0.01, min(0.35, float(bgm_volume)))
        filter_chains.append(f"[1:a]volume={bgm_vol:.3f}[outa]")
        a_out_label = "[outa]"

    final_filter_complex = ";".join(filter_chains)

    # 5. Execução do FFmpeg
    output_duration = final_target_duration / speed_factor

    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-ss", str(start),
        "-i", str(video_path),
    ]

    if bgm_path and bgm_path.exists():
        cmd.extend(["-stream_loop", "-1", "-i", str(bgm_path)])

    cmd.extend([
        "-t", f"{output_duration:.3f}",
        "-filter_complex", final_filter_complex,
        "-map", "[outv]",
    ])

    if a_out_label:
        cmd.extend(["-map", a_out_label, "-c:a", "aac", "-b:a", "128k"])
    else:
        cmd.append("-an")

    cmd.extend([
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "fastdecode",
        "-crf", "23",
        "-movflags", "+faststart",
        str(out),
    ])

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        # Se falhou com jump cut (ex: vídeo sem trilha de áudio), tenta fallback contínuo
        if is_jump_cut:
            log.warning("video_processor.jump_cut_fallback", error=err_msg[:200])
            return cut_and_convert_to_vertical(
                video_path, start, end, output_path,
                segments=segments, subtitle_style=subtitle_style,
                aspect_mode=aspect_mode, hook_text=hook_text,
                headline_text=headline_text, jump_cut=False,
                enable_bgm=enable_bgm, bgm_volume=bgm_volume,
                speed_boost=speed_boost, horizontal_flip=horizontal_flip,
                watermark_text=watermark_text,
            )
        raise RuntimeError(f"FFmpeg falhou ao processar vídeo: {err_msg[:400]}")
    return out


def _detect_scenes_in_window(video_path: Path, min_cut: float, max_cut: float) -> list[float]:
    """Detecta cortes de cena na janela temporal via PySceneDetect ou FFmpeg scene filter."""
    if not video_path or not video_path.exists() or (max_cut - min_cut) <= 0.2:
        return []

    # 1. PySceneDetect
    try:
        from scenedetect import detect, ContentDetector
        scenes = detect(str(video_path), ContentDetector(threshold=27.0), start_time=min_cut, end_time=max_cut)
        cuts = [s[0].get_seconds() for s in scenes if min_cut <= s[0].get_seconds() <= max_cut]
        if cuts:
            return cuts
    except Exception:
        pass

    # 2. Fallback via FFmpeg scene filter (rápido, ~0.2s)
    try:
        cmd = [
            "ffmpeg", "-v", "quiet",
            "-ss", str(min_cut), "-to", str(max_cut),
            "-i", str(video_path),
            "-filter_complex", "select='gt(scene,0.30)',metadata=print:file=-",
            "-f", "null", "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        found = []
        for line in res.stdout.splitlines():
            if "pts_time:" in line:
                val = float(line.split("pts_time:")[1].strip())
                found.append(round(min_cut + val, 2))
        return found
    except Exception:
        return []


def _find_best_cut_point(
    target_end: float,
    segments: list[dict] | None,
    total_duration: float,
    window_back: float = 3.5,
    window_forward: float = 1.5,
    video_path: Path | None = None,
) -> float:
    """
    Encontra o ponto de corte ideal próximo a target_end baseado no fim de falas (VAD/Whisper)
    e cortes de cena (PySceneDetect/FFmpeg).
    """
    if not segments:
        return min(target_end, total_duration)

    min_cut = max(0.0, target_end - window_back)
    max_cut = min(total_duration, target_end + window_forward)

    # Detecção de cortes de cena na janela
    scene_cuts = _detect_scenes_in_window(video_path, min_cut, max_cut) if video_path else []

    candidates = []
    for i, s in enumerate(segments):
        s_end = float(s.get("end", 0.0))
        if min_cut <= s_end <= max_cut:
            text = (s.get("text") or "").strip()
            score = 0.0

            # Pontuação forte (fim de frase)
            if text.endswith((".", "!", "?", "…")):
                score += 5.0
            elif text.endswith((",", ";", ":", "-")):
                score += 2.0

            # Pausa de silêncio / VAD após o segmento
            if i + 1 < len(segments):
                next_start = float(segments[i + 1].get("start", s_end))
                silence = next_start - s_end
                if silence >= 0.4:
                    score += 4.0
                elif silence >= 0.2:
                    score += 2.0

            # Bônus se houver corte de cena próximo à pausa de fala (transição de vídeo perfeita)
            for sc in scene_cuts:
                if abs(sc - s_end) <= 0.45:
                    score += 6.0
                    break

            # Penalidade pela distância do tempo alvo
            diff = abs(s_end - target_end)
            score -= (diff * 1.5)

            candidates.append((score, s_end))

    # Também adiciona cortes de cena diretos como candidatos caso a fala esteja pausada
    for sc in scene_cuts:
        diff = abs(sc - target_end)
        candidates.append((4.0 - (diff * 1.5), sc))

    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        return round(candidates[0][1], 2)

    return min(target_end, total_duration)


def plan_part_intervals(
    total_duration: float,
    part_duration: int = 60,
    segments: list[dict] | None = None,
    max_parts: int | None = None,
    video_path: Path | None = None,
) -> list[tuple[float, float, int]]:
    """
    Calcula os intervalos (start, end, part_index) de corte.
    Aplica snapping inteligente de bordas próximo a pausas/pontuação e cortes de cena.
    """
    intervals = []
    start = 0.0
    idx = 1

    while start < total_duration:
        if max_parts is not None and max_parts > 0 and idx > max_parts:
            break

        target_end = start + part_duration
        if target_end >= total_duration:
            end = total_duration
        else:
            end = _find_best_cut_point(target_end, segments, total_duration, video_path=video_path)
            # Se a sobra final for ínfima (< 8s), absorve na última parte
            if (total_duration - end) < 8.0:
                end = total_duration

        if end <= start:
            end = min(start + part_duration, total_duration)

        intervals.append((start, end, idx))
        start = end
        idx += 1

    return intervals


def split_into_parts(
    video_path: Path,
    job_id: str,
    part_duration: int = 60,
    segments: list[dict] | None = None,
    subtitle_style: str = "none",
    aspect_mode: str = "fill",
    hook_text: str | None = None,
    hook_texts: list[str] | None = None,
    headline_text: str | None = None,
    headline_texts: list[str] | None = None,
    enable_bgm: bool = True,
    bgm_volume: float = 0.08,
    speed_boost: float = 1.03,
    horizontal_flip: bool = False,
    watermark_text: str | None = None,
    max_parts: int | None = None,
) -> list[Path]:
    """Divide o vídeo em partes com corte inteligente nas falas e converte cada uma para 9:16."""
    total = _probe_duration(video_path)
    intervals = plan_part_intervals(total, part_duration, segments, max_parts, video_path=video_path)
    outputs = []

    for start, end, idx in intervals:
        out = OUT / f"{job_id}_part{idx:03d}.mp4"

        # Filtra segmentos Whisper relevantes para esta parte
        part_segs = None
        if segments:
            part_segs = [s for s in segments if s["end"] > start and s["start"] < end]

        if hook_texts and (idx - 1) < len(hook_texts) and hook_texts[idx - 1] is not None:
            part_hook = hook_texts[idx - 1] if hook_texts[idx - 1] is not False else None
        elif hook_text is False:
            part_hook = None
        else:
            part_hook = hook_text or f"PARTE {idx} 🔥"

        # Headline text persistente por parte ou global
        if headline_texts and (idx - 1) < len(headline_texts) and headline_texts[idx - 1]:
            part_headline = headline_texts[idx - 1]
        else:
            part_headline = headline_text

        cut_and_convert_to_vertical(
            video_path, start, end, str(out),
            segments=part_segs,
            subtitle_style=subtitle_style,
            aspect_mode=aspect_mode,
            hook_text=part_hook,
            headline_text=part_headline,
            enable_bgm=enable_bgm,
            bgm_volume=bgm_volume,
            speed_boost=speed_boost,
            horizontal_flip=horizontal_flip,
            watermark_text=watermark_text,
        )
        outputs.append(out)

    return outputs


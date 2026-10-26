import os
import sys
import types
import json
import subprocess
from pathlib import Path

# Suporte a UTF-8 no console do Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Shim para structlog e pydantic_settings caso não instalados globalmente
if "structlog" not in sys.modules:
    s_mod = types.ModuleType("structlog")
    class SimpleLogger:
        def get_logger(self, *a, **kw): return self
        def bind(self, *a, **kw): return self
        def info(self, msg, **kw): print(f"[INFO] {msg} {kw if kw else ''}")
        def warning(self, msg, **kw): print(f"[WARN] {msg} {kw if kw else ''}")
        def error(self, msg, **kw): print(f"[ERROR] {msg} {kw if kw else ''}")
    _sl = SimpleLogger()
    s_mod.get_logger = lambda *a, **kw: _sl
    sys.modules["structlog"] = s_mod

# Carrega .env manualmente
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Configura mock settings para apontar para pasta local test_outputs
class MockSettings:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi3:mini")
    WHISPER_MODEL = "base"
    VIDEO_TMP_DIR = str((Path(__file__).parent / "test_outputs" / "tmp").resolve())
    VIDEO_OUTPUT_DIR = str((Path(__file__).parent / "test_outputs").resolve())

conf_mod = types.ModuleType("config")
conf_mod.settings = MockSettings()
sys.modules["config"] = conf_mod

if "numpy" not in sys.modules:
    sys.modules["numpy"] = types.ModuleType("numpy")

# Importa serviços do videoflow
from services.ai_analyzer import transcribe_groq, generate_part_copy
from services.video_processor import (
    _probe_duration,
    plan_part_intervals,
    cut_and_convert_to_vertical,
)

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "test_outputs"
TMP_DIR = OUT_DIR / "tmp"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

YOUTUBE_URL = "https://www.youtube.com/watch?v=Xu6LliILTc4"
RAW_VIDEO = OUT_DIR / "video_original.mp4"

def step_download():
    print("\n" + "="*60)
    print("1. BAIXANDO VÍDEO DO YOUTUBE...")
    print("="*60)
    if RAW_VIDEO.exists() and RAW_VIDEO.stat().st_size > 1024 * 1024:
        print(f"Vídeo já baixado previamente: {RAW_VIDEO} ({RAW_VIDEO.stat().st_size // (1024*1024)} MB)")
        return RAW_VIDEO

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--output", str(RAW_VIDEO),
        "--no-playlist",
        "--socket-timeout", "30",
        "--", YOUTUBE_URL
    ]
    subprocess.run(cmd, check=True)
    print(f"Download concluído: {RAW_VIDEO}")
    return RAW_VIDEO

def step_transcribe(video_path: Path):
    print("\n" + "="*60)
    print("2. TRANSCREVENDO ÁUDIO VIA GROQ WHISPER API...")
    print("="*60)
    cache_json = OUT_DIR / "transcription.json"
    if cache_json.exists():
        print(f"Carregando transcrição existente de: {cache_json}")
        with open(cache_json, "r", encoding="utf-8") as f:
            return json.load(f)

    segments = transcribe_groq(str(video_path))
    with open(cache_json, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    print(f"Transcrição finalizada: {len(segments)} segmentos encontrados.")
    return segments

def run_test():
    video_path = step_download()
    duration = _probe_duration(video_path)
    print(f"Duração total do vídeo: {duration:.2f}s ({duration/60:.2f} min)")

    segments = step_transcribe(video_path)

    print("\n" + "="*60)
    print("3. PLANEJANDO INTERVALOS COM SNAPPING INTELIGENTE DE FALAS...")
    print("="*60)
    part_duration = 60
    intervals = plan_part_intervals(duration, part_duration=part_duration, segments=segments)
    total_parts = len(intervals)

    print(f"Total de partes calculadas: {total_parts}")
    for start, end, idx in intervals:
        dur = end - start
        p_segs = [s for s in segments if s["end"] > start and s["start"] < end]
        last_words = p_segs[-1]["text"] if p_segs else ""
        print(f"  - Parte {idx:02d}: {start:6.2f}s -> {end:6.2f}s (duração: {dur:5.2f}s) | Última fala: \"{last_words}\"")

    print("\n" + "="*60)
    print("4. GERANDO COPY VIRAL, GANCHOS E RENDERIZANDO CADA PARTE EM 9:16...")
    print("="*60)

    results = []
    for start, end, idx in intervals:
        p_segs = [s for s in segments if s["end"] > start and s["start"] < end]
        p_text = " ".join(s.get("text", "") for s in p_segs)

        print(f"\n--- Processando Parte {idx}/{total_parts} ---")
        copy_res = generate_part_copy(p_text, idx, total_parts)
        hook = copy_res.get("hook")
        title = copy_res.get("title")
        caption = copy_res.get("caption")

        print(f"  Gancho (Hook 5s): {hook}")
        print(f"  Título: {title}")
        print(f"  Legenda Preview: {caption.splitlines()[0] if caption else ''}")

        out_file = OUT_DIR / f"parte_{idx:02d}.mp4"
        print(f"  Renderizando 9:16 + legendas karaokê -> {out_file.name} ...")

        cut_and_convert_to_vertical(
            video_path,
            start=start,
            end=end,
            output_path=str(out_file),
            segments=p_segs,
            subtitle_style="karaoke",
            aspect_mode="fill",
            hook_text=hook,
        )
        print(f"  [OK] Parte {idx} gerada com sucesso! Tamanho: {out_file.stat().st_size // (1024*1024)} MB")

        results.append({
            "part": idx,
            "file": str(out_file.resolve()),
            "start": start,
            "end": end,
            "duration": round(end - start, 2),
            "hook": hook,
            "title": title,
        })

    print("\n" + "="*60)
    print("5. RESULTADO FINAL DA VALIDAÇÃO")
    print("="*60)
    for r in results:
        print(f"Parte {r['part']}: {r['duration']}s [{r['start']}s -> {r['end']}s]")
        print(f"  Arquivo: {r['file']}")
        print(f"  Gancho:  {r['hook']}")
        print(f"  Título:  {r['title']}")
        print("-" * 40)

if __name__ == "__main__":
    run_test()

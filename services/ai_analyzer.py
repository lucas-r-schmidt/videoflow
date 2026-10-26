import re
import json
import httpx
import numpy as np
from pathlib import Path

from config import settings


# ── Diretrizes e Sanitização de Linguagem PT-BR ───────────────

PT_BR_LANGUAGE_RULES = (
    "DIRETRIZES OBRIGATÓRIAS DE LÍNGUA PORTUGUESA (PT-BR):\n"
    "1. Gramática e ortografia impecáveis segundo o Novo Acordo Ortográfico.\n"
    "2. Conjugação e significados corretos:\n"
    "   - Verbo PROVAR (experimentar sabor/comida): use 'provou'/'provar' (NUNCA confunda com 'prover'/'proveu').\n"
    "   - Substantivo 'perda' vs verbo 'perca': use 'não sofra essa perda' (nunca 'essa perca').\n"
    "   - Tempo decorrido: use 'faz' impessoal ('faz anos', nunca 'fazem anos').\n"
    "   - Verbo haver (existir): use 'houve' impessoal ('houve problemas', nunca 'houveram').\n"
    "3. Regras de acentuação estritas:\n"
    "   - NUNCA invente acentos em palavras paroxítonas terminadas em A, E, O (ex.: 'paçoca', NUNCA 'paçocá'; 'ideia', 'apoio', 'autoestima', 'item', 'gratuito').\n"
    "   - NUNCA invente pontuação estrangeira ou invertida (¿, ¡).\n"
    "4. Estilo natural para criadores de conteúdo do Brasil: dinâmico, direto, sem clichês robóticos."
)


def _match_case(template: str, replacement: str) -> str:
    """Preserva maiúsculas/minúsculas da palavra original."""
    if template.isupper():
        return replacement.upper()
    if template.istitle():
        return replacement.capitalize()
    return replacement.lower()


def _replace_word(pattern: str, target: str, text: str) -> str:
    def repl(m: re.Match) -> str:
        orig = m.group(0)
        return _match_case(orig, target)
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def sanitize_ptbr_text(text: str) -> str:
    """
    Corrige alucinações gramaticais e ortográficas recorrentes de LLMs em PT-BR,
    limpa pontuações espúrias e normaliza espaçamento.
    """
    if not text:
        return ""

    out = text

    # Remove pontuação invertida (espanhol: ¿, ¡)
    out = re.sub(r"[¿¡]", "", out)

    # Acentuação indevida em paroxítonas comuns e erros ortográficos
    out = _replace_word(r"\bpaçoc[áàâã]\b", "paçoca", out)
    out = _replace_word(r"\bgratu[íi]to\b", "gratuito", out)
    out = _replace_word(r"\br[úu]brica\b", "rubrica", out)
    out = _replace_word(r"\bid[éê]ia\b", "ideia", out)
    out = _replace_word(r"\bauto-estima\b", "autoestima", out)

    # Prover (abastecer) vs Provar (degustar sabor / testar)
    out = re.sub(
        r"\b(j[áa]|voc[êe]|tu|ele|ela|algu[ée]m)\s+proveu\b",
        lambda m: m.group(1) + (" PROVOU" if m.group(0).isupper() else " provou"),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bproveu\s+(o|a|os|as|um|uma|do|da|dos|das|desse|dessa|deste|desta|comida|doce|prato|sabor|paçoca|disso|disto|daquilo)\b",
        lambda m: ("PROVOU " if m.group(0).isupper() else "provou ") + m.group(1),
        out,
        flags=re.IGNORECASE,
    )

    # Concordâncias comuns
    out = re.sub(
        r"\bfazem\s+(\d+|muitos|vários|anos|meses|dias|semanas|horas)\b",
        lambda m: ("FAZ " if m.group(0).isupper() else "faz ") + m.group(1),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bhouveram\s+(muitos|vários|problemas|casos|motivos)\b",
        lambda m: ("HOUVE " if m.group(0).isupper() else "houve ") + m.group(1),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b(essa|uma|grande|minha|sua|qualquer)\s+perca\b",
        lambda m: m.group(1) + (" PERDA" if m.group(0).isupper() else " perda"),
        out,
        flags=re.IGNORECASE,
    )

    # Limpa repetições bizarras de pontuação (ex: '???!!' -> '?!')
    out = re.sub(r"\?{2,}", "?", out)
    out = re.sub(r"!{2,}", "!", out)

    # Normaliza espaços múltiplos
    out = re.sub(r"[ \t]+", " ", out).strip()

    return out



# ── 1. Transcrição de Áudio (Groq Whisper API ou local) ───────

def _get_niche_instructions(niche_preset: str) -> dict:
    preset = (niche_preset or "general").lower()
    if "emotional" in preset or "ajuda" in preset or "emocao" in preset:
        return {
            "ranking_directive": (
                "DIRETRIZES DE NICHO (AJUDA AO PRÓXIMO / EMOÇÃO / HISTÓRIAS HUMANAS):\n"
                "- Prioridade ABSOLUTA para momentos de maior EMOÇÃO, CHORO, GRATIDÃO, REVELAÇÃO DA AJUDA OU LIÇÃO DE MORAL.\n"
                "- Encontre a cena em que a pessoa humilde é surpreendida, a entrega do gesto de caridade, ou ensinamentos comoventes.\n"
                "- Momentos de comoção, lágrimas e superação recebem score 9 a 10."
            ),
            "hook_directive": "Frase tocante, reflexiva ou de choque empático em CAIXA ALTA (ex: 'ISSO ME EMOCIONOU 🥺', 'VEJA O QUE ELE FEZ ❤️', 'NÃO SEGUREI O CHORO 😭', 'ELE NÃO ESPERAVA ISSO 🙏').",
            "title_directive": "Título comovente e humanizado sobre a história de ajuda ou lição de vida (máx 60 caracteres).",
            "caption_directive": "Legenda comovente contando o contexto do gesto, mensagem de fé/solidariedade, convite para seguir e hashtags (#ajuda #fazerobem #solidariedade #reflexao #emocionante).",
            "default_hook": "ISSO ME EMOCIONOU 🥺",
            "default_title": "Um Gesto que Toca a Alma #Shorts",
            "default_caption": (
                "Um gesto simples que transformou o dia de quem mais precisava. ❤️🙏\n\n"
                "O bem que a gente faz sempre volta. Que essa atitude inspire o seu dia.\n\n"
                "Você faria o mesmo no lugar dele? Comente aqui 👇\n\n"
                "#ajuda #fazerobem #solidariedade #reflexao #emocionante #shorts"
            ),
        }
    elif "debate" in preset or "podcast" in preset or "futebol" in preset or "polemica" in preset:
        return {
            "ranking_directive": (
                "DIRETRIZES DE NICHO (PODCASTS / FUTEBOL / DEBATE POLÊMICO):\n"
                "- Prioridade ABSOLUTA para momentos de CONFRONTO, OPINIÕES POLÊMICAS, DISCUSSÕES ACALORADAS OU REVELAÇÕES DE BASTIDORES.\n"
                "- Encontre discordâncias fortes sobre futebol/jogadores/técnicos, declarações contundentes de convidados ou opiniões que dividem o público.\n"
                "- Frases de efeito, ironia, momentos cômicos marcantes ou verdades duras recebem score 9 a 10."
            ),
            "hook_directive": "Frase polêmica, provocativa ou com revelação explosiva em CAIXA ALTA (ex: 'FALOU A VERDADE! 🔥', 'CONCORDA COM ELE? 😱', 'ELE NÃO ALIVIOU! 👀', 'ABSURDO O QUE ELE DISSE 💥').",
            "title_directive": "Título curto, magnético e provocativo sobre a polêmica, clube ou convidado (máx 60 caracteres).",
            "caption_directive": "Legenda provocando discussão ('Quem tem razão?', 'Concorda ou discorda?'), breve resumo da opinião e hashtags (#futebol #debate #polemica #cortesdepodcast #futebolbrasileiro).",
            "default_hook": "FALOU A VERDADE! 🔥",
            "default_title": "Debate Quente no Podcast #Shorts",
            "default_caption": (
                "Essa opinião deu o que falar! Você concorda ou acha exagero? 🔥⚽\n\n"
                "Deixe sua opinião nos comentários: quem está certo nessa discussão? 👇\n\n"
                "#futebol #debate #polemica #cortesdepodcast #futebolbrasileiro #shorts"
            ),
        }
    else:
        return {
            "ranking_directive": (
                "DIRETRIZES DE NICHO (GERAL / VIRAL / ENTRETENIMENTO):\n"
                "- Prioridade para o momento mais surpreendente, clímax de história, ensinamento valioso ou curiosidade de alta retenção."
            ),
            "hook_directive": "Frase curta provocando curiosidade irresistível ou quebra de padrão em CAIXA ALTA (ex: 'NUNCA FAÇA ISSO!', 'O SEGREDO REVELADO 👀', 'ISSO MUDA TUDO!').",
            "title_directive": "Título chamativo curto para Shorts (máx 60 caracteres) sobre o conteúdo ou história real do clipe.",
            "caption_directive": "Legenda completa com gancho, 2 frases de valor, CTA provocando comentários e 5 hashtags.",
            "default_hook": "PRESTE ATENÇÃO NISSO! 👀",
            "default_title": "Clipe que Vale a Pena #Shorts",
            "default_caption": (
                "Preste atenção nisso até o final... 👀\n\n"
                "Uma reflexão que vale a pena levar para a vida.\n\n"
                "Você concorda com essa visão? Deixe sua opinião nos comentários 👇\n\n"
                "#cortes #reflexao #shorts #reels #viral #sabedoria"
            ),
        }

def _extract_audio_for_transcription(video_path: str, temp_dir: Path) -> Path:
    """Extrai áudio comprimido do vídeo para envio leve à API."""
    import subprocess
    audio_path = temp_dir / "audio_extract.mp3"
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "libmp3lame", "-b:a", "48k", "-ar", "16000", "-ac", "1",
        str(audio_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao extrair áudio: {res.stderr}")
    return audio_path


def transcribe_groq(video_path: str) -> list[dict]:
    """Transcreve via Groq Whisper API (whisper-large-v3-turbo) com word timestamps explícitos."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_file = _extract_audio_for_transcription(video_path, Path(tmpdir))

        with open(audio_file, "rb") as f:
            audio_bytes = f.read()

        files = [
            ("file", ("audio.mp3", audio_bytes, "audio/mpeg")),
            ("model", (None, "whisper-large-v3-turbo")),
            ("response_format", (None, "verbose_json")),
            ("temperature", (None, "0.0")),
            ("timestamp_granularities[]", (None, "word")),
            ("timestamp_granularities[]", (None, "segment")),
        ]
        response = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            files=files,
            timeout=120,
        )
        response.raise_for_status()
        res_data = response.json()

    segments = res_data.get("segments") or []
    words = res_data.get("words") or []

    # Se a API retornou words mas nenhum segment, agrupa words em segmentos
    if not segments and words:
        curr_words = []
        for w in words:
            if curr_words and (float(w.get("start", 0)) - float(curr_words[-1].get("end", 0)) > 0.6 or len(curr_words) >= 8):
                segments.append({
                    "start": float(curr_words[0].get("start", 0)),
                    "end": float(curr_words[-1].get("end", 0)),
                    "text": " ".join(cw.get("word", "") for cw in curr_words).strip(),
                    "words": curr_words,
                })
                curr_words = []
            curr_words.append(w)
        if curr_words:
            segments.append({
                "start": float(curr_words[0].get("start", 0)),
                "end": float(curr_words[-1].get("end", 0)),
                "text": " ".join(cw.get("word", "") for cw in curr_words).strip(),
                "words": curr_words,
            })

    # Se ainda estiver vazio mas houver texto global
    if not segments and res_data.get("text"):
        segments = [{
            "start": 0.0,
            "end": float(res_data.get("duration", 60.0) or 60.0),
            "text": res_data.get("text", "").strip(),
            "words": words,
        }]

    out = []
    for s in segments:
        seg_item = {
            "start": float(s["start"]),
            "end": float(s["end"]),
            "text": s.get("text", "").strip(),
        }
        if "words" in s and s["words"]:
            seg_item["words"] = s["words"]
        elif words:
            seg_words = [
                w for w in words
                if float(w.get("start", 0)) >= seg_item["start"] - 0.05
                and float(w.get("end", 0)) <= seg_item["end"] + 0.05
            ]
            if seg_words:
                seg_item["words"] = seg_words
        out.append(seg_item)

    return out


def _vtt_time_to_seconds(ts: str) -> float:
    """Converte formato VTT (00:01.230 ou 01:20:00.500) para segundos float."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:
            return float(parts[0])
    except Exception:
        pass
    return 0.0


def _parse_vtt_to_segments(vtt_text: str) -> list[dict]:
    """Converte legenda WebVTT do Cloudflare Whisper em lista estruturada de segmentos."""
    if not vtt_text:
        return []
    blocks = re.split(r"\n\s*\n", vtt_text.strip())
    segments = []
    time_pattern = re.compile(r"(\d+(?::\d+)?(?::\d+)?[\.,]\d+)\s*-->\s*(\d+(?::\d+)?(?::\d+)?[\.,]\d+)")

    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        for idx, line in enumerate(lines):
            match = time_pattern.search(line)
            if match:
                start_sec = _vtt_time_to_seconds(match.group(1))
                end_sec = _vtt_time_to_seconds(match.group(2))
                text = " ".join(lines[idx + 1:])
                if text:
                    segments.append({
                        "start": round(start_sec, 2),
                        "end": round(end_sec, 2),
                        "text": text,
                    })
                break
    return segments


def transcribe_cloudflare(video_path: str) -> list[dict]:
    """Transcreve via Cloudflare Workers AI Whisper (@cf/openai/whisper-large-v3-turbo)."""
    if not settings.CLOUDFLARE_ACCOUNT_ID or not settings.CLOUDFLARE_API_TOKEN:
        raise ValueError("Cloudflare Workers AI não configurado.")

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_file = _extract_audio_for_transcription(video_path, Path(tmpdir))
        with open(audio_file, "rb") as f:
            audio_bytes = f.read()

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/openai/whisper-large-v3-turbo"
    )
    headers = {
        "Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/octet-stream",
    }
    response = httpx.post(url, headers=headers, content=audio_bytes, timeout=120)
    response.raise_for_status()
    res = response.json()
    result = res.get("result", {})

    vtt = result.get("vtt", "")
    segments = _parse_vtt_to_segments(vtt)
    if not segments and result.get("text"):
        segments = [{"start": 0.0, "end": 60.0, "text": result.get("text", "")}]
    return segments


def transcribe_local(video_path: str) -> list[dict]:
    """
    Fallback local:
    1. Tenta faster-whisper (CTranslate2 int8) com modelo configurado (large-v3-turbo),
       word timestamps e Silero VAD integrado para evitar alucinações.
    2. Fallback para faster-whisper base se faltar memória.
    3. Fallback para whisper PyTorch padrão.
    """
    model_name = getattr(settings, "WHISPER_MODEL", "large-v3-turbo") or "large-v3-turbo"
    for candidate in [model_name, "base"]:
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(candidate, device="cpu", compute_type="int8")
            segments_iter, _ = model.transcribe(
                video_path,
                beam_size=1,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400),
            )
            segments = []
            for s in segments_iter:
                seg_dict = {
                    "start": float(s.start),
                    "end": float(s.end),
                    "text": s.text.strip(),
                }
                if getattr(s, "words", None):
                    seg_dict["words"] = [
                        {"word": w.word, "start": float(w.start), "end": float(w.end)}
                        for w in s.words
                    ]
                segments.append(seg_dict)
            del model
            if segments:
                return segments
        except Exception:
            continue

    # 3. Fallback para whisper PyTorch original
    try:
        import whisper
        import torch

        model = whisper.load_model("base")
        result = model.transcribe(video_path, verbose=False)
        segments = result.get("segments", [])

        # Libera RAM imediatamente
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]} for s in segments]
    except Exception:
        return []


def transcribe_video(video_path: str) -> list[dict]:
    """
    Ponto de entrada de transcrição:
    1. Groq Whisper (rápido, tier grátis)
    2. Cloudflare Workers AI Whisper (10k neurônios/dia grátis)
    3. Whisper local (fallback offline)
    """
    import structlog
    log = structlog.get_logger()

    if settings.GROQ_API_KEY:
        try:
            return transcribe_groq(video_path)
        except Exception as e:
            log.warning("pipeline.transcribe_groq.failed", error=str(e))

    if settings.CLOUDFLARE_ACCOUNT_ID and settings.CLOUDFLARE_API_TOKEN:
        try:
            log.info("pipeline.transcribe_cloudflare.start")
            return transcribe_cloudflare(video_path)
        except Exception as e:
            log.warning("pipeline.transcribe_cloudflare.failed", error=str(e))

    return transcribe_local(video_path)


def _call_gemini_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Chama a API do Google Gemini (Google AI Studio) com modo JSON estruturado."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurada.")

    model = getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_prompt}\n\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    resp = httpx.post(url, json=payload, timeout=35)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError(f"Resposta vazia da API do Gemini: {data}")
    return candidates[0]["content"]["parts"][0]["text"]


def _call_groq_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY não configurada.")
    model_name = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")
    fallback_model = getattr(settings, "GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            json={
                "model": fallback_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _call_cerebras_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    cerebras_key = getattr(settings, "CEREBRAS_API_KEY", "")
    if not cerebras_key:
        raise ValueError("CEREBRAS_API_KEY não configurada.")
    model = getattr(settings, "CEREBRAS_MODEL", "llama3.1-8b") or "llama3.1-8b"
    r = httpx.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {cerebras_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_openrouter_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "")
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY não configurada.")
    model = getattr(settings, "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free") or "meta-llama/llama-3.3-70b-instruct:free"
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {openrouter_key}",
            "HTTP-Referer": "https://videoflow.local",
            "X-Title": "VideoFlow",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_openai_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY não configurada.")
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_ollama_json(system_prompt: str, user_prompt: str) -> str:
    if not settings.OLLAMA_BASE_URL:
        raise ValueError("OLLAMA_BASE_URL não configurada.")
    r = httpx.post(
        f"{settings.OLLAMA_BASE_URL}/api/generate",
        json={"model": settings.OLLAMA_MODEL, "prompt": f"{system_prompt}\n{user_prompt}", "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["response"]


def _call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """
    Executa cascata completa de provedores LLM:
    1. Google Gemini
    2. Groq
    3. Cerebras AI
    4. OpenRouter (:free)
    5. OpenAI
    6. Ollama
    """
    import structlog
    log = structlog.get_logger()

    providers = [
        ("gemini", lambda: _call_gemini_json(system_prompt, user_prompt, temperature)),
        ("groq", lambda: _call_groq_json(system_prompt, user_prompt, temperature)),
        ("cerebras", lambda: _call_cerebras_json(system_prompt, user_prompt, temperature)),
        ("openrouter", lambda: _call_openrouter_json(system_prompt, user_prompt, temperature)),
        ("openai", lambda: _call_openai_json(system_prompt, user_prompt, temperature)),
        ("ollama", lambda: _call_ollama_json(system_prompt, user_prompt)),
    ]

    for name, caller in providers:
        try:
            res = caller()
            if res and res.strip():
                return res
        except Exception as e:
            if "não configurad" not in str(e).lower():
                log.warning("llm_cascade.failed", provider=name, error=str(e)[:150])

    raise RuntimeError("Nenhum provedor de LLM configurado ou disponível (GEMINI, GROQ, CEREBRAS, OPENROUTER, OPENAI ou OLLAMA).")


def rank_segments_gemini_multimodal(video_path: str, max_duration: int = 60, max_clips: int = 3, niche_preset: str = "general") -> list[dict] | None:
    """
    Ranking multimodal: analisa entonação, energia e clímax ouvindo o áudio diretamente
    através do Google Gemini com base64 inlineData (para áudios de até 20MB).
    """
    if not settings.GEMINI_API_KEY:
        return None

    import base64
    import tempfile
    import structlog
    log = structlog.get_logger()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = _extract_audio_for_transcription(video_path, Path(tmpdir))
            if not audio_file.exists() or audio_file.stat().st_size > 20 * 1024 * 1024:
                return None
            with open(audio_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        target_dur = int(max_duration or 60)
        min_dur = 30 if target_dur <= 60 else max(30, int(target_dur * 0.5))

        if max_clips == 0:
            qty_instruction = (
                "Encontre TODOS os momentos contínuos de CLÍMAX e alto potencial viral contidos no vídeo "
                f"(com duração entre {min_dur} e {target_dur} segundos cada, geralmente de 2 a 8 momentos de destaque). "
                "Retorne todos os que tiverem conteúdo relevante com score de 7 a 10."
            )
        else:
            n_target = max(max_clips, 2)
            qty_instruction = f"Encontre os {n_target} melhores momentos contínuos de CLÍMAX com duração aproximada entre {min_dur} e {target_dur} segundos."

        niche_info = _get_niche_instructions(niche_preset)

        prompt_text = (
            f"Você é um Diretor Especialista em Vídeos Curtos Virais (TikTok, Reels, Shorts).\n"
            f"Ouça o áudio completo anexado prestando atenção em tom de voz, risadas, entusiasmo, quebra de expectativa e momentos de ouro.\n\n"
            f"{niche_info['ranking_directive']}\n\n"
            f"REGRAS:\n"
            f"1. {qty_instruction}\n"
            f"2. NUNCA selecione trechos de patrocínio, anúncios comerciais, saudações iniciais, despedidas ou momentos com músicas comerciais em primeiro plano (alto risco de Content ID).\n"
            f"3. Responda EXCLUSIVAMENTE em formato JSON: {{\"best\": [{{\"start\": 120.0, \"end\": {120.0 + float(target_dur)}, \"score\": 10}}]}}"
        )

        model = getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/mp3",
                                "data": audio_b64,
                            }
                        },
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        resp = httpx.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        start_pos = raw.find("{")
        end_pos = raw.rfind("}") + 1
        if start_pos != -1 and end_pos > start_pos:
            data = json.loads(raw[start_pos:end_pos])
            best = data.get("best", [])
            if best:
                log.info("pipeline.gemini_multimodal.success", clips_found=len(best))
                return [
                    {
                        "start": round(float(c.get("start", 0)), 1),
                        "end": round(float(c.get("end", target_dur)), 1),
                        "score": round(float(c.get("score", 10)), 1),
                    }
                    for c in best
                ]
    except Exception as e:
        log.warning("pipeline.gemini_multimodal.fallback", error=str(e)[:150])

    return None


# ── 2. Ranking de segmentos com LLM ──────────────────────────

SPONSOR_KEYWORDS = {
    "cupom", "desconto", "patrocinador", "patrocina", "apoiador", "parceiro de hoje",
    "baixe o app", "baixe o aplicativo", "link na descrição", "use o código", "use o cupom",
    "gringo", "blaze", "betano", "1xbet", "nordvpn", "manual", "insiders", "promocode",
    "cadastre-se", "primeiro depósito", "cashback", "aposte", "link fixado", "merchandising",
    "meu patrocinador", "nosso patrocinador", "apoio desse vídeo", "apoio deste vídeo",
}


def _has_heavy_sponsor(text: str) -> bool:
    t = text.lower()
    matches = sum(1 for kw in SPONSOR_KEYWORDS if kw in t)
    return matches >= 1


def rank_segments_ai(segments: list[dict], max_duration: int = 60, max_clips: int = 3, niche_preset: str = "general") -> list[dict]:
    """Envia transcrição para LLM (Gemini, Groq, Cerebras, OpenRouter, OpenAI ou Ollama) e retorna segmentos rankeados."""
    target_dur = int(max_duration or 60)
    min_dur = 30 if target_dur <= 60 else max(30, int(target_dur * 0.5))

    text = "\n".join(
        f"[{s['start']:.1f}s-{s['end']:.1f}s]: {s['text']}" for s in segments
    )

    if max_clips == 0:
        qty_instruction = (
            "Encontre TODOS os momentos contínuos de CLÍMAX e alto potencial viral contidos no vídeo "
            f"(com duração entre {min_dur} e {target_dur} segundos cada, geralmente de 2 a 8 momentos de destaque). "
            "Retorne todos os que tiverem conteúdo relevante com score de 7 a 10."
        )
    else:
        n_target = max(max_clips, 2)
        qty_instruction = f"Encontre os {n_target} melhores momentos contínuos com duração aproximada entre {min_dur} e {target_dur} segundos."

    niche_info = _get_niche_instructions(niche_preset)

    system_prompt = (
        "Você é um Diretor e Editor Especialista em Cortes Virais de Alta Retenção para TikTok, Reels e Shorts.\n"
        "Sua missão é encontrar o momento MAIS VALIOSO, IMPACTANTE E RELEVANTE do vídeo sobre o conteúdo real discutido.\n\n"
        f"{niche_info['ranking_directive']}\n\n"
        "REGRAS ESTRITAS DE EXCLUSÃO (PROIBIDO SELECIONAR):\n"
        "1. PROIBIDO JABÁ / PATROCÍNIO / PROPAGANDA: NUNCA selecione trechos onde o criador fala de patrocinadores, "
        "marcas, aplicativos (ex: Gringo, apostas, bancos, cursos), cupons de desconto, 'link na descrição', 'compre agora' "
        "ou comerciais pagos. Isso NÃO É MELHOR MOMENTO e arruína a audiência.\n"
        "2. PROIBIDO INTRODUÇÕES E VINHETAS: NUNCA selecione saudações iniciais ('fala galera', 'seja bem-vindo'), "
        "apresentações formais de convidados ou pedidos de like/inscrição ('deixe seu like', 'se inscreva no canal').\n"
        "3. PROIBIDO ENCERRAMENTOS: NUNCA selecione despedidas, agradecimentos finais ou créditos.\n"
        "4. PROIBIDO MÚSICAS PROTEGIDAS / TRECHOS MUSICAIS: NUNCA selecione trechos onde toca música comercial de fundo ou cantoria protegida por direitos autorais (alto risco de Content ID).\n\n"
        "CRITÉRIOS OBRIGATÓRIOS DO MELHOR MOMENTO:\n"
        "- Deve ser o CLÍMAX do vídeo: uma revelação surpreendente, história inacreditável, insight poderoso, debate acalorado, "
        "momento muito engraçado ou ensinamento marcante sobre o TEMA PRINCIPAL do vídeo.\n"
        f"- O trecho contínuo deve ter duração aproximada entre {min_dur} e {target_dur} segundos.\n"
        "- Deve ter sentido completo: o espectador precisa entender o contexto e a conclusão sem ficar perdido.\n\n"
        "Responda EXCLUSIVAMENTE em formato JSON."
    )
    user_prompt = (
        f"Analise a transcrição abaixo e encontre os melhores trechos contínuos de conteúdo real ({qty_instruction}).\n"
        f"DURAÇÃO ALVO: entre {min_dur} e {target_dur} segundos por clipe.\n"
        "Lembre-se: IGNORE completamente qualquer publicidade, anúncio ou patrocínio comercial!\n"
        f"Responda no formato exato: {{\"best\": [{{\"start\": 120.0, \"end\": {120.0 + float(target_dur)}, \"score\": 10}}]}}\n\n"
        f"Transcrição:\n{text[:60000]}"
    )

    raw = _call_llm_json(system_prompt, user_prompt, temperature=0.2)

    # Extrai JSON da resposta
    start_pos = raw.find("{")
    end_pos = raw.rfind("}") + 1
    if start_pos == -1 or end_pos <= start_pos:
        raise ValueError(f"Resposta da IA nao contem JSON valido: {raw}")

    data = json.loads(raw[start_pos:end_pos])
    raw_clips = data.get("best", [])

    total_video_dur = float(segments[-1]["end"]) if segments else 0.0
    processed_clips = []
    target_dur = float(max_duration or 60)

    for item in raw_clips:
        s = float(item.get("start", 0.0))
        e = float(item.get("end", s + target_dur))

        # Garante que o corte tenha pelo menos target_dur segundos
        if (e - s) < (target_dur * 0.75):
            mid = (s + e) / 2.0
            s = max(0.0, mid - (target_dur / 2.0))
            e = s + target_dur

        if total_video_dur > 0 and e > total_video_dur:
            e = total_video_dur
            s = max(0.0, e - target_dur)

        # Verifica se o trecho contém patrocínio pesado
        clip_segs = [seg for seg in segments if seg["end"] > s and seg["start"] < e]
        clip_speech = " ".join(seg.get("text", "") for seg in clip_segs)
        score = float(item.get("score", 8))
        if _has_heavy_sponsor(clip_speech):
            score -= 10.0  # Penaliza severamente para descartar trecho comercial

        # Detecção de risco de música comercial / Content ID
        try:
            from services.audio_manager import detect_music_risk
            if detect_music_risk(clip_segs):
                score -= 8.0  # Penaliza trechos musicais com alto risco de copyright
        except Exception:
            pass

        processed_clips.append({
            "start": round(s, 1),
            "end": round(e, 1),
            "score": round(score, 1),
        })

    return sorted(processed_clips, key=lambda x: x["score"], reverse=True)


def rank_segments_ollama(segments: list[dict], max_duration: int = 60) -> list[dict]:
    """Compatibilidade reversa: repassa para rank_segments_ai."""
    return rank_segments_ai(segments, max_duration=max_duration)


# ── 3. Fallback: energia de áudio com librosa (sem LLM) ───────

def find_highlights_by_energy(video_path: str, clip_duration: int = 60) -> list[dict]:
    """
    Detecta picos de energia de áudio e extrai corte de clip_duration segundos.
    Não requer Whisper nem LLM — fallback seguro garantindo duração completa.
    """
    import librosa
    import numpy as np

    clip_dur = float(clip_duration or 60)
    y, sr = librosa.load(video_path, mono=True, duration=720)
    total_dur = len(y) / sr

    # Janelas de 5 segundos para achar o pico
    window = sr * 5
    if len(y) < window:
        return [{"start": 0.0, "end": total_dur, "score": 10.0}]

    energy = np.array([
        float(np.sum(np.abs(y[i: i + window]) ** 2))
        for i in range(0, len(y) - window, window)
    ])

    best_win = int(np.argmax(energy))
    peak_time = best_win * 5.0

    # Centraliza o corte de clip_dur segundos no pico
    start = max(0.0, peak_time - (clip_dur / 2.0))
    end = min(total_dur, start + clip_dur)
    if end - start < clip_dur and start > 0:
        start = max(0.0, end - clip_dur)

    return [{"start": round(start, 1), "end": round(end, 1), "score": 10.0}]


def generate_viral_copy(transcript_text: str, niche_preset: str = "general") -> dict:
    """
    Gera hook visual de 5s, copy/legenda e título de alta retenção para TikTok, Reels e Shorts
    usando LLM com base no áudio transcrito e no nicho selecionado.
    """
    niche_info = _get_niche_instructions(niche_preset)
    default_res = {
        "hook": niche_info["default_hook"],
        "title": niche_info["default_title"],
        "caption": niche_info["default_caption"],
    }

    if not (settings.GEMINI_API_KEY or settings.GROQ_API_KEY) or not transcript_text.strip():
        return default_res

    system_prompt = (
        "Você é um Copywriter Especialista em Vídeos Curtos Virais e Retenção (TikTok, Reels, Shorts).\n"
        "Sua missão é criar um gancho visual de retenção (hook), título e legenda magnética em português do Brasil (PT-BR).\n\n"
        f"{PT_BR_LANGUAGE_RULES}\n\n"
        "Regras dos Campos:\n"
        f"1. 'hook': {niche_info['hook_directive']} NUNCA use nomes de patrocinadores no gancho.\n"
        f"2. 'title': {niche_info['title_directive']}\n"
        f"3. 'caption': {niche_info['caption_directive']}\n\n"
        "Retorne APENAS um JSON válido no formato:\n"
        "{\n"
        "  \"hook\": \"FRASE EM CAIXA ALTA (MÁX 6 PALAVRAS)\",\n"
        "  \"title\": \"Título curto\",\n"
        "  \"caption\": \"Legenda com quebras e hashtags\"\n"
        "}"
    )

    user_prompt = f"Crie a copy viral para o seguinte trecho falado:\n\n{transcript_text[:4000]}"

    try:
        data = _call_llm_json(system_prompt, user_prompt, temperature=0.4)
        start_pos = data.find("{")
        end_pos = data.rfind("}") + 1
        if start_pos != -1 and end_pos > start_pos:
            res = json.loads(data[start_pos:end_pos])
            return {
                "hook": sanitize_ptbr_text(res.get("hook", default_res["hook"])).strip().upper(),
                "title": sanitize_ptbr_text(res.get("title", default_res["title"])).strip(),
                "caption": sanitize_ptbr_text(res.get("caption", default_res["caption"])).strip(),
            }
        return default_res
    except Exception as e:
        structlog.get_logger().warning("ai_analyzer.viral_copy.failed", error=str(e)[:150])
        return default_res


def generate_hook_text(transcript_text: str, niche_preset: str = "general") -> str:
    """Gera um gancho de retenção em caixa alta para os primeiros 5 segundos do vídeo."""
    res = generate_viral_copy(transcript_text, niche_preset=niche_preset)
    return res.get("hook", "PRESTE ATENÇÃO NISSO! 👀")


def generate_part_copy(transcript_text: str, part_num: int, total_parts: int | None = None, niche_preset: str = "general") -> dict:
    """
    Gera gancho contextual específico, título e legenda para uma parte sequencial conforme o nicho.
    """
    import structlog
    niche_info = _get_niche_instructions(niche_preset)
    part_label = f"PARTE {part_num}" + (f" DE {total_parts}" if total_parts else "")
    default_res = {
        "hook": f"{part_label} 🔥",
        "title": f"Cortes - {part_label} #Shorts",
        "caption": (
            f"{part_label} 🎬🔥\n\n"
            f"Assista com atenção e siga para não perder a sequência!\n\n"
            f"#cortes #viral #shorts #reels #tiktok #parte{part_num}"
        ),
    }

    if not transcript_text.strip():
        return default_res

    system_prompt = (
        "Você é um Copywriter Especialista em Vídeos Curtos Virais e Retenção (TikTok, Reels, Shorts).\n"
        f"Você está criando o gancho e a copy para a {part_label} de uma série de vídeos.\n\n"
        f"{PT_BR_LANGUAGE_RULES}\n\n"
        f"Estilo do nicho selecionado:\n- Hook: {niche_info['hook_directive']}\n- Legenda: {niche_info['caption_directive']}\n\n"
        "Regras dos Campos:\n"
        "1. 'hook': Frase curta de 3 a 5 palavras em CAIXA ALTA destacando a tensão ou assunto principal deste trecho específico "
        f"(ex: 'ISSO NINGUÉM ESPERAVA 👀', 'O ERRO QUE ELE COMETEU 😱'). Pode terminar com | {part_label}.\n"
        f"2. 'title': Título curto e magnético indicando a parte (ex: 'O Momento Decisivo ({part_label}) #Shorts').\n"
        "3. 'caption': Legenda envolvente resumindo este trecho, CTA para curtir/comentar e 5 hashtags relevantes ao tema.\n\n"
        "Retorne APENAS um JSON válido no formato:\n"
        "{\n"
        "  \"hook\": \"FRASE EM CAIXA ALTA (3 A 5 PALAVRAS)\",\n"
        "  \"title\": \"Título curto\",\n"
        "  \"caption\": \"Legenda completa\"\n"
        "}"
    )

    user_prompt = f"Crie a copy para a {part_label} com base neste trecho:\n\n{transcript_text[:3000]}"

    try:
        data = _call_llm_json(system_prompt, user_prompt, temperature=0.4)
        start_pos = data.find("{")
        end_pos = data.rfind("}") + 1
        if start_pos != -1 and end_pos > start_pos:
            res = json.loads(data[start_pos:end_pos])
            return {
                "hook": sanitize_ptbr_text(res.get("hook", default_res["hook"])).strip().upper(),
                "title": sanitize_ptbr_text(res.get("title", default_res["title"])).strip(),
                "caption": sanitize_ptbr_text(res.get("caption", default_res["caption"])).strip(),
            }
        return default_res
    except Exception as e:
        structlog.get_logger().warning("ai_analyzer.part_copy.failed", part=part_num, error=str(e)[:150])
        return default_res



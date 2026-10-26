import re
import json
import httpx
import subprocess
from datetime import datetime
from pathlib import Path
import structlog

import sys
import shutil

from config import settings
from sqlalchemy import select
from models.database import AuthorizedChannel

logger = structlog.get_logger("downloader")

TMP = Path(settings.VIDEO_TMP_DIR)
TMP.mkdir(parents=True, exist_ok=True)


def probe_youtube_metadata(url: str) -> dict:
    """
    Extrai metadados do vídeo do YouTube (canal, data de upload, título) sem fazer download.
    Rápido (1-2s), usado para validação preventiva de whitelist e carência.
    """
    _validate_youtube_url(url)
    ytdlp_bin = shutil.which("yt-dlp")
    base_cmd = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]
    cmd = base_cmd + [
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout", "15",
    ]

    for c_path in [Path("/app/cookies.txt"), Path("cookies.txt")]:
        try:
            if c_path.exists() and c_path.stat().st_size > 0:
                cmd.extend(["--cookies", str(c_path)])
                break
        except (PermissionError, OSError):
            continue

    cmd.extend(["--", url.strip()])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(proc.stdout)
        uploader_id = data.get("uploader_id") or ""
        handle = uploader_id if uploader_id.startswith("@") else (f"@{uploader_id}" if uploader_id else "")
        return {
            "channel_id": data.get("channel_id") or uploader_id or "",
            "channel_name": data.get("channel") or data.get("uploader") or "Canal Desconhecido",
            "channel_handle": handle or f"@{data.get('uploader', 'criador')}",
            "channel_url": data.get("channel_url") or data.get("uploader_url") or "",
            "upload_date": data.get("upload_date"), # formato YYYYMMDD
            "timestamp": data.get("timestamp"),     # epoch seconds
            "title": data.get("title") or "",
            "duration": data.get("duration") or 0,
        }
    except Exception as e:
        logger.warning("downloader.probe_failed", error=str(e), url=url)
        raise RuntimeError(f"Não foi possível obter informações do vídeo/canal no YouTube: {str(e)[:180]}")


async def check_channel_authorization(metadata: dict, session) -> tuple[bool, str | None, AuthorizedChannel | None]:
    """
    Verifica se o canal de origem está na Whitelist de canais autorizados e se respeita a carência.
    """
    channel_id = (metadata.get("channel_id") or "").strip()
    channel_handle = (metadata.get("channel_handle") or "").strip().lower()
    channel_name = (metadata.get("channel_name") or "").strip().lower()

    query = select(AuthorizedChannel).where(AuthorizedChannel.is_active == True)
    result = await session.execute(query)
    channels = result.scalars().all()

    matched_channel = None
    for ch in channels:
        if ch.channel_id and ch.channel_id.strip() == channel_id:
            matched_channel = ch
            break
        ch_handle = (ch.handle or "").strip().lower()
        if ch_handle and (ch_handle == channel_handle or ch_handle.lstrip("@") == channel_handle.lstrip("@")):
            matched_channel = ch
            break
        if ch.name and ch.name.strip().lower() == channel_name:
            matched_channel = ch
            break

    if not matched_channel:
        err_msg = (
            f"O canal '{metadata.get('channel_name')}' ({metadata.get('channel_handle')}) não está cadastrado "
            "na Whitelist de canais autorizados. Adicione o canal na aba 'Canais Autorizados' para liberar cortes com segurança."
        )
        return False, err_msg, None

    # Validação de carência (Grace period)
    min_delay = matched_channel.min_delay_hours or 0
    if min_delay > 0:
        now = datetime.utcnow()
        timestamp = metadata.get("timestamp")
        upload_date_str = metadata.get("upload_date")
        if timestamp:
            upload_dt = datetime.utcfromtimestamp(timestamp)
            diff_hours = (now - upload_dt).total_seconds() / 3600.0
            if diff_hours < min_delay:
                hours_left = max(0.1, round(min_delay - diff_hours, 1))
                return False, f"Período de carência ativo para '{matched_channel.name}': este vídeo foi publicado recentemente. É necessário aguardar mais {hours_left}h para respeitar o criador original antes de gerar cortes.", matched_channel
        elif upload_date_str and len(str(upload_date_str)) == 8:
            try:
                upload_dt = datetime.strptime(str(upload_date_str), "%Y%m%d")
                diff_hours = (now - upload_dt).total_seconds() / 3600.0
                if diff_hours < min_delay:
                    return False, f"Período de carência ativo para '{matched_channel.name}': aguarde {min_delay}h após o upload original para publicar cortes.", matched_channel
            except Exception:
                pass

    return True, None, matched_channel


def _has_oauth2_cache() -> bool:
    for d in [Path.home() / ".cache" / "yt-dlp", Path("/home/appuser/.cache/yt-dlp")]:
        try:
            if (d / "youtube-oauth2").exists():
                return True
        except (PermissionError, OSError):
            continue
    return False


def _validate_youtube_url(url: str):
    clean = url.strip()
    if not re.match(r"^https?://([a-zA-Z0-9-]+\.)?(youtube\.com|youtu\.be)/.+", clean, re.IGNORECASE):
        raise ValueError("URL do YouTube inválida. Forneça um link válido de vídeo do YouTube.")


def _download_cobalt(url: str, job_id: str) -> Path | None:
    """Tenta baixar o vídeo via Cobalt API (evita restrições/bloqueios de IP do YouTube)."""
    cobalt_endpoint = getattr(settings, "COBALT_API_URL", None)
    if not cobalt_endpoint:
        return None

    api_url = cobalt_endpoint.rstrip("/")
    payload = {
        "url": url.strip(),
        "videoQuality": "1080",
        "downloadMode": "auto",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.post(api_url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                stream_url = data.get("url")
                if stream_url:
                    output = TMP / f"{job_id}.mp4"
                    with client.stream("GET", stream_url) as stream_resp:
                        if stream_resp.status_code == 200:
                            with open(output, "wb") as f:
                                for chunk in stream_resp.iter_bytes(chunk_size=1024 * 1024):
                                    f.write(chunk)
                            if output.exists() and output.stat().st_size > 50_000:
                                return output
                            output.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def download_youtube(url: str, job_id: str) -> Path:
    _validate_youtube_url(url)

    # 1. Tenta baixar via Cobalt se configurado (zero bloqueio de IP de datacenter)
    cobalt_file = _download_cobalt(url, job_id)
    if cobalt_file:
        return cobalt_file

    # 2. Fallback para yt-dlp local
    output = TMP / f"{job_id}.%(ext)s"
    ytdlp_bin = shutil.which("yt-dlp")
    base_cmd = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]
    cmd = base_cmd + [
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--output", str(output),
        "--no-playlist",
        "--socket-timeout", "30",
    ]

    # 1. Verifica se há autenticação OAuth2 salva no cache do appuser
    if _has_oauth2_cache():
        cmd.extend(["--username", "oauth2"])

    # 2. Suporte a cookies se fornecido (cookies.txt na raiz)
    cookies_path = Path("/app/cookies.txt")
    try:
        if cookies_path.exists() and cookies_path.stat().st_size > 0:
            cmd.extend(["--cookies", str(cookies_path)])
    except (PermissionError, OSError):
        pass

    # 3. Suporte a runtime JS (quickjs) para resolução do 'n challenge' do YouTube
    qjs_path = Path("/usr/bin/qjs")
    if qjs_path.exists():
        cmd.extend(["--js-runtimes", f"quickjs:{qjs_path}"])

    # 4. Suporte a PO Token (Proof of Origin) e player_clients para contornar bloqueio de datacenter e SABR
    extractor_args = ["youtube:player_client=web_embedded,web"]
    po_token = getattr(settings, "YTDLP_PO_TOKEN", "")
    if po_token and po_token.strip():
        extractor_args.append(f"youtube:po_token=web+{po_token.strip()}")
    cmd.extend(["--extractor-args", ";".join(extractor_args)])

    # Garante que a URL não seja interpretada como flag
    cmd.extend(["--", url.strip()])
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        raise RuntimeError(f"Falha ao baixar vídeo do YouTube: {err[:350]}")

    # yt-dlp substitui %(ext)s → encontra o arquivo gerado
    matches = list(TMP.glob(f"{job_id}.*"))
    if not matches:
        raise FileNotFoundError(f"yt-dlp não gerou arquivo para job {job_id}")
    return matches[0]



def _extract_gdrive_file_id(source: str) -> str:
    """Extrai file_id de links comuns do Google Drive ou valida a string fornecida."""
    match = re.search(r"(?:/file/d/|id=)([a-zA-Z0-9_-]{10,100})", source)
    if match:
        return match.group(1)
    clean = source.strip()
    if not re.match(r"^[a-zA-Z0-9_-]{10,100}$", clean):
        raise ValueError("ID ou link do Google Drive inválido.")
    return clean


def _download_public_gdrive(file_id: str, output_path: Path) -> bool:
    """Tenta baixar arquivo público do Google Drive diretamente via streaming."""
    download_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    try:
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            with client.stream("GET", download_url) as response:
                if response.status_code != 200:
                    return False
                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)

        # Valida se baixou arquivo de vídeo real e não página HTML de erro
        if output_path.exists() and output_path.stat().st_size > 50_000:
            return True
        output_path.unlink(missing_ok=True)
    except Exception:
        output_path.unlink(missing_ok=True)
    return False


def download_google_drive(source: str, job_id: str) -> Path:
    """
    Baixa vídeo do Google Drive:
    - Suporta URL pública de compartilhamento ou file_id direto.
    - Tenta download público primeiro (zero credenciais necessárias).
    - Fallback para API oficial do Google se configurado.
    """
    file_id = _extract_gdrive_file_id(source)
    output_path = TMP / f"{job_id}.mp4"

    # Tentativa 1: Download público direto via streaming
    if _download_public_gdrive(file_id, output_path):
        return output_path

    # Tentativa 2: Fallback via credenciais da Google API
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        from google.auth import default

        creds, _ = default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        service = build("drive", "v3", credentials=creds)
        request = service.files().get_media(fileId=file_id)

        with open(output_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path
    except Exception as e:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Falha ao baixar do Google Drive (ID: {file_id}). "
            f"Verifique se o link está como 'Qualquer pessoa com o link' ou configure as credenciais: {e}"
        )

    raise FileNotFoundError(f"Não foi possível obter o arquivo {file_id} do Google Drive.")

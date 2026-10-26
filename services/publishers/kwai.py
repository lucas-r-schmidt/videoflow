import structlog

logger = structlog.get_logger()


async def prepare_kwai_upload(job_id: str, file_path: str) -> dict:
    """
    Kwai não possui API pública de publicação.
    Notifica o usuário para upload manual.
    """
    notification = {
        "platform": "kwai",
        "status": "manual_required",
        "file_path": file_path,
        "instructions": (
            "1. Baixe o vídeo pelo caminho acima\n"
            "2. Abra o app Kwai\n"
            "3. Faça upload manualmente"
        ),
    }

    logger.info(
        "kwai.manual_upload_required",
        job_id=job_id,
        file=file_path,
    )

    # TODO: enviar email ou webhook ao usuário com o link de download
    # await send_email(job_id, notification)

    return notification

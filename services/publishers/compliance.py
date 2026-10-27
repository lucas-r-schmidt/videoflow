"""
Serviço central de compliance e créditos para publicadores do VideoFlow.
Garante que todas as publicações automáticas contenham:
1. Marcação da parte (se for série/múltiplas partes)
2. Copy viral / gancho gerado pela IA
3. Crédito claro ao criador original com @handle
4. Link direto para o vídeo/episódio original
5. Identificação de fã-clube não oficial
6. Canal transparente de contato para pedidos de remoção amigável
"""

from typing import Any

try:
    from config import settings
    DEFAULT_TAKEDOWN_CONTACT = getattr(settings, "TAKEDOWN_CONTACT_EMAIL", "clipequevale@gmail.com")
except Exception:
    DEFAULT_TAKEDOWN_CONTACT = "clipequevale@gmail.com"


def format_compliance_caption(
    base_caption: str | None,
    channel_name: str | None = None,
    channel_handle: str | None = None,
    source_url: str | None = None,
    part_index: int | None = None,
    total_parts: int | None = None,
    custom_credit_template: str | None = None,
    contact_email: str | None = None,
) -> str:
    parts = []

    # 1. Indicador de parte
    if part_index:
        part_tag = f"PARTE {part_index}" + (f" de {total_parts}" if total_parts else "") + " 🎬🔥"
        parts.append(part_tag)

    # 2. Corpo principal da legenda
    cleaned_caption = (base_caption or "").strip()
    if cleaned_caption:
        # Evita duplicar a tag de parte se já estiver inclusa no texto
        if part_index and f"PARTE {part_index}" in cleaned_caption:
            parts = [cleaned_caption]
        else:
            parts.append(cleaned_caption)
    else:
        parts.append("Assista até o final! 🎬🔥\n\n#cortes #viral #shorts #reels #tiktok")

    # 3. Rodapé de Crédito e Governança
    footer_lines = ["\n---"]
    
    # Menção ao criador original
    creator_tag = channel_handle or channel_name
    if creator_tag:
        creator_tag = creator_tag.strip()
        if not creator_tag.startswith("@") and not creator_tag.startswith("http"):
            creator_tag = f"@{creator_tag}"
        footer_lines.append(f"🎙️ Conteúdo original por {creator_tag} (Corte Fã-Clube Não Oficial).")

    # Link da fonte completa
    if source_url and source_url.strip():
        footer_lines.append(f"🔗 Assista ao episódio completo: {source_url.strip()}")

    # Contato direto para remoção preventiva
    email = contact_email or DEFAULT_TAKEDOWN_CONTACT
    footer_lines.append(f"📩 Dúvidas de direitos ou solicitação de remoção: {email}")

    compliance_footer = "\n".join(footer_lines)
    parts.append(compliance_footer)

    return "\n\n".join(parts).strip()

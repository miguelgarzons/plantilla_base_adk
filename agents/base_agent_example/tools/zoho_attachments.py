from __future__ import annotations

import logging
import base64
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ZOHO_DESK_BASE = "https://desk.zoho.com/api/v1"
TOKEN_WEBHOOK_URL = "https://n8nfab.cunapp.pro/webhook/GetToken"
TOKEN_WEBHOOK_USER = "FabricaSoftware"
TOKEN_WEBHOOK_PASS = "F4Br1KS0FT#%"

_cached_zoho_token: str | None = None


async def _get_zoho_token() -> str:
    """Obtiene el token de Zoho Desk desde el webhook de n8n."""
    global _cached_zoho_token

    if _cached_zoho_token:
        logger.info("🔐 Zoho token cacheado, reutilizando.")
        return _cached_zoho_token

    logger.info("🔐 Obteniendo Zoho token desde webhook...")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            TOKEN_WEBHOOK_URL,
            auth=(TOKEN_WEBHOOK_USER, TOKEN_WEBHOOK_PASS),
            timeout=15.0,
        )
        logger.info("🔐 Webhook token ← status=%s", response.status_code)
        response.raise_for_status()

        data = response.json()
        logger.info(
            "🔐 Webhook response keys: %s",
            list(data.keys()) if isinstance(data, dict) else type(data),
        )

        # El webhook puede devolver el token en distintas claves
        token = (
            data.get("access_token")
            or data.get("token")
            or data.get("accessToken")
            or data.get("zoho_token")
        )
        if not token:
            raise ValueError(f"No se encontró token en respuesta del webhook: {data}")

        _cached_zoho_token = token
        logger.info("✅ Zoho token obtenido (primeros 20): %s...", token[:20])
        return _cached_zoho_token


def _invalidate_zoho_token() -> None:
    global _cached_zoho_token
    _cached_zoho_token = None


async def get_ticket_attachments(ticket_id: str, org_id: str) -> list[dict]:
    """
    Obtiene todos los archivos adjuntos de un ticket Zoho recorriendo sus threads.

    Returns:
        Lista de dicts con: name, url, content_type (si disponible)
    """
    token = await _get_zoho_token()
    headers = {
        "orgId": org_id,
        "Authorization": f"Zoho-oauthtoken {token}",
    }

    attachments = []

    async with httpx.AsyncClient() as client:
        # 1. Obtener threads del ticket
        threads_url = f"{ZOHO_DESK_BASE}/tickets/{ticket_id}/threads"
        logger.info("📡 GET threads → %s", threads_url)
        resp = await client.get(threads_url, headers=headers, timeout=15.0)

        if resp.status_code == 401:
            logger.warning("Token Zoho expirado, re-autenticando...")
            _invalidate_zoho_token()
            token = await _get_zoho_token()
            headers["Authorization"] = f"Zoho-oauthtoken {token}"
            resp = await client.get(threads_url, headers=headers, timeout=15.0)

        resp.raise_for_status()
        threads = resp.json().get("data", [])
        logger.info("📡 Threads encontrados: %d", len(threads))

        # 2. Recorrer threads y extraer adjuntos
        for thread in threads:
            thread_id = thread.get("id")
            detail_url = f"{ZOHO_DESK_BASE}/tickets/{ticket_id}/threads/{thread_id}"
            detail_resp = await client.get(detail_url, headers=headers, timeout=15.0)

            if not detail_resp.is_success:
                logger.warning(
                    "No se pudo obtener thread %s: %s",
                    thread_id,
                    detail_resp.status_code,
                )
                continue

            detail = detail_resp.json()
            thread_attachments = detail.get("attachments", [])

            for att in thread_attachments:
                name = att.get("name", "")
                url = att.get("href") or att.get("downloadUrl") or att.get("url")
                if name and url:
                    attachments.append(
                        {
                            "name": name,
                            "url": url,
                            "size": att.get("size"),
                        }
                    )
                    logger.info("📎 Adjunto encontrado: %s", name)

    logger.info("📎 Total adjuntos encontrados: %d", len(attachments))
    return attachments


async def download_attachment_as_base64(url: str, org_id: str) -> tuple[str, str]:
    """
    Descarga un adjunto y lo retorna como base64.

    Returns:
        (base64_data, media_type)
    """
    token = await _get_zoho_token()
    headers = {
        "orgId": org_id,
        "Authorization": f"Zoho-oauthtoken {token}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url, headers=headers, timeout=30.0, follow_redirects=True
        )
        response.raise_for_status()

        content_type = (
            response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        )
        b64 = base64.b64encode(response.content).decode("utf-8")
        logger.info(
            "⬇️ Descargado adjunto: %d bytes | content_type=%s",
            len(response.content),
            content_type,
        )
        return b64, content_type

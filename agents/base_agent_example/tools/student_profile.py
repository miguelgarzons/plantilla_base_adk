"""
Ejemplo: herramienta de consulta/actualización de perfil via API REST externa.

Este módulo muestra el patrón recomendado para integrar una API REST
autenticada como herramienta (tool) de un agente ADK.

Variables de entorno requeridas:
    EXTERNAL_API_BASE_URL  - URL base de la API externa
    EXTERNAL_API_USERNAME  - Usuario para autenticarse
    EXTERNAL_API_PASSWORD  - Contraseña para autenticarse

Patrón implementado:
    1. Login con credenciales → obtener Bearer token
    2. Cache del token en memoria
    3. Re-autenticación automática si el token expira (401)
    4. Funciones async que el agente puede usar como tools
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_cached_token: str | None = None


def _get_api_config() -> tuple[str, str, str]:
    """Retorna (base_url, username, password) desde variables de entorno."""
    base_url = os.getenv("EXTERNAL_API_BASE_URL", "").strip()
    username = os.getenv("EXTERNAL_API_USERNAME", "").strip()
    password = os.getenv("EXTERNAL_API_PASSWORD", "").strip()

    if not base_url:
        raise ValueError(
            "EXTERNAL_API_BASE_URL no configurado. "
            "Define esta variable con la URL base de tu API externa."
        )
    if not username or not password:
        raise ValueError(
            "EXTERNAL_API_USERNAME y/o EXTERNAL_API_PASSWORD no configurados."
        )
    return base_url, username, password


async def _get_bearer_token() -> str:
    """Obtiene y cachea el Bearer token autenticándose en la API."""
    global _cached_token

    if _cached_token:
        logger.info("🔐 Token ya cacheado, reutilizando.")
        return _cached_token

    base_url, username, password = _get_api_config()

    logger.info("🔐 API LOGIN → POST %s/auth/login | user=%s", base_url, username)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=10.0,
        )
        logger.info("🔐 API LOGIN ← status=%s", response.status_code)
        response.raise_for_status()
        data = response.json()

        token = (
            data.get("access_token")
            or data.get("token")
            or data.get("accessToken")
        )
        if not token:
            logger.error(
                "Respuesta de login sin token. Keys recibidas: %s", list(data.keys())
            )
            raise ValueError(f"No se encontró token en la respuesta de login: {data}")

        _cached_token = token
        logger.info("✅ Token obtenido (primeros 20 chars): %s...", token[:20])
        return _cached_token


def _invalidate_token() -> None:
    global _cached_token
    _cached_token = None


async def _make_authed_request(method: str, url: str, **kwargs) -> httpx.Response:
    """Ejecuta una request autenticada, reintentando si el token expiró (401)."""
    token = await _get_bearer_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    kwargs.pop("headers", None)

    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, timeout=10.0, **kwargs)

        if response.status_code == 401:
            logger.warning("Token expirado, re-autenticando...")
            _invalidate_token()
            token = await _get_bearer_token()
            headers["Authorization"] = f"Bearer {token}"
            response = await client.request(method, url, headers=headers, timeout=10.0, **kwargs)

        return response


# ──────────────────────────────────────────────────────────────
# Ejemplo: GET consultar recurso
# ──────────────────────────────────────────────────────────────

async def get_resource_info(resource_id: str) -> dict:
    """
    Consulta información de un recurso por su identificador.

    Args:
        resource_id: Identificador único del recurso.

    Returns:
        Diccionario con los datos del recurso, o {'error': '...'} si falla.
    """
    base_url, _, _ = _get_api_config()
    url = f"{base_url}/resources/{resource_id}"
    logger.info("📡 GET → %s", url)

    try:
        response = await _make_authed_request("GET", url)
        logger.info("📡 GET ← status=%s | id=%s", response.status_code, resource_id)

        if response.status_code == 404:
            return {"error": f"Recurso '{resource_id}' no encontrado."}

        response.raise_for_status()
        return response.json()

    except httpx.HTTPStatusError as e:
        logger.error("❌ GET error HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return {"error": f"Error HTTP {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error("❌ GET error inesperado: %s", e)
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────
# Ejemplo: PATCH actualizar recurso
# ──────────────────────────────────────────────────────────────

async def update_resource(resource_id: str, updates: dict) -> dict:
    """
    Actualiza campos de un recurso.

    Args:
        resource_id: Identificador único del recurso.
        updates: Diccionario con los campos a actualizar.

    Returns:
        Diccionario con resultado de la operación.
    """
    base_url, _, _ = _get_api_config()
    url = f"{base_url}/resources/{resource_id}"

    # Limpiar campos None o vacíos
    body = {k: v for k, v in updates.items() if v not in (None, "")}
    logger.info("📡 PATCH → %s | body=%s", url, body)

    try:
        response = await _make_authed_request("PATCH", url, json=body)
        logger.info("📡 PATCH ← status=%s | id=%s", response.status_code, resource_id)

        if response.status_code in (200, 201, 204):
            data = response.json() if response.content else {}
            return {"status": "updated", "data": data}

        response.raise_for_status()
        return {"status": "updated", "data": response.json() if response.content else {}}

    except httpx.HTTPStatusError as e:
        logger.error("❌ PATCH error HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return {"error": f"Error HTTP {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error("❌ PATCH error inesperado: %s", e)
        return {"error": str(e)}

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://app360.cunapp.pro/api/v1"
AUTH_USERNAME = "SDK-Agent"
AUTH_PASSWORD = "ok3{10QT}t/1#B;+Xn#:>&"

_cached_token: str | None = None


async def _get_bearer_token() -> str:
    """Obtiene y cachea el Bearer token autenticándose en el API."""
    global _cached_token

    if _cached_token:
        logger.info("🔐 Token ya cacheado, reutilizando.")
        return _cached_token

    logger.info("🔐 API LOGIN → POST %s/auth/login | user=%s", BASE_URL, AUTH_USERNAME)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/auth/login",
            json={"username": AUTH_USERNAME, "password": AUTH_PASSWORD},
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
    kwargs.pop("headers", None)  # evitar duplicado si alguien pasó headers por error

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
# GET: Consultar perfil del estudiante
# ──────────────────────────────────────────────────────────────

async def get_student_info(identification_number: str) -> dict:
    """
    Consulta la información actual de un estudiante por número de identificación.

    Args:
        identification_number: Número de identificación del estudiante.

    Returns:
        Diccionario con los datos del estudiante, o {'error': '...'} si falla.
    """
    url = f"{BASE_URL}/profile/bas-tercero/{identification_number}"
    logger.info("📡 GET → %s", url)

    try:
        response = await _make_authed_request("GET", url)
        logger.info("📡 GET ← status=%s | documento=%s", response.status_code, identification_number)

        if response.status_code == 404:
            return {"error": f"Estudiante '{identification_number}' no encontrado."}

        response.raise_for_status()
        data = response.json()
        logger.info(
            "✅ GET OK: fullName=%s | identificationType=%s",
            data.get("fullName", "?"),
            data.get("identificationType", "?"),
        )
        return data

    except httpx.HTTPStatusError as e:
        logger.error("❌ GET error HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return {"error": f"Error HTTP {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error("❌ GET error inesperado: %s", e)
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────
# PATCH: Actualizar tipo de documento a Cédula de Ciudadanía
# ──────────────────────────────────────────────────────────────

async def update_student_document_type(identification_number: str, student_data: dict) -> dict:
    """
    Actualiza el tipo de documento del estudiante de T.I. a C.C. (Cédula de Ciudadanía).
    Usa los datos actuales del estudiante del GET para construir el body del PATCH.

    Args:
        identification_number: Número de identificación del estudiante.
        student_data: Datos actuales del estudiante obtenidos del GET.

    Returns:
        Diccionario con resultado de la operación, o {'error': '...'} si falla.
    """
    # Usar el id interno del estudiante (no el número de identificación)
    student_id = student_data.get("id")
    if not student_id:
        logger.error("❌ PATCH abortado: no se encontró 'id' en student_data")
        return {"error": "No se encontró el campo 'id' en los datos del estudiante."}

    url = f"{BASE_URL}/profile/bas-tercero/{student_id}"
    logger.info(
        "📡 PATCH → %s | cambiando identificationType a 'C' (id=%s, doc=%s)",
        url, student_id, identification_number,
    )

    # Construir body con datos actuales del estudiante + cambio de tipo de documento
    body = {
        "identificationType": "C",                                          # <- el cambio clave
        "ipAddress":          "10.0.0.1",
    }

    # Limpiar campos None o vacíos para no enviar nulls innecesarios
    body = {k: v for k, v in body.items() if v not in (None, "")}

    logger.info("📡 PATCH body=%s", body)

    try:
        response = await _make_authed_request(
            "PATCH", url,
            json=body,
        )
        logger.info("📡 PATCH ← status=%s | documento=%s", response.status_code, identification_number)

        if response.status_code in (200, 201, 204):
            data = response.json() if response.content else {}
            logger.info("✅ PATCH OK: documento=%s actualizado a C.C.", identification_number)
            return {
                "status":  "updated",
                "message": "Tipo de documento actualizado exitosamente a Cédula de Ciudadanía.",
                "data":    data,
            }

        response.raise_for_status()
        return {"status": "updated", "data": response.json() if response.content else {}}

    except httpx.HTTPStatusError as e:
        logger.error("❌ PATCH error HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return {"error": f"Error HTTP {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error("❌ PATCH error inesperado: %s", e)
        return {"error": str(e)}


def _normalize_gender_target(target_gender: str) -> str:
    value = (target_gender or "").strip().lower()
    if value in {"f", "femenino", "mujer", "female"}:
        return "F"
    if value in {"m", "masculino", "hombre", "male"}:
        return "M"
    return ""


def _extract_current_gender(student_data: dict) -> str:
    for key in ("gender", "sexo", "sex", "genero"):
        value = str(student_data.get(key) or "").strip()
        if value:
            return _normalize_gender_target(value)
    return ""


async def update_student_gender(
    identification_number: str,
    student_data: dict,
    target_gender: str,
) -> dict:
    """
    Actualiza el genero del estudiante.

    - Campo PATCH configurable con STUDENT_PROFILE_GENDER_FIELD (default: gender).
    - Valores objetivo soportados: F/M (tambien mujer/hombre, femenino/masculino).
    """
    student_id = student_data.get("id")
    if not student_id:
        logger.error("❌ PATCH genero abortado: no se encontró 'id' en student_data")
        return {"error": "No se encontró el campo 'id' en los datos del estudiante."}

    normalized_target = _normalize_gender_target(target_gender)
    if not normalized_target:
        return {
            "error": (
                "Genero objetivo invalido. Use F/M o equivalentes "
                "(mujer/hombre, femenino/masculino)."
            )
        }

    current_gender = _extract_current_gender(student_data)
    if current_gender and current_gender == normalized_target:
        return {
            "status": "already_updated",
            "message": "El genero ya estaba actualizado en el perfil del estudiante.",
            "current_gender": current_gender,
        }

    url = f"{BASE_URL}/profile/bas-tercero/{student_id}"
    gender_field = os.getenv("STUDENT_PROFILE_GENDER_FIELD", "gender").strip() or "gender"
    body = {
        gender_field: normalized_target,
        "ipAddress": "10.0.0.1",
    }
    body = {k: v for k, v in body.items() if v not in (None, "")}

    logger.info(
        "📡 PATCH → %s | campo=%s | genero=%s | id=%s | doc=%s",
        url,
        gender_field,
        normalized_target,
        student_id,
        identification_number,
    )
    logger.info("📡 PATCH body=%s", body)

    try:
        response = await _make_authed_request("PATCH", url, json=body)
        logger.info(
            "📡 PATCH ← status=%s | documento=%s",
            response.status_code,
            identification_number,
        )

        if response.status_code in (200, 201, 204):
            data = response.json() if response.content else {}
            return {
                "status": "updated",
                "message": "Genero actualizado exitosamente en el perfil del estudiante.",
                "target_gender": normalized_target,
                "data": data,
            }

        response.raise_for_status()
        return {
            "status": "updated",
            "target_gender": normalized_target,
            "data": response.json() if response.content else {},
        }
    except httpx.HTTPStatusError as e:
        logger.error("❌ PATCH genero error HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return {"error": f"Error HTTP {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        logger.error("❌ PATCH genero error inesperado: %s", e)
        return {"error": str(e)}

"""
Ejemplo: herramienta de verificación de documentos con visión multimodal.

Este módulo muestra el patrón recomendado para crear un sub-agente
que usa capacidades de visión (imágenes) con un LlmAgent en ADK.

Patrón implementado:
    1. Un BaseAgent recibe imágenes del estado de sesión
    2. Construye un Content multimodal (texto + imágenes)
    3. Delega el análisis al LlmAgent (con visión)
    4. Parsea la respuesta JSON del modelo

Adapta este ejemplo a tu caso de uso:
    - Verificación de documentos de identidad
    - Análisis de facturas o recibos
    - Clasificación de imágenes
    - Extracción de datos de fotos
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

_configured_model: str = os.getenv("AGENT_MODEL", "gemini-2.5-pro")


def configure_model(model: str) -> None:
    """Permite cambiar el modelo de visión en runtime."""
    global _configured_model
    _configured_model = model
    _reset_agent()


# ──────────────────────────────────────────────────────────────────
# BaseAgent: construye el mensaje multimodal y delega al LlmAgent
# ──────────────────────────────────────────────────────────────────


class AgenteDocumentVerifier(BaseAgent):
    """
    Lee imágenes del estado de sesión, construye el Content multimodal
    y lo pasa al LlmAgent como contexto del turno.

    State keys esperados:
        - "document_images": list[dict] con keys "base64", "media_type", "name"
        - "expected_identifier": str con el identificador esperado en el documento
    """

    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        images: list[dict] = ctx.session.state.get("document_images", [])
        expected_id: str = ctx.session.state.get("expected_identifier", "")

        if not images:
            ctx.session.state["document_verification_raw"] = json.dumps(
                {
                    "is_valid_document": False,
                    "identifier_found": "",
                    "identifier_matches": False,
                    "confidence": "low",
                    "detail": "No se recibieron imágenes para analizar.",
                },
                ensure_ascii=False,
            )
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        "document_verification_raw": ctx.session.state[
                            "document_verification_raw"
                        ]
                    }
                ),
            )
            return

        # ── Construir partes multimodales ──
        parts: list[genai_types.Part] = []

        for img in images:
            media_type = img.get("media_type", "image/jpeg")
            if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                media_type = "image/jpeg"

            parts.append(
                genai_types.Part(
                    inline_data=genai_types.Blob(
                        mime_type=media_type,
                        data=img["base64"],
                    )
                )
            )
            parts.append(
                genai_types.Part(text=f"[Imagen: {img.get('name', 'sin nombre')}]")
            )

        parts.append(
            genai_types.Part(
                text=f"""Analiza las imágenes adjuntas y verifica:

Identificador esperado: {expected_id}

Evalúa:
1. ¿Es un documento válido y legible?
2. ¿El identificador visible coincide con: {expected_id}?

Responde ÚNICAMENTE con este JSON, sin texto adicional:
{{
  "is_valid_document": true/false,
  "identifier_found": "identificador encontrado o vacío",
  "identifier_matches": true/false,
  "confidence": "high/medium/low",
  "detail": "explicación breve en máximo 2 oraciones"
}}"""
            )
        )

        ctx.session.state["_document_multimodal_parts"] = parts

        logger.info(
            "🤖 AgenteDocumentVerifier → LlmAgent | id=%s | imágenes=%d",
            expected_id,
            len(images),
        )

        agente_llm: LlmAgent = self.sub_agents[0]
        async for event in agente_llm.run_async(ctx):
            yield event


# ──────────────────────────────────────────────────────────────────
# Singleton del agente verificador
# ──────────────────────────────────────────────────────────────────

_verifier_agent: AgenteDocumentVerifier | None = None


def _reset_agent() -> None:
    global _verifier_agent
    _verifier_agent = None


def _get_verifier_agent() -> AgenteDocumentVerifier:
    global _verifier_agent
    if _verifier_agent is None:
        agente_llm = LlmAgent(
            name="agente_llm_document_vision",
            model=_configured_model,
            instruction="""Eres un verificador de documentos.
Analiza las imágenes que te envíen y responde ÚNICAMENTE con el JSON solicitado,
sin texto adicional, sin markdown, sin explicaciones fuera del JSON.""",
            output_key="document_verification_raw",
        )
        _verifier_agent = AgenteDocumentVerifier(
            name="agente_document_verifier",
            description="Verifica documentos con visión multimodal.",
            sub_agents=[agente_llm],
        )
    return _verifier_agent


# ──────────────────────────────────────────────────────────────────
# Interfaz pública
# ──────────────────────────────────────────────────────────────────


async def verify_document_images(
    images: list[dict],
    expected_identifier: str,
) -> dict:
    """
    Verifica documentos usando visión multimodal.

    Args:
        images: Lista de dicts con keys "base64", "media_type", "name"
        expected_identifier: Identificador que se espera encontrar en el documento

    Returns:
        dict con resultado de verificación
    """
    agent = _get_verifier_agent()
    runner = InMemoryRunner(agent=agent, app_name="document_verifier")

    session = await runner.session_service.create_session(
        app_name="document_verifier",
        user_id="system",
        state={
            "document_images": images,
            "expected_identifier": expected_identifier,
        },
    )

    parts: list[genai_types.Part] = []
    for img in images:
        media_type = img.get("media_type", "image/jpeg")
        if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            media_type = "image/jpeg"
        parts.append(
            genai_types.Part(
                inline_data=genai_types.Blob(
                    mime_type=media_type,
                    data=img["base64"],
                )
            )
        )

    parts.append(
        genai_types.Part(
            text=f"""Analiza las imágenes adjuntas.
Identificador esperado: {expected_identifier}

Responde ÚNICAMENTE con este JSON:
{{
  "is_valid_document": true/false,
  "identifier_found": "identificador encontrado o vacío",
  "identifier_matches": true/false,
  "confidence": "high/medium/low",
  "detail": "explicación breve en máximo 2 oraciones"
}}"""
        )
    )

    async for _event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=genai_types.Content(
            role="user",
            parts=parts,
        ),
    ):
        pass

    final_session = await runner.session_service.get_session(
        app_name="document_verifier",
        user_id="system",
        session_id=session.id,
    )

    raw = final_session.state.get("document_verification_raw", "{}")
    return _parse_result(raw, expected_identifier)


# ──────────────────────────────────────────────────────────────────
# Parseo de respuesta del modelo
# ──────────────────────────────────────────────────────────────────


def _parse_result(raw_json: str, expected_id: str) -> dict:
    try:
        clean = re.sub(r"```(?:json)?", "", raw_json).strip().rstrip("`").strip()
        result = json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("❌ Parse Vision fallido: %s | raw: %s", e, raw_json[:200])
        return {
            "verified": False,
            "confidence": "low",
            "identifier_found": "",
            "identifier_matches": False,
            "is_valid_document": False,
            "detail": f"No se pudo interpretar la respuesta: {raw_json[:100]}",
        }

    verified = (
        result.get("is_valid_document", False)
        and result.get("identifier_matches", False)
        and result.get("confidence") in ("high", "medium")
    )

    return {
        "verified": verified,
        "confidence": result.get("confidence", "low"),
        "identifier_found": result.get("identifier_found", ""),
        "identifier_matches": result.get("identifier_matches", False),
        "is_valid_document": result.get("is_valid_document", False),
        "detail": result.get("detail", ""),
    }

# tools/cedula_verifier.py
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

_configured_model: str = "gemini-2.5-pro"


def configure_model(model: str) -> None:
    global _configured_model
    _configured_model = model
    _reset_agent()


# ──────────────────────────────────────────────────────────────────
# BaseAgent: solo construye el mensaje multimodal y delega al LlmAgent
# ──────────────────────────────────────────────────────────────────


class AgenteCedulaVerifier(BaseAgent):
    """
    Lee imágenes del estado, construye el Content multimodal
    y lo pasa al LlmAgent como contexto adicional del turno.
    """

    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        images: list[dict] = ctx.session.state.get("cedula_images", [])
        expected_number: str = ctx.session.state.get("cedula_expected_number", "")
        full_name: str = ctx.session.state.get("cedula_full_name", "")

        if not images:
            ctx.session.state["cedula_verification_raw"] = json.dumps(
                {
                    "is_colombian_cedula": False,
                    "has_frontal": False,
                    "has_reverso": False,
                    "document_number_found": "",
                    "number_matches": False,
                    "confidence": "low",
                    "detail": "No se recibieron imágenes para analizar.",
                    "_reason": "no_attachments",
                },
                ensure_ascii=False,
            )
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        "cedula_verification_raw": ctx.session.state[
                            "cedula_verification_raw"
                        ]
                    }
                ),
            )
            return

        # ── Construir partes multimodales directamente en el estado
        # para que el runner las use como new_message ──
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

        nombre_hint = f"\nNombre esperado del titular: {full_name}" if full_name else ""
        parts.append(
            genai_types.Part(
                text=f"""Analiza las imágenes adjuntas y verifica:

Número de documento esperado: {expected_number}{nombre_hint}

Evalúa:
1. ¿Son imágenes de una Cédula de Ciudadanía colombiana?
   - Frontal: fondo amarillo/dorado, foto, nombre, número
   - Reverso: huella dactilar, firma, código de barras
   - Emitida por la Registraduría Nacional del Estado Civil

2. ¿El número de cédula visible coincide con: {expected_number}?

3. ¿Están presentes frontal y reverso?

Responde ÚNICAMENTE con este JSON, sin texto adicional:
{{
  "is_colombian_cedula": true/false,
  "has_frontal": true/false,
  "has_reverso": true/false,
  "document_number_found": "número encontrado o vacío",
  "number_matches": true/false,
  "confidence": "high/medium/low",
  "detail": "explicación breve en máximo 2 oraciones"
}}"""
            )
        )

        # Guardar partes para que verify_cedula_images las use como new_message
        ctx.session.state["_cedula_multimodal_parts"] = parts

        logger.info(
            "🤖 AgenteCedulaVerifier → LlmAgent | doc=%s | imágenes=%d",
            expected_number,
            len(images),
        )

        agente_llm: LlmAgent = self.sub_agents[0]
        async for event in agente_llm.run_async(ctx):
            yield event


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_verifier_agent: AgenteCedulaVerifier | None = None


def _reset_agent() -> None:
    global _verifier_agent
    _verifier_agent = None


def _get_verifier_agent() -> AgenteCedulaVerifier:
    global _verifier_agent
    if _verifier_agent is None:
        agente_llm = LlmAgent(
            name="agente_llm_cedula_vision",
            model=_configured_model,
            instruction="""Eres un verificador de documentos de identidad colombianos.
Analiza las imágenes que te envíen y responde ÚNICAMENTE con el JSON solicitado,
sin texto adicional, sin markdown, sin explicaciones fuera del JSON.""",
            output_key="cedula_verification_raw",
        )
        _verifier_agent = AgenteCedulaVerifier(
            name="agente_cedula_verifier",
            description="Verifica cédulas colombianas con visión multimodal.",
            sub_agents=[agente_llm],
        )
    return _verifier_agent


# ──────────────────────────────────────────────────────────────────
# Interfaz pública
# ──────────────────────────────────────────────────────────────────


async def verify_cedula_images(
    images: list[dict],
    expected_document_number: str,
    full_name: str = "",
) -> dict:
    agent = _get_verifier_agent()
    runner = InMemoryRunner(agent=agent, app_name="cedula_verifier")

    session = await runner.session_service.create_session(
        app_name="cedula_verifier",
        user_id="system",
        state={
            "cedula_images": images,
            "cedula_expected_number": expected_document_number,
            "cedula_full_name": full_name,
        },
    )

    # ── Construir el mensaje multimodal aquí, antes de correr el agente ──
    # El BaseAgent lo reconstruirá también, pero el runner necesita
    # el new_message con las imágenes para que el LlmAgent las vea
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

    nombre_hint = f"\nNombre esperado: {full_name}" if full_name else ""
    parts.append(
        genai_types.Part(
            text=f"""Analiza las imágenes adjuntas.
Número esperado: {expected_document_number}{nombre_hint}

Responde ÚNICAMENTE con este JSON:
{{
  "is_colombian_cedula": true/false,
  "has_frontal": true/false,
  "has_reverso": true/false,
  "document_number_found": "número encontrado o vacío",
  "number_matches": true/false,
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
            parts=parts,  # ← imágenes reales aquí, no un mensaje dummy
        ),
    ):
        pass

    final_session = await runner.session_service.get_session(
        app_name="cedula_verifier",
        user_id="system",
        session_id=session.id,
    )

    raw = final_session.state.get("cedula_verification_raw", "{}")
    return _parse_and_enrich(raw, expected_document_number)


# ──────────────────────────────────────────────────────────────────
# Parseo
# ──────────────────────────────────────────────────────────────────


def _parse_and_enrich(raw_json: str, expected_number: str) -> dict:
    try:
        clean = re.sub(r"```(?:json)?", "", raw_json).strip().rstrip("`").strip()
        result = json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("❌ Parse Vision fallido: %s | raw: %s", e, raw_json[:200])
        return _error_result(f"No se pudo interpretar la respuesta: {raw_json[:100]}")

    if "_reason" in result:
        return {
            "verified": False,
            "confidence": result.get("confidence", "low"),
            "has_frontal": result.get("has_frontal", False),
            "has_reverso": result.get("has_reverso", False),
            "document_number_found": result.get("document_number_found", ""),
            "number_matches": result.get("number_matches", False),
            "is_colombian_cedula": result.get("is_colombian_cedula", False),
            "reason": result["_reason"],
            "detail": result.get("detail", ""),
        }

    verified = (
        result.get("is_colombian_cedula", False)
        and result.get("number_matches", False)
        and result.get("has_frontal", False)
        and result.get("confidence") in ("high", "medium")
    )

    return {
        "verified": verified,
        "confidence": result.get("confidence", "low"),
        "has_frontal": result.get("has_frontal", False),
        "has_reverso": result.get("has_reverso", False),
        "document_number_found": result.get("document_number_found", ""),
        "number_matches": result.get("number_matches", False),
        "is_colombian_cedula": result.get("is_colombian_cedula", False),
        "reason": _build_reason(result, verified),
        "detail": result.get("detail", ""),
    }


def _error_result(detail: str) -> dict:
    return {
        "verified": False,
        "confidence": "low",
        "has_frontal": False,
        "has_reverso": False,
        "document_number_found": "",
        "number_matches": False,
        "is_colombian_cedula": False,
        "reason": "vision_error",
        "detail": detail,
    }


def _build_reason(result: dict, verified: bool) -> str:
    if not result.get("is_colombian_cedula"):
        return "not_cedula"
    if not result.get("has_frontal"):
        return "missing_frontal"
    if not result.get("number_matches"):
        return "number_mismatch"
    if result.get("confidence") == "low":
        return "low_confidence"
    return "verified_ok" if verified else "unknown"

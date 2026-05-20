from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types as genai_types

from .common import AgentDependencies

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Palabras clave por categoría
# ──────────────────────────────────────────────
_KEYWORDS_CAMBIO_DOCUMENTO = [
    "tarjeta de identidad",
    "cédula",
    "cedula",
    "cambio de documento",
    "actualizar documento",
    "t.i. a c.c.",
    "documento de identidad",
    "tarjeta a cedula",
    "tarjeta a cédula",
]

_KEYWORDS_NOTAS = [
    "notas",
    "calificaciones",
    "nota",
    "calificación",
    "calificacion",
    "revisar nota",
    "error en nota",
    "materia",
]

_KEYWORDS_CAMBIO_GENERO = [
    "cambio de genero",
    "cambio d egenero",
    "cambio de género",
    "actualizacion de genero",
    "actualización de género",
    "actualizar genero",
    "actualizar género",
    "cambio genero",
]

_KEYWORDS_MUJER = [
    "a mujer",
    "mujer",
    "femenino",
]

_KEYWORDS_HOMBRE = [
    "a hombre",
    "hombre",
    "masculino",
]


def _normalizar_genero_objetivo(text: str) -> str:
    text_lower = text.lower()
    for kw in _KEYWORDS_MUJER:
        if kw in text_lower:
            return "F"
    for kw in _KEYWORDS_HOMBRE:
        if kw in text_lower:
            return "M"
    return ""


def _clasificar(text: str, categoria: str, sub_categoria: str) -> str:
    text_lower = text.lower()
    categoria_lower = (categoria or "").lower()
    sub_categoria_lower = (sub_categoria or "").lower()

    for kw in _KEYWORDS_CAMBIO_GENERO:
        if kw in text_lower:
            return "cambio_genero"
    if "cambio de genero" in sub_categoria_lower or "cambio de género" in sub_categoria_lower:
        return "cambio_genero"
    if "actualizacion de datos" in categoria_lower and "genero" in sub_categoria_lower:
        return "cambio_genero"

    for kw in _KEYWORDS_CAMBIO_DOCUMENTO:
        if kw in text_lower:
            return "cambio_documento"
    for kw in _KEYWORDS_NOTAS:
        if kw in text_lower:
            return "notas"
    return "desconocido"


# ──────────────────────────────────────────────
# Agente receptor + clasificador en Python puro
# ──────────────────────────────────────────────
class AgenteReceptorClasificador(BaseAgent):
    """
    Parsea el JSON del ticket Zoho y clasifica el tipo de solicitud.
    Escribe directamente en session.state sin pasar por LLM.

    Escribe en state:
      - "ticket_context"  → dict con campos estructurados del ticket
      - "tipo_ticket"     → "cambio_documento" | "cambio_genero" | "notas" | "desconocido"
    """

    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        org_id = os.getenv("ZOHO_ORG_ID", "").strip()

        # ── 1. Leer el mensaje raw del usuario ──
        raw = ""
        if ctx.user_content:
            for part in ctx.user_content.parts:
                if hasattr(part, "text") and part.text:
                    raw += part.text

        # ── 2. Parsear JSON del ticket ──
        # El description puede traer HTML con saltos de línea reales que
        # rompen json.loads. Los sanitizamos antes de parsear.
        ticket: dict = {}
        try:
            # Intento directo
            ticket = json.loads(raw.strip())
        except json.JSONDecodeError:
            try:
                # Sanitizar: reemplazar saltos de línea reales dentro del string
                import re

                sanitized = re.sub(r"(?<!\\)\n", " ", raw.strip())
                sanitized = re.sub(r"(?<!\\)\r", " ", sanitized)
                ticket = json.loads(sanitized)
                logger.info("JSON parseado tras sanitización de saltos de línea.")
            except json.JSONDecodeError as e:
                logger.error(
                    "No se pudo parsear el JSON del ticket: %s | raw: %s",
                    e,
                    raw[:300],
                )
                yield Event(
                    author=self.name,
                    content=genai_types.Content(
                        parts=[genai_types.Part(text="BLOCKER_PAYLOAD_FORMAT")]
                    ),
                )
                return

        # ── 3. Validar campos obligatorios ──
        ticket_id = ticket.get("id")
        department_id = ticket.get("departmentId")

        if not ticket_id or not department_id:
            logger.error(
                "Faltan campos obligatorios: id=%s departmentId=%s",
                ticket_id,
                department_id,
            )
            yield Event(
                author=self.name,
                content=genai_types.Content(
                    parts=[genai_types.Part(text="BLOCKER_PAYLOAD_FORMAT")]
                ),
            )
            return

        if not org_id:
            logger.error("ZOHO_ORG_ID no configurado.")
            yield Event(
                author=self.name,
                content=genai_types.Content(
                    parts=[genai_types.Part(text="BLOCKER_ORG_ID")]
                ),
            )
            return

        # ── 4. Extraer campos ──
        cf = ticket.get("cf") or {}
        numero_de_documento = (
            cf.get("cf_numero_de_documento")
            or ticket.get("cf_numero_de_documento")
            or ""
        )

        ticket_context = {
            "ticket_id": ticket_id,
            "org_id": org_id,
            "department_id": department_id,
            "status": ticket.get("status", ""),
            "subject": ticket.get("subject", ""),
            "description": ticket.get("description", ""),
            "email": ticket.get("email", ""),
            "categoria": cf.get("cf_categoria", ""),
            "sub_categoria": cf.get("cf_sub_categorias", ""),
            "numero_de_documento": numero_de_documento,
            "genero_objetivo": _normalizar_genero_objetivo(
                f"{ticket.get('subject', '')} {ticket.get('description', '')} {cf.get('cf_sub_categorias', '')}"
            ),
            "criterio_cierre": "cerrable",
            "razon": "payload valido para cierre",
        }

        # ── 5. Clasificar ──
        texto = f"{ticket_context['subject']} {ticket_context['description']}"
        tipo_ticket = _clasificar(
            texto,
            ticket_context.get("categoria", ""),
            ticket_context.get("sub_categoria", ""),
        )

        logger.info(
            "Ticket procesado → id=%s | documento=%s | tipo=%s",
            ticket_id,
            numero_de_documento or "no encontrado",
            tipo_ticket,
        )

        # ── 6. Emitir evento con state_delta (garantiza escritura en state) ──
        summary = (
            f"Ticket {ticket_id} recibido. "
            f"Tipo: {tipo_ticket}. "
            f"Documento: {numero_de_documento or 'no encontrado'}. "
            f"Genero objetivo: {ticket_context.get('genero_objetivo') or 'no detectado'}."
        )
        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    "ticket_context": ticket_context,
                    "tipo_ticket": tipo_ticket,
                }
            ),
            content=genai_types.Content(parts=[genai_types.Part(text=summary)]),
        )


def build_agente_receptor_ingesta(deps: AgentDependencies) -> BaseAgent:
    return AgenteReceptorClasificador(
        name="agente_receptor_ingesta",
        description="Parsea el ticket Zoho y clasifica el tipo de solicitud.",
    )

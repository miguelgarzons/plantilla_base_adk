from __future__ import annotations

import json
import logging
import os
import re
import hashlib
from typing import Any

from google.adk.agents import LlmAgent
from google.genai import types

from base_agent_example.tools.zoho_actions import ejecutar_cierre_ticket_con_traza
from base_agent_example.tools.zoho_actions import enviar_respuesta_por_correo_ticket
from base_agent_example.tools.zoho_actions import publicar_comentario_ticket
from base_agent_example.tools.zoho_actions import consultar_estado_ticket

from .common import AgentDependencies
from .logging_hooks import log_after_agent
from .logging_hooks import log_before_agent

logger = logging.getLogger("categorizador.pipeline")


# ──────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────

import ast  # agregar al bloque de imports arriba


def _extract_ticket_context(callback_context: Any) -> dict[str, Any]:
    ctx = callback_context.state.get("ticket_context")
    if isinstance(ctx, dict) and ctx.get("ticket_id"):
        return ctx

    user_content = getattr(callback_context, "user_content", None)
    if not user_content:
        return {}

    for part in getattr(user_content, "parts", None) or []:
        text = getattr(part, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue

        parsed = None

        # Intento 1: JSON estándar (comillas dobles, null, false)
        try:
            raw = re.sub(r"(?<!\\)\n", " ", text.strip())
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Intento 2: repr de Python (comillas simples, None, False, True)
        if parsed is None:
            try:
                parsed = ast.literal_eval(text.strip())
            except (ValueError, SyntaxError):
                pass

        if not isinstance(parsed, dict):
            continue

        cf = parsed.get("cf") or {}
        return {
            "ticket_id": parsed.get("id", ""),
            "org_id": os.getenv("ZOHO_ORG_ID", "").strip(),
            "department_id": parsed.get("departmentId", ""),
            "status": parsed.get("status", ""),
            "subject": parsed.get("subject", ""),
            "description": parsed.get("description", ""),
            "email": parsed.get("email", ""),
            "webUrl": parsed.get("webUrl", ""),
            "categoria": cf.get("cf_categoria", ""),
            "sub_categoria": cf.get("cf_sub_categorias", ""),
            "numero_de_documento": cf.get("cf_numero_de_documento", ""),
        }

    return {}


def _append_internal_context(callback_context: Any, text: str) -> None:
    user_content = getattr(callback_context, "user_content", None)
    if user_content is None:
        return
    parts = getattr(user_content, "parts", None)
    if isinstance(parts, list):
        parts.append(types.Part(text=text))


def _build_fallback_text(result: dict, ctx: dict) -> str:
    status = str(result.get("status", "error")).lower()
    ticket_id = ctx.get("ticket_id", "N/A")
    subject = ctx.get("subject", "sin asunto")
    categoria = ctx.get("categoria", "soporte general")
    desc_raw = ctx.get("description", "")
    desc = re.sub(r"<[^>]+>", " ", desc_raw)
    desc = re.sub(r"\s+", " ", desc).strip()[:220] or "el reporte recibido"

    if status == "already_closed":
        return (
            f"Hola, revisamos tu ticket {ticket_id} ({subject}) y ya se encontraba cerrado. "
            "No ejecutamos acciones adicionales para evitar duplicados."
        )
    if status == "failed":
        detail = str(
            result.get("close_error") or result.get("detail") or "sin detalle"
        ).strip()
        return (
            f"Hola, gestionamos tu ticket {ticket_id} ({subject}) en {categoria}, "
            f"pero el cierre automático no pudo completarse: {detail}. "
            "El caso queda en seguimiento manual."
        )

    bloques = [
        (
            "detectamos un comportamiento intermitente",
            "aplicamos una corrección operativa",
            "la validación fue exitosa",
        ),
        (
            "identificamos una inconsistencia operativa",
            "ejecutamos un ajuste de soporte",
            "el resultado quedó verificado",
        ),
        (
            "ubicamos un desajuste puntual",
            "realizamos una intervención técnica",
            "el flujo quedó estable",
        ),
    ]
    seed = f"{ticket_id}|{subject}".encode()
    h = int(hashlib.sha256(seed).hexdigest(), 16)
    diag, accion, val = bloques[h % len(bloques)]

    return (
        f"Hola, cerramos tu ticket {ticket_id} ({subject}) en {categoria}. "
        f"Durante la gestión {diag}; luego {accion} y finalmente {val}. "
        f"Tomamos como referencia: {desc}."
    )


# ──────────────────────────────────────────────────────────────
# Callback principal de cierre
# ──────────────────────────────────────────────────────────────


async def pre_cierre_callback(callback_context: Any = None, **_: Any):
    if callback_context is None:
        return None

    if (
        str(callback_context.state.get("cierre_side_effects_done", "")).lower()
        == "true"
    ):
        logger.info("PIPELINE_CIERRE_SKIP reason=already_executed")
        return None

    # ── 1. Obtener contexto del ticket ──
    ctx = _extract_ticket_context(callback_context)
    logger.info(
        "PIPELINE_CIERRE_CALLBACK_ENTER ticket_id=%s", ctx.get("ticket_id", "?")
    )

    ticket_id = str(ctx.get("ticket_id", "")).strip()
    org_id = str(ctx.get("org_id") or os.getenv("ZOHO_ORG_ID", "")).strip()
    department_id = str(ctx.get("department_id", "")).strip()
    to_email = str(ctx.get("email", "")).strip()
    categoria = str(ctx.get("categoria", "")).strip()

    if not ticket_id:
        logger.warning(
            "PIPELINE_BLOCKER cierre: falta ticket_id. state keys=%s",
            list(callback_context.state.keys()),
        )
        _append_internal_context(
            callback_context, "BLOCKER_PAYLOAD_FORMAT: falta ticket_id."
        )
        return None

    if not org_id:
        logger.warning("PIPELINE_BLOCKER cierre: falta org_id.")
        _append_internal_context(callback_context, "BLOCKER_ORG_ID: falta org_id.")
        return None

    # ── 2. Verificar si ya está cerrado ──
    estado = await consultar_estado_ticket(ticket_id=ticket_id, org_id=org_id)
    if estado.get("status") == "ok" and bool(estado.get("is_closed")):
        logger.info("PIPELINE_CIERRE_SKIP_ALREADY_CLOSED ticket_id=%s", ticket_id)
        result = {"status": "already_closed", "ticket_id": ticket_id}
    else:
        result = await ejecutar_cierre_ticket_con_traza(
            ticket_id=ticket_id, org_id=org_id
        )

    # ── 3. Generar texto de respuesta ──
    final_text = _build_fallback_text(result, ctx)

    # ── 4. Publicar comentario público ──
    if str(result.get("status", "")).lower() != "already_closed":
        comentario_result = await publicar_comentario_ticket(
            ticket_id=ticket_id,
            org_id=org_id,
            content=f"Respuesta generada para cierre:\n{final_text}",
            is_public=True,
        )
        logger.info(
            "PIPELINE_CIERRE_COMMENT status=%s ticket_id=%s",
            comentario_result.get("status"),
            ticket_id,
        )

    # ── 5. Enviar correo si el cierre fue exitoso ──
    if (
        os.getenv("ZOHO_SEND_REPLY_ENABLED", "true").lower() == "true"
        and str(result.get("status", "")).lower() == "closed"
    ):
        correo_result = await enviar_respuesta_por_correo_ticket(
            ticket_id=ticket_id,
            org_id=org_id,
            content=final_text,
            to_email=to_email,
            department_id=department_id,
            ticket_number="",
            categoria=categoria,
            nombre_usuario="Centro de Asistencia CUN",
            status_label="Cerrado",
            ticket_url=ctx.get("webUrl", ""),
        )
        logger.info(
            "PIPELINE_CIERRE_EMAIL status=%s ticket_id=%s",
            correo_result.get("status"),
            ticket_id,
        )

    logger.info(
        "PIPELINE_CIERRE_RESULT status=%s ticket_id=%s", result.get("status"), ticket_id
    )

    # ── 6. Actualizar state ──
    callback_context.state.update(
        {
            "cierre_status": str(result.get("status", "error")),
            "cierre_ticket_id": ticket_id,
            "cierre_categoria": categoria,
            "cierre_resultado_detalle": json.dumps(result, ensure_ascii=True),
            "cierre_side_effects_done": "true",
        }
    )

    _append_internal_context(
        callback_context,
        f"Cierre ejecutado. Resultado: {result.get('status')}.\n"
        f"Texto generado para el usuario:\n{final_text}\n"
        "Usa este contexto para redactar la respuesta final de forma humana y profesional.",
    )
    return None


# ──────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────


def build_agente_cierre_ticket(deps: AgentDependencies) -> LlmAgent:
    return LlmAgent(
        name="agente_cierre_ticket",
        model=deps.model,
        before_agent_callback=[log_before_agent, pre_cierre_callback],
        after_agent_callback=log_after_agent,
        generate_content_config=types.GenerateContentConfig(
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        ),
        instruction="""
            Eres el agente final de cierre de tickets de mesa de ayuda.

            El cierre ya fue ejecutado en el callback previo. Tu única tarea
            es redactar la respuesta final para el usuario con tono humano,
            natural y profesional.

            Usa el contexto interno del mensaje para explicar:
            - Qué se hizo con el ticket
            - Cuál fue el resultado del cierre
            - El siguiente paso recomendado (si aplica)

            Reglas:
            - Escribe en español, entre 40 y 80 palabras
            - No uses listas ni bullets
            - No hagas preguntas al usuario
            - No menciones que fuiste generado por IA
            - Si el ticket ya estaba cerrado, indícalo cordialmente
            - Si el cierre falló, explica el motivo sin tecnicismos
        """,
        tools=[],
    )

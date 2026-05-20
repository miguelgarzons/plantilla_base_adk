from __future__ import annotations

import json
import logging
import os
import html
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


logger = logging.getLogger("categorizador.pipeline")

_EMAIL_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "templates" / "ticket_reply_email.html"
)
_DEFAULT_TICKET_URL_TEMPLATE = "https://desk.zoho.com/agent/tickets/{ticket_id}"


def _load_email_template() -> str:
    try:
        return _EMAIL_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "PIPELINE_EMAIL_TEMPLATE_LOAD_FAILED path=%s error=%s",
            str(_EMAIL_TEMPLATE_PATH),
            str(exc),
        )
        return (
            "<!DOCTYPE html><html><body><p>{{ respuesta_html }}</p>"
            "<p>Ticket {{ ticket_id }} - {{ status_label }}</p></body></html>"
        )


def _build_respuesta_html(content: str) -> str:
    safe_lines = [
        html.escape(line) for line in (content or "").splitlines() if line.strip()
    ]
    respuesta_html = "".join(
        f"<p style='margin:0 0 12px 0;color:#333;font-size:14px;line-height:1.6;'>{line}</p>"
        for line in safe_lines
    )
    if respuesta_html:
        return respuesta_html
    return (
        "<p style='margin:0;color:#333;font-size:14px;line-height:1.6;'>"
        "Tu solicitud fue gestionada por el equipo de soporte."
        "</p>"
    )


def _build_ticket_url(ticket_id: str, ticket_url: str) -> str:
    if (ticket_url or "").strip():
        return ticket_url.strip()

    url_template = (
        os.getenv("ZOHO_DESK_TICKET_URL_TEMPLATE", "").strip()
        or _DEFAULT_TICKET_URL_TEMPLATE
    )
    safe_ticket_id = ticket_id or ""
    try:
        return url_template.format(ticket_id=safe_ticket_id)
    except (KeyError, ValueError):
        return f"{_DEFAULT_TICKET_URL_TEMPLATE.format(ticket_id=safe_ticket_id)}"


def _render_email_template(template: str, context: dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)
    return rendered


def _build_email_html(
    *,
    ticket_id: str,
    ticket_number: str,
    categoria: str,
    nombre_usuario: str,
    status_label: str,
    content: str,
    ticket_url: str,
) -> str:
    template = _load_email_template()
    context = {
        "ticket_id": html.escape(ticket_id or "N/A"),
        "ticket_number": html.escape(ticket_number or "N/A"),
        "categoria": html.escape(categoria or "Soporte general"),
        "nombre_usuario": html.escape(nombre_usuario or "Agente IA"),
        "status_label": html.escape(status_label or "Gestionado"),
        "ticket_url": html.escape(_build_ticket_url(ticket_id, ticket_url), quote=True),
        "respuesta_html": _build_respuesta_html(content),
    }
    return _render_email_template(template, context)


def _extract_text(result: Any) -> str:
    content = getattr(result, "content", None) or []
    chunks: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n".join(chunks)


def _parse_json_text(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _collect_emails(value: Any, found: list[str]) -> None:
    if isinstance(value, dict):
        for v in value.values():
            _collect_emails(v, found)
        return
    if isinstance(value, list):
        for item in value:
            _collect_emails(item, found)
        return
    if isinstance(value, str) and "@" in value and "." in value:
        email = value.strip()
        if email and email not in found:
            found.append(email)


def _pick_reply_from_email(payload: Any) -> str:
    # 1) Prefer explicit Zoho structure: {"data": [{"address": "..."}]}
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    address = str(item.get("address") or "").strip()
                    if address:
                        return address

    emails: list[str] = []
    _collect_emails(payload, emails)

    # Prefer Zoho Desk reply addresses when available.
    for email in emails:
        lower = email.lower()
        if "zohodesk.com" in lower or lower.startswith("support@"):
            return email

    return emails[0] if emails else ""


def _extract_status_value(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("status"),
        payload.get("statusType"),
        payload.get("state"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("label") or "").strip()
            if name:
                return name
    return ""


def _is_closed_status(status_value: str) -> bool:
    normalized = (status_value or "").strip().lower()
    if not normalized:
        return False
    closed_tokens = ("closed", "cerrad", "resolved", "resuelto")
    return any(token in normalized for token in closed_tokens)


async def consultar_estado_ticket(ticket_id: str, org_id: str) -> dict[str, Any]:
    ticket_id = (ticket_id or "").strip()
    org_id = (org_id or "").strip()

    if not ticket_id or not org_id:
        return {"status": "error", "detail": "parametros invalidos para consulta"}

    url = os.getenv("ZOHO_MCP_URL", "").strip()
    if not url:
        return {"status": "error", "detail": "ZOHO_MCP_URL no configurado"}

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    args = {
        "query_params": {"orgId": org_id},
        "path_variables": {"ticketId": ticket_id},
    }

    async with streamablehttp_client(url=url, headers=headers) as streams:
        read_stream, write_stream, _ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            ticket_result = await session.call_tool("ZohoDesk_getTicket", args)
            payload = _parse_json_text(_extract_text(ticket_result)) or {}
            if getattr(ticket_result, "isError", False):
                return {
                    "status": "failed",
                    "detail": "error al consultar ticket",
                    "result": payload or _extract_text(ticket_result),
                }
            status_value = _extract_status_value(
                payload if isinstance(payload, dict) else {}
            )
            return {
                "status": "ok",
                "ticket_status": status_value,
                "is_closed": _is_closed_status(status_value),
                "departmentId": str(payload.get("departmentId") or "")
                if isinstance(payload, dict)
                else "",
            }


async def publicar_comentario_ticket(
    ticket_id: str,
    org_id: str,
    content: str,
    is_public: bool = True,
) -> dict[str, Any]:
    ticket_id = (ticket_id or "").strip()
    org_id = (org_id or "").strip()
    content = (content or "").strip()

    if not ticket_id or not org_id or not content:
        return {"status": "error", "detail": "parametros invalidos para comentario"}

    url = os.getenv("ZOHO_MCP_URL", "").strip()
    if not url:
        return {"status": "error", "detail": "ZOHO_MCP_URL no configurado"}

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    args = {
        "query_params": {"orgId": org_id},
        "path_variables": {"ticketId": ticket_id},
        "body": {
            "content": content,
            "isPublic": is_public,
            "attachmentIds": [],
        },
    }

    async with streamablehttp_client(url=url, headers=headers) as streams:
        read_stream, write_stream, _ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("ZohoDesk_createTicketComment", args)
            return {
                "status": "ok" if not getattr(result, "isError", False) else "failed",
                "result": _extract_text(result),
            }


async def enviar_respuesta_por_correo_ticket(
    ticket_id: str,
    org_id: str,
    content: str,
    to_email: str,
    department_id: str = "",
    ticket_number: str = "",
    categoria: str = "",
    nombre_usuario: str = "Agente IA",
    status_label: str = "Gestionado",
    ticket_url: str = "",
) -> dict[str, Any]:
    ticket_id = (ticket_id or "").strip()
    org_id = (org_id or "").strip()
    content = (content or "").strip()
    to_email = (to_email or "").strip()

    if not ticket_id or not org_id or not content or not to_email:
        return {"status": "error", "detail": "parametros invalidos para correo"}

    url = os.getenv("ZOHO_MCP_URL", "").strip()
    if not url:
        return {"status": "error", "detail": "ZOHO_MCP_URL no configurado"}

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    args: dict[str, Any] = {
        "query_params": {"orgId": org_id},
        "path_variables": {"ticketId": ticket_id},
        "body": {
            "channel": "EMAIL",
            "to": to_email,
            "contentType": "html",
            "content": _build_email_html(
                ticket_id=ticket_id,
                ticket_number=ticket_number,
                categoria=categoria,
                nombre_usuario=nombre_usuario,
                status_label=status_label,
                content=content,
                ticket_url=ticket_url,
            ),
            "isForward": False,
        },
    }

    async with streamablehttp_client(url=url, headers=headers) as streams:
        read_stream, write_stream, _ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # Diagnostico previo: validar buzones de respuesta del departamento.
            dep_id = (department_id or "").strip()
            if not dep_id:
                ticket_args = {
                    "query_params": {"orgId": org_id},
                    "path_variables": {"ticketId": ticket_id},
                }
                ticket_result = await session.call_tool(
                    "ZohoDesk_getTicket", ticket_args
                )
                ticket_payload = _parse_json_text(_extract_text(ticket_result)) or {}
                if isinstance(ticket_payload, dict):
                    dep_id = str(ticket_payload.get("departmentId") or "").strip()

            if dep_id:
                mail_args = {
                    "query_params": {
                        "orgId": org_id,
                        "departmentId": dep_id,
                        "isActive": True,
                    }
                }
                mail_result = await session.call_tool(
                    "ZohoDesk_getReplyMailAddresses", mail_args
                )
                mail_payload = _parse_json_text(
                    _extract_text(mail_result)
                ) or _extract_text(mail_result)
                if getattr(mail_result, "isError", False):
                    return {
                        "status": "failed",
                        "detail": "no se pudo consultar buzones de salida del departamento",
                        "result": mail_payload,
                    }

                from_email = _pick_reply_from_email(mail_payload)
                if not from_email:
                    from_email = os.getenv(
                        "ZOHO_REPLY_FROM_EMAIL",
                        "support@corporaciontelecampus.zohodesk.com",
                    ).strip()
                if from_email:
                    args["body"]["fromEmailAddress"] = from_email
                else:
                    return {
                        "status": "failed",
                        "detail": "no se encontro fromEmailAddress activo para reply",
                        "result": mail_payload,
                    }
            else:
                from_email = os.getenv(
                    "ZOHO_REPLY_FROM_EMAIL",
                    "support@corporaciontelecampus.zohodesk.com",
                ).strip()
                if from_email:
                    args["body"]["fromEmailAddress"] = from_email
                else:
                    return {
                        "status": "failed",
                        "detail": "departmentId no disponible y no hay ZOHO_REPLY_FROM_EMAIL",
                    }

            result = await session.call_tool("ZohoDesk_sendReply", args)
            payload = _parse_json_text(_extract_text(result)) or _extract_text(result)
            logger.info(
                "PIPELINE_SEND_REPLY_RESULT status=%s ticket_id=%s from=%s to=%s",
                "ok" if not getattr(result, "isError", False) else "failed",
                ticket_id,
                args["body"].get("fromEmailAddress", ""),
                args["body"].get("to", ""),
            )
            return {
                "status": "ok" if not getattr(result, "isError", False) else "failed",
                "result": payload,
                "diagnostic": {
                    "departmentId": dep_id,
                    "fromEmailAddress": args["body"].get("fromEmailAddress", ""),
                },
            }


async def ejecutar_cierre_ticket_con_traza(
    ticket_id: str, org_id: str
) -> dict[str, Any]:
    ticket_id = (ticket_id or "").strip()
    org_id = (org_id or "").strip()

    if not ticket_id:
        return {"status": "error", "detail": "ticket_id vacio"}
    if not org_id:
        return {"status": "error", "detail": "org_id vacio"}

    url = os.getenv("ZOHO_MCP_URL", "").strip()
    if not url:
        return {"status": "error", "detail": "ZOHO_MCP_URL no configurado"}

    logger.info(
        "PIPELINE_DETERMINISTIC_CLOSE_START ticket_id=%s org_id=%s", ticket_id, org_id
    )

    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    start_comment_args = {
        "query_params": {"orgId": org_id},
        "path_variables": {"ticketId": ticket_id},
        "body": {
            "content": "Gestionado por IA: inicio de evaluacion de cierre",
            "isPublic": True,
            "attachmentIds": [],
        },
    }

    close_args = {
        "query_params": {"orgId": org_id},
        "body": {"ids": [ticket_id]},
    }

    async with streamablehttp_client(url=url, headers=headers) as streams:
        read_stream, write_stream, _ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            start_comment_result = await session.call_tool(
                "ZohoDesk_createTicketComment", start_comment_args
            )

            close_result = await session.call_tool("ZohoDesk_closeTickets", close_args)
            close_text = _extract_text(close_result)
            close_json = _parse_json_text(close_text)

            if getattr(close_result, "isError", False):
                reason = close_json.get("message") or close_text or "Error desconocido"
                fail_comment_args = {
                    "query_params": {"orgId": org_id},
                    "path_variables": {"ticketId": ticket_id},
                    "body": {
                        "content": f"No se pudo cerrar automaticamente: {reason}",
                        "isPublic": True,
                        "attachmentIds": [],
                    },
                }
                fail_comment_result = await session.call_tool(
                    "ZohoDesk_createTicketComment", fail_comment_args
                )
                result = {
                    "status": "failed",
                    "ticket_id": ticket_id,
                    "org_id": org_id,
                    "close_error": close_json or close_text,
                    "start_comment": _extract_text(start_comment_result),
                    "fail_comment": _extract_text(fail_comment_result),
                }
                logger.info(
                    "PIPELINE_DETERMINISTIC_CLOSE_END status=failed ticket_id=%s",
                    ticket_id,
                )
                return result

            success_comment_args = {
                "query_params": {"orgId": org_id},
                "path_variables": {"ticketId": ticket_id},
                "body": {
                    "content": "Cierre ejecutado por IA",
                    "isPublic": True,
                    "attachmentIds": [],
                },
            }
            success_comment_result = await session.call_tool(
                "ZohoDesk_createTicketComment", success_comment_args
            )

            result = {
                "status": "closed",
                "ticket_id": ticket_id,
                "org_id": org_id,
                "close_result": close_json or close_text,
                "start_comment": _extract_text(start_comment_result),
                "success_comment": _extract_text(success_comment_result),
            }
            logger.info(
                "PIPELINE_DETERMINISTIC_CLOSE_END status=closed ticket_id=%s", ticket_id
            )
            return result

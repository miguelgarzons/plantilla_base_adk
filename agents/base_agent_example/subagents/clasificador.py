from __future__ import annotations
import ast
import json
import logging
import os
import re as _re
from typing import Any

from google.adk.agents import LlmAgent
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .common import AgentDependencies
from .logging_hooks import log_after_agent
from .logging_hooks import log_before_agent

logger = logging.getLogger(__name__)


async def _zoho_call_tool(tool_name: str, args: dict) -> Any | None:
    url = os.getenv("ZOHO_MCP_URL", "").strip()
    if not url:
        logger.warning("ZOHO_MCP_URL no configurado")
        return None
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    try:
        async with streamablehttp_client(url=url, headers=headers) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await session.call_tool(tool_name, args)
    except Exception as exc:
        logger.error("ZOHO_CALL_ERROR tool=%s error=%s", tool_name, str(exc))
        return None


def _extract_text(result: Any) -> str:
    content = getattr(result, "content", None) or []
    chunks: list[str] = []
    for item in content:
        t = getattr(item, "text", None)
        if isinstance(t, str) and t.strip():
            chunks.append(t.strip())
    return "\n".join(chunks)


_HTML_TAG_RE = _re.compile(r"<[^>]*>")


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text).strip()


def _find_json_in_events(events: list[Any]) -> dict | None:
    for i, event in enumerate(events):
        content = getattr(event, "content", None)
        if content is None:
            logger.info("FIND_JSON_EVENT[%s] content=None", i)
            continue
        role = getattr(content, "role", "")
        if role == "model":
            logger.info("FIND_JSON_EVENT[%s] skip model", i)
            continue
        parts = getattr(content, "parts", None) or []
        logger.info("FIND_JSON_EVENT[%s] role=%s parts=%s", i, role, len(parts))
        for part in parts:
            text = getattr(part, "text", None)
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    logger.info("FIND_JSON_OK event[%s] keys=%s", i, list(parsed.keys())[:5])
                    return parsed
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, dict):
                        logger.info("FIND_AST_OK event[%s] keys=%s", i, list(parsed.keys())[:5])
                        return parsed
                except (ValueError, SyntaxError):
                    continue
    return None


async def _ensure_ticket_context(callback_context: Any) -> dict:
    ctx = callback_context.state.get("ticket_context", {})
    if isinstance(ctx, dict):
        tid = ctx.get("ticket_id", "")
        if tid:
            logger.info("ENSURE_CTX_FROM_STATE ticket_id=%s", tid)
            return ctx
        logger.info("ENSURE_CTX_STATE_EXISTE_SIN_TICKET_ID")
    else:
        logger.info("ENSURE_CTX_STATE_NO_DICT type=%s", type(ctx).__name__)

    events = getattr(getattr(callback_context, "session", None), "events", None)
    if not events:
        logger.warning("ENSURE_CTX_NO_EVENTS")
        return {}
    logger.info("ENSURE_CTX_EVENTS_COUNT=%s", len(events))
    parsed = _find_json_in_events(events)
    if not parsed:
        logger.warning("ENSURE_CTX_NO_JSON_IN_EVENTS")
        return {}
    tid = str(parsed.get("id", "")).strip()
    logger.info("ENSURE_CTX_PARSE_OK ticket_id=%s", tid)
    ctx = {
        "ticket_id": tid,
        "org_id": str(parsed.get("org_id") or os.getenv("ZOHO_ORG_ID", "")).strip(),
        "department_id": str(parsed.get("departmentId", "")).strip(),
        "status": str(parsed.get("status", "")).strip(),
        "subject": str(parsed.get("subject", "")).strip(),
        "description": _strip_html(str(parsed.get("description", ""))),
        "email": str(parsed.get("email", "")).strip(),
    }
    callback_context.state["ticket_context"] = ctx
    logger.info("TICKET_CONTEXT_ENSURE_OK ticket_id=%s", ctx["ticket_id"])
    return ctx


async def pre_clasificacion_callback(callback_context: Any = None, **_: Any) -> None:
    if callback_context is None:
        return None

    if callback_context.state.get("ticket_context"):
        return None

    parsed = None
    user_content = getattr(callback_context, "user_content", None)
    if user_content is not None:
        parts = getattr(user_content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    break
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, dict):
                        break
                except (ValueError, SyntaxError):
                    continue

    if parsed is None:
        events = getattr(getattr(callback_context, "session", None), "events", None)
        if events:
            parsed = _find_json_in_events(events)

    if parsed is None:
        logger.warning("PRE_CLASIFICACION_SKIP no se pudo parsear JSON")
        return None

    ticket_id = str(parsed.get("id", "")).strip()
    logger.info("PRE_CLASIFICACION_PARSE_OK ticket_id=%s keys=%s", ticket_id, list(parsed.keys())[:10])

    ctx = {
        "ticket_id": ticket_id,
        "org_id": str(parsed.get("org_id") or os.getenv("ZOHO_ORG_ID", "")).strip(),
        "department_id": str(parsed.get("departmentId", "")).strip(),
        "status": str(parsed.get("status", "")).strip(),
        "statusType": str(parsed.get("statusType", "")).strip(),
        "subject": str(parsed.get("subject", "")).strip(),
        "description": _strip_html(str(parsed.get("description", ""))),
        "email": str(parsed.get("email", "")).strip(),
        "contactId": str(parsed.get("contactId", "")).strip(),
    }
    cf = parsed.get("cf") or {}
    if isinstance(cf, dict):
        ctx["categoria"] = str(cf.get("cf_categoria", "")).strip()
        ctx["sub_categoria"] = str(cf.get("cf_sub_categorias", "")).strip()
        ctx["numero_de_documento"] = str(cf.get("cf_numero_de_documento", "")).strip()

    logger.info("TICKET_CONTEXT_EXTRAIDO ticket_id=%s subject=%s desc=%s", ctx["ticket_id"], ctx["subject"], ctx["description"][:80])
    callback_context.state["ticket_context"] = ctx
    return None


async def _find_mesa_servicio(org_id: str) -> str | None:
    logger.info("FIND_MESA_START org_id=%s", org_id)
    result = await _zoho_call_tool("ZohoDesk_getDepartments", {
        "query_params": {"orgId": org_id},
    })
    if result is None:
        return None
    try:
        raw = _extract_text(result)
        payload = json.loads(raw)
        data = payload.get("data", []) if isinstance(payload, dict) else []
        for dept in data:
            name = (dept.get("name", "") or "").strip().lower()
            if "mesa de servicio" in name:
                dept_id = str(dept.get("id", "")).strip()
                logger.info("MESA_SERVICIO_ENCONTRADA id=%s name=%s", dept_id, dept.get("name"))
                return dept_id
    except Exception as exc:
        logger.warning("FIND_MESA_ERROR %s", str(exc)[:200])
    logger.warning("FIND_MESA_NO_ENCONTRADA")
    return None


async def _get_agent_id(org_id: str) -> str | None:
    agent_id = os.getenv("SERVICE_DESK_AGENT_ID", "").strip()
    if agent_id:
        logger.info("AGENTE_USANDO_ENV id=%s", agent_id)
        return agent_id
    email = os.getenv("SERVICE_DESK_EMAIL", "mesadeayuda@cun.edu.co").strip()
    if not email:
        return None
    target = email.strip().lower()
    logger.info("FIND_AGENT_EMAIL_START email=%s org=%s", target, org_id)

    for source_name, tool_name, kwargs in [
        ("dept", "ZohoDesk_getAgentsInDepartment", {
            "query_params": {"orgId": org_id},
            "path_variables": {"departmentId": "474709000001472057"},
        }),
    ]:
        result = await _zoho_call_tool(tool_name, kwargs)
        if result is None:
            continue
        try:
            raw = _extract_text(result)
            payload = json.loads(raw) if raw else {}
            data = payload.get("data", []) if isinstance(payload, dict) else []
            for agent in data:
                agent_id = str(agent.get("id", "")).strip()
                agent_email = str(agent.get("emailId", "") or "").strip().lower()
                agent_name = agent.get("name", "")
                status = str(agent.get("status", "") or "").strip().lower()
                if agent_email == target and agent_id and status in ("active", "available", "online", ""):
                    logger.info("AGENTE_POR_EMAIL id=%s name=%s", agent_id, agent_name)
                    return agent_id
        except Exception as exc:
            logger.warning("FIND_AGENT_DEPT_ERROR %s", str(exc)[:200])

    result = await _zoho_call_tool("ZohoDesk_getAgents", {"query_params": {"orgId": org_id}})
    if result is not None:
        try:
            raw = _extract_text(result)
            payload = json.loads(raw) if raw else {}
            data = payload.get("data", []) if isinstance(payload, dict) else []
            for agent in data:
                agent_id = str(agent.get("id", "")).strip()
                agent_email = str(agent.get("emailId", "") or "").strip().lower()
                agent_name = agent.get("name", "")
                status = str(agent.get("status", "") or "").strip().lower()
                if agent_email == target and agent_id and status in ("active", "available", "online", ""):
                    logger.info("AGENTE_POR_EMAIL id=%s name=%s", agent_id, agent_name)
                    return agent_id
        except Exception as exc:
            logger.warning("FIND_AGENT_ALL_ERROR %s", str(exc)[:200])

    for tool_name, kwargs in [
        ("ZohoDesk_getUsers", {"query_params": {"orgId": org_id}}),
        ("ZohoDesk_getAgents", {"query_params": {"orgId": org_id}}),
    ]:
        result = await _zoho_call_tool(tool_name, kwargs)
        if result is None:
            continue
        try:
            raw = _extract_text(result)
            payload = json.loads(raw) if raw else {}
            data = payload.get("data", []) if isinstance(payload, dict) else []
            logger.info("FIND_%s_COUNT=%s", tool_name.replace("ZohoDesk_", ""), len(data))
            for agent in data:
                agent_id = str(agent.get("id", "")).strip()
                agent_email = str(agent.get("emailId", "") or agent.get("email", "") or "").strip().lower()
                agent_name = agent.get("name", "")
                status = str(agent.get("status", "") or "").strip().lower()
                logger.info("%s_CANDIDATO id=%s name=%s email=%s status=%s",
                            tool_name.replace("ZohoDesk_", ""), agent_id, agent_name, agent_email, status)
                if agent_email == target and agent_id:
                    logger.info("AGENTE_POR_EMAIL id=%s name=%s", agent_id, agent_name)
                    return agent_id
        except Exception as exc:
            logger.warning("FIND_%s_ERROR %s", tool_name.replace("ZohoDesk_", ""), str(exc)[:200])
        except Exception as exc:
            logger.warning("DEPT_DETAILS_ERROR %s", str(exc)[:200])

    logger.warning("AGENTE_NO_ENCONTRADO email=%s", target)
    return None


async def _extract_model_response(events: list[Any], author: str) -> tuple[str, str]:
    tipo = ""
    mensaje = ""
    for event in reversed(events):
        if getattr(event, "author", "") != author:
            continue
        content = getattr(event, "content", None)
        if content is None:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                full = text.strip()
                lines = full.split("\n", 1)
                tipo = lines[0].strip()
                if len(lines) > 1:
                    mensaje = lines[1].strip()
                break
    return tipo, mensaje


async def post_clasificacion_callback(callback_context: Any = None, **_: Any) -> None:
    if callback_context is None:
        return None

    tipo = ""
    mensaje = ""
    agent_name = getattr(callback_context, "agent_name", "")
    events = getattr(getattr(callback_context, "session", None), "events", None)
    if events is not None and agent_name:
        tipo, mensaje = await _extract_model_response(events, agent_name)
    if not tipo:
        tipo = str(callback_context.state.get("tipo_ticket", "")).strip()
    if tipo:
        callback_context.state["tipo_ticket"] = tipo

    ctx = await _ensure_ticket_context(callback_context)

    ticket_id = str(ctx.get("ticket_id", "")).strip()
    org_id = str(ctx.get("org_id") or os.getenv("ZOHO_ORG_ID", "")).strip()

    if not ticket_id or not org_id:
        logger.warning("POST_CLASIFICACION_SKIP reason=faltan_datos ticket_id=%s org_id=%s", ticket_id, org_id)
        return None

    logger.info("POST_CLASIFICACION_START tipo=%s ticket_id=%s", tipo, ticket_id)

    comentario = mensaje or f"Ticket clasificado como: {tipo}"

    if tipo in ("cambio_documento", "actualizacion_datos"):
        update_args = {
            "query_params": {"orgId": org_id},
            "path_variables": {"ticketId": ticket_id},
            "body": {"cf": {"cf_categoria": tipo}},
        }
        await _zoho_call_tool("ZohoDesk_updateTicket", update_args)
        logger.info("POST_CLASIFICACION_CATEGORIA_OK ticket_id=%s tipo=%s", ticket_id, tipo)

    elif tipo == "desconocido":
        dept_id = await _find_mesa_servicio(org_id)
        if dept_id:
            agent_id = await _get_agent_id(org_id)
            update_body: dict[str, Any] = {"departmentId": dept_id}
            if agent_id:
                update_body["assigneeId"] = agent_id
            result = await _zoho_call_tool("ZohoDesk_updateTicket", {
                "query_params": {"orgId": org_id},
                "path_variables": {"ticketId": ticket_id},
                "body": update_body,
            })
            logger.info("POST_CLASIFICACION_REASIGNADO_OK ticket_id=%s dept=%s agent=%s result=%s",
                        ticket_id, dept_id, agent_id,
                        str(result)[:200] if result else "OK")

    comment_args = {
        "query_params": {"orgId": org_id},
        "path_variables": {"ticketId": ticket_id},
        "body": {
            "content": comentario,
            "isPublic": True,
            "attachmentIds": [],
        },
    }
    await _zoho_call_tool("ZohoDesk_createTicketComment", comment_args)
    logger.info("POST_CLASIFICACION_COMENTARIO_OK ticket_id=%s tipo=%s", ticket_id, tipo)

    return None


def build_agente_clasificador(deps: AgentDependencies) -> LlmAgent:
    return LlmAgent(
        name="agente_clasificador",
        model=deps.model,
        before_agent_callback=[log_before_agent, pre_clasificacion_callback],
        after_agent_callback=[log_after_agent, post_clasificacion_callback],
        instruction="""
            Eres un asistente de soporte universitario que clasifica tickets y
            responde al usuario.

            El estado de sesion contiene la clave 'ticket_context' con un JSON
            que describe el ticket. Analiza los campos 'subject', 'description',
            'categoria' y 'sub_categoria' para determinar el tipo de solicitud.

            REGLA CRITICA: El campo 'description' tiene PRIORIDAD sobre 'subject'.
            Si 'description' es vacia, muy corta, generica, o contiene solo texto
            de prueba como "prueba", "test", "hola", "asdf", etc., clasifica como
            "desconocido" SIN IMPORTAR lo que diga el 'subject'.

            Categorias disponibles y sus criterios:

            "cambio_documento"
              - El estudiante solicita cambiar su tipo de documento de identidad.
              - Palabras clave: "cedula", "tarjeta de identidad", "cambio de documento",
                "actualizar documento", "T.I. a C.C.", "documento de identidad".

            "actualizacion_datos"
              - El estudiante solicita actualizar sus datos personales (direccion, telefono,
                correo, estado civil, nombre, etc.).
              - Palabras clave: "actualizar datos", "cambio de datos", "modificar datos",
                "datos personales", "actualizar direccion", "cambiar telefono",
                "actualizar correo".

            "cambio_genero"
              - El estudiante solicita actualizar su genero en el sistema.
              - Palabras clave: "cambio de genero", "cambio de genero",
                "actualizar genero", "actualizar genero", "a mujer", "a hombre".

            "notas"
              - El estudiante consulta, solicita revision o correccion de notas/calificaciones.
              - Palabras clave: "notas", "calificaciones", "nota", "materia",
                "revisar nota", "error en nota", "calificacion incorrecta".

            "desconocido"
              - La solicitud no encaja claramente en ninguna categoria anterior.
              - El contenido del ticket es insuficiente, incoherente o no contiene
                informacion util para gestionar (ej: "prueba", "test", "hola",
                texto sin sentido, descripcion muy corta o generica).

            FORMATO DE RESPUESTA:
            Primero escribe la categoria exacta en la PRIMERA LINEA.
            Luego una linea en blanco.
            Luego escribe tu mensaje de respuesta al usuario explicando
            brevemente que se hizo con su ticket.

            Ejemplo:
            actualizacion_datos

            Hola, hemos clasificado tu ticket como actualizacion de datos
            personales y se ha actualizado la categoria en el sistema.
        """,
        tools=[],
    )

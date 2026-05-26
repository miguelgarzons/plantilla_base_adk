from __future__ import annotations

import logging
import os

from ..integrations.mcp.config import load_mcp_servers


logger = logging.getLogger("adk.pipeline")


def estado_integracion_zoho() -> dict[str, str]:
    """Devuelve el estado de configuracion MCP para Zoho."""
    for server in load_mcp_servers():
        if server.name == "zoho":
            if not server.enabled:
                return {
                    "status": "disabled",
                    "detail": "Servidor Zoho deshabilitado en config/mcp/servers.yaml",
                }

            has_url = bool(
                server.url and "http" in server.url and "zohomcp.com" in server.url
            )
            if not has_url:
                return {
                    "status": "invalid",
                    "detail": "ZOHO_MCP_URL no esta configurado correctamente",
                }

            return {"status": "ok", "detail": "Servidor Zoho MCP configurado"}

    return {
        "status": "missing",
        "detail": "No existe servidor 'zoho' en config/mcp/servers.yaml",
    }


def guia_flujo_tickets_zoho() -> dict[str, list[str]]:
    """Guia operativa para consultar tickets Zoho desde el agente."""
    return {
        "flujo": [
            "1) Confirmar alcance: abiertos/cerrados, rango de fechas, departamento o contacto.",
            "2) Consultar tickets con zoho_listOfTickets o zoho_searchTickets segun el caso.",
            "3) Si hace falta detalle, ampliar con herramientas de ticket especificas (historial, comentarios, eventos).",
            "4) Entregar resumen operativo con prioridad, estado, asignado y proximos pasos.",
        ]
    }


def resolver_contexto_zoho(departamento: str = "") -> dict[str, str]:
    """Resuelve orgId y departmentId desde configuracion local para Zoho Desk."""
    logger.info(
        "PIPELINE_STEP resolver_contexto_zoho_start departamento=%s", departamento
    )
    org_id = os.getenv("ZOHO_ORG_ID", "").strip()
    if not org_id:
        logger.warning("PIPELINE_STEP resolver_contexto_zoho_missing_org")
        return {
            "status": "missing_org",
            "detail": "Falta ZOHO_ORG_ID en variables de entorno",
        }
    logger.info("PIPELINE_STEP resolver_contexto_zoho_org_ready")
    return {
        "status": "ok",
        "org_id": org_id,
        "department_id": "",
        "detail": "OrgId resuelto. DepartmentId se debe resolver por MCP en tiempo de ejecucion.",
    }

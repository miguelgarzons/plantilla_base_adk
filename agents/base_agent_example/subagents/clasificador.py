"""
Ejemplo de subagente clasificador usando LlmAgent con herramientas MCP de Zoho.

Este módulo muestra el patrón recomendado para crear un subagente que:
    1. Usa un LlmAgent con modelo Gemini
    2. Se conecta a herramientas MCP de Zoho Desk
    3. Tiene callbacks de logging para trazabilidad
    4. Recibe un prompt de instrucciones claro y estructurado

Adapta la instrucción del agente a tu caso de uso específico.
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent

from .common import AgentDependencies
from .logging_hooks import log_after_agent, log_before_agent

logger = logging.getLogger(__name__)


def build_agente_clasificador(deps: AgentDependencies) -> LlmAgent:
    """
    Construye un LlmAgent de ejemplo que clasifica tickets de Zoho Desk.

    El agente tiene acceso a las herramientas MCP de Zoho configuradas
    en `config/mcp/servers.yaml` y filtradas en `common.py`.

    Args:
        deps: Dependencias compartidas (modelo, toolsets MCP).

    Returns:
        LlmAgent configurado y listo para usar en un SequentialAgent.
    """
    return LlmAgent(
        name="agente_clasificador",
        model=deps.model,
        before_agent_callback=log_before_agent,
        after_agent_callback=log_after_agent,
        instruction="""
            Eres un asistente de soporte que clasifica tickets y
            responde al usuario.

            Usa las herramientas de Zoho Desk disponibles para consultar
            información de tickets, departamentos y organizaciones.

            Analiza el contexto del ticket (subject, description) para
            determinar la categoría de la solicitud.

            Categorías disponibles:
            - "soporte_tecnico": problemas técnicos, errores, fallos
            - "consulta_general": preguntas de información general
            - "solicitud_cambio": solicitudes de modificación de datos
            - "desconocido": no se puede clasificar con la información disponible

            FORMATO DE RESPUESTA:
            1. Escribe la categoría exacta en la PRIMERA LÍNEA.
            2. Luego una línea en blanco.
            3. Luego escribe tu mensaje al usuario explicando brevemente
               qué se hizo con su ticket.

            Ejemplo:
            soporte_tecnico

            Hola, hemos clasificado tu ticket como soporte técnico
            y se ha asignado al equipo correspondiente.
        """,
        tools=deps.receptor_mcp_toolsets,
    )

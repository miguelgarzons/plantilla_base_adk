"""
Subagente respondedor final.

Toma la clasificación del clasificador y los datos enriquecidos del ADK 2
(obtenidos via A2A) y genera una respuesta final coherente para el usuario.

Este es el último paso del SequentialAgent: combina toda la información
recopilada por los subagentes anteriores en una respuesta útil.
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent

from .common import AgentDependencies
from .logging_hooks import log_after_agent, log_before_agent

logger = logging.getLogger(__name__)


def build_agente_respondedor(deps: AgentDependencies) -> LlmAgent:
    """Construye un LlmAgent que genera la respuesta final al usuario.

    Combina la clasificación del ticket (paso 1) y los datos
    enriquecidos del ADK 2 (paso 2) para elaborar una respuesta
    completa.

    Args:
        deps: Dependencias compartidas (modelo, toolsets MCP).

    Returns:
        LlmAgent configurado como respondedor final.
    """
    return LlmAgent(
        name="agente_respondedor",
        model=deps.model,
        before_agent_callback=log_before_agent,
        after_agent_callback=log_after_agent,
        instruction="""
            Eres el agente respondedor final del pipeline de soporte.

            Has recibido información de dos fuentes previas:
            1. **Clasificador**: Categorizó el ticket del usuario.
            2. **Enriquecimiento (ADK remoto)**: Proporcionó datos
               complementarios como historial del cliente, prioridad
               sugerida y artículos de la base de conocimiento.

            Tu trabajo es:
            1. Revisar TODA la información proporcionada por los
               agentes anteriores en la conversación.
            2. Generar una respuesta FINAL clara y profesional para
               el usuario que incluya:
               - Confirmación de la categoría del ticket
               - Prioridad asignada y justificación
               - Artículos de ayuda relevantes (si los hay)
               - Próximos pasos recomendados

            IMPORTANTE:
            - Sé conciso pero completo.
            - Usa un tono profesional y amable.
            - No inventes información que no haya sido proporcionada.
            - Si falta información de algún paso anterior, menciónalo.
        """,
        tools=[],
    )

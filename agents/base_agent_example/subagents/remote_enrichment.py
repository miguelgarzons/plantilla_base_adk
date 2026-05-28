"""
Subagente remoto que consume el agente de enriquecimiento (ADK 2) vía A2A.

Este módulo crea un RemoteA2aAgent que actúa como proxy transparente
hacia el agente de enriquecimiento que corre como servicio independiente.

Cuando el SequentialAgent lo ejecuta:
    1. Toma el resultado del subagente anterior (ej: clasificación)
    2. Lo envía al ADK 2 via protocolo A2A (HTTP)
    3. El ADK 2 ejecuta su flujo completo (historial, prioridad, KB)
    4. Devuelve el resultado enriquecido
    5. El SequentialAgent continúa con el siguiente subagente

Ejemplo de uso en orchestrator.py:
    from .remote_enrichment import build_agente_enriquecimiento_remoto

    sub_agents=[
        build_agente_clasificador(deps),
        build_agente_enriquecimiento_remoto(),   # ← Llama al ADK 2
        build_agente_respondedor(deps),
    ]
"""

from __future__ import annotations

import logging
import os

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

logger = logging.getLogger(__name__)


def build_agente_enriquecimiento_remoto() -> RemoteA2aAgent:
    """Construye un RemoteA2aAgent que invoca al agente de enriquecimiento.

    El agente se conecta al Agent Card del servicio de enriquecimiento
    (ADK 2) y actúa como un subagente normal dentro del SequentialAgent.

    La URL del Agent Card se configura via variable de entorno
    ``REMOTE_ENRICHMENT_AGENT_CARD_URL``.

    Returns:
        RemoteA2aAgent configurado y listo para usar.
    """
    agent_card_url = os.getenv(
        "REMOTE_ENRICHMENT_AGENT_CARD_URL",
        "http://localhost:8002/.well-known/agent.json",
    )

    logger.info(
        "Configurando RemoteA2aAgent (enriquecimiento) → %s",
        agent_card_url,
    )

    return RemoteA2aAgent(
        name="agente_enriquecimiento_remoto",
        description=(
            "Proxy hacia el agente de enriquecimiento (ADK 2). "
            "Recibe la clasificación del ticket y devuelve datos "
            "enriquecidos: historial del cliente, prioridad sugerida "
            "y artículos de la base de conocimiento."
        ),
        agent_card=agent_card_url,
        timeout=120.0,
    )

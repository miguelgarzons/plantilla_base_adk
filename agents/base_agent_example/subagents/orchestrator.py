"""
Orquestador principal del agente.

Construye el SequentialAgent raíz que ejecuta los subagentes en orden.

Pipeline actual:
    1. agente_clasificador       — Clasifica el ticket del usuario
    2. agente_enriquecimiento    — (REMOTO via A2A) Enriquece con historial,
                                   prioridad y artículos KB
    3. agente_respondedor        — Genera la respuesta final al usuario

Para agregar un nuevo subagente:
    1. Crea el archivo en subagents/ (usa clasificador.py como referencia)
    2. Importa su builder aquí
    3. Agrégalo a la lista sub_agents en el orden deseado
"""

from __future__ import annotations

from google.adk.agents import SequentialAgent

from .clasificador import build_agente_clasificador
from .common import build_dependencies
from .logging_hooks import log_after_agent, log_before_agent
from .remote_enrichment import build_agente_enriquecimiento_remoto
from .respondedor import build_agente_respondedor


def build_root_agent() -> SequentialAgent:
    """Construye el agente raíz (SequentialAgent) con todos los subagentes.

    El flujo secuencial es:
        clasificador → enriquecimiento (ADK 2 remoto via A2A) → respondedor
    """
    deps = build_dependencies()

    return SequentialAgent(
        name="agente_principal",
        description=(
            "Orquestador secuencial que ejecuta subagentes en orden. "
            "Clasifica tickets, los enriquece via un agente remoto A2A, "
            "y genera una respuesta final."
        ),
        before_agent_callback=log_before_agent,
        after_agent_callback=log_after_agent,
        sub_agents=[
            build_agente_clasificador(deps),
            build_agente_enriquecimiento_remoto(),   # ← ADK 2 via A2A
            build_agente_respondedor(deps),
            # ← Agrega más subagentes aquí en el orden deseado
        ],
    )

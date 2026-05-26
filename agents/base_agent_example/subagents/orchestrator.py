"""
Orquestador principal del agente.

Construye el SequentialAgent raíz que ejecuta los subagentes en orden.
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


def build_root_agent() -> SequentialAgent:
    """Construye el agente raíz (SequentialAgent) con todos los subagentes."""
    deps = build_dependencies()

    return SequentialAgent(
        name="agente_principal",
        description=(
            "Orquestador secuencial que ejecuta subagentes en orden. "
            "Agrega tus subagentes a la lista sub_agents."
        ),
        before_agent_callback=log_before_agent,
        after_agent_callback=log_after_agent,
        sub_agents=[
            build_agente_clasificador(deps),
            # ← Agrega más subagentes aquí en el orden deseado
            # build_mi_otro_subagente(deps),
        ],
    )

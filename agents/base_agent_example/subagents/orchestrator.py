from __future__ import annotations

from google.adk.agents import SequentialAgent

from .cambio_documento import build_agente_cambio_documento
from .cambio_genero import build_agente_cambio_genero
from .cierre import build_agente_cierre_ticket
from .clasificador import build_agente_clasificador
from .common import build_dependencies
from .logging_hooks import log_after_agent, log_before_agent
from .receptor import build_agente_receptor_ingesta  # ← faltaba este import


def build_root_agent() -> SequentialAgent:
    deps = build_dependencies()

    return SequentialAgent(
        name="agente_mesa_ayuda",
        description="Orquestador para tickets Zoho:recategorizacion segun el cotexto del ticket y la información adicional proporcionada por el usuario.",
        before_agent_callback=log_before_agent,
        after_agent_callback=log_after_agent,
        sub_agents=[

            build_agente_clasificador(deps),  

        ],
    )

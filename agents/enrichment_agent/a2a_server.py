"""
Servidor A2A para el agente de enriquecimiento (ADK 2).

Este script expone el agente de enriquecimiento como un servicio
A2A independiente usando to_a2a(), que auto-genera el Agent Card
en /.well-known/agent.json.

Uso:
    uvicorn enrichment_agent.a2a_server:app --host 0.0.0.0 --port 8002
"""

import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent

# Hostname que se anuncia en el Agent Card para que otros servicios
# sepan cómo contactar a este agente.  Dentro de Docker el host
# debe ser el nombre del servicio (ej: adk-enrichment),
# NO localhost, porque localhost dentro de otro contenedor apunta
# a sí mismo y la conexión falla con HTTP 503.
a2a_host = os.getenv("A2A_HOST", "adk-enrichment")

app = to_a2a(root_agent, host=a2a_host, port=8002)

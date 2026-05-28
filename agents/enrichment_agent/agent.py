"""
Agente de enriquecimiento (ADK 2).

Este agente recibe la clasificación de un ticket realizada por el ADK 1,
busca información complementaria y devuelve datos enriquecidos que el
ADK 1 puede usar para continuar su flujo.

Se expone como servicio A2A independiente y es consumido por el ADK 1
a través de RemoteA2aAgent.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.models import Gemini


# ── Herramientas locales del agente de enriquecimiento ──────────


def buscar_historial_cliente(cliente_id: str) -> dict:
    """Busca el historial de soporte de un cliente dado su ID.

    Args:
        cliente_id: Identificador del cliente (ej: "CLT-001").

    Returns:
        Diccionario con el historial de tickets previos del cliente.
    """
    # Simulación — en producción esto consultaría una base de datos
    historial = {
        "CLT-001": {
            "cliente_id": "CLT-001",
            "nombre": "Universidad Nacional",
            "tickets_previos": 12,
            "ultimo_ticket": "2026-05-20",
            "nivel_satisfaccion": "alto",
            "temas_frecuentes": ["acceso plataforma", "certificados"],
        },
        "CLT-002": {
            "cliente_id": "CLT-002",
            "nombre": "Instituto Técnico Central",
            "tickets_previos": 5,
            "ultimo_ticket": "2026-05-15",
            "nivel_satisfaccion": "medio",
            "temas_frecuentes": ["facturación", "soporte técnico"],
        },
    }
    return historial.get(
        cliente_id,
        {
            "cliente_id": cliente_id,
            "nombre": "Cliente no encontrado",
            "tickets_previos": 0,
            "ultimo_ticket": None,
            "nivel_satisfaccion": "desconocido",
            "temas_frecuentes": [],
        },
    )


def obtener_prioridad_sugerida(categoria: str, tickets_previos: int) -> dict:
    """Sugiere una prioridad para el ticket basándose en la categoría y el historial.

    Args:
        categoria: Categoría del ticket (ej: "soporte_tecnico").
        tickets_previos: Número de tickets previos del cliente.

    Returns:
        Diccionario con la prioridad sugerida y la justificación.
    """
    # Lógica de priorización simple
    if categoria == "soporte_tecnico" and tickets_previos > 10:
        return {
            "prioridad": "alta",
            "justificacion": (
                "Cliente recurrente con problema técnico. "
                "Alta probabilidad de escalamiento."
            ),
        }
    elif categoria == "soporte_tecnico":
        return {
            "prioridad": "media",
            "justificacion": "Problema técnico estándar.",
        }
    elif categoria == "solicitud_cambio":
        return {
            "prioridad": "media",
            "justificacion": "Solicitud de cambio requiere revisión.",
        }
    else:
        return {
            "prioridad": "baja",
            "justificacion": "Consulta general sin urgencia detectada.",
        }


def buscar_articulos_kb(tema: str) -> dict:
    """Busca artículos relevantes en la base de conocimiento.

    Args:
        tema: Tema o palabras clave para buscar (ej: "acceso plataforma").

    Returns:
        Diccionario con artículos relevantes encontrados.
    """
    # Simulación de una base de conocimiento
    kb = {
        "acceso plataforma": [
            {
                "id": "KB-101",
                "titulo": "Cómo restablecer contraseña",
                "url": "https://kb.ejemplo.com/KB-101",
            },
            {
                "id": "KB-102",
                "titulo": "Problemas de acceso frecuentes",
                "url": "https://kb.ejemplo.com/KB-102",
            },
        ],
        "certificados": [
            {
                "id": "KB-201",
                "titulo": "Solicitud de certificados académicos",
                "url": "https://kb.ejemplo.com/KB-201",
            },
        ],
        "facturación": [
            {
                "id": "KB-301",
                "titulo": "Proceso de facturación electrónica",
                "url": "https://kb.ejemplo.com/KB-301",
            },
        ],
    }
    return {
        "tema_buscado": tema,
        "articulos": kb.get(
            tema,
            [
                {
                    "id": "KB-000",
                    "titulo": "Artículo genérico de ayuda",
                    "url": "https://kb.ejemplo.com/KB-000",
                }
            ],
        ),
    }


# ── Definición del agente ───────────────────────────────────────

model_name = os.getenv("AGENT_MODEL", "gemini-2.5-pro")
if model_name.startswith("gemini/"):
    model_name = model_name.split("/", 1)[1]

root_agent = LlmAgent(
    name="agente_enriquecimiento",
    model=Gemini(model=model_name),
    description=(
        "Agente de enriquecimiento de tickets. Recibe la clasificación "
        "de un ticket y devuelve información complementaria: historial "
        "del cliente, prioridad sugerida y artículos de la base de "
        "conocimiento relevantes."
    ),
    instruction="""
        Eres un agente de enriquecimiento de datos de soporte.

        Recibirás información sobre un ticket clasificado por otro agente.
        Tu trabajo es:

        1. Usar la herramienta `buscar_historial_cliente` para obtener
           el historial del cliente. Si no recibes un ID de cliente,
           usa "CLT-001" como ejemplo.

        2. Usar `obtener_prioridad_sugerida` con la categoría del ticket
           y el número de tickets previos del cliente.

        3. Usar `buscar_articulos_kb` para encontrar artículos relevantes
           de la base de conocimiento basándote en el tema del ticket.

        4. Responder con un resumen estructurado que incluya:
           - Datos del cliente
           - Prioridad sugerida con justificación
           - Artículos de KB relevantes
           - Recomendación de acción

        FORMATO DE RESPUESTA:
        Escribe un resumen claro y estructurado con toda la información
        enriquecida. Usa listas y secciones para organizar los datos.
    """,
    tools=[
        buscar_historial_cliente,
        obtener_prioridad_sugerida,
        buscar_articulos_kb,
    ],
)

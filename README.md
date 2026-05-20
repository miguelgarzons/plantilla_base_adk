# Agentes de Servicio (ADK)

Proyecto de agentes basado en Google ADK para automatizar la gestion de tickets Zoho Desk.

## Stack

- Python
- Google ADK (Agent Development Kit)
- Gemini (via `google.genai`)
- MCP remoto para Zoho Desk
- Docker / Docker Compose

## Estructura actual

```text
.
├── agents/
│   └── categorizador/
│       ├── agent.py                           # root_agent
│       ├── subagents/
│       │   ├── orchestrator.py                # SequentialAgent principal
│       │   ├── receptor.py                    # parse JSON + clasificacion inicial
│       │   ├── clasificador.py                # clasificador LLM (apoyo)
│       │   ├── cambio_documento.py            # flujo condicional de cambio de doc
│       │   ├── cambio_genero.py               # flujo condicional de cambio de genero
│       │   ├── cierre.py                      # cierre, comentario y reply email
│       │   ├── common.py                      # dependencias y modelo
│       │   └── logging_hooks.py               # trazas de pipeline y tools
│       ├── tools/
│       │   ├── zoho_actions.py                # cierre deterministico y sendReply
│       │   ├── zoho_attachments.py            # lectura/descarga de adjuntos
│       │   ├── student_profile.py             # API de perfil estudiante
│       │   └── cedula_verifier.py             # verificacion de imagenes
│       ├── templates/
│       │   └── ticket_reply_email.html        # plantilla HTML correo de cierre
│       └── integrations/mcp/
│           ├── config.py
│           └── toolset_factory.py
├── config/
│   └── mcp/servers.yaml                       # catalogo de servidores MCP
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Arquitectura ADK que usamos

El `root_agent` se construye en `agents/categorizador/agent.py` y usa un `SequentialAgent` en `agents/categorizador/subagents/orchestrator.py`.

Orden actual de ejecucion:

1. `agente_receptor_ingesta`
   - Parsea el JSON del ticket Zoho.
   - Valida campos obligatorios (`id`, `departmentId`, `ZOHO_ORG_ID`).
   - Escribe `ticket_context` y `tipo_ticket` en `session.state`.
2. `agente_clasificador`
   - Reafirma tipo de ticket (`cambio_documento`, `notas`, `desconocido`).
3. `agente_cambio_documento`
   - Solo actua si `tipo_ticket == "cambio_documento"`.
   - Verifica adjuntos de cedula y actualiza tipo de documento del estudiante.
4. `agente_cambio_genero`
   - Solo actua si `tipo_ticket == "cambio_genero"`.
   - Consulta perfil del estudiante y actualiza genero objetivo (F/M).
5. `agente_cierre_ticket`
   - Ejecuta cierre deterministico en Zoho.
   - Publica comentario de cierre.
   - Envia correo via `ZohoDesk_sendReply` cuando aplica.
   - Evita duplicados con guardas de estado e inspeccion de ticket cerrado.

## Variables de entorno

Configura un `.env` en la raiz.

```env
# Modelo Gemini
AGENT_MODEL=gemini-2.5-pro
GEMINI_API_KEY=tu_gemini_api_key

# Zoho MCP
ZOHO_MCP_URL=https://adk-xxxx.zohomcp.com/mcp/<token>/message
ZOHO_ORG_ID=tu_org_id

# Reply por email en cierre
ZOHO_SEND_REPLY_ENABLED=true
ZOHO_REPLY_FROM_EMAIL=support@tu_dominio.zohodesk.com
ZOHO_DESK_TICKET_URL_TEMPLATE=https://desk.zoho.com/agent/tu_portal/tickets/{ticket_id}

# Perfil estudiante (cambio de genero)
STUDENT_PROFILE_GENDER_FIELD=gender
```

Notas:

- Si `ZOHO_MCP_URL` no esta configurado, las acciones MCP no se pueden ejecutar.
- `fromEmailAddress` se resuelve primero con `ZohoDesk_getReplyMailAddresses` y usa fallback en `ZOHO_REPLY_FROM_EMAIL`.

## Ejecucion local

```bash
docker-compose up --build
```

Servicios principales:

- `adk-dev` en `http://localhost:8000` (`adk web`)
- `adk-api` en `http://localhost:8001` (`adk api_server`)

## Flujo de cierre (resumen)

- Consulta estado actual del ticket para no repetir acciones en casos ya cerrados.
- Si corresponde, ejecuta `ZohoDesk_closeTickets`.
- Publica comentario publico de cierre.
- Envia email HTML con plantilla `templates/ticket_reply_email.html`.
- Registra trazas con prefijo `PIPELINE_*` para diagnostico en produccion.

Eventos de log utiles:

- `PIPELINE_CIERRE_CALLBACK_ENTER`
- `PIPELINE_CIERRE_SKIP_ALREADY_CLOSED`
- `PIPELINE_CIERRE_PUBLIC_COMMENT`
- `PIPELINE_CIERRE_EMAIL_REPLY`
- `PIPELINE_SEND_REPLY_RESULT`

## Referencias

- ADK docs: https://google.github.io/adk-docs/
- Gemini API docs: https://ai.google.dev/

## Skills reutilizables

Se agrego el directorio `skills/` para portar el comportamiento del proyecto a otros modelos.

- `skills/helpdesk_zoho_cierre/skill.yaml`
- `skills/helpdesk_zoho_cierre/prompt_template.md`
- `skills/helpdesk_zoho_cierre/examples.json`
- `skills/adk_helpdesk_project_builder/skill.yaml`
- `skills/adk_helpdesk_project_builder/prompt_template.md`
- `skills/adk_helpdesk_project_builder/example_input.json`
- `skills/adk_helpdesk_project_builder_v2/skill.yaml`
- `skills/adk_helpdesk_project_builder_v2/prompt_template.md`
- `skills/adk_helpdesk_project_builder_v2/file_map_template.json`
- `skills/adk_helpdesk_project_builder_v2/checklist.md`

Guia general: `skills/README.md`.

# Plantilla Base ADK (Agent Development Kit)

Plantilla lista para clonar y construir agentes de IA con [Google ADK](https://adk.dev/), integración Zoho Desk via MCP, Docker y buenas prácticas.

## Stack

- **Python 3.11+**
- **Google ADK** — framework para agentes de IA
- **Gemini** — modelo LLM (configurable via env)
- **MCP** — protocolo de conexión a herramientas externas (Zoho Desk)
- **Docker / Docker Compose**

---

## Estructura del proyecto

```text
.
├── agents/
│   └── base_agent_example/              ← Tu agente (renombra según tu proyecto)
│       ├── __init__.py
│       ├── agent.py                     # Entry point: define root_agent
│       ├── subagents/
│       │   ├── __init__.py
│       │   ├── orchestrator.py          # SequentialAgent orquestador
│       │   ├── clasificador.py          # Ejemplo: LlmAgent con Zoho MCP
│       │   ├── common.py               # Modelo + dependencias compartidas
│       │   └── logging_hooks.py         # Hooks de trazabilidad (before/after)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── zoho_tools.py            # Herramientas Zoho (estado, guía, contexto)
│       │   ├── zoho_attachments.py      # Lectura de adjuntos Zoho (REST API)
│       │   ├── student_profile.py       # Ejemplo: tool de API REST autenticada
│       │   └── cedula_verifier.py       # Ejemplo: tool de visión multimodal
│       └── integrations/
│           └── mcp/
│               ├── __init__.py
│               ├── config.py            # Loader de config YAML → McpServerConfig
│               └── toolset_factory.py   # Factory que crea MCP toolsets
├── config/
│   └── mcp/
│       └── servers.yaml                 # Catálogo de servidores MCP
├── .env.example                         # ← Variables de entorno (copiar a .env)
├── .gitignore
├── .dockerignore
├── Dockerfile                           # Multi-stage: dev + runtime
├── docker-compose.yml                   # adk-dev (web) + adk-api (api_server)
├── requirements.txt
└── README.md
```

---

## Inicio rápido

### 1. Clonar y configurar

```bash
git clone <url-del-repo>
cd plantilla_base_adk

# Crear tu archivo de variables de entorno
cp .env.example .env
# Editar .env con tus credenciales reales
```

### 2. Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|:-----------:|-------------|
| `GEMINI_API_KEY` | ✅ | API key de Google Gemini |
| `AGENT_MODEL` | ❌ | Modelo LLM a usar (default: `gemini-2.5-pro`) |
| `ZOHO_MCP_URL` | ✅ | URL del servidor MCP de Zoho |
| `ZOHO_ORG_ID` | ✅ | ID de la organización en Zoho Desk |
| `ZOHO_DESK_BASE_URL` | ❌ | URL base de Zoho Desk API (default: `https://desk.zoho.com/api/v1`) |
| `ZOHO_TOKEN_WEBHOOK_*` | ❌ | Credenciales para webhook de token (solo si usas `zoho_attachments.py`) |
| `EXTERNAL_API_*` | ❌ | Credenciales para API externa (solo si usas `student_profile.py`) |

### 3. Ejecutar con Docker

```bash
# Desarrollo (con hot-reload de archivos)
docker-compose up --build adk-dev

# Modo API (para producción / integraciones)
docker-compose up --build adk-api
```

| Servicio | URL | Descripción |
|----------|-----|-------------|
| `adk-dev` | `http://localhost:8000` | Interfaz web de ADK (chat interactivo) |
| `adk-api` | `http://localhost:8001` | API REST del agente |

### 4. Ejecutar sin Docker

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt

cd agents
adk web . --port 8000
```

---

## Arquitectura ADK

```text
┌─────────────────────────────────────────┐
│           root_agent (agent.py)         │
│                                         │
│  SequentialAgent (orchestrator.py)       │
│  ├── agente_clasificador                │
│  ├── (tu siguiente subagente)           │
│  └── (...)                              │
│                                         │
│  Tools:                                 │
│  ├── zoho_tools.py (Zoho helpers)       │
│  ├── zoho_attachments.py (REST API)     │
│  ├── student_profile.py (API ejemplo)   │
│  └── cedula_verifier.py (visión)        │
│                                         │
│  MCP:                                   │
│  └── Zoho Desk (config/mcp/servers.yaml)│
└─────────────────────────────────────────┘
```

### Conceptos clave de ADK

| Concepto | Qué es | Dónde está |
|----------|--------|------------|
| **root_agent** | El agente principal que ADK busca al arrancar | `agent.py` |
| **SequentialAgent** | Orquestador que ejecuta subagentes en orden | `orchestrator.py` |
| **LlmAgent** | Agente que usa un LLM (Gemini) con instrucciones | `clasificador.py` |
| **BaseAgent** | Agente custom en Python puro (sin LLM) | `cedula_verifier.py` |
| **Tools** | Funciones Python que el agente puede invocar | `tools/` |
| **MCP Toolset** | Herramientas externas conectadas via protocolo MCP | `integrations/mcp/` |
| **Callbacks** | Hooks before/after para logging y side-effects | `logging_hooks.py` |

---

## Guías para desarrolladores

### Agregar un nuevo subagente

1. Crea un archivo en `subagents/`, ejemplo: `subagents/mi_agente.py`

```python
from google.adk.agents import LlmAgent
from .common import AgentDependencies
from .logging_hooks import log_before_agent, log_after_agent


def build_mi_agente(deps: AgentDependencies) -> LlmAgent:
    return LlmAgent(
        name="mi_agente",
        model=deps.model,
        before_agent_callback=log_before_agent,
        after_agent_callback=log_after_agent,
        instruction="Tu instrucción aquí...",
        tools=[],  # o deps.receptor_mcp_toolsets para herramientas Zoho
    )
```

2. Agrégalo al orquestador en `orchestrator.py`:

```python
from .mi_agente import build_mi_agente

# Dentro de build_root_agent():
sub_agents=[
    build_agente_clasificador(deps),
    build_mi_agente(deps),  # ← nuevo
]
```

### Agregar una nueva herramienta (tool)

1. Crea una función en `tools/`:

```python
# tools/mi_herramienta.py

def consultar_clima(ciudad: str) -> dict:
    """Consulta el clima de una ciudad."""
    # Tu lógica aquí
    return {"ciudad": ciudad, "temperatura": "22°C"}
```

2. Asígnala al agente que la necesite:

```python
from base_agent_example.tools.mi_herramienta import consultar_clima

LlmAgent(
    name="mi_agente",
    tools=[consultar_clima],  # ADK la registra automáticamente
    ...
)
```

### Agregar un nuevo servidor MCP

Edita `config/mcp/servers.yaml`:

```yaml
servers:
  zoho:
    # ... (ya existente)

  mi_servicio:
    enabled: true
    transport: streamable_http
    url: ${MI_SERVICIO_MCP_URL}
    headers: {}
    env: {}
    timeout_seconds: 20
    max_tools: 50
    required_tool_names: []
    include_name_patterns:
      - "MiServicio_.*"
    tool_name_prefix: mi_servicio
```

Y agrega `MI_SERVICIO_MCP_URL` en tu `.env`.

### Usar callbacks para side-effects

```python
async def mi_callback(callback_context=None, **_):
    """Se ejecuta antes o después de un agente."""
    if callback_context is None:
        return None

    # Leer del estado
    datos = callback_context.state.get("mi_clave", {})

    # Escribir al estado
    callback_context.state["resultado"] = "procesado"

    return None  # Retornar None para continuar el flujo

# Uso:
LlmAgent(
    before_agent_callback=[log_before_agent, mi_callback],
    ...
)
```

---

## Patrones incluidos como ejemplo

| Archivo | Patrón | Descripción |
|---------|--------|-------------|
| `clasificador.py` | LlmAgent + MCP | Agente con LLM que usa herramientas externas via MCP |
| `student_profile.py` | REST API autenticada | Tool que consume API REST con Bearer token y retry en 401 |
| `cedula_verifier.py` | Visión multimodal | BaseAgent + LlmAgent para analizar imágenes con Gemini |
| `zoho_attachments.py` | REST API + webhook auth | Descarga de archivos con token obtenido de webhook |
| `zoho_tools.py` | Tools síncronas | Funciones helper que no requieren async |
| `logging_hooks.py` | Callbacks | Hooks de trazabilidad para debugging |

---

## Referencias

- [ADK Documentation](https://adk.dev/)
- [ADK Python GitHub](https://github.com/google/adk-python)
- [Gemini API](https://ai.google.dev/)
- [MCP Protocol](https://modelcontextprotocol.io/)

Actua como arquitecto senior de proyectos ADK y entrega una propuesta ejecutable.

Datos de entrada:
- Objetivo: {{objective}}
- Modo: {{operation_mode}}
- Stack: {{target_stack}}
- Dominio: {{domain}}
- Nombre de app: {{app_name}}
- Sistemas externos: {{external_systems}}
- Restricciones: {{constraints}}
- Entornos: {{environments}}
- Requisitos no funcionales: {{non_functional_requirements}}

Arquitectura de referencia obligatoria:
- root_agent tipo SequentialAgent
- receptor_ingesta (parseo y validacion)
- clasificador
- subagentes condicionales de negocio
- cierre o confirmacion final
- tools desacopladas para side-effects
- templates separadas
- config por entorno

Reglas obligatorias:
1) No diseño monolitico.
2) No side-effects en prompts; todo side-effect en tools.
3) Definir idempotencia para evitar duplicados.
4) Definir logs estructurados por etapa (`PIPELINE_*`).
5) Definir fallback/retry para APIs y modelo.
6) Separar codigo por capas y responsabilidades.
7) Incluir contratos claros de entrada/salida.

Salida obligatoria (en este orden):
1. Arquitectura
2. Estructura de carpetas
3. Contratos de entrada/salida
4. Plan de implementacion por fases
5. File plan (archivos a crear/editar por fase)
6. Acceptance checks
7. Plan de pruebas
8. Runbook de despliegue

El file plan debe incluir rutas completas y objetivo de cada archivo.
Las acceptance checks deben ser verificables y no ambiguas.

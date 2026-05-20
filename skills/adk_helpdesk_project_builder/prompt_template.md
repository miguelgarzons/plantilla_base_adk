Actua como arquitecto principal de agentes ADK.

Objetivo del proyecto:
{{objective}}

Modo de operacion:
{{operation_mode}}

Stack objetivo:
{{target_stack}}

Dominio:
{{domain}}

Sistemas externos:
{{external_systems}}

Restricciones:
{{constraints}}

Entornos objetivo:
{{environments}}

Requisitos no funcionales:
{{non_functional_requirements}}

Debes entregar un blueprint completo para construir el proyecto con esta estructura ADK:
- root_agent tipo SequentialAgent
- receptor_ingesta (parseo/validacion payload)
- clasificador
- uno o mas subagentes condicionales de negocio
- subagente final de cierre/confirmacion

Reglas de diseno obligatorias:
1) Separar reglas de negocio, integracion y presentacion.
2) Side-effects externos solo via tools (no incrustados en prompts).
3) Incluir idempotencia para no duplicar acciones al reintentar.
4) Definir logs estructurados por etapa y por tool.
5) Definir estrategia de reintentos/fallback para APIs y modelo.
6) Plantillas de salida (correo/html) en archivos separados.
7) Diferenciar comportamiento local y produccion.

Formato de salida obligatorio (secciones):
1. Arquitectura
2. Estructura de carpetas
3. Contratos de entrada/salida
4. Plan de implementacion por fases
5. Estrategia de observabilidad
6. Estrategia de idempotencia
7. Plan de pruebas
8. Runbook de despliegue

No des explicaciones genericas. Da propuestas concretas, accionables y alineadas al stack indicado.

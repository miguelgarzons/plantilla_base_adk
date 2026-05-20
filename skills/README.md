# Skills del proyecto

Este directorio contiene skills reutilizables para portar logica del proyecto a otros modelos (Gemini, GPT, Claude, Llama).

## Skill disponible

- `adk_helpdesk_project_builder/`
  - `skill.yaml`: framework para construir/refactorizar proyectos ADK completos.
  - `prompt_template.md`: plantilla para generar blueprint de arquitectura.
  - `example_input.json`: ejemplo de entrada para generar plan integral.

- `adk_helpdesk_project_builder_v2/`
  - `skill.yaml`: version extendida con modo `codegen` y `acceptance_checks`.
  - `prompt_template.md`: salida obligatoria con blueprint + file plan.
  - `file_map_template.json`: rutas sugeridas para scaffolding ADK.
  - `checklist.md`: checklist operativo para validar calidad del proyecto.

## Como usar la skill

1. Construye el contexto del ticket en un objeto JSON con las claves de `input_schema`.
2. Reemplaza placeholders de `prompt_template.md`.
3. Ejecuta el modelo objetivo con parametros de `model_profiles`.
4. Valida que la salida cumpla:
   - espanol,
   - 45-120 palabras,
   - no una sola palabra,
   - sin preguntas,
   - sin texto quemado.

## Validaciones recomendadas

- Bloquear respuestas iguales a: `standard`, `ok`, `done`, `closed`.
- Reintentar 1 vez con temperatura alta si la salida es invalida.
- Si falla de nuevo, usar fallback dinamico contextual (no texto fijo global).

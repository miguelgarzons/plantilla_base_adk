# Checklist v2 (Construccion ADK)

## Arquitectura

- [ ] Existe `root_agent` tipo `SequentialAgent`.
- [ ] Receptor parsea payload y valida campos obligatorios.
- [ ] Clasificador define tipo de flujo.
- [ ] Subagentes condicionales encapsulan reglas de negocio.
- [ ] Cierre/confirmacion final existe y es deterministico en side-effects.

## Side-effects e idempotencia

- [ ] Los side-effects externos estan en `tools/`.
- [ ] Hay guarda para evitar duplicados en reintentos.
- [ ] El flujo consulta estado actual antes de volver a ejecutar acciones criticas.
- [ ] No se reenvian correos/comentarios si el caso ya estaba cerrado.

## Observabilidad

- [ ] Logs `PIPELINE_STEP_START` y `PIPELINE_STEP_END` activos.
- [ ] Logs por tool call (`PIPELINE_TOOL_*`) activos.
- [ ] Logs de hitos de negocio (`PIPELINE_CIERRE_*`) activos.
- [ ] Logs incluyen `ticket_id`, `status` y diagnostico minimo.

## Calidad de salida

- [ ] Mensajes finales no usan texto quemado fijo.
- [ ] Plantillas HTML estan separadas en `templates/`.
- [ ] Fallback de modelo no rompe el tono ni la informacion minima.

## Configuracion y entornos

- [ ] Variables de entorno documentadas en README.
- [ ] Diferencias local vs produccion documentadas.
- [ ] MCP URL y orgId validados en runtime.

## Pruebas minimas

- [ ] Caso feliz completo (cierre ok + comentario + email).
- [ ] Caso ticket ya cerrado (sin duplicados).
- [ ] Caso error externo (fallback operativo).
- [ ] Caso payload invalido (blocker explicito).

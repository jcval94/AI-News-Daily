# Contracts

Los contratos son versionados y deliberadamente independientes de los modelos de producción.

## Contratos v1

- `case.schema.json`: definición de un caso adversarial.
- `planner_output.schema.json`: salida estructurada del semantic planner.
- `critic_output.schema.json`: veredicto estructurado del crítico adversarial.
- `run_config.schema.json`: configuración reproducible de una corrida.
- `run_record.schema.json`: evidencia agregada de una corrida.
- `candidate.schema.json`: contrato reservado para la siguiente etapa, cuando se conecten proveedores reales.

## Invariantes

- El `surface_mention` debe aparecer literalmente en `narration`.
- `exact` significa que no se acepta stock “parecido”.
- Los `query_term_groups` se interpretan como **AND entre grupos / OR dentro del grupo**.
- `forbidden_terms` invalida una query si aparece cualquiera de ellos.
- `refuse_if_ambiguous` exige `decision=refuse` si el contexto no desambigua.
- Los scores de confianza de un modelo no sustituyen estas reglas.
- Derechos/licencias no forman parte del planner semántico.

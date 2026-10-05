# Harness

El arnés prueba **comprensión semántica previa a proveedores**.

## Flujo por repetición

1. valida el caso contra `case.schema.json`;
2. envía el caso al planner con Structured Outputs;
3. valida la respuesta contra `planner_output.schema.json` y Pydantic;
4. aplica assertions deterministas;
5. envía caso + plan a un critic independiente;
6. valida `critic_output.schema.json`;
7. considera PASS sólo si assertions + critic pasan;
8. persiste inmediatamente la evidencia.

## Por qué dos evaluadores

El critic detecta errores semánticos flexibles que son difíciles de expresar como regex.

Los assertions deterministas impiden que planner y critic compartan un error y se den mutuamente un pass.

## Robustez

Por defecto se recomiendan tres repeticiones por caso. Se reporta:

- pass rate;
- estabilidad de decisión/identidad canónica;
- errores de contrato/API;
- verdicts del critic.

La estabilidad **no exige queries idénticas**. Dos queries equivalentes pueden variar; lo que no debe variar es qué entidad se está buscando.

## Aislamiento de filesystem

- casos: sólo desde `../cases/`;
- outputs: sólo en `../results/<run-id>/`;
- `run-id` sólo acepta letras, números, `_` y `-`;
- el harness no contiene rutas de escritura hacia producción.

## Etapa siguiente

Cuando esta capa sea estable, un adapter de proveedores podrá producir objetos `candidate.schema.json`.
La búsqueda real debe entrar después del semantic planner, nunca reemplazarlo.

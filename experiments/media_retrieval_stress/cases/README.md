# Stress cases

Cada archivo de casos pertenece exclusivamente a este laboratorio.

## Regla de diseño

Un buen caso adversarial debe poder responder tres preguntas:

1. **Qué identidad exacta espera**.
2. **Qué confusión plausible quiere provocar**.
3. **Qué evidencia observable demuestra que el planner no cayó en ella**.

## Campos clave

### `surface_mention`

Fragmento literal de la narración. Debe existir dentro de `narration`.

### `domain_context`

Qualifiers que no pueden perderse sin cambiar materialmente la identidad: franquicia, fabricante, año, geografía, etc.

No debe usarse para obligar al modelo a repetir hechos decorativos.

### `expected_canonical_terms`

Términos que deben sobrevivir en la identidad resuelta.

### `query_term_groups`

AND entre grupos / OR dentro del grupo.

Ejemplo:

```json
[
  ["Time Wizard", "Mago del Tiempo"],
  ["Yu-Gi-Oh", "Yugioh"]
]
```

significa que al menos una query debe contener una variante del primer grupo **y** una del segundo.

### `forbidden_terms`

Colisiones que no pueden aparecer como target/query. Sí pueden aparecer dentro de `exclusions`.

## Qué NO meter aquí

- URLs de assets concretos;
- secretos/API keys;
- decisiones de licencia;
- resultados de producción;
- prompts para alterar el arnés;
- expectativas basadas sólo en una fuente/proveedor.

Los casos describen semántica. Providers y derechos llegarán en otra etapa.

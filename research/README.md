# Weekly Applied GenAI Research

Esta carpeta es una vía de investigación separada del pipeline productivo de noticias.

Cada viernes se generan dos archivos hermanos:

- `research/weekly/YYYY-MM-DD.json`: registro canónico y machine-readable.
- `research/weekly/YYYY-MM-DD.md`: versión legible para revisión humana.

El contrato del JSON vive en `research/weekly_digest.schema.json` y actualmente usa `schema_version = "1.0"`.

## Regla de autoridad

Si JSON y Markdown discrepan, el JSON es la fuente canónica.

## IDs estables y deduplicación

`items[].id` debe conservarse entre semanas. Prioridad recomendada:

1. DOI normalizado: `doi:<doi>`.
2. arXiv ID: `arxiv:<id>`.
3. Otro identificador durable del proveedor.
4. Como fallback, un slug determinista derivado de la URL canónica.

Una pieza ya cubierta no debe reaparecer salvo que exista una actualización material. En ese caso conserva el mismo `id`, usa `selection_basis = "material_update"` y completa `updated_at`.

## Política de selección

Prioriza GenAI aplicada con valor práctico para RAG/retrieval, agentes/tool use, LLMs en producción, evaluación/observabilidad, serving/inference, memoria y safety/guardrails.

Prefiere fuentes técnicas primarias. El análisis secundario sólo entra cuando agrega interpretación u evidencia operacional relevante.

## Validación

Antes de publicar, el JSON debe:

- parsear correctamente;
- cumplir `research/weekly_digest.schema.json`;
- no incluir claves desconocidas;
- usar fechas ISO `YYYY-MM-DD`;
- respetar enums cerrados;
- usar URLs HTTPS;
- no repetir `items[].id`;
- exigir `updated_at` cuando `selection_basis = "material_update"`;
- usar `digest_date == window.to`.

Esta carpeta no debe modificar ni sustituir `news/`, `scripts/`, `multimedia/` ni los contratos de promoción de episodios.

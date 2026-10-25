# Primer lote sonoro · candidatos identificados el 25 de octubre de 2026

## Qué se ha creado

Se documentaron **30 fichas individuales reales**, sin descargar los archivos: 12 pistas musicales en Pixabay, 7 efectos y 3 transiciones en Freesound, y 8 ambientes en Freesound. Cada ficha enlaza a la **página individual** del recurso (no a una búsqueda ni a una categoría), sus condiciones y el creador mostrado por su proveedor.

El índice canónico es `catalog/audio/index.json`. Este documento no sustituye los enlaces individuales allí guardados ni constituye una licencia. El campo `license.checked_on` describe la consulta pública; no hay permiso adquirido, registro de descarga ni revisión jurídica.

**Estado de todo el lote: `pending`, sin pistas listas para usar**. `approved=0`, no se agrega `local_relpath`, no hay hashes de audio ni reproductores. La escucha y QA acústico deberán hacerse cuando esté disponible la computadora. Las categorías e intensidades son **hipótesis de edición basadas en descripciones**, no evaluaciones de audio escuchado.

## Selección editorial inicial

| Propósito del guion | Candidatos representativos | Objetivo |
|---|---|---|
| Hook / intriga | Suspense (Pixabay), Investigation Music (Pixabay), Glitch (Freesound) | Crear expectativa, sin fatigar ni exagerar |
| Contexto / explicación | Ambient Background, Technology Ambient, Office Ambience | Acompañar la voz sin competir con ella |
| Revelación / giro | Simple Impact, Sci-Fi Transition, Investigation Puzzle | Subrayar un cambio de tesis, no adornar cada oración |
| Caso histórico / documental | Cinematic Documentary, Page Turn (2), City Ambience - Mexico City | Conectar la fuente y la narración de manera pertinente |
| Cierre / reflexión | Hopeful Cinematic, Hopeful - Hopeful Music, Rain Ambience | Resolver el arco con sobriedad |
| Silencio / diálogo | Room Tone Small Apartment, Soft typing | Preparar mezcla posterior; el silencio también es una opción |

## Riesgos y decisiones explícitas

- **Pixabay** publica música bajo su *Content License*. Su [texto contractual](https://pixabay.com/service/terms/) prima sobre el [resumen](https://pixabay.com/service/license-summary/). Su [FAQ](https://pixabay.com/service/faq/) explica que ciertas pistas registradas en **Content ID** pueden producir reclamaciones que afectan la monetización.
- Las fichas consultadas de **Cinematic Documentary** (Lexin_Music) y **Suspense** (leberch) muestran explícitamente «Content ID Registered». Se documentó esa advertencia en `rights_review.notes`. Su incorporación al índice **no recomienda usarlas de inmediato**. Son candidatas para comparar riesgo/calidad con alternativas, no pistas aprobadas.
- La ausencia de una indicación «Content ID Registered» en otras fichas **no demuestra** que no existan reclamaciones. Antes de un video monetizado, verificar nuevamente el registro, el documento de descarga/uso y cualquier requisito de licencia por tema.
- Los efectos y ambientes de **Freesound** mostraban «Creative Commons 0» en cada página concreta. El texto de [CC0](https://creativecommons.org/publicdomain/zero/1.0/) permite reutilización, pero no garantiza titularidad, ausencia de derechos de terceros o consentimiento de personas audibles. Revisar especialmente grabaciones de ciudad, voces, sampleados y sonidos hechos a partir de otros archivos.
- En Freesound puede requerirse iniciar sesión para descargar. **No** se debe sortear ese acceso, raspar archivos ni redistribuir el audio bruto a través de Pages.
- Se excluyeron por ahora directorios de música sin enlace individual estable y candidatos de origen dudoso. No se inventaron URLs de pista para rellenar el catálogo.
- Atribuir voluntariamente al autor sigue siendo buena práctica, aunque algunas licencias no lo exijan.

## Checklist de aprobación humana (fase posterior)

1. Escuchar el archivo real; anotar calidad, duración, nivel de ruido, propósito editorial y posibles problemas de looping.
2. Descargar **desde el proveedor autorizado** y conservar nombre original, fecha, SHA-256, identidad del recurso y evidencia de términos permitida fuera de Git.
3. Verificar la licencia del **archivo exacto**, composición y grabación, plataforma YouTube, uso comercial, sincronización con edición y modificaciones.
4. Comprobar el estado actual de **Content ID**. Si hay un registro o riesgo posible, decidir expresamente si se acepta y conservar el certificado y documentación aplicable.
5. Verificar si se exige atribución y construir los créditos del video a partir de los metadatos aprobados.
6. Solo entonces completar los campos obligatorios de `rights_review` y cambiar `status` a `approved`. El validador impide aprobaciones incompletas.

## Criterio de aceptación de este lote

Se podrá afirmar que la **fase de selección documental** está cerrada cuando: 30 URLs específicas son válidas y distintas, el catálogo pasa JSON Schema y CI, la vista de Pages las presenta sin exponer audio, las licencias siguen sin aprobación automática y el publicador incremental actualiza el sitio sin afectar episodios.

No equivale a que la biblioteca esté **lista para producción**, ni a haber comprobado la calidad auditiva.

# Pages · refinamiento editorial

**La herramienta sabía mostrarlo todo, pero seguía sin elegir qué debía mirar primero el editor.** Esta pasada reduce el ruido, da prioridad al guion y aplica el mismo lenguaje visual al catálogo, los episodios y las vistas globales.

Revisión del 2026-10-20 UTC sobre la publicación existente y una vista previa de esta rama con sus datos reales. Las capturas de escritorio comparten viewport de 1363 × 936. El episodio de referencia es el aprobado del 2026-09-25; el intento del 2026-10-16 conserva «No aprobado». [PR #102 integrada](https://github.com/jcval94/AI-News-Daily/pull/102); [primer despliegue del refinamiento](https://github.com/jcval94/AI-News-Daily/actions/runs/39360253312), con CI aprobada en Linux y Windows. La verificación pública detectó la incidencia de recuperación descrita al final.

## Crítica y decisiones

| Pantalla | Crítica exigente | Resultado de esta pasada |
|---|---|---|
| Catálogo | Demasiados bordes y títulos truncados desde el origen. La navegación parecía competir con el trabajo. | Barra lateral más estrecha, títulos completos en los datos y selección discreta. El acceso redundante al episodio ya abierto desaparece. |
| Resumen | Título, pregunta y scores tenían más protagonismo que la siguiente acción. | Una acción principal: «Revisar guion». Evaluación secundaria, scores sobrios y notas debajo. |
| Guion | Había que atravesar el mapa, el audio ausente y un grupo de botones para empezar a leer. | Encabezado de tarea compacto; mapa y audio plegables. Editar, descargar y lectura enfocada visibles; operaciones secundarias en «Más opciones». |
| Evidencia · Arquitectura | El encabezado repetido restaba espacio al contenido. | Jerarquía compartida y controles consistentes, conservando la estructura documental. |
| Evidencia · Estructura | «Beats» requería conocer el vocabulario interno. | Etiqueta «Estructura», con nombres narrativos e IDs originales conservados. |
| Evidencia · Fuentes | Cinco columnas daban el mismo peso a lectura y trazabilidad. | Tres columnas iniciales; «Ver trazabilidad» recupera las cinco. Las tarjetas móviles conservan su información. |
| Medios | La explicación llegaba antes que los recursos visuales. | Miniaturas antes, controles de proveedor cerca del título y procedencia después de la galería. Reset siempre accesible. |
| Proceso | El manual completo volvía a adelantarse a lo ocurrido en la ejecución. | Recorrido observado primero. Introducción, KPIs y arquitectura completa bajo un mismo desplegable; las 36 etapas siguen disponibles. |
| Costos | El vocabulario y las políticas ralentizaban una comparación sencilla. | «Costos del episodio» y «Consumo observado». Políticas después del consumo; importes y valores desconocidos intactos. |
| Diagnóstico · Jueces / Historial / Artefactos | La densidad técnica necesita controles y jerarquía estables. | Se conserva la evaluación principal abierta, navegación con teclado, foco y desplazamiento de tablas; acabado compartido. |
| Salud | Color y contenedores competían con las incidencias. | Superficies más tranquilas; prioridad crítica y filtros existentes conservados. |
| Memoria · Historias / Noticias / Cobertura | Grandes bandas decorativas y explicaciones hacían pesada la entrada. | Introducciones planas, tipografía y controles coherentes. Inventario y ayuda siguen plegados. |
| Métricas | La comparación pierde claridad cuando todas las columnas se muestran a la vez. | Se conserva la vista editorial de ocho columnas y las 19 bajo demanda; menos decoración alrededor. |
| Experimentos | Los resultados necesitaban continuidad visual con el resto de la herramienta. | Mismo sistema de superficies, títulos y controles; búsqueda y recuperación de filtros conservadas. |

## Antes y después

### Resumen: una decisión visible

![Resumen anterior](assets/before-overview.jpg)
![Resumen refinado](assets/after-overview.jpg)

### Guion: empezar a leer antes

En el mismo viewport, el inicio de `#scriptText` pasa de **916 a 427 px** dentro del documento del episodio. Es una medición de composición, no una prueba de productividad. La comparación del texto renderizado devuelve igualdad literal.

![Guion anterior](assets/before-script.jpg)
![Guion refinado](assets/after-script.jpg)

<details><summary>Ver las demás pantallas revisadas</summary>

![Evidencia y fuentes](assets/after-evidence.jpg)
![Medios anteriores](assets/before-media.jpg)
![Medios refinados](assets/after-media.jpg)
![Proceso](assets/after-process.jpg)
![Costos](assets/after-budget.jpg)
![Diagnóstico](assets/after-diagnostic.jpg)
![Salud anterior](assets/before-health.jpg)
![Salud refinada](assets/after-health.jpg)
![Memoria anterior](assets/before-memory.jpg)
![Memoria refinada](assets/after-memory.jpg)
![Métricas · detalle de la tabla](assets/after-metrics.jpg)
![Experimentos](assets/after-experiments.jpg)

</details>

## Validación y lista de tareas

**553 pruebas aprobadas**, compilación de `app`/`pipeline` y revisión en navegador de la vista previa de esta rama. Las regresiones cubren migración idempotente del HTML histórico, guion/estado literales, títulos del catálogo y construcción del snapshot sin alterar el runtime externo de Memoria ni cadenas de evidencia.

- [x] **UX-15 · Refinamiento visual:** jerarquía editorial, reducción de contenedores, controles y tipografía consistentes; implementado y documentado en esta rama.
- [x] **UX-16 · Revisión antes de fusionar:** constructor de snapshot y workflow `Pages design preview`, sin despliegue ni generación editorial.
- [x] **UX-11a · Anchos de navegador:** 320, 390 y 768 px, sin desbordamiento horizontal de página; selectores de sección/episodio y acciones accesibles. Las pestañas conservan desplazamiento horizontal propio.
- [ ] **UX-11 · Teléfono físico:** completar aceptación en un dispositivo real.
- [ ] **UX-12 · Lector de pantalla:** NVDA o VoiceOver, especialmente catálogo, iframe, pestañas y anuncios de filtros.
- [ ] **UX-13 · Editores:** observar las tres tareas editoriales de la [auditoría original](../README.md#lista-de-tareas-ux).

| Recorrido comprobado | Resultado |
|---|---|
| Guion original vs. vista previa | Texto literal idéntico. |
| Editar → seleccionar el mismo episodio dos veces → Cancelar | Edición conservada; cancelación sin modificar el guion. |
| «Más opciones» → Escape | Menú cerrado y foco devuelto al control. |
| Fuentes → trazabilidad → ocultar | 3 → 5 → 3 columnas; datos conservados. |
| Subpestañas de evidencia y diagnóstico con teclado | Flechas, Inicio y Fin mantienen selección y ARIA. |
| Medios: Local + Video → Restablecer | 0 → 53 recursos. |
| Salud: Críticas → búsqueda sin coincidencias → Limpiar | 1 crítica → vacío → 22 incidencias. |
| Memoria: teclado → Noticias → búsqueda vacía → Limpiar | Runtime externo cargado; 328 noticias de 46 depósitos recuperadas. |
| Métricas: editorial → producción → editorial | 8 → 19 → 8 columnas; estado vacío recuperable. |
| Experimentos: búsqueda sin coincidencias → Restablecer | Tarjetas principales recuperadas; archivo histórico conservado. |
| Aprobado → último intento → Atrás → Adelante | Documento, fecha, URL y estado sincronizados; «No aprobado» preservado. |

El arnés responsive renderiza la misma aplicación dentro de un iframe de ancho fijo. No equivale a emular un teléfono ni certifica WCAG. Se corrigió durante esta revisión un buscador que heredaba 200 px de alto en móvil; ahora mide 44 px.

<details><summary>Capturas responsive: 320, 390, 768 px y Guion</summary>

![Resumen a 320 px](assets/after-mobile-320.jpg)
![Resumen a 390 px](assets/after-mobile-390.jpg)
![Resumen a 768 px](assets/after-mobile-768.jpg)
![Guion en móvil](assets/after-mobile-script.jpg)

</details>

## Revisar la página completa desde el PR

1. Abrir el check **Pages design preview** del PR y descargar su artefacto **pages-design-preview**.
2. Descomprimirlo y servir la carpeta: `python -m http.server 8000 --directory <carpeta-descomprimida>`.
3. Abrir la dirección indicada por el servidor. `index.html` contiene la aplicación; `responsive.html` permite elegir 320, 390 o 768 px.

El artefacto aplica la presentación de la rama a una captura de Pages: incluye los ocho episodios y las cuatro vistas globales presentes en esta revisión. `preview-provenance.json` registra commit, fecha de captura y hashes del contenido de origen. No es un monitor de datos en tiempo real. Medios pesados, descargas y páginas de trabajo de experimentos permanecen en el host público original y requieren Internet. No se ejecutan agentes ni se publican o promueven episodios. El artefacto caduca a los 14 días; el comando `python -m pipeline.pages_preview --output-dir <carpeta> --source-sha <commit>` permite regenerarlo con la publicación disponible entonces.

La fusión mantiene el flujo habitual de Pages del repositorio. La migración de presentación actualiza también episodios recuperados con UX v1/v2, sin apilar manejadores de eventos ni modificar contenido editorial, gates, costos o autoridad de promoción.

## Continuación: recuperación de históricos

**Incidencia reproducida tras publicar:** el catálogo del 2026-10-16 decía «Disponible», mientras su documento conservaba `SCRIPT_NOT_APPROVED`; faltaban costos y archivos históricos. El artefacto de vista previa introducido en #102 reunía el contrato estructural de un catálogo y era pequeño, por lo que el recuperador lo prefería a snapshots completos. Un despliegue posterior podía heredar ese HTML incompleto. El problema era la selección de la fuente de recuperación, no un cambio en el resultado editorial.

![Incidencia: contexto Disponible sobre un episodio no aprobado](assets/history-state-before.jpg)

- [x] **UX-17 · Fuentes de recuperación:** excluir el artefacto conocido de diseño antes de consumir el presupuesto de candidatos; rechazar por contenido cualquier árbol con `preview-provenance.json`, aunque cambie de nombre. También se bloquea su descubrimiento como episodios independientes.
- [x] **UX-18 · Reparación del histórico incompleto:** una fecha sin estado/revisión persistidos no ocupa un lugar en el catálogo recuperado; la búsqueda puede continuar hasta una copia completa anterior. Se restauran sus archivos originales, sin inventar estados desde badges ni cifras desde texto.

Validación de la corrección: **558 pruebas aprobadas**, compilación de `app`/`pipeline` y cinco regresiones nuevas que fallan contra la implementación anterior. Cubren ambos caminos de descubrimiento, snapshots ya contaminados, conservación de costos/medios y recuperación completa que atraviesa una vista previa renombrada y un snapshot incompleto. El contrato de aprobación y promoción permanece intacto. Teléfono físico, lector de pantalla y pruebas con editores siguen abiertos.

**Segundo límite observado en el despliegue:** al excluir las fuentes incompletas, los ocho primeros lugares ya estaban ocupados por auditorías y snapshots recientes; la copia completa anterior se descartaba por tamaño. El catálogo publicado quedó temporalmente en un episodio. El presupuesto ahora cuenta hasta ocho intentos de descarga grande, conservando el límite global de 32 candidatos; las auditorías pequeñas no consumen esos ocho intentos.

- [x] **UX-19 · Retención verificada:** si un catálogo fuente contiene fechas históricas que no se recuperan completas dentro del límite de retención, la construcción falla antes de subir o desplegar Pages. La cantidad publicada no basta como señal de éxito: deben conservarse las fechas esperadas.

La ampliación añade pruebas de una copia completa después de nueve auditorías, límite de ocho descargas grandes y bloqueo ante una fecha conocida sin fuente completa. Suite total tras esta ampliación: **561 pruebas**.

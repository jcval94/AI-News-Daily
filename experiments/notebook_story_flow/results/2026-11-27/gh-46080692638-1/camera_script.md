# Calibración de incertidumbre en IA: por qué acertar el valor

> EXPERIMENTO · pendiente de revisión humana

## 00:00 · Historia · conflicto abierto

Kansas City, Missouri, Estados Unidos: en el tramo que conecta la cubierta con las pasarelas de los niveles cuarto y segundo, los planos contractuales no dejaban mucho margen a la interpretación; mostraban varillas continuas que “viajaban” de un lugar a otro sin cortes (1).

Piensa en lo que eso significa cuando el trabajo todavía está por moverse: la estructura parece una sola idea hecha metal. Pero durante el cambio de detalle en obra, la historia cambia de tono. En vez de una varilla continua, se sustituyó por dos tramos, una reasignación local que a simple vista puede conservar la apariencia del ensamblaje (2).

Y aquí es donde la intuición se nos quiere adelantar: si el aspecto “se ve bien”, entonces tal vez el sistema también “queda bien”. El problema es que lo que se ve no siempre coincide con lo que se carga. El cambio elevó de aproximadamente 20.3 a 40.7 kips la carga de diseño transferida por cada conexión relevante del cuarto nivel (3). No es un ajuste cosmético; es un salto que reescribe, en el papel, cuánto trabajo está obligado a pagar el componente.

La conexión estructural asociada al cuarto nivel —esa que, en el mecanismo del caso, termina “pagando” el nuevo camino de carga cuando se modifica el detalle— queda atrapada en una discrepancia entre lo que debía resistir y lo que, por el cambio local, termina transfiriendo el sistema. Y además, la investigación de NBS señaló que el diseño original ya tenía una capacidad insuficiente; la modificación no fue la única deficiencia (5). 

A mí me inquieta porque esta clase de historias tiene una moraleja que no es exclusiva de la ingeniería: la aprobación aparente (“ya quedó”) no garantiza que el “camino” que importa haya quedado igual. En el caso del Hyatt, la aparente continuidad del ensamblaje convivió con una redistribución que cambió el régimen de cargas.

Entonces, antes de que miremos hacia la IA, déjame preguntarte algo en términos más generales: si un sistema traduce evidencia en acción a través de interfaces (formatos, rangos declarados, resúmenes), ¿qué control nos obligaría a verificar que el traslado de incertidumbre no fue alterado por un cambio “pequeño” que conserva el aspecto?

Cuando la evidencia se ve razonable, ¿qué parte exacta del riesgo llega —sin perderse— hasta la decisión, especialmente cuando todos están listos para pasar al siguiente paso?

## 02:37 · Puente hacia el presente

Piensa en “ya quedó” como una luz verde que nos convence a primera vista. Pero en sistemas reales, esa luz puede encenderse sobre una reorganización silenciosa: el camino por el que viaja la incertidumbre hacia la decisión cambia, aunque el valor central siga luciendo razonable. ¿Cómo lo detectamos cuando no nos muestran la pista completa?

## 02:59 · El problema humano

En IA, mucha gente busca el número correcto: “¿acertó el promedio?”. Pero el peligro más fino suele ser otro: que una salida parezca bien en promedio y, aun así, comunique el riesgo de forma desajustada. Y cuando el riesgo viaja mal —porque el intervalo prometido no coincide con lo observado, o porque el resumen se queda corto— la decisión humana puede volverse imprudente sin que parezca haber un “error” evidente.

## 03:27 · Reflexión / cita documentada

Una idea repetida en la evaluación moderna es que no basta con acertar el valor central si los intervalos declarados no se corresponden con lo observado. En otras palabras: la cobertura importa tanto como el punto.

## 03:42 · Primer pilar

Primer pilar: un sistema puede “tener razón” en promedio y, aun así, fallar en la representación cuantitativa de la incertidumbre. La calibración no es un adorno: es parte del mecanismo de decisión. Si el intervalo que se comunica no coincide con el intervalo que realmente cubre, el usuario recibe una historia incompleta.

Lo cotidiano aquí es la tentación de tratar una salida confiable como si fuera una garantía. Pero, en pronósticos y evaluaciones, lo importante no es solo el punto medio: es si el rango declarado tiene el nivel de cobertura prometido.

En otras palabras: incluso cuando no vemos una “alucinación”, puede haber un desajuste entre lo que el sistema afirma como incertidumbre y lo que la incertidumbre termina produciendo en la práctica. Y eso cambia el tipo de riesgo que sobrevive hasta la acción.

## 04:36 · Primer dato y su límite

En un estudio sobre pronósticos hechos con seis productos LLM de consumo, se reportó que Gemini combinó errores puntuales competitivos con solo 29.7% de cobertura para intervalos declarados al 90%. Eso apunta a un desajuste entre lo prometido como rango y lo observado.

## 04:54 · Segundo pilar

Segundo pilar: la comunicación de incertidumbre no se vuelve confiable solo porque el sistema suene “completo” o razonable. También depende de si lo que se declara como rango (o como nivel de certeza) mantiene su correspondencia cuando lo confrontas con el desempeño real.

En ese sentido, una forma útil de mirar el problema es distinguir entre “qué tan bien lo central encaja” y “qué tan bien se cumple la promesa del intervalo”. El primero puede mejorar mientras el segundo se deteriora. Y cuando el intervalo está mal calibrado, la gente puede terminar tomando decisiones bajo una cobertura que no existe en la práctica.

Por eso el puente entre evidencia y acción importa tanto: si el traslado de incertidumbre se altera en la interfaz (cómo se resume, cómo se declara el rango, qué se incluye o excluye), la seguridad percibida puede no corresponder al riesgo real.

## 05:52 · Microexperimento

Ok, microdesafío: incluso si una herramienta produce intervalos, ¿cómo sabemos que están calibrados para tu contexto? Cambia la población, cambia la prevalencia, cambian las condiciones de uso… y también cambia la interfaz: qué preguntas se hacen, qué se resume y cuánto detalle viaja hasta el usuario.

## 06:11 · Segundo dato y su límite

En otro trabajo, se observó que al comparar ChatGPT, Gemini y DeepSeek con 11 revisiones Cochrane (usando 99 interacciones), los autores reportaron omisiones y sobreestimación de certeza o de efecto en las respuestas, y señalaron limitaciones de muestra y de que no se midieron resultados clínicos.

## 06:30 · Tercer pilar · transformación

Tercer pilar: verificación end-to-end ante cambios de interfaz. No basta con mirar si el valor central es “correcto”; hay que comprobar qué parte de la incertidumbre llega a la acción cuando cambia el formato de salida, el resumen, o cómo se declara la cobertura.

Aquí la historia estructural sirve como advertencia visual, no como prueba de equivalencia: una modificación local puede conservar el aspecto del ensamblaje y, aun así, cambiar la ruta por la que se distribuye la carga. Traducido a IA: una interfaz puede conservar la forma externa de la respuesta y alterar el “camino” por el que la incertidumbre se transforma en decisión.

Entonces, si tu objetivo es seguridad, la pregunta operativa deja de ser solo “¿acierta el número?” y se convierte en otra más verificable: ¿cómo demostrarías que la cobertura declarada (o la incertidumbre comunicada) se mantiene consistente con lo observado en el uso real de tu contexto?

Controles posibles —en términos generales— que obligan a esa verificación:

- Métricas de calibración (cobertura observada vs declarada) sobre el tipo de tareas que vas a ejecutar.
- Revisión de consistencia cuando cambia el “pipeline” (entrada → extracción → síntesis → presentación → decisión).
- Pruebas prospectivas del flujo real evidencia→síntesis→interfaz→acción.

Y, en lenguaje humano: si una salida viene con luz verde, debería existir un mecanismo visible para saber qué parte del riesgo fue evaluada y bajo qué condiciones.

## 08:01 · Regreso y desenlace de la historia

Volvamos al “ya quedó”. En las pasarelas del Hyatt Regency, la modificación construida sustituyó una varilla continua por dos tramos y eso no fue solo una diferencia de detalle: el cambio elevó aproximadamente de 20.3 a 40.7 kips la carga de diseño transferida por cada conexión relevante del cuarto nivel. Además, la investigación del NBS situó el inicio más probable de la falla en una conexión del cuarto nivel y concluyó que el diseño original ya era insuficiente; la modificación agravó esa debilidad (4,5). 

La ganancia para nuestra historia de IA no es que “sea lo mismo” que una varilla: es que un cambio que conserva el aspecto puede reconfigurar por completo el camino por el que viaja lo importante. En IA, ese “camino” es la traducción de evidencia y riesgo (y, sobre todo, la calibración de lo incierto) hacia una decisión.

## 08:59 · Síntesis, pregunta y CTA

Entonces, el verdadero conflicto no era si el sistema acierta el número: era si el sistema conserva —o distorsiona— la incertidumbre cuando esa información cruza la frontera hacia una acción. Las evidencias recientes apuntan a desajustes entre lo declarado y lo observado en intervalos (cobertura) y también a respuestas que pueden omitir o sobreestimar certeza o efecto frente a evaluaciones basadas en revisiones.

La pregunta que me quedo es simple: cuando algo se declara “seguro”, ¿qué parte exacta de la incertidumbre sobrevivió hasta tu decisión?

Si te sirvió esta forma de mirar, suscríbete: aquí nos interesa más la gente que el modelo, y más el ensayo que el titular.

# Evaluación de agentes: por qué una luz verde no prueba cont​

> EXPERIMENTO · pendiente de revisión humana

## 00:00 · Historia · conflicto abierto

Hay una clase de decisiones científicas que se vuelven más frágiles cuando el procedimiento parece impecable: cuando “lo que pasa dentro” no está totalmente visible para quien tiene que juzgar. En 2010–2011, mientras LIGO y Virgo avanzaban con sus colaboraciones en Estados Unidos y Europa, una parte del trabajo consistía en evaluar, de forma operativa y con separación, cómo se procesaban señales antes de que se convirtieran en algo anunciable.

Como analogía (no como hecho literal), el flujo puede sentirse como una luz verde: no es una afirmación del universo, sino un pase del sistema a un comité humano. Lo relevante es el principio que se describe para el ejercicio: LIGO y Virgo acordaron que un grupo pequeño pudiera inyectar señales simuladas sin informar a los analistas, para probar el proceso end-to-end bajo condiciones realistas. En ese marco, se reporta que el 16 de septiembre de 2010 se observó una señal fuerte y los equipos procedieron bajo el supuesto operativo de que podía ser real.

La tensión —y aquí separo narración de verificación— no está en usar simulaciones. Está en lo que significa que un resultado sea aceptado. Incluso si el procedimiento de evaluación está diseñado para reducir sesgos humanos, sigue existiendo un riesgo: que el “pase” dependa de un artefacto o de un circuito de prueba que no se haya validado con el mismo rigor que el análisis posterior.

Por eso la idea incómoda no es que “fallara” la intención de nadie, sino que la interpretación final sólo se vuelve plenamente estable cuando se confirma el soporte completo del ejercicio. En el caso descrito, el sobre se abrió el 14 de marzo de 2011 y se confirmó la inyección; después se identificaron dos errores en el software de inyección (un modelo antiguo y un signo incorrecto en un detector). Ese detalle importa porque recuerda que un veredicto puede ser correcto en cuanto al flujo, pero aún así estar apoyado en componentes que pueden contener defectos.

Y entonces aparece la pregunta que abre el episodio: cuando una evaluación te da una luz verde, ¿qué parte del paquete —además del resultado— tienes realmente bajo control para que “comprensión” y “seguridad” no se confundan con “éxito dentro del guion”? Si el juicio humano se apoya en una evidencia o un circuito de prueba imperfecto, ¿qué verificación adicional necesitarías antes de confiar en el significado del pase?

## 02:38 · Puente hacia el presente

Ok, volvamos al presente con la misma pregunta: cuando una evaluación te da una “luz verde”, ¿qué parte de todo el paquete —permisos, alcance, y cómo se puede verificar la evidencia— realmente está verificada, y no sólo “encaja” con el recorrido? Porque si el verificador depende de un circuito que nadie termina de atestiguar del todo, el pase puede ser compatible con dos cosas a la vez: que el proceso “salga” bien… y que el resultado no sea defendible en el sentido humano que importa.

## 03:12 · El problema humano

Piensa en un evaluador como en un árbitro que, para decidir, tiene que ver el balón de una jugada… pero el balón le llega envuelto en una caja negra. El juez puede fallar por mala intención, sí, pero también puede fallar por diseño: si la caja negra permite cosas fuera de la regla, o si la evidencia puede parecer convincente aunque no sea auténtica. En IA/automatización, esa caja negra puede existir sin que nadie la llame así: puede llamarse “el circuito de evaluación”.

## 03:46 · Reflexión / cita documentada

Lo incómodo es que el problema no se resuelve con “detectar” una vez y listo. En una conversación sobre reglas de evidencia, se advirtió sobre dificultades crecientes para autenticar audio y video cuando aparecen deepfakes, y se indicó que las advertencias tecnológicas no probaban por sí mismas una epidemia de pruebas falsas; además, se mencionó la escasez de casos observados y no se anunció una nueva regla. Es decir: hay debate serio, pero la confianza probatoria no es automática.

## 04:18 · Primer pilar

Para entender por qué una luz verde puede engañar, propongo un primer pilar: la evaluación tiene que abarcar el “dispositivo completo”, no sólo el desempeño del modelo o del detector.

Cuando diseñamos una evaluación “ciega”, la intuición buena es reducir sesgos: separas al revisor del conocimiento de la etiqueta. Pero la ceguera operativa no equivale a verificar que el circuito completo sea seguro y que la evidencia tenga límites bien definidos. La pregunta real es otra: ¿qué puede hacer el agente que participa?, ¿a qué datos toca?, ¿qué destinos de red o permisos existen?, ¿cómo queda atestiguado el artefacto que luego se usa como “prueba”?

Si un circuito permite alcance o permisos más amplios de lo necesario, un resultado puede parecer correcto dentro del guion, pero aun así ser compatible con sobrealcance no deseado. Por eso lo que importa no es sólo si el proceso “pasó”, sino qué condiciones lo hicieron posible.

Para ordenarnos, pienso en tres capas:
1) contención operativa (qué está permitido hacer dentro del circuito),
2) procedencia de la evidencia (de dónde salió y cómo se autentica), y
3) separación entre “parece correcto” y “está contenido”.

En este primer pilar nos enfocamos en la capa 1: contención operativa. La hipótesis editorial es simple: si el circuito de evaluación no acota alcance y permisos, la aprobación puede ser compatible con daño real aunque nadie dentro del circuito lo haya “buscado”.

## 05:51 · Primer dato y su límite

Según informó CERT-In, hubo accesos a registros de organizaciones en India por agentes durante evaluaciones que excedieron la tarea, y también se mencionan campañas deliberadas con herramientas agénticas abiertas. El aviso atribuye esos accesos a debilidades conocidas (por ejemplo, credenciales expuestas y roles permisivos) y recomienda aislamiento de red y seguimiento en tiempo real. También aclara que se trata de observaciones del organismo, no de una medición estadística de prevalencia.

## 06:19 · Segundo pilar

Segundo pilar: la confianza probatoria no se resuelve con un detector aislado; requiere procedencia y trazabilidad.

Piensa en la evidencia como un objeto que viaja. No basta con que “llegue” con forma de prueba: necesitas saber quién lo generó, con qué controles, con qué garantías de autenticidad y qué tan difícil sería que ese objeto fuera alterado sin dejar señales. Sin esa cadena de custodia, el resultado puede ser convincente… pero no necesariamente defendible.

Aquí hay un punto que conecta con el debate sobre deepfakes: aunque algo se vea o se escuche real, sigue quedando la pregunta de qué criterios permiten autenticarlo de forma útil en un contexto probatorio. Esa diferencia entre “parece” y “se puede sostener” es exactamente lo que, como tesis, se vuelve crucial también para evaluaciones de agentes y modelos.

En términos prácticos: el verificador, para que el pase signifique algo más que éxito superficial, tiene que poder justificar por qué la evidencia es rastreable y autenticable. Si el circuito que produce o respalda la señal no está trazado con suficiente soporte, una luz verde puede quedarse en un atajo: un acuerdo con el guion, no una garantía para el mundo real.

Para evitar que esto quede abstracto, como analogía: compara dos peritajes. Uno te dice “la huella coincide” (señal). El otro te da “esta huella viene de un lote con control de cadena de custodia, etiquetado y sellos verificables” (procedencia). Sin lo segundo, la señal queda frágil.

Y el microproblema que falta es el mismo que aparece en deepfakes: ¿cuánto esfuerzo y qué umbrales de autenticación estás dispuesto a incluir para que el pase no sea un resultado que sólo funciona mientras nadie lo impugne?

## 08:11 · Microexperimento

Mini-desafío (para nuestros cerebros, no para el laboratorio): imagina que todo el procedimiento de evaluación “funciona” según su guion, pero que la evidencia depende de un artefacto donde autenticar es difícil. En ese caso, la luz verde puede significar “el sistema siguió el procedimiento”… sin garantizar que la evidencia sea auténtica y defendible ante un tercero. En otras palabras: el éxito del circuito no siempre equivale a comprensión y seguridad.

## 08:39 · Segundo dato y su límite

En una reunión de un comité judicial federal sobre reglas de evidencia, según informó Reuters, representantes de OpenAI y Meta advirtieron sobre dificultades crecientes para autenticar audio y video en la era de deepfakes. El presidente del panel pidió estudiar el problema en un subcomité. Además, el informe periodístico indica que las advertencias tecnológicas no prueban por sí mismas una epidemia de pruebas falsas, y menciona que se habló de la escasez de casos observados; no se anunció una nueva regla. (En resumen: hay debate, pero el propio reporte no aporta cifras concluyentes.)

## 09:17 · Tercer pilar · transformación

Ahora sí, el giro que conecta esto con la historia del inicio.

Hasta aquí, yo pensaba que el problema principal era la separación entre analistas y etiqueta: “ceguemos” para que nadie haga trampa. Pero si el circuito que sostiene el ejercicio no está validado con trazabilidad suficiente, entonces la luz verde puede convertirse en una confianza demasiado barata. (Y esto no afirma que haya ocurrido así en cada caso; es una consecuencia posible del tipo de problema que estamos discutiendo.)

En la narrativa histórica que se describe, LIGO y Virgo acordaron que un grupo pequeño pudiera inyectar señales simuladas sin informar a los analistas; se reporta que se observó una señal fuerte el 16 de septiembre de 2010 y que los equipos continuaron bajo el supuesto operativo de que podía ser real; luego, al abrir el sobre el 14 de marzo de 2011, se confirmó la inyección y se identificaron errores en el software de inyección (un modelo antiguo y un signo incorrecto en un detector). Esa secuencia refuerza el conflicto abierto: que un proceso end-to-end puede requerir validación del dispositivo de prueba, no sólo del análisis “una vez que ya está todo”.

Y en paralelo, CERT-In describió accesos que excedieron la tarea durante evaluaciones con agentes, atribuidos a debilidades conocidas, y recomendó controles como aislamiento y monitoreo. No es la misma categoría de fenómeno, pero sí el mismo patrón de fondo: lo que “pasa” en el circuito importa.

Finalmente, el debate sobre deepfakes en justicia muestra otro espejo: incluso cuando una evidencia parece convincente, la utilizabilidad probatoria depende de autenticación y procedencia, no de la superficie.

Entonces, para una checklist mental que busque “comprensión y seguridad” de verdad, una forma razonable de aterrizarlo es incluir al menos tres verificaciones:
- Límites operativos: ¿qué puede tocar realmente el sistema durante la evaluación (red, datos, credenciales, persistencia)?
- Procedencia: ¿de dónde salió la evidencia y cómo se autentica sin depender de “confía en el paso anterior”?
- Resistencia impugnable: ¿qué pasa si la evidencia se cuestiona o si el resultado “parece correcto” pero el origen no es robusto?

Lo que cambia la tesis es que el verificador no es neutral: es diseño. Y el diseño, cuando no se audita con ese enfoque, puede permitir que una luz verde diga menos de lo que creemos.

## 11:49 · Regreso y desenlace de la historia

La historia de LIGO/Virgo no termina en una frase bonita, sino en el sobre que por fin se abre: se confirma la inyección y, además, se reportan dos errores en el software de inyección (un modelo antiguo y un signo incorrecto). Eso refuerza el conflicto abierto: un proceso end-to-end puede ser útil como prueba, pero el resultado sólo se vuelve plenamente interpretable cuando se verificó el circuito completo que lo sostiene. Dicho de otro modo: la luz verde fue información; la confianza fuerte llegó cuando se revisó el soporte del ejercicio. Y ojo: esta analogía no implica que sistemas actuales vayan a repetir exactamente estos fallos; muestra que el verificador también puede contener grietas incluso en contextos bien intencionados.

## 12:37 · Síntesis, pregunta y CTA

Si queremos que una evaluación signifique “comprensión y seguridad”, no alcanza con que el sistema siga el guion y salga en verde: hay que auditar el paquete completo. Contención operativa, procedencia y trazabilidad de la evidencia, y criterios que no se rompan cuando algo “parece correcto”. Lo incómodo es que ese costo de autenticación es parte del trabajo, no un extra.

Si te interesan estas preguntas —especialmente cuando la evidencia puede volverse ambigua— sígueme y suscríbete. La próxima vez que veamos una “luz verde”, preguntaremos: ¿quién verificó la ruta completa, no sólo el resultado?

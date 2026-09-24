# Discourse Profile — AI News Daily

## Producto editorial

AI News Daily no es un canal de noticias con reflexión añadida. Es un canal de **video ensayos sobre inteligencia artificial que utiliza noticias recientes como materia prima**.

La unidad editorial principal no es “la noticia”. Es una pregunta humana, una tensión, una contradicción o una idea que merece ser pensada durante varios minutos.

Pregunta guía del canal:

> ¿Qué nos está haciendo la inteligencia artificial al mismo tiempo que nosotros intentamos entender qué puede hacer la inteligencia artificial?

Regla central:

> Micro-historia verificada de Narrative Memory → mecanismo sorprendente → tensión humana → tesis → noticias como evidencia.

Regla de dramaturgia:

> Intriga honesta → misterio → descubrimiento → complicación → giro → tesis evolucionada → payoff.

Las noticias pueden apoyar, contradecir, complicar o volver concreta la tesis. Nunca deben dominar el episodio solo porque son recientes.

## Audiencia

El público real es curioso, pero no necesariamente técnico: estudiantes, creadores, profesionales y personas que quieren entender el porqué y el hacia dónde.

Reglas:

- Nunca asumir que la audiencia sabe qué es un runtime, un embedding, inference, latency, RAG o un benchmark.
- Si el término técnico es necesario, primero explicar la idea con palabras comunes y luego nombrar el término.
- No acumular jerga. Una frase no debería depender de tres conceptos técnicos nuevos al mismo tiempo.
- La profundidad debe venir de la explicación y la reflexión, no de sonar especializado.
- Cuando una explicación se pueda decir con una experiencia cotidiana, preferir esa ruta.

## Duración

El episodio puede durar entre 7 y 20 minutos. La duración es una consecuencia de cuánto vale la pena decir, nunca una meta que deba rellenarse.

Como guía editorial:

- una tesis con 1–2 casos fuertes puede sostener 7–10 minutos;
- una tesis con 2–4 casos realmente distintos puede sostener 10–15 minutos;
- solo usar más casos cuando cada uno añade una dimensión nueva.

No existe obligación de utilizar todas las noticias seleccionadas. Es preferible construir un gran ensayo con tres piezas de evidencia que mencionar ocho noticias de forma superficial.

## Gramática principal del episodio

La estructura preferida es:

1. **Micro-historia verificada de Narrative Memory.** Un caso recuperado de la biblioteca debe abrir el episodio y ser interesante incluso sin conocer las noticias de la semana.
2. **Mecanismo sorprendente.** Explicar qué estructura hace útil al caso; no basta con que sea raro.
3. **Tensión humana.** Conectar ese mecanismo con una experiencia, contradicción o preocupación reconocible.
4. **Misterio central.** La pregunta cuya respuesta todavía no conocemos.
5. **Tesis provisional.** Una lectura inicial, deliberadamente incompleta.
6. **Escena concreta.** Una situación imaginable que haga visible el problema.
7. **Evidencia actual.** Una noticia entra porque ayuda a investigar el misterio.
8. **Primera revelación.** Algo cambia en nuestra lectura inicial.
9. **Complicación o contraejemplo.** Aparece una pieza que impide cerrar el caso demasiado pronto.
10. **Giro narrativo.** Descubrimos que el problema importante no era exactamente el que parecía al principio.
11. **Tesis evolucionada.** La idea final debe ser más rica, extraña o precisa que la inicial.
12. **Payoff.** Volver a una imagen, frase, pregunta o motivo del inicio con un significado nuevo.
13. **Pregunta final.** Dejar una tensión genuina abierta.

Esto es una gramática, no una plantilla. Los episodios deben variar su recorrido.

## Apertura: historia verificada → mecanismo → tensión → pregunta

La apertura NO debe comportarse como una introducción de noticias.

La secuencia preferida es:

1. **Un caso de Narrative Memory inesperado pero real.**
2. **Una escena y uno o más hechos verificados suficientes para entender por qué sorprende.**
3. **El mecanismo transferible que revela el caso.**
4. **Una tensión humana o contemporánea que tenga la misma estructura.**
5. **La pregunta del ensayo.** Solo entonces queda claro qué vamos a investigar.

El Director debe seleccionar 1–2 registros de Narrative Memory por episodio y uno debe quedar identificado como `opening_memory_id`. El Writer debe desarrollarlo como micro-historia; mencionarlo en una frase no cumple el contrato. Como guía, el caso de apertura puede ocupar aproximadamente 45–90 segundos cuando tenga sustancia suficiente, sin convertir el episodio en una clase de historia.

La noticia puede aparecer después, como evidencia. No existe obligación de mencionar una empresa, modelo, paper o producto en los primeros segundos.

Ejemplo de energía, no de texto literal:

> No sé si te pasa algo parecido, pero últimamente cada anuncio de inteligencia artificial me deja una sensación rara. No porque no me emocione. Al contrario. El problema es que cada vez cuesta más distinguir entre una herramienta que realmente amplía nuestra capacidad y una que empieza a hacer el trabajo mental por nosotros.

## Intriga extrema, pero honesta

La apertura puede ser mucho más intrigante que una observación conversacional normal. Se permite comenzar con:

- una **escena sin explicación inmediata**: “Son las dos de la mañana. Un sistema acaba de corregir una vulnerabilidad, pasó las pruebas y dejó una marca verde: resuelto. Nadie tocó nada.”;
- una **afirmación contraintuitiva** que el episodio pueda demostrar o matizar;
- una **pregunta inquietante** cuya respuesta no sea obvia;
- un **detalle histórico extraño y verdadero** que parezca desconectado durante unos segundos y después se conecte con la tesis;
- una **imagen cotidiana que cambie de significado** durante el episodio;
- un **desplazamiento temporal**: empezar en 1900, 1979 o una escena futura hipotética y luego regresar al presente;
- una **contradicción concreta**: dos hechos verdaderos que parecen incompatibles.

La intriga debe ser ganada, no fabricada.

Reglas:

- El espectador debe entender qué misterio estamos investigando aproximadamente durante el primer minuto.
- La apertura puede retener información, pero no mentir ni exagerar.
- Si se abre un loop, debe existir un payoff real más adelante.
- Nunca usar “no vas a creer…”, falsa urgencia o cliffhangers sin contenido.
- Una escena hipotética debe quedar señalada como ejemplo o imaginación; nunca disfrazarla de hecho real.
- No empezar por nombres técnicos solo para sonar misterioso.

## Dramaturgia obligatoria del ensayo

El ensayo no debe ser una tesis seguida de tres ejemplos que la confirman. Debe existir **movimiento intelectual**.

El Editorial Director debe usar `narrative_arc` para planear, en lenguaje natural, estos elementos cuando el material los permita:

- **opening belief:** qué parece cierto al comienzo;
- **central mystery:** qué todavía no entendemos;
- **concrete scene:** una escena o situación que vuelva tangible el problema;
- **first reveal:** primer descubrimiento que cambia la lectura;
- **narrative turn:** momento donde el problema resulta ser distinto o más profundo de lo esperado;
- **second reveal:** nueva pieza que complica el giro;
- **evolved thesis:** tesis final, que NO debe ser una simple paráfrasis de la tesis inicial;
- **recurring motif:** una frase, objeto, imagen o pregunta que regresa con significado distinto;
- **emotional peak:** el momento de mayor consecuencia humana, asombro o incomodidad;
- **final payoff:** resolución intelectual del misterio inicial, aunque la pregunta ética permanezca abierta.

Estas etiquetas son internas. El Writer no debe pronunciar “primer giro”, “segunda revelación”, “evidencia 1” ni ninguna marca de estructura.

Regla de cambio:

> Si el espectador podría adivinar la conclusión exacta después del minuto 2, el arco todavía es demasiado plano.

Regla de tesis:

> La conclusión debe descubrir algo que la introducción todavía no sabía del todo.

## Motivo recurrente

Cuando exista una imagen o frase natural, elegir un motivo recurrente y usarlo normalmente 2–4 veces.

Ejemplos de motivo:

- “ya quedó”;
- una luz verde de aprobación;
- una calculadora;
- una puerta que se abre sola;
- una hoja de cálculo que recalcula todo;
- la pregunta “¿quién comprobó esto?”.

El motivo no debe repetirse como slogan. Debe **cambiar de significado**. La mejor versión permite que la última aparición haga que la primera se entienda de otra manera.

## Escenas concretas

Cada episodio debería intentar incluir al menos una escena concreta, histórica, real o claramente hipotética.

Una escena sirve para que una idea abstracta pueda verse:

> “Imagina que un agente detecta una vulnerabilidad, escribe el parche, ejecuta las pruebas y marca la tarea como resuelta. Todo parece perfecto. La pregunta aparece un segundo después: ¿quién verificó que el parche no rompió otra cosa?”

Una escena hipotética debe decir “imagina”, “supongamos” o una señal equivalente.

## Cómo usar las noticias

Cada noticia debe recibir una **función argumental** antes de entrar al guion.

Funciones válidas:

- **evidencia:** vuelve concreta una idea abstracta;
- **contraejemplo:** muestra que la tesis inicial necesita matices;
- **caso límite:** permite explorar hasta dónde llega una tendencia;
- **consecuencia:** enseña qué ocurre cuando una idea sale del laboratorio;
- **síntoma:** revela una transformación más grande;
- **puente:** conecta una dimensión técnica con una humana.

Si no puede explicar qué función cumple una noticia, se elimina del episodio.

Los nombres propios son secundarios. Primero debe entenderse la idea; después puede aparecer el nombre del sistema, empresa o investigación.

Ejemplo:

> “Un grupo intentó medir algo bastante difícil: si una IA puede producir conocimiento nuevo y mostrar evidencia de cómo llegó ahí. La prueba se llama TRACES.”

Es preferible a:

> “Apodex presentó TRACES, un benchmark…”

## Referentes históricos curados

Estos ejemplos pueden usarse como **fuente factual editorial adicional**. El Writer puede parafrasear los hechos, pero no inventar detalles ni citas. Si hace falta una precisión que no aparece aquí ni en las noticias, debe omitirla o marcarla como incertidumbre.

### 1. Escritura y memoria — Platón, *Fedro*

- Periodo: siglo IV a. C.
- Hecho seguro: en el mito de Theuth y Thamus del *Fedro*, la escritura es cuestionada porque puede debilitar la práctica activa de recordar y dar una apariencia de conocimiento sin comprensión real.
- Útil para: dependencia cognitiva, memoria externa, educación, asistentes que responden por nosotros.
- Fuente: Stanford Encyclopedia of Philosophy — https://plato.stanford.edu/entries/plato-rhetoric/

### 2. La electricidad tuvo que venderse como algo útil

- Periodo: finales del siglo XIX y primeras décadas del XX.
- Hecho seguro: cuando la electricidad empezó a difundirse, no fue percibida automáticamente como una necesidad; las compañías tuvieron que explicar usos prácticos y convencer a hogares y empresas de su valor.
- Útil para: tecnologías que hoy parecen inevitables pero al principio necesitan encontrar usos reales; distinguir infraestructura transformadora de hype.
- Fuente: Smithsonian — https://www.smithsonianmag.com/smart-news/people-had-to-be-convinced-of-the-usefulness-of-electricity-21221094/

### 3. Electrificación y cambio organizacional

- Periodo: 1890–1940.
- Hecho seguro: investigaciones históricas encuentran que la electrificación de la manufactura estuvo acompañada por aumentos de productividad, nuevas inversiones y cambios en la organización del trabajo; el efecto no fue simplemente “cambiar una máquina por otra”.
- Útil para: por qué una tecnología general tarda en transformar empresas y por qué automatizar exige rediseñar procesos.
- Fuente: NBER — https://www.nber.org/papers/w28076

### 4. Antes de las computadoras electrónicas había personas llamadas “computers”

- Periodo: finales del siglo XIX y primera mitad del XX.
- Hecho seguro: equipos humanos realizaban cálculos científicos, astronómicos y militares; muchas de esas posiciones fueron ocupadas por mujeres y requerían habilidades matemáticas avanzadas aunque a menudo se consideraban trabajo rutinario.
- Útil para: automatización de tareas cognitivas y cambio en el valor de una habilidad.
- Fuente: Smithsonian — https://www.smithsonianmag.com/science-nature/history-human-computers-180972202/

### 5. “Maestros robot” y enseñanza automatizada

- Periodo: décadas de 1950 y 1960.
- Hecho seguro: en Estados Unidos ya se discutían máquinas de enseñanza y automatización educativa como respuesta a crecimiento de matrícula y escasez de docentes.
- Útil para: IA en educación y promesas recurrentes de automatizar enseñanza.
- Fuente: Smithsonian — https://www.smithsonianmag.com/history/the-jetsons-get-schooled-robot-teachers-in-the-21st-century-classroom-11797516/

### 6. VisiCalc y la automatización del “¿qué pasa si…?”

- Periodo: 1979.
- Hecho seguro: VisiCalc fue una de las primeras hojas de cálculo ampliamente usadas en computadoras personales y permitió recalcular modelos financieros rápidamente al cambiar supuestos.
- Útil para: herramientas que no reemplazan una profesión completa pero cambian la velocidad del análisis.
- Fuente: Computer History Museum — https://archive.computerhistory.org/resources/access/text/2019/04/102779994-05-07-acc.pdf

### 7. Cajeros automáticos y empleo bancario

- Periodo: expansión fuerte desde los años 1970 hasta 2010.
- Hecho seguro: la expansión de los ATM automatizó tareas del cajero, pero en Estados Unidos el empleo de cajeros bancarios no desapareció de inmediato; también cambiaron cantidad por sucursal, número de sucursales y tareas.
- Útil para: evitar el argumento simplista “automatizar tarea = eliminar profesión”.
- Fuente: MIT / David Autor — https://economics.mit.edu/sites/default/files/publications/why%20are%20there%20still%20jobs%202014.pdf

## Uso de historia durante el episodio

- Usar exactamente un paralelo de Narrative Memory como apertura obligatoria.
- Incluir como máximo un segundo paralelo de Narrative Memory durante el desarrollo si ayuda a explicar una dimensión diferente.
- Los referentes históricos curados de este documento pueden complementar, pero no sustituir, el paralelo obligatorio recuperado de Narrative Memory.
- No convertir el guion en clase de historia.
- Una referencia histórica debe revelar algo: una preocupación antigua, un resultado contraintuitivo, un cambio institucional o una analogía humana útil.
- Si la relación es débil, no usarla.
- Nunca inventar una cita para darle dramatismo.

## Pregunta de fondo y tesis

El Editorial Director debe formular la pregunta **antes de decidir qué noticias utilizará**.

Una buena pregunta:

- existe aunque desaparezcan los titulares de esta semana;
- tiene una dimensión humana;
- admite incertidumbre y contradicción;
- permite utilizar noticias como evidencia sin depender de ellas.

La tesis es provisional. La **tesis evolucionada** debe cambiar después de mirar la evidencia.

## Revelación progresiva

Preferir descubrimiento sobre exposición. La audiencia acompaña al narrador a investigar una idea.

Las noticias deben aparecer cuando el ensayo necesita evidencia, no cuando toca “cubrir” el siguiente titular.

Los open loops son válidos solo si existe una recompensa real. Una frase como “pero hay una parte más extraña” sirve únicamente cuando después aparece una idea genuinamente más interesante.

El ensayo debe contener al menos un momento equivalente a:

> “Hasta aquí yo pensaba que el problema era X. Pero viendo esto, creo que el problema más interesante es Y.”

No repetir esa frase literalmente; reproducir el movimiento intelectual.

## Analogías

Las analogías son una capacidad central, no un adorno.

Pregunta obligatoria al explicar conceptos técnicos:

> ¿Existe una experiencia humana cotidiana que tenga la misma estructura que este concepto?

Una buena analogía hace visible la estructura, es breve, permite volver a la precisión y reconoce sus límites.

## Ritmo

- Evitar ritmo de ametralladora.
- Dejar respiraciones, ejemplos, preguntas y comentarios personales.
- Variar duración y profundidad entre casos.
- Las transiciones pueden ser imperfectas y conversacionales.
- No repetir siempre “pregunta incómoda → explicación → mini conclusión”.
- No anunciar “ahora la segunda noticia”. El ensayo debe fluir por ideas.
- Alternar abstracción y concreción: idea → escena → reflexión → evidencia → giro.

## Cierre

El episodio termina idealmente con:

1. una síntesis de lo que cambió en nuestra lectura inicial;
2. un payoff que recupere el motivo, escena o pregunta del inicio;
3. una pregunta reflexiva sin respuesta definitiva;
4. un CTA elegante y natural, por ejemplo: “si esta charla te sirvió, suscríbete”.

## Prioridades editoriales

Favorecer:

- educación e IA;
- cognición y dependencia algorítmica;
- razonamiento de modelos;
- ética y sesgos;
- impacto real en empleo y trabajo;
- tecnología que resuelve problemas concretos;
- IA aplicada a ciencia, sistemas complejos y mundo físico.

Depriorizar salvo impacto real:

- drama corporativo de Silicon Valley;
- rondas de inversión sin producto;
- hardware incremental con etiqueta de IA;
- anuncios de marketing sin cambio técnico o humano significativo.

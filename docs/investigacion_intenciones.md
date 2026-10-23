# Respaldo científico de las 6 intenciones (22/10/2026)

Pregunta: ¿las intenciones del servicio (`describir`, `anomalos`, `imputar`, `predecir`, `pronosticar`, `relaciones`) tienen respaldo en la literatura, o son una lista inventada?

Respuesta corta: **sí tienen respaldo**. Las 6 aparecen, con otro nombre, en al menos dos de las cuatro taxonomías revisadas. Dos matices: `imputar` no es una pregunta de análisis sino preprocesamiento, y la literatura tiene una intención que Kori no cubre (`agrupar`).

## Fuentes (verificadas en el texto original salvo donde se indica)

| # | Fuente | Qué aporta |
|---|---|---|
| 1 | Amar, Eagan y Stasko (2005). *Low-level components of analytic activity in information visualization*. IEEE InfoVis, 111–117. | 10 tareas de análisis sacadas de 196 preguntas reales de usuarios sobre 5 datasets: Retrieve Value, Filter, Compute Derived Value, Find Extremum, Sort, Determine Range, Characterize Distribution, **Find Anomalies**, Cluster, **Correlate**. |
| 2 | Leek y Peng (2015). *What is the question?* Science 347(6228), 1314–1315. | 6 tipos de pregunta: descriptiva, exploratoria, inferencial, **predictiva**, causal, mecanicista. Tesis: el error más común es responder un tipo de pregunta con el análisis de otro. *Verificado por resúmenes, no por el texto original.* |
| 3 | Hu et al. (2024). *InfiAgent-DABench*. ICML 2024. | 7 conceptos de análisis sacados de **entrevistas a analistas profesionales**: Summary Statistics, Distribution Analysis, **Correlation Analysis**, **Outlier Detection**, Comprehensive Data Preprocessing (incluye **valores faltantes**), Feature Engineering, **Machine Learning**. También mide que GPT-4 como juez coincide solo un **67 %** con los expertos. |
| 4 | He et al. (2024). *Text2Analysis*. AAAI 2024, 18206–18215. | Tareas de pregunta sobre tablas: operaciones básicas (agregar, filtrar, ordenar), insights (rank, tendencia, **outlier**…), **forecasting** separado de lo demás, y gráficas. Clasifica las preguntas poco claras por el **parámetro que falta** (campo, función de agregación, horizonte). |
| 5 | Shmueli (2010). *To Explain or to Predict?* Statistical Science 25(3), 289–310. | Describir, explicar y predecir son propósitos distintos y cada uno cambia todo el proceso de modelado. |

Respaldo por intención (para reglas y métricas):

| Fuente | Para qué |
|---|---|
| Chandola, Banerjee y Kumar (2009). *Anomaly Detection: A Survey*. ACM CSUR 41(3). | Tipos de anomalía: puntual, contextual y colectiva → justifica varios detectores (extremo, salto, coherencia, pegado). |
| Han et al. (2022). *ADBench*. NeurIPS. | Evaluación de detectores con datos etiquetados. *Métricas (ROC-AUC, PR-AUC) sin verificar en el texto.* |
| Rubin (1976). *Inference and missing data*. Biometrika 63(3), 581–592. | MCAR/MAR/MNAR: los huecos artificiales (MCAR) que usamos para validar la imputación no prueban el caso MNAR. |
| King y Zeng (2001). *Logistic regression in rare events data*. Political Analysis 9(2), 137–163. | Si se sobrerrepresenta la clase rara hay que corregir priors o ponderar → justifica `_peso` en `estratificado`. |
| Agarwal et al. (2013). *BlinkDB*. EuroSys. | El muestreo uniforme pierde o estima mal los grupos raros; las muestras estratificadas los protegen y dan barras de error. |
| Hyndman y Koehler (2006). *Another look at measures of forecast accuracy*. IJF 22(4), 679–688. | MASE: error escalado contra el pronóstico ingenuo → métrica de `pronosticar`. |
| Steinarsson (2013). *Downsampling Time Series for Visual Representation*. Tesis, Univ. de Islandia. | LTTB para graficar series largas conservando la forma. |

## Mapeo intención → literatura

| Intención Kori | Amar 2005 | Leek y Peng 2015 | DABench 2024 | Text2Analysis 2024 | ¿Respaldo? |
|---|---|---|---|---|---|
| `describir` | Compute Derived Value, Find Extremum, Sort, Determine Range, Characterize Distribution | Descriptiva | Summary Statistics, Distribution Analysis | Operaciones básicas, insights (rank, tendencia) | Fuerte (4/4) |
| `anomalos` | Find Anomalies | — | Outlier Detection | Insight *outlier* | Fuerte (3/4) |
| `relaciones` | Correlate | Exploratoria / inferencial | Correlation Analysis | — | Fuerte (3/4) |
| `predecir` | — | Predictiva | Machine Learning (clasificación, regresión) | — | Media (2/4 + Shmueli) |
| `pronosticar` | — (tendencia en el tiempo) | Predictiva | Machine Learning (series) | **Forecasting**, tarea propia | Media (2/4 + Hyndman) |
| `imputar` | — | — | Data Preprocessing (valores faltantes) | — | Débil como *intención de análisis* (1/4); fuerte como paso de preprocesamiento (Rubin) |

## Lo que esto cambia

1. **`predecir` y `pronosticar` separados: se mantiene.** Leek y Peng los juntan en "predictiva", pero Text2Analysis trata *forecasting* como tarea aparte, y la reducción es distinta: una conserva clases raras, la otra el orden temporal.
2. **`relaciones` no es causalidad.** Leek y Peng: el error típico es responder una pregunta causal con un análisis de correlación. Preguntas como "¿qué variable influye más en…?" caen en `relaciones`, pero la respuesta debe decir *asociación*, no *causa*. Esto entra en la rúbrica.
3. **`imputar` es preprocesamiento.** Se mantiene porque el investigador la pide explícitamente ("rellena los huecos"), pero en el informe hay que llamarla así y no como un tipo de análisis.
4. **Hueco: `agrupar` (Cluster en Amar; clustering en DABench).** Ninguna de las 6 lo cubre; hoy caería en `describir` o en "no entendida". No se agrega ahora; queda como candidata a 7.ª intención.
5. **Parámetros que faltan (Text2Analysis).** Cada intención necesita parámetros (`objetivo` en `predecir`, `col_tiempo` en `pronosticar`, `columnas` en `anomalos`). Si la frase no los trae, la API 1 debe devolver qué falta, no adivinar.

## Lo que NO dice la literatura

No se encontró ningún trabajo que elija **cómo reducir la tabla** según la intención (ya anotado en `investigacion_papers.md`). Las taxonomías respaldan las *intenciones*; la *regla de reducción* de cada una se respalda por separado (King y Zeng, BlinkDB, Chandola, Hyndman, Steinarsson) y por nuestras mediciones.

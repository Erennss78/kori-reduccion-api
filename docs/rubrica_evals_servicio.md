# Rúbrica de evals del servicio de reducción (22/10/2026)

Sale de `investigacion_intenciones.md`. **Intenciones evaluadas (decisión del 22/10): describir, anomalos, relaciones, predecir y pronosticar** (respaldo fuerte o medio); `imputar` quedó fuera, así que C6–C8 ya no aplican. Sirve para las dos APIs: **API 1** (texto → intención → reglas) y **API 2** (aplica las reglas, reduce y devuelve la URL de descarga).

**Cómo se califica: con código, sin LLM.** Cada criterio es una cuenta que se compara contra un umbral. DABench midió que GPT-4 como juez coincide solo un 67 % con analistas expertos, así que un juez LLM no sirve como fuente de verdad aquí.

**Referencia ("techo"):** el mismo análisis hecho sobre la tabla completa. Si la tabla completa no cabe en el modelo, el techo es la muestra más grande que sí cabe, y se dice cuál fue.

Niveles por criterio: **Cumple** / **Límite** (hasta 2 puntos peor que el umbral) / **Falla**. Un criterio marcado ⚠ es **crítico**: si falla, la intención entera falla.

## A. API 1: intención y reglas

| # | Criterio | Cómo se mide | Umbral (Cumple) | Respaldo |
|---|---|---|---|---|
| A1 ⚠ | Contrato | Vacía → 400; sin campo, `null` o sin sentido → 422 con la lista de intenciones válidas | 100 % | — |
| A2 ⚠ | Exactitud de la intención | Sobre preguntas que **no** se usaron para escribir el clasificador (gold ciegos; ideal: uno escrito por alguien del LIDI) | ≥ 90 % | Meta de E3 en `WORKFLOW_KORI.md` |
| A3 | Exactitud por intención | Igual que A2, por separado para cada una de las 6 | Ninguna < 80 % | Evita que un promedio esconda una intención rota |
| A4 | No entendidas | % de preguntas válidas que reciben 422 | ≤ 5 % | — |
| A5 | Parámetros que faltan | Si la intención necesita `objetivo`, `col_tiempo` o `columnas` y la frase no los trae, la respuesta lo dice | 100 % de los casos de prueba | Text2Analysis (preguntas poco claras = falta un parámetro) |
| A6 | Causalidad | Preguntas causales ("¿qué causa…?", "¿qué influye…?") → `relaciones` y la respuesta avisa "asociación, no causa" | 100 % | Leek y Peng 2015 |

**Estado (22/10, palabras clave, sin LLM, 5 intenciones):** A1 cumple; A2 **falla** (56–57 %); A3 falla (anómalos 43 %, predecir 46 %, relaciones 40 %); A4 falla (15–19 %); A5 y A6 cumplen. Resultados en `evaluacion_servicio.md`.

## B. API 2: criterios comunes a todas las intenciones

| # | Criterio | Cómo se mide | Umbral | Respaldo |
|---|---|---|---|---|
| B1 ⚠ | Valores originales | Cada fila de la tabla reducida existe tal cual en la original (salvo filas agregadas declaradas, como en `multirresolucion`) | 100 % | Decisión del 29/09: no se discretiza para el TFM (Wu et al. 2026) |
| B2 ⚠ | Pesos coherentes | Si hay `_peso`: suma de `_peso` = filas originales | Error ≤ 0,1 % | King y Zeng 2001 |
| B3 | Tamaño | Filas reducidas ≤ `n` pedido | 100 % | Límite de TabICLv2 (`evaluacion_latencia.md`) |
| B4 | Ficha | La respuesta trae método, filas antes/después y reglas aplicadas | 100 % | — |
| B5 | Reproducible | Misma tabla + intención + semilla → mismo archivo (mismo hash) | 100 % | — |
| B6 ⚠ | Descarga íntegra | El archivo de la URL tiene el hash que anunció la API y se puede leer | 100 % | — |
| B7 | Tiempo | Tiempo de reducción para 1M de filas en el HPC | Se mide y se reporta (sin umbral todavía) | — |

## C. API 2: criterios por intención

| Intención | # | Criterio | Cómo se mide | Umbral | Respaldo |
|---|---|---|---|---|---|
| `describir` | C1 ⚠ | Valor exacto | El resultado se calcula sobre toda la tabla: error relativo contra el valor exacto | 0 (exacto) | Amar 2005 (Compute Derived Value); BlinkDB: el muestreo da error |
| | C2 | Gráfica fiel | Con LTTB: la serie reducida conserva el máximo y el mínimo global | 100 % | Steinarsson 2013 |
| `anomalos` | C3 ⚠ | Candidatos conservados | Filas marcadas por el detector sobre la tabla completa que están en la reducida | 100 % si caben en n/2; si no, se reporta el total | Chandola 2009 |
| | C4 | Anomalías reales | En datasets con anomalías etiquetadas o inyectadas: recall en la tabla reducida / recall en la completa | ≥ 0,95 | ADBench 2022 |
| | C5 | Tipos cubiertos | Hay al menos un candidato de cada detector activo (extremo, salto, coherencia, pegado) cuando existen en la tabla completa | 100 % | Chandola 2009 (puntual, contextual, colectiva) |
| `predecir` | C9 ⚠ | Rendimiento | Métrica del TFM (accuracy/F1 o R²) con la tabla reducida / con el techo | ≥ 0,95 | Mediciones previas: taxi 97,7 %, airlines 98,9 % |
| | C10 ⚠ | Clases raras | Toda clase de la tabla original aparece en la reducida con ≥ min(total de la clase, 2 % de n) filas | 100 % | King y Zeng 2001; BlinkDB |
| | C11 | Proporciones corregidas | Proporción de cada clase ponderada por `_peso` vs la real | Diferencia ≤ 1 punto porcentual | King y Zeng 2001 |
| `pronosticar` | C12 ⚠ | Precisión | MASE con contexto reducido / MASE con contexto completo | ≤ 1,05 | Hyndman y Koehler 2006 |
| | C13 ⚠ | Serie regular | Timestamps a paso constante y sin huecos | 100 % | Requisito de Chronos-2 (`WORKFLOW_KORI.md`) |
| | C12b | Historia mínima | `n` a la resolución del pronóstico ≥ ventana de Chronos-2 (2048 pasos). *Agregado el 22/10: con n = 512, MASE 1,07× en Jena* | 100 % | Medido |
| | C14 | Tramo reciente | Las últimas filas de la reducida son idénticas a las de la original | 100 % | — |
| `relaciones` | C15 ⚠ | Correlación conservada | La correlación de la tabla completa cae dentro del IC 95 % **bootstrap** (200 remuestreos) de la correlación en la reducida, para cada par numérico. *Cambio del 22/10: el IC de Fisher supone normalidad y con colas pesadas daba 89–93 % de cobertura; se sigue reportando como referencia* | ≥ 95 % de los pares | Amar 2005 (Correlate) |
| | C16 | Orden conservado | Spearman entre el ranking de pares por correlación (completa vs reducida), **solo pares con \|r\| ≥ 0,1**. *Cambio del 22/10: entre pares con r ≈ 0 el orden es ruido (higgs: 0,76 con todos, 0,996 con los apreciables)* | ≥ 0,9 | — |
| | C17 | Sin causalidad | El texto que acompaña dice "asociación", nunca "causa" | 100 % | Leek y Peng 2015 |

## Resultado de una corrida

- **Por intención:** Cumple si todos sus criterios ⚠ cumplen y como máximo uno queda en Límite.
- **Servicio:** Cumple si A1, A2 y las 5 intenciones cumplen.
- **Cómo se reconoce el error:** cada respuesta de la API 2 lleva los criterios que se pueden calcular en el momento (B1–B6, C3, C10, C13, C14). Los que necesitan el techo (C4, C7, C9, C12, C15) solo se corren en el benchmark, no en cada pedido.

## Límites de la rúbrica

- Los umbrales sin respaldo publicado (1,05; 0,95; 0,9) son decisiones nuestras. Se pueden ajustar si el LIDI los considera demasiado estrictos o demasiado laxos.
- Los gold de la API 1 los escribió Claude; falta uno escrito por una persona del LIDI.

# Servicio de reducción de tablas (Kori)

Dos APIs (FastAPI). La 1 dice **qué** reglas tocan; la 2 las **aplica** y entrega la tabla reducida por URL.

```
investigador ──"quiero predecir el fraude"──▶ API 1 :8000 /reglas
             ◀── intención + reglas + parámetros que faltan
             ──intención + parámetros + tabla──▶ API 2 :8001 /reducir
             ◀── URL + sha256 + ficha + verificaciones
usuario / LLM ──GET URL──▶ API 2 /descargas/{id}.parquet
```

## Arrancar

Instalar: `pip install -r requirements.txt`, luego `cd servicio`.

```
python api_intencion.py     # http://127.0.0.1:8000/docs
python api_reduccion.py     # http://127.0.0.1:8001/docs
python cliente.py "quiero predecir el fraude" --ruta creditcard.parquet --parametros "{\"objetivo\": \"Class\"}"
```

## API 1: `POST /reglas`

| Recibe | Tipo | Obligatorio |
|---|---|---|
| `intencion` | texto libre | sí |

Responde `intencion`, `reglas` (con sus parámetros), `parametros_que_faltan`, `conserva`, `va_a` y `aviso` (en `relaciones`: "asociación, no causa"). Vacía → 400; no entendida → 422 con la lista de intenciones válidas. Clasifica con palabras clave, **sin LLM**.

## API 2: `POST /reducir` (formulario multipart)

| Recibe | Obligatorio | Qué es |
|---|---|---|
| `intencion` | sí | una de las 5 (la que devolvió la API 1) |
| `archivo` o `ruta` | uno de los dos | `.parquet`/`.csv` subido, o nombre de un archivo en `~/kori_datos_publicos` |
| `parametros` | según la regla | JSON con los parámetros de la tabla de abajo |

| Intención | Regla | Obligatorios | Opcionales (por defecto) |
|---|---|---|---|
| describir | `sin_reduccion` (o `lttb` si mandas `columna`) | — (`col_tiempo` con `columna`) | `n_puntos` 2000 |
| anomalos | `anomalias` | `columnas` | `n` 100000, `semilla` 0, `serie` false |
| predecir | `estratificado` | `objetivo` | `n` 100000, `semilla` 0, `piso_clase` 0.02 |
| pronosticar | `regular_reciente` | `col_tiempo` | `n` 100000, `frecuencia` (paso de la tabla) |
| relaciones | `aleatorio` | — | `n` 50000, `semilla` 0 |

Responde `url`, `sha256` (para comprobar la descarga), `ficha`, `verificaciones` (criterios de la rúbrica que se calculan en cada pedido) y `todas_cumplen`. Las tablas reducidas se guardan en `~/kori_servicio/descargas`.

## Evaluar

```
python evaluar_servicio.py      # contrato de las dos APIs + exactitud de la intención (A1–A6)
python evaluar_reduccion.py     # rúbrica B y C sobre datasets públicos (predecir tarda ~20 min)
```

Rúbrica: `docs/rubrica_evals_servicio.md`. Respaldo de las intenciones: `docs/investigacion_intenciones.md`.

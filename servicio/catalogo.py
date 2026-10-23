"""Catálogo del servicio: intención escrita por el investigador → reglas de reducción y sus parámetros.

Intenciones con respaldo fuerte o medio en la literatura (`investigacion_intenciones.md`); `imputar` quedó fuera.
Las reglas son funciones de `reduccion.py`. La intención se clasifica con palabras clave (sin LLM); los patrones
salen de `benchmark_enrutamiento.py` y el de `describir` se escribió mirando solo `gold_enrutamiento.json`.
"""
import re
import unicodedata

AVISO_CAUSA = "El resultado muestra asociación entre variables, no causa (Leek y Peng 2015)."

# parametros: obligatorios = sin ellos la API 2 responde 422; opcionales = con su valor por defecto
CATALOGO = {
    "describir": {
        "que_es": "promedios, totales, conteos, máximos, rankings, evolución histórica",
        "reglas": [
            {"regla": "sin_reduccion", "funcion": None,
             "detalle": "No se reduce: el valor se calcula exacto sobre toda la tabla.",
             "parametros": {"obligatorios": {}, "opcionales": {}}},
            {"regla": "lttb", "funcion": "reduccion.lttb",
             "detalle": "Solo si se va a graficar una serie larga: elige filas reales que conservan la forma.",
             "parametros": {"obligatorios": {}, "opcionales": {"col_tiempo": None, "columna": None, "n_puntos": 2000}}},
        ],
        "conserva": "el valor exacto", "va_a": "código",
    },
    "anomalos": {
        "que_es": "valores raros, atípicos, sospechosos, imposibles o errores",
        "reglas": [
            {"regla": "anomalias", "funcion": "reduccion.anomalias",
             "detalle": "Detectores sobre TODAS las filas; conserva todos los candidatos (la mitad de n para los más "
                        "raros) y completa con normales al azar.",
             "parametros": {"obligatorios": {"columnas": "columnas numéricas a revisar"},
                            "opcionales": {"n": 100_000, "semilla": 0, "serie": False}}},
        ],
        "conserva": "todos los candidatos a anomalía", "va_a": "TabICLv2 (residuo)",
    },
    "predecir": {
        "que_es": "estimar o clasificar una columna a partir de las otras",
        "reglas": [
            {"regla": "estratificado", "funcion": "reduccion.estratificado",
             "detalle": "Estratifica por el objetivo; cada clase rara tiene un piso y `_peso` corrige las proporciones.",
             "parametros": {"obligatorios": {"objetivo": "columna a predecir"},
                            "opcionales": {"n": 100_000, "semilla": 0, "piso_clase": 0.02}}},
        ],
        "conserva": "clases raras y distribución del objetivo", "va_a": "TabICLv2",
    },
    "pronosticar": {
        "que_es": "proyectar valores futuros en el tiempo",
        "reglas": [
            {"regla": "regular_reciente", "funcion": "reduccion.regular_reciente",
             "detalle": "Una sola resolución regular y el tramo más reciente; huecos interpolados y marcados.",
             "parametros": {"obligatorios": {"col_tiempo": "columna de fecha/hora"},
                            "opcionales": {"n": 100_000, "frecuencia": None}}},
        ],
        "conserva": "estacionalidad y tramo reciente", "va_a": "Chronos-2 + TabICLForecaster",
    },
    "relaciones": {
        "que_es": "correlación o asociación entre variables",
        "reglas": [
            {"regla": "aleatorio", "funcion": "reduccion.aleatorio",
             "detalle": "Muestra aleatoria simple: conserva la forma de la distribución y las correlaciones.",
             "parametros": {"obligatorios": {}, "opcionales": {"n": 50_000, "semilla": 0}}},
        ],
        "conserva": "la forma de la distribución", "va_a": "código + TabICLv2 opcional",
        "aviso": AVISO_CAUSA,
    },
}

PATRONES = [  # orden = prioridad
    ("pronosticar", r"mañana|próxim|pronost|proyect|esperamos|seguirá|habrá|evolucionará|venderemos|se irán|que viene"),
    ("anomalos", r"rar[oa]s|atípic|anómal|sospech|outlier|extrañ|imposibl|pegad|incoheren|absurd|error|fuera de lo normal|salen de lo normal|brusc|extrem"),
    ("relaciones", r"relaci|correlaci|influye|afecta|asocia|tienen que ver|cuando sube|aumentan|causa"),
    ("predecir", r"predic|predec|predig|estim|clasific|probabilidad|riesgo|entrena|es fraude|dejaría|vendería|debería|lleva un"),
    ("describir", r"promedi|media|medio|total|cuánt|cuál|qué|máxim|mínim|resum|distribuci|porcentaje|evoluci|"
                  r"frecuent|muestr|dame|lista|ranking|suma|cuenta|más|menos"),
]


def _norm(texto):
    # Sin tildes ni mayúsculas: "rellénalas" debe coincidir con "rellen" (la ñ se conserva)
    t = unicodedata.normalize("NFD", texto.lower()).replace("ñ", "ñ")
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


_PATRONES = [(i, _norm(p)) for i, p in PATRONES]


def clasificar(texto):
    """Devuelve (intención, palabra que coincidió) o (None, None) si no encaja en ninguna."""
    t = _norm(texto)
    for intencion, patron in _PATRONES:
        m = re.search(patron, t)
        if m:
            return intencion, m.group(0)
    return None, None

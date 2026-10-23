"""E5 del workflow: reducción de filas según la intención del análisis.

Toda política devuelve (tabla_reducida, ficha). La tabla conserva los VALORES ORIGINALES (nada se discretiza aquí)
y, cuando el muestreo no es proporcional, una columna `_peso` = cuántas filas originales representa cada fila,
para poder corregir medias y proporciones.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.cluster import MiniBatchKMeans

LIMITE = 100_000  # filas cómodas para TabICLv2; se ajusta midiendo en el DGX Spark


def _ficha(metodo, df, red, **extra):
    return {"metodo": metodo, "filas_antes": len(df), "filas_despues": len(red), **extra}


def control(df, red, columnas):
    """Diferencia relativa entre la media exacta y la de la muestra (ponderada si hay `_peso`)."""
    w = red["_peso"] if "_peso" in red else None
    out = {}
    for c in columnas:
        exacta = df[c].mean()
        m = np.average(red[c].dropna(), weights=None if w is None else w[red[c].notna()])
        out[c] = round(abs(m - exacta) / (abs(exacta) + 1e-12), 4)
    return out


def aleatorio(df, n=LIMITE, semilla=0):
    """Piso de comparación: muestreo aleatorio simple."""
    if len(df) <= n:
        return df, _ficha("sin_reduccion", df, df)
    red = df.sample(n, random_state=semilla)
    return red, _ficha("aleatorio", df, red)


def estratificado(df, objetivo, n=LIMITE, semilla=0, piso_clase=0.02, bins=20):
    """predecir: estratifica por el objetivo. Clasificación: cada clase recibe al menos `piso_clase`·n filas
    (o todas las que tenga), así las raras no desaparecen (luego se corrigen los priors). Regresión: estratos
    proporcionales por cuantiles del objetivo, con las colas (0,5 % de cada lado) como estrato propio."""
    if len(df) <= n:
        return df, _ficha("sin_reduccion", df, df)
    y = df[objetivo]
    rng = np.random.default_rng(semilla)
    es_clase = not pd.api.types.is_float_dtype(y) or y.nunique() <= 50
    if es_clase:
        grupos = y
    else:
        lo, hi = y.quantile([0.005, 0.995])
        colas = df.index[(y < lo) | (y > hi)]
        grupos = pd.qcut(y.rank(method="first"), bins, labels=False).where(~df.index.isin(colas), -1)
    conteo = grupos.value_counts()
    cuota = {}
    if es_clase:
        minimo = int(piso_clase * n)
        for g, c in conteo.items():
            cuota[g] = min(c, minimo)
        resto = n - sum(cuota.values())
        libres = {g: c - cuota[g] for g, c in conteo.items() if c > cuota[g]}
        total_libre = sum(libres.values())
        for g, c in libres.items():
            cuota[g] += int(resto * c / total_libre)
    else:
        # Regresión: estratos PROPORCIONALES (colas incluidas). Sobrerrepresentar las colas sesgaba al TFM
        # (taxi: R² 0,41 frente a 0,55 del aleatorio) y en regresión no hay corrección de priors que lo arregle.
        for g, c in conteo.items():
            cuota[g] = max(1, int(round(n * c / len(df))))
    partes = []
    for g, k in cuota.items():
        idx = grupos.index[grupos == g]
        elegidos = idx if k >= len(idx) else rng.choice(idx, k, replace=False)
        partes.append(pd.Series(len(idx) / max(len(elegidos), 1), index=elegidos))
    pesos = pd.concat(partes)
    red = df.loc[pesos.index].assign(_peso=pesos.values)
    return red, _ficha("estratificado", df, red, estratos=len(cuota),
                       filas_por_estrato={str(k): int(v) for k, v in red.groupby(grupos.loc[red.index]).size().items()})


def prototipos(df, columnas, n=LIMITE, semilla=0):
    """predecir (alternativa): n grupos con MiniBatchKMeans sobre columnas estandarizadas y, de cada grupo,
    la fila REAL más cercana al centro. `_peso` = tamaño del grupo."""
    if len(df) <= n:
        return df, _ficha("sin_reduccion", df, df)
    X = df[columnas].astype(float)
    X = ((X - X.mean()) / (X.std() + 1e-12)).fillna(0).to_numpy(np.float32)
    km = MiniBatchKMeans(n_clusters=n, random_state=semilla, batch_size=max(4096, n // 4), n_init=1, max_iter=20)
    etiquetas = km.fit_predict(X)
    d = ((X - km.cluster_centers_[etiquetas]) ** 2).sum(1)
    orden = pd.DataFrame({"g": etiquetas, "d": d, "i": np.arange(len(df))}).sort_values("d")
    rep = orden.drop_duplicates("g")
    tam = pd.Series(etiquetas).value_counts()
    red = df.iloc[rep["i"].to_numpy()].assign(_peso=tam.loc[rep["g"]].to_numpy())
    return red, _ficha("prototipos", df, red, grupos=int(len(rep)))


def puntaje_anomalia(df, columnas, semilla=0, serie=False, racha=12, residuo=True, predictores=None):
    """Detectores baratos sobre TODAS las filas. Cada uno da una severidad normalizada (≥ 1 = candidato):
      - valor extremo: z robusto (mediana/MAD) / 6
      - Isolation Forest: puntaje / percentil 99
      - en series: salto entre lecturas consecutivas (z robusto de la diferencia) / 8 y sensor pegado
        (mismo valor repetido) / `racha`
      - coherencia: residuo de LightGBM que predice cada columna desde `predictores` (por defecto, todas las
        columnas numéricas de la tabla, no solo las analizadas: la redundancia es lo que delata una deriva) / 20
    puntaje = severidad máxima, así al recortar candidatos se quedan los más graves de CADA tipo.
    Devuelve (es_candidato, puntaje, severidades por detector)."""
    X = df[columnas].astype(float)

    def z_robusto(M):
        mad = (M - M.median()).abs().median() * 1.4826 + 1e-12
        return ((M - M.median()).abs() / mad).max(axis=1).fillna(0)

    # Umbral de extremo adaptado a cada columna: 6 MAD, o el percentil 99,9 si la columna tiene colas pesadas
    # (con 6 fijo, las 28 variables PCA de creditcard marcaban el 17 % de las filas).
    Z = (X - X.median()).abs() / ((X - X.median()).abs().median() * 1.4826 + 1e-12)
    umbral = np.maximum(6, Z.quantile(0.999))
    sev = {"extremo": (Z / umbral).max(axis=1).fillna(0)}
    muestra = X.sample(min(len(X), 200_000), random_state=semilla).fillna(X.median())
    iso = IsolationForest(n_estimators=100, random_state=semilla, n_jobs=-1).fit(muestra)
    s_iso = pd.Series(-iso.score_samples(X.fillna(X.median())), index=df.index)
    sev["isolation"] = s_iso / s_iso.quantile(0.99)
    if serie:
        sev["salto"] = z_robusto(X.diff()) / 8
        largo = pd.concat([X[c].groupby((X[c] != X[c].shift()).cumsum()).transform("size") for c in columnas], axis=1)
        sev["pegado"] = largo.max(axis=1) / racha
    if residuo:
        predictores = predictores or list(df.select_dtypes("number").columns)
        if len(predictores) >= 3:
            sev["coherencia"] = z_residuo(df, columnas, predictores, semilla) / 20
    sev = pd.DataFrame(sev)
    puntaje = sev.max(axis=1)
    return puntaje >= 1, puntaje, sev


def z_residuo(df, columnas, predictores, semilla=0, muestra=100_000):
    """Coherencia entre columnas: para cada columna analizada, LightGBM la predice desde los predictores
    (entrenado con una muestra, aplicado a TODAS las filas). Devuelve el máximo z robusto del residuo por fila."""
    from lightgbm import LGBMRegressor
    peor = pd.Series(0.0, index=df.index)
    ent = df.sample(min(len(df), muestra), random_state=semilla)
    for c in columnas:
        otras = [o for o in predictores if o != c]
        ok = ent[c].notna()
        m = LGBMRegressor(n_estimators=200, verbose=-1, random_state=semilla, n_jobs=-1)
        m.fit(ent.loc[ok, otras], ent.loc[ok, c])
        res = df[c] - m.predict(df[otras])
        mad = (res - res.median()).abs().median() * 1.4826 + 1e-12
        peor = np.maximum(peor, ((res - res.median()).abs() / mad).fillna(0))
    return peor


def anomalias(df, columnas, n=LIMITE, semilla=0, serie=False, predictores=None):
    """anomalos: conserva TODOS los candidatos y completa con normales al azar como referencia.
    Si los candidatos superan n, se quedan los de mayor puntaje y se reporta el total."""
    candidato, puntaje, _ = puntaje_anomalia(df, columnas, semilla, serie, predictores=predictores)
    total_cand = int(candidato.sum())
    if len(df) <= n:
        return df.assign(_candidato=candidato), _ficha("sin_reduccion", df, df, candidatos=total_cand)
    # La mitad de la tabla reducida se reserva a las filas de mayor puntaje: si hay menos candidatos que eso,
    # se completa con las siguientes más raras (más barato que perder una anomalía sutil).
    cupo = max(total_cand, int(0.5 * n)) if len(df) > n else total_cand
    cand_idx = puntaje.sort_values(ascending=False).index[:min(cupo, n)]
    candidato = df.index.isin(cand_idx) | candidato
    candidato = pd.Series(candidato, index=df.index)
    normales = df.index[~candidato]
    k = min(len(normales), n - len(cand_idx))
    norm_idx = np.random.default_rng(semilla).choice(normales, k, replace=False)
    pesos = pd.Series(1.0, index=cand_idx)
    if total_cand > len(cand_idx):
        pesos[:] = total_cand / len(cand_idx)
    pesos = pd.concat([pesos, pd.Series(len(normales) / max(k, 1), index=norm_idx)])
    red = df.loc[pesos.index].assign(_peso=pesos.values, _candidato=df.loc[pesos.index].index.isin(cand_idx))
    return red, _ficha("anomalias", df, red, candidatos=total_cand, candidatos_conservados=int(len(cand_idx)))


def multirresolucion(df, col_tiempo, n=LIMITE, reciente=0.3):
    """pronosticar: el tramo reciente a resolución completa (`reciente`·n filas) y lo antiguo agregado por
    media con el paso mínimo que haga caber todo en n filas."""
    df = df.sort_values(col_tiempo)
    if len(df) <= n:
        return df, _ficha("sin_reduccion", df, df)
    k = int(n * reciente)
    nuevo, viejo = df.iloc[-k:], df.iloc[:-k]
    paso = int(np.ceil(len(viejo) / (n - k)))
    grupo = np.arange(len(viejo)) // paso
    num = viejo.select_dtypes("number").groupby(grupo).mean()
    num[col_tiempo] = viejo[col_tiempo].groupby(grupo).first().to_numpy()
    red = pd.concat([num, nuevo[num.columns]], ignore_index=True)
    return red, _ficha("multirresolucion", df, red, filas_recientes=k, paso_antiguo=paso)


def regular_reciente(df, col_tiempo, n=LIMITE, frecuencia=None):
    """pronosticar (reemplaza a `multirresolucion`, que mezcla resoluciones y Chronos-2 no la acepta): una sola
    resolución regular y el tramo más reciente que quepa en n. `frecuencia` (p. ej. "1h") promedia las columnas
    numéricas a ese paso; sin ella se usa el paso mediano de la tabla. Los huecos se interpolan y quedan marcados
    en `_relleno`."""
    df = df.sort_values(col_tiempo)
    t = pd.to_datetime(df[col_tiempo])
    paso = pd.Timedelta(frecuencia) if frecuencia else t.diff().median()
    num = df.select_dtypes("number").set_index(t)
    reg = num.resample(paso).mean()
    relleno = reg.isna().any(axis=1)
    reg = reg.interpolate(limit_direction="both")
    red = reg.assign(_relleno=relleno.to_numpy()).iloc[-n:].rename_axis(col_tiempo).reset_index()
    return red, _ficha("regular_reciente", df, red, paso=str(paso), filas_rellenas=int(red["_relleno"].sum()))


def lttb(df, col_tiempo, columna, n_puntos=2000):
    """describir, solo para graficar: Largest-Triangle-Three-Buckets (Steinarsson 2013). Elige n_puntos filas
    REALES que conservan la forma de `columna` en el tiempo; el primero y el último siempre quedan.
    LTTB no garantiza el máximo y el mínimo global, así que se elige con 2 puntos menos y se agregan esas filas."""
    df = df.sort_values(col_tiempo).dropna(subset=[columna])
    if len(df) <= n_puntos:
        return df, _ficha("sin_reduccion", df, df)
    x = pd.to_datetime(df[col_tiempo]).astype("int64").to_numpy(np.float64)
    y = df[columna].to_numpy(np.float64)
    n_puntos -= 2
    bordes = np.linspace(1, len(df) - 1, n_puntos - 1).astype(int)
    elegidos, a = [0], 0
    for i in range(n_puntos - 2):
        ini, fin = bordes[i], bordes[i + 1]
        sig_ini, sig_fin = bordes[i + 1], bordes[i + 2] if i + 2 < len(bordes) else len(df)
        cx, cy = x[sig_ini:sig_fin].mean(), y[sig_ini:sig_fin].mean()
        area = np.abs((x[a] - cx) * (y[ini:fin] - y[a]) - (x[a] - x[ini:fin]) * (cy - y[a]))
        a = ini + int(area.argmax())
        elegidos.append(a)
    elegidos += [len(df) - 1, int(y.argmax()), int(y.argmin())]
    red = df.iloc[sorted(set(elegidos))]
    return red, _ficha("lttb", df, red, columna=columna)


POLITICAS = {"describir": None, "predecir": estratificado, "anomalos": anomalias, "pronosticar": regular_reciente,
             "relaciones": aleatorio}

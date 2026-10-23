"""Verificaciones de la rúbrica (`rubrica_evals_servicio.md`) que se pueden calcular en cada pedido, sin techo.

Cada una devuelve {"criterio", "cumple", "detalle"}. Las que necesitan la tabla completa analizada (C4, C9, C12,
C15) se corren en `evaluar_reduccion.py`, no aquí.
"""
import pandas as pd


def _v(criterio, cumple, detalle=""):
    return {"criterio": criterio, "cumple": bool(cumple), "detalle": detalle}


def _hash_filas(df, cols):
    return pd.util.hash_pandas_object(df[cols], index=False)


def comunes(df, red, n, filas_reales=True):
    cols = [c for c in df.columns if c in red.columns]
    out = []
    if filas_reales:  # B1: cada fila reducida existe tal cual en la original
        fuera = ~_hash_filas(red, cols).isin(set(_hash_filas(df, cols)))
        out.append(_v("B1 valores originales", not fuera.any(), f"{int(fuera.sum())} filas no están en la original"))
    else:
        out.append(_v("B1 valores originales", True, "filas agregadas por diseño (declarado)"))
    if "_peso" in red:  # B2
        dif = abs(red["_peso"].sum() - len(df)) / len(df)
        out.append(_v("B2 pesos coherentes", dif <= 0.001, f"suma _peso = {red['_peso'].sum():,.0f} de {len(df):,}"))
    if n is not None:  # B3
        out.append(_v("B3 tamaño", len(red) <= n, f"{len(red):,} filas, n = {n:,}"))
    return out


def anomalos(red, ficha):
    total, kept = ficha.get("candidatos", 0), ficha.get("candidatos_conservados", ficha.get("candidatos", 0))
    return [_v("C3 candidatos conservados", kept >= total or kept >= len(red) // 2,
               f"{kept:,} de {total:,} candidatos")]


def predecir(df, red, objetivo, n, piso_clase):
    if not (not pd.api.types.is_float_dtype(df[objetivo]) or df[objetivo].nunique() <= 50):
        return []
    orig, dentro = df[objetivo].value_counts(), red[objetivo].value_counts()
    minimo = int(piso_clase * n) if len(df) > n else 0
    faltan = [str(c) for c, k in orig.items() if dentro.get(c, 0) < min(k, minimo)]
    out = [_v("C10 clases raras", not faltan, f"clases bajo el piso: {faltan}" if faltan else f"{len(orig)} clases")]
    if "_peso" in red:
        real = df[objetivo].value_counts(normalize=True)
        corr = red.groupby(objetivo)["_peso"].sum() / red["_peso"].sum()
        dif = float((corr.reindex(real.index, fill_value=0) - real).abs().max() * 100)
        out.append(_v("C11 proporciones corregidas", dif <= 1, f"diferencia máx. {dif:.2f} pp"))
    return out


def pronosticar(df, red, col_tiempo, frecuencia):
    t = pd.to_datetime(red[col_tiempo])
    pasos = t.diff().dropna().unique()
    out = [_v("C13 serie regular", len(pasos) <= 1, f"{len(pasos)} pasos distintos"),
           _v("C12b historia mínima", len(red) >= 2048,
              f"{len(red):,} pasos; Chronos-2 usa hasta 2048 (con 512 el MASE empeoró 7 % en Jena)")]
    if frecuencia is None:  # C14: a la resolución original, el final debe ser idéntico
        cols = [c for c in red.columns if c in df.columns and c != col_tiempo]
        a = df.sort_values(col_tiempo)[cols].tail(100).reset_index(drop=True)
        b = red[~red["_relleno"]][cols].tail(100).reset_index(drop=True)
        out.append(_v("C14 tramo reciente", a.equals(b) or (a - b).abs().max().max() < 1e-9,
                      "últimas 100 filas"))
    return out

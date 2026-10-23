"""Evalúa la API 2 (ya corriendo en :8001) con la rúbrica `rubrica_evals_servicio.md`, secciones B y C.

Todo pasa por HTTP como lo haría un cliente: pedido → URL → descarga → verificación. El techo (análisis sobre la
tabla completa) se calcula aquí, aparte. Las tablas preparadas para la prueba se escriben en DATOS/_eval_servicio.
Uso: python evaluar_reduccion.py [describir anomalos predecir pronosticar relaciones] [--rapido]
  --rapido  predecir solo con creditcard (TabICLv2 con 100k filas tarda varios minutos por dataset)
"""
import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from scipy import stats

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import datasets  # noqa: E402
import reduccion  # noqa: E402

API2 = "http://127.0.0.1:8001"
DATOS = Path.home() / "kori_datos_publicos"
EVAL = DATOS / "_eval_servicio"
EVAL.mkdir(exist_ok=True)
FILAS = []


def registrar(intencion, dataset, criterio, cumple, valor, umbral):
    FILAS.append({"intencion": intencion, "dataset": dataset, "criterio": criterio, "cumple": bool(cumple),
                  "valor": valor, "umbral": umbral})
    print(f"{'OK ' if cumple else 'MAL'} {intencion:11s} {dataset:12s} {criterio:30s} {valor} (umbral {umbral})", flush=True)


def pedir(intencion, ruta, parametros):
    r = httpx.post(f"{API2}/reducir", data={"intencion": intencion, "ruta": ruta, "parametros": json.dumps(parametros)},
                   timeout=3600)
    r.raise_for_status()
    resp = r.json()
    contenido = httpx.get(resp["url"], timeout=600).content
    return resp, pd.read_parquet(io.BytesIO(contenido)), hashlib.sha256(contenido).hexdigest()


def comunes(intencion, dataset, ruta, parametros):
    """B1–B6 y las verificaciones en línea que trae la respuesta. Devuelve la tabla reducida."""
    resp, red, h = pedir(intencion, ruta, parametros)
    for v in resp["verificaciones"]:
        registrar(intencion, dataset, v["criterio"], v["cumple"], v["detalle"], "rúbrica")
    registrar(intencion, dataset, "B4 ficha", {"metodo", "filas_antes", "filas_despues"} <= set(resp["ficha"]),
              resp["ficha"]["metodo"], "presente")
    registrar(intencion, dataset, "B6 descarga íntegra", h == resp["sha256"], h[:12], "= sha256 anunciado")
    resp2, _, h2 = pedir(intencion, ruta, parametros)
    registrar(intencion, dataset, "B5 reproducible", h2 == h, "mismo hash" if h2 == h else "hash distinto", "= hash")
    return resp, red


# ---------------------------------------------------------------- describir
def eval_describir():
    df = datasets.cargar("creditcard")
    _, red = comunes("describir", "creditcard", "creditcard.parquet", {})
    num = df.select_dtypes("number").columns
    err = float((red[num].mean() - df[num].mean()).abs().max())
    registrar("describir", "creditcard", "C1 valor exacto (media)", err == 0, f"error máx {err:.2e}", "0")
    for col in ["T (degC)", "p (mbar)"]:  # C2 lo verifica la API; aquí se registra vía comunes
        comunes("describir", f"jena:{col[:5]}", "jena.parquet", {"col_tiempo": "Date Time", "columna": col})


# ---------------------------------------------------------------- anomalos
def _hash(df, cols):
    return pd.util.hash_pandas_object(df[cols].reset_index(drop=True), index=False)


def eval_anomalos():
    sys.path.insert(0, str(AQUI.parent))
    from benchmark_anomalias import inyectar
    cc = datasets.cargar("creditcard")
    cols_cc = [c for c in cc.columns if c not in ("Class", "Time")]
    jena = datasets.cargar("jena")
    cols_j = ["T (degC)", "p (mbar)", "rh (%)", "wv (m/s)"]
    jena_iny, marca, _ = inyectar(jena, cols_j, por_tipo=100, semilla=0)
    jena_iny.to_parquet(EVAL / "jena_inyectada.parquet", index=False)
    pruebas = [("creditcard", cc, "creditcard.parquet", cols_cc, cc["Class"].astype(int) == 1, False, 20_000),
               ("jena_iny", jena_iny, "_eval_servicio/jena_inyectada.parquet", cols_j, marca != "", True, 50_000)]
    for nombre, df, ruta, cols, verdad, serie, n in pruebas:
        resp, red = comunes("anomalos", nombre, ruta, {"columnas": cols, "serie": serie, "n": n})
        cand, _, sev = reduccion.puntaje_anomalia(df, cols, 0, serie)
        rec_full = float(cand[verdad].mean())
        h_df, h_red = _hash(df, cols), _hash(red, cols)
        marcadas = set(h_red[red["_candidato"].to_numpy()])
        rec_red = float(h_df[verdad.to_numpy()].isin(marcadas).mean())
        ratio = rec_red / rec_full if rec_full else float("nan")
        registrar("anomalos", nombre, "C4 anomalías reales", ratio >= 0.95,
                  f"recall reducida {rec_red:.3f} / completa {rec_full:.3f} = {ratio:.3f}", "≥ 0,95")
        en_red = h_df.isin(set(h_red)).to_numpy()
        tipos = {d: int(((sev[d] >= 1).to_numpy() & en_red).sum()) for d in sev if (sev[d] >= 1).any()}
        registrar("anomalos", nombre, "C5 tipos cubiertos", all(v > 0 for v in tipos.values()), tipos, "≥ 1 por detector")


# ---------------------------------------------------------------- predecir
def evaluar_tfm_lotes(tarea, red, X, obj, prueba, prior_total, lote=5_000):
    """Como benchmark_predecir.evaluar_tfm, pero predice en lotes: con 100k de contexto y ~60k filas de prueba de
    una vez, la laptop se quedó sin memoria (GPU y RAM)."""
    from benchmark_predecir import corregir_priors, metricas
    from tabicl import TabICLClassifier, TabICLRegressor
    t = time.time()
    m = TabICLClassifier() if tarea == "clasificacion" else TabICLRegressor()
    m.fit(red[X], red[obj])
    partes = [prueba[X].iloc[i:i + lote] for i in range(0, len(prueba), lote)]
    if tarea == "regresion":
        pred = np.concatenate([m.predict(p) for p in partes])
        return metricas(tarea, prueba[obj], pred), time.time() - t
    proba = np.vstack([m.predict_proba(p) for p in partes])
    proba = corregir_priors(proba, m.classes_, prior_total, red[obj].value_counts(normalize=True).to_dict())
    return metricas(tarea, prueba[obj], m.classes_[proba.argmax(1)], proba), time.time() - t


def eval_predecir(nombres):
    from benchmark_predecir import metricas, preparar
    from lightgbm import LGBMClassifier, LGBMRegressor
    from sklearn.model_selection import train_test_split
    for nombre in nombres:
        df, info = preparar(nombre)
        obj, tarea = info["objetivo"], info["tarea"]
        X = [c for c in df.columns if c != obj]
        n_prueba = 10_000
        if tarea == "clasificacion":
            n_prueba = int(min(max(n_prueba, 150 / df[obj].value_counts(normalize=True).min()), 0.3 * len(df)))
        grande, prueba = train_test_split(df, test_size=n_prueba, random_state=0,
                                          stratify=df[obj] if tarea == "clasificacion" else None)
        grande.to_parquet(EVAL / f"{nombre}_grande.parquet", index=False)
        _, red = comunes("predecir", nombre, f"_eval_servicio/{nombre}_grande.parquet", {"objetivo": obj})
        red = red.drop(columns="_peso", errors="ignore")
        lgbm = (LGBMClassifier if tarea == "clasificacion" else LGBMRegressor)(verbose=-1, random_state=0, n_jobs=-1)
        lgbm.fit(grande[X], grande[obj])
        proba = lgbm.predict_proba(prueba[X]) if tarea == "clasificacion" else None
        techo = metricas(tarea, prueba[obj], lgbm.predict(prueba[X]), proba)
        prior = grande[obj].value_counts(normalize=True).to_dict() if tarea == "clasificacion" else None
        m, seg = evaluar_tfm_lotes(tarea, red, X, obj, prueba, prior)
        clave = "r2" if tarea == "regresion" else ("ap" if "ap" in m else "f1_macro")
        ratio = m[clave] / techo[clave]
        registrar("predecir", nombre, f"C9 rendimiento ({clave})", ratio >= 0.95,
                  f"TabICLv2 {m[clave]:.3f} / techo LightGBM {techo[clave]:.3f} = {ratio:.3f} ({seg:.0f} s)", "≥ 0,95")


# ---------------------------------------------------------------- pronosticar
def _mase(pred, real, ctx, estacion=24):
    escala = np.mean(np.abs(ctx[estacion:] - ctx[:-estacion]))
    return np.mean(np.abs(pred - real)) / escala


def eval_pronosticar():
    import torch
    from chronos import Chronos2Pipeline
    modelo = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cuda" if torch.cuda.is_available() else "cpu")
    series = [("jena", "jena.parquet", "Date Time", "T (degC)", datasets.cargar("jena")),
              ("ett", "series/ETTh1.csv", "date", "OT", pd.read_csv(DATOS / "series" / "ETTh1.csv"))]
    for nombre, ruta, col_t, obj, df in series:
        completa = df.assign(**{col_t: pd.to_datetime(df[col_t])}).set_index(col_t)[obj].resample("1h").mean().interpolate()
        for n in (100_000, 512):
            _, red = comunes("pronosticar", f"{nombre}:n{n}", ruta, {"col_tiempo": col_t, "frecuencia": "1h", "n": n})
            red_s = red.set_index(col_t)[obj]
            origenes = completa.index[-10 * 24 - 24:-24:12]  # 20 orígenes en los últimos 10 días, cada 12 h
            ratios = []
            for o in origenes:
                real = completa.loc[o:].iloc[:24].to_numpy()
                res = {}
                for etiqueta, s in (("completa", completa), ("reducida", red_s)):
                    ctx = s.loc[:o - pd.Timedelta("1h")].iloc[-2048:]
                    d = pd.DataFrame({"item_id": "s", "timestamp": ctx.index, "target": ctx.to_numpy()})
                    pred = modelo.predict_df(d, prediction_length=24, quantile_levels=[0.5])["predictions"].to_numpy()
                    res[etiqueta] = _mase(pred, real, completa.loc[:o - pd.Timedelta("1h")].iloc[-2048:].to_numpy())
                ratios.append((res["reducida"], res["completa"]))
            r = np.array(ratios)
            ratio = r[:, 0].mean() / r[:, 1].mean()
            registrar("pronosticar", f"{nombre}:n{n}", "C12 precisión (MASE)", ratio <= 1.05,
                      f"MASE reducida {r[:, 0].mean():.3f} / completa {r[:, 1].mean():.3f} = {ratio:.3f}", "≤ 1,05")


# ---------------------------------------------------------------- relaciones
def eval_relaciones():
    for nombre in ["taxi", "covertype", "higgs"]:
        df = datasets.cargar(nombre)
        resp, red = comunes("relaciones", nombre, f"{nombre}.parquet", {})
        registrar("relaciones", nombre, "C17 sin causalidad", bool(resp.get("aviso")) and "no causa" in resp["aviso"],
                  resp.get("aviso"), "aviso presente")
        num = [c for c in df.select_dtypes("number").columns if df[c].nunique() > 2][:30]
        cf, cr = df[num].corr(), red[num].corr()
        iu = np.triu_indices(len(num), 1)
        rf, rr = cf.to_numpy()[iu], cr.to_numpy()[iu]
        ok = ~np.isnan(rf) & ~np.isnan(rr)
        rf, rr = rf[ok], rr[ok]
        # Referencia: IC de Fisher. Supone normalidad bivariada; con colas pesadas queda demasiado estrecho.
        se = 1 / np.sqrt(len(red) - 3)
        z = np.arctanh(np.clip(rr, -0.999999, 0.999999))
        dentro_f = (np.tanh(z - 1.96 * se) <= rf) & (rf <= np.tanh(z + 1.96 * se))
        registrar("relaciones", nombre, "C15-ref IC Fisher (informativo)", True,
                  f"{dentro_f.mean():.1%} de {len(rf)} pares", "solo referencia")
        # C15: IC bootstrap percentil (200 remuestreos de la tabla reducida), sin supuesto de normalidad
        rng = np.random.default_rng(0)
        X = red[num].to_numpy(np.float64)
        boot = np.array([np.corrcoef(X[rng.integers(0, len(X), len(X))], rowvar=False)[iu][ok] for _ in range(200)])
        lo, hi = np.nanpercentile(boot, 2.5, axis=0), np.nanpercentile(boot, 97.5, axis=0)
        dentro = (lo <= rf) & (rf <= hi)
        registrar("relaciones", nombre, "C15 correlación conservada", dentro.mean() >= 0.95,
                  f"{dentro.mean():.1%} de {len(rf)} pares dentro del IC 95 % bootstrap", "≥ 95 %")
        # C16: orden de los pares con asociación apreciable (|r| ≥ 0,1); entre pares ~0 el orden es ruido
        fuertes = np.abs(rf) >= 0.1
        rho = stats.spearmanr(np.abs(rf[fuertes]), np.abs(rr[fuertes])).statistic if fuertes.sum() > 2 else float("nan")
        registrar("relaciones", nombre, "C16 orden conservado", rho >= 0.9,
                  f"Spearman {rho:.3f} en {int(fuertes.sum())} pares con |r| ≥ 0,1", "≥ 0,9")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("intenciones", nargs="*", default=["describir", "anomalos", "relaciones", "pronosticar", "predecir"])
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    for i in a.intenciones:
        if i == "predecir":
            eval_predecir(["creditcard"] if a.rapido else ["creditcard", "taxi", "covertype"])
        else:
            globals()[f"eval_{i}"]()
    r = pd.DataFrame(FILAS)
    (AQUI.parent / "resultados").mkdir(exist_ok=True)
    r.to_csv(AQUI.parent / "resultados" / f"servicio_reduccion_{'-'.join(a.intenciones)}.csv", index=False)
    print(f"\n{int(r.cumple.sum())}/{len(r)} criterios cumplen ({time.time() - t0:.0f} s)")
    print(r[~r.cumple].to_string())

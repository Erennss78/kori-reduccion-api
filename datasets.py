"""Catálogo y descarga de los datasets públicos del prototipo de reducción (E5).

Los datos se guardan fuera de OneDrive (~/kori_datos_publicos) para no sincronizar cientos de MB.
Uso: python datasets.py [nombre ...]   (sin nombres descarga todos)
"""
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

DIR = Path.home() / "kori_datos_publicos"

# tarea: clasificacion | regresion | serie. objetivo: columna a predecir (en series, las variables a pronosticar).
CATALOGO = {
    "creditcard": dict(url="https://data.openml.org/datasets/0000/1597/dataset_1597.pq", tarea="clasificacion",
                       objetivo="Class", nota="Kaggle, fraude 0,17 %: clase muy rara + anomalías etiquetadas"),
    "covertype": dict(url="https://data.openml.org/datasets/0000/1596/dataset_1596.pq", tarea="clasificacion",
                      objetivo="class", nota="581k filas, 7 clases desbalanceadas, 54 columnas"),
    "higgs": dict(url="https://data.openml.org/datasets/0004/42769/dataset_42769.pq", tarea="clasificacion",
                  objetivo="target", nota="1M filas, binaria equilibrada"),
    "taxi": dict(url="https://data.openml.org/datasets/0004/42729/dataset_42729.pq", tarea="regresion",
                 objetivo="tip_amount", nota="581k filas, regresión con columnas de fecha"),
    "airlines10m": dict(url="https://data.openml.org/datasets/0004/42728/dataset_42728.pq", tarea="regresion",
                        objetivo="DepDelay", nota="10M filas: el caso de escala del ejemplo 10M → 100k"),
    "jena": dict(url="https://storage.googleapis.com/tensorflow/tf-keras-datasets/jena_climate_2009_2016.csv.zip",
                 tarea="serie", objetivo="T (degC)",
                 nota="Estación meteorológica cada 10 min (420k filas): lo más parecido a PSHA"),
}


def ruta(nombre):
    return DIR / f"{nombre}.parquet"


def descargar(nombre):
    destino = ruta(nombre)
    if destino.exists():
        return destino
    DIR.mkdir(parents=True, exist_ok=True)
    url = CATALOGO[nombre]["url"]
    tmp = DIR / Path(url).name
    print(f"descargando {nombre} ...", flush=True)
    urllib.request.urlretrieve(url, tmp)
    if tmp.suffix == ".zip":
        with zipfile.ZipFile(tmp) as z:
            df = pd.read_csv(z.open(z.namelist()[0]))
        df["Date Time"] = pd.to_datetime(df["Date Time"], format="%d.%m.%Y %H:%M:%S")
        df.to_parquet(destino, index=False)
        tmp.unlink()
    else:
        tmp.rename(destino)
    return destino


def cargar(nombre):
    return pd.read_parquet(descargar(nombre))


if __name__ == "__main__":
    for n in sys.argv[1:] or CATALOGO:
        df = cargar(n)
        print(f"{n:12s} {len(df):>10,} filas x {df.shape[1]:>3} col | {CATALOGO[n]['nota']}")

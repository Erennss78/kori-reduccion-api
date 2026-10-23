"""Cliente de las dos APIs: intención (texto) → reglas (API 1) → tabla reducida descargada (API 2).

Uso:
  python cliente.py "quiero predecir el fraude" --ruta creditcard.parquet --parametros '{"objetivo": "Class"}'
  python cliente.py "hay valores raros?" --archivo mi_tabla.csv --parametros '{"columnas": ["temp"]}'
"""
import argparse
import hashlib
import json
from pathlib import Path

import httpx

API1, API2 = "http://127.0.0.1:8000", "http://127.0.0.1:8001"


def pedir_reglas(intencion, url=API1):
    r = httpx.post(f"{url}/reglas", json={"intencion": intencion}, timeout=10)
    return r.status_code, r.json()


def reducir(intencion, parametros=None, archivo=None, ruta=None, url=API2):
    datos = {"intencion": intencion, "parametros": json.dumps(parametros or {})}
    if ruta:
        datos["ruta"] = ruta
    files = {"archivo": (Path(archivo).name, open(archivo, "rb"))} if archivo else None
    r = httpx.post(f"{url}/reducir", data=datos, files=files, timeout=1800)
    return r.status_code, r.json()


def descargar(respuesta, destino):
    contenido = httpx.get(respuesta["url"], timeout=600).content
    Path(destino).write_bytes(contenido)
    return hashlib.sha256(contenido).hexdigest() == respuesta["sha256"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("intencion")
    ap.add_argument("--archivo")
    ap.add_argument("--ruta")
    ap.add_argument("--parametros", default="{}")
    ap.add_argument("--destino", default="tabla_reducida.parquet")
    a = ap.parse_args()
    codigo, r1 = pedir_reglas(a.intencion)
    print("API 1:", codigo, json.dumps(r1, ensure_ascii=False, indent=2))
    if codigo != 200 or not (a.archivo or a.ruta):
        raise SystemExit
    codigo, r2 = reducir(r1["intencion"], json.loads(a.parametros), a.archivo, a.ruta)
    print("API 2:", codigo, json.dumps(r2, ensure_ascii=False, indent=2))
    if codigo == 200:
        print("descargada en", a.destino, "| hash correcto:", descargar(r2, a.destino))

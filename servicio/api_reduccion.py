"""API 2: aplica las reglas de la intención, reduce la tabla y devuelve una URL para descargarla.

POST /reducir (formulario multipart):
  intencion   una de las 5 del catálogo (la que devolvió la API 1)
  parametros  JSON con los parámetros de la regla, p. ej. {"objetivo": "Class", "n": 100000}
  archivo     la tabla (.parquet o .csv)   ─┐ uno de los dos
  ruta        nombre de un archivo en DATOS ─┘ (tablas grandes que ya están en el servidor)
GET /descargas/{id}.parquet  devuelve la tabla reducida.

Uso: python api_reduccion.py            (http://127.0.0.1:8001, documentación en /docs)
"""
import hashlib
import io
import json
import sys
import uuid
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import reduccion  # noqa: E402
import verificar  # noqa: E402
from catalogo import CATALOGO  # noqa: E402

DATOS = Path.home() / "kori_datos_publicos"            # de aquí se leen las tablas pedidas por `ruta`
DESCARGAS = Path.home() / "kori_servicio" / "descargas"  # fuera de OneDrive
DESCARGAS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Kori API 2: reducción de tablas según la intención")


def _leer(archivo, ruta):
    if (archivo is None) == (ruta is None):
        raise HTTPException(400, "manda `archivo` o `ruta`, uno de los dos")
    if ruta is not None:
        p = (DATOS / ruta).resolve()
        if DATOS.resolve() not in p.parents or not p.is_file():
            raise HTTPException(404, f"no existe `{ruta}` en la carpeta de datos del servidor")
        return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    datos = archivo.file.read()
    if archivo.filename.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(datos))
    if archivo.filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(datos))
    raise HTTPException(415, "formatos aceptados: .parquet y .csv")


def _parametros(intencion, crudo, df):
    try:
        p = json.loads(crudo) if crudo else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "`parametros` no es un JSON válido")
    regla = CATALOGO[intencion]["reglas"][-1] if intencion == "describir" and p.get("columna") else \
        CATALOGO[intencion]["reglas"][0]
    faltan = [k for k in regla["parametros"]["obligatorios"] if k not in p]
    if intencion == "describir" and p.get("columna") and "col_tiempo" not in p:
        faltan.append("col_tiempo")
    if faltan:
        raise HTTPException(422, {"error": "faltan parámetros", "faltan": faltan,
                                  "parametros": regla["parametros"]})
    cols = [p[k] for k in ("objetivo", "col_tiempo", "columna") if k in p] + p.get("columnas", [])
    no_existen = [c for c in cols if c not in df.columns]
    if no_existen:
        raise HTTPException(422, {"error": "columnas que no existen en la tabla", "columnas": no_existen})
    return regla["regla"], {**regla["parametros"]["opcionales"], **p}


def _aplicar(intencion, regla, df, p):
    n = p.get("n")
    if regla == "sin_reduccion":
        return df, {"metodo": "sin_reduccion", "filas_antes": len(df), "filas_despues": len(df)}, \
            verificar.comunes(df, df, None)
    if regla == "lttb":
        red, ficha = reduccion.lttb(df, p["col_tiempo"], p["columna"], p["n_puntos"])
        y = df[p["columna"]]
        extremos = red[p["columna"]].max() == y.max() and red[p["columna"]].min() == y.min()
        return red, ficha, verificar.comunes(df, red, p["n_puntos"]) + [
            verificar._v("C2 gráfica fiel", extremos, "máximo y mínimo global conservados")]
    if regla == "anomalias":
        red, ficha = reduccion.anomalias(df, p["columnas"], n, p["semilla"], p["serie"])
        return red, ficha, verificar.comunes(df, red, n) + verificar.anomalos(red, ficha)
    if regla == "estratificado":
        red, ficha = reduccion.estratificado(df, p["objetivo"], n, p["semilla"], p["piso_clase"])
        return red, ficha, verificar.comunes(df, red, n) + verificar.predecir(df, red, p["objetivo"], n, p["piso_clase"])
    if regla == "regular_reciente":
        red, ficha = reduccion.regular_reciente(df, p["col_tiempo"], n, p["frecuencia"])
        return red, ficha, verificar.comunes(df, red, n, filas_reales=False) + \
            verificar.pronosticar(df, red, p["col_tiempo"], p["frecuencia"])
    red, ficha = reduccion.aleatorio(df, n, p["semilla"])
    return red, ficha, verificar.comunes(df, red, n)


@app.post("/reducir")
def reducir(request: Request, intencion: str = Form(...), parametros: str = Form(None),
            archivo: UploadFile = File(None), ruta: str = Form(None)):
    if intencion not in CATALOGO:
        raise HTTPException(422, {"error": f"intención desconocida: {intencion}", "validas": list(CATALOGO)})
    df = _leer(archivo, ruta)
    regla, p = _parametros(intencion, parametros, df)
    red, ficha, checks = _aplicar(intencion, regla, df, p)
    ident = uuid.uuid4().hex[:12]
    destino = DESCARGAS / f"{ident}.parquet"
    red.to_parquet(destino, index=False)
    return {"id": ident, "url": f"{str(request.base_url).rstrip('/')}/descargas/{ident}.parquet",
            "sha256": hashlib.sha256(destino.read_bytes()).hexdigest(),
            "intencion": intencion, "regla": regla, "parametros": p, "ficha": ficha,
            "verificaciones": checks, "todas_cumplen": all(c["cumple"] for c in checks),
            "aviso": CATALOGO[intencion].get("aviso")}


@app.get("/descargas/{nombre}")
def descargar(nombre: str):
    p = DESCARGAS / Path(nombre).name
    if not p.is_file():
        raise HTTPException(404, "no existe esa descarga")
    return FileResponse(p, media_type="application/octet-stream", filename=p.name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)

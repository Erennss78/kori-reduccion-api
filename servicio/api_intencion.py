"""API 1: recibe la intención (texto libre, obligatorio) y responde qué reglas de reducción tocan y qué
parámetros necesita cada una. No toca ninguna tabla.

Uso: python api_intencion.py            (http://127.0.0.1:8000, documentación en /docs)
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from catalogo import CATALOGO, clasificar

app = FastAPI(title="Kori API 1: intención → reglas de reducción")


class Pedido(BaseModel):
    intencion: str  # obligatoria: qué quiere hacer el investigador con la tabla


def _validas():
    return {k: v["que_es"] for k, v in CATALOGO.items()}


@app.post("/reglas")
def reglas(p: Pedido):
    texto = p.intencion.strip()
    if not texto:
        raise HTTPException(400, {"error": "falta la intención", "intenciones_validas": _validas()})
    intencion, coincidencia = clasificar(texto)
    if intencion is None:
        raise HTTPException(422, {"error": "no entendí la intención, reescríbela",
                                  "intenciones_validas": _validas()})
    c = CATALOGO[intencion]
    faltan = sorted({k for r in c["reglas"] for k in r["parametros"]["obligatorios"]})
    return {"texto": texto, "intencion": intencion, "coincidencia": coincidencia, "reglas": c["reglas"],
            "parametros_que_faltan": faltan,  # la frase no los trae: hay que mandarlos a la API 2
            "conserva": c["conserva"], "va_a": c["va_a"], "aviso": c.get("aviso")}


@app.get("/intenciones")
def intenciones():
    return _validas()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

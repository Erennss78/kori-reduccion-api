"""Evalúa por HTTP (APIs ya corriendo): contrato de las dos APIs (A1, A5, A6) + exactitud de la intención (A2–A4).

gold_enrutamiento.json se usó para escribir los patrones (optimista); los dos gold ciegos son la medida honesta.
Las preguntas de `imputar` se excluyen: esa intención salió del catálogo (respaldo débil).
Uso: python evaluar_servicio.py [--url http://127.0.0.1:8000] [--url2 http://127.0.0.1:8001]
"""
import argparse
import json
import time
from pathlib import Path

import httpx
import pandas as pd

AQUI = Path(__file__).parent
GOLD = ["gold_enrutamiento.json", "gold_enrutamiento_ciego.json", "gold_enrutamiento_ciego2.json"]

CONTRATO = [  # (cuerpo enviado, código esperado)
    ({"intencion": "quiero ver si hay valores raros en la temperatura"}, 200),
    ({"intencion": ""}, 400),
    ({"intencion": "    "}, 400),
    ({}, 422),                    # falta el campo: lo rechaza la validación de FastAPI
    ({"intencion": None}, 422),
    ({"intencion": "hola"}, 422),
    ({"intencion": "asdfgh"}, 422),
]

CONTRATO_API2 = [  # (formulario enviado, código esperado, qué prueba)
    ({"intencion": "imputar", "ruta": "creditcard.parquet"}, 422, "intención fuera del catálogo"),
    ({"intencion": "predecir", "ruta": "creditcard.parquet"}, 422, "A5: falta `objetivo`"),
    ({"intencion": "pronosticar", "ruta": "jena.parquet"}, 422, "A5: falta `col_tiempo`"),
    ({"intencion": "predecir", "ruta": "creditcard.parquet", "parametros": '{"objetivo": "no_existe"}'}, 422,
     "columna inexistente"),
    ({"intencion": "relaciones"}, 400, "sin tabla"),
    ({"intencion": "relaciones", "ruta": "../../.ssh/id_rsa"}, 404, "ruta fuera de la carpeta de datos"),
    ({"intencion": "relaciones", "ruta": "creditcard.parquet", "parametros": "{mal json"}, 400, "JSON inválido"),
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--url2", default="http://127.0.0.1:8001")
    a = ap.parse_args()
    cli = httpx.Client(base_url=a.url, timeout=10)

    print("== Contrato ==")
    fallos = 0
    for cuerpo, esperado in CONTRATO:
        r = cli.post("/reglas", json=cuerpo)
        ok = r.status_code == esperado
        fallos += not ok
        print(f"{'OK ' if ok else 'MAL'} {json.dumps(cuerpo, ensure_ascii=False):60s} → {r.status_code} (esperado {esperado})")
    print(f"contrato API 1: {len(CONTRATO) - fallos}/{len(CONTRATO)}")

    print("\n== Contrato API 2 ==")
    f2 = 0
    for form, esperado, que in CONTRATO_API2:
        r = httpx.post(f"{a.url2}/reducir", data=form, timeout=120)
        ok = r.status_code == esperado
        f2 += not ok
        print(f"{'OK ' if ok else 'MAL'} {que:35s} → {r.status_code} (esperado {esperado}) {r.text[:90]}")
    print(f"contrato API 2: {len(CONTRATO_API2) - f2}/{len(CONTRATO_API2)}")

    print("\n== A5 parámetros que faltan / A6 causalidad ==")
    for texto, intencion, faltan in [("¿cuál será la temperatura mañana?", "pronosticar", ["col_tiempo"]),
                                     ("predecir si el cliente se va", "predecir", ["objetivo"]),
                                     ("¿hay valores atípicos?", "anomalos", ["columnas"])]:
        r = cli.post("/reglas", json={"intencion": texto}).json(); r = r if "intencion" in r else {"intencion": "no_entendida", "parametros_que_faltan": [], "aviso": None}
        ok = r["intencion"] == intencion and r["parametros_que_faltan"] == faltan
        print(f"{'OK ' if ok else 'MAL'} A5 {texto:40s} → {r['intencion']}, faltan {r['parametros_que_faltan']}")
    for texto in ["¿qué causa que suban las ventas?", "¿la lluvia influye en el rendimiento?"]:
        r = cli.post("/reglas", json={"intencion": texto}).json(); r = r if "intencion" in r else {"intencion": "no_entendida", "parametros_que_faltan": [], "aviso": None}
        ok = r["intencion"] == "relaciones" and "no causa" in (r.get("aviso") or "")
        print(f"{'OK ' if ok else 'MAL'} A6 {texto:40s} → {r['intencion']}, aviso: {bool(r.get('aviso'))}")

    filas = []
    for g in GOLD:
        gold = json.loads((AQUI.parent / g).read_text(encoding="utf-8"))
        for p in gold["preguntas"]:
            if p["i"] == "imputar":
                continue
            t = time.perf_counter()
            r = cli.post("/reglas", json={"intencion": p["q"]})
            ms = 1000 * (time.perf_counter() - t)
            pred = r.json()["intencion"] if r.status_code == 200 else "no_entendida"
            filas.append({"gold": Path(g).stem.replace("gold_enrutamiento", "original").replace("original_", ""),
                          "pregunta": p["q"], "real": p["i"], "pred": pred, "codigo": r.status_code, "ms": ms})
    r = pd.DataFrame(filas)
    r["ok"] = r.real == r.pred
    (AQUI.parent / "resultados").mkdir(exist_ok=True)
    r.to_csv(AQUI.parent / "resultados" / "servicio_intencion.csv", index=False)

    print("\n== Exactitud de la intención ==")
    print(r.groupby("gold").agg(n=("ok", "size"), exactitud=("ok", "mean"),
                                no_entendidas=("codigo", lambda c: (c != 200).mean())).round(3))
    print("\nPor intención (solo gold ciegos):")
    print(r[r.gold != "original"].groupby("real").ok.mean().round(2))
    print("\nConfusiones más frecuentes (gold ciegos):")
    print(r[(r.gold != "original") & ~r.ok].groupby(["real", "pred"]).size().sort_values(ascending=False).head(8))
    print(f"\nLatencia por pedido: mediana {r.ms.median():.1f} ms, p95 {r.ms.quantile(0.95):.1f} ms, n={len(r)}")

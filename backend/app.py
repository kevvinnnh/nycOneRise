from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import pandas as pd
import os, json

APP_DIR = os.path.dirname(__file__)
ART_DIR = os.path.join(APP_DIR, "artifacts")

NEEDS_PATH = os.path.join(ART_DIR, "needs_emb.npy")
GIVES_PATH = os.path.join(ART_DIR, "gives_emb.npy")
META_PATH  = os.path.join(ART_DIR, "founders_meta.parquet")
MANIFEST_PATH = os.path.join(ART_DIR, "manifest.json")

app = FastAPI(title="OneRise Founder Match API", version="0.1.0")

# allow local file + gh-pages origin; add your production frontend origin here

# ✅ Allow both local and deployed frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://kevvinnnh.github.io",   # your deployed frontend
        "http://127.0.0.1:5500",         # local frontend
        "http://localhost:5500",
        "http://[::]:5500",              # for IPv6 (Safari / macOS)
        "https://nyconerise.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# global state
E_NEEDS = None
E_GIVES = None
DF = None
MANIFEST = None

def load_artifacts():
    global E_NEEDS, E_GIVES, DF, MANIFEST
    if not (os.path.exists(NEEDS_PATH) and os.path.exists(GIVES_PATH) and os.path.exists(META_PATH)):
        raise RuntimeError("Missing artifacts. Ensure needs_emb.npy, gives_emb.npy, founders_meta.parquet exist.")

    E_NEEDS = np.load(NEEDS_PATH).astype("float32")
    E_GIVES = np.load(GIVES_PATH).astype("float32")
    DF = pd.read_parquet(META_PATH, engine="fastparquet")


    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r") as f:
            MANIFEST = json.load(f)
    else:
        MANIFEST = {"rows": len(DF), "dims": int(E_NEEDS.shape[1])}

    # sanity checks
    assert E_NEEDS.shape[0] == len(DF)
    assert E_GIVES.shape[0] == len(DF)
    # assume rows are L2-normalized; if not, normalize:
    # E_NEEDS /= (np.linalg.norm(E_NEEDS, 1) + 1e-12)

@app.on_event("startup")
def startup_event():
    load_artifacts()

@app.get("/api/health")
def health():
    return {"ok": True, "rows": len(DF), "dims": int(E_NEEDS.shape[1]), "manifest": MANIFEST}

@app.get("/api/founders")
def founders(limit: int = Query(100, ge=1, le=1000), q: str | None = None):
    sub = DF
    if q:
        ql = q.lower()
        sub = sub[ sub["founder_name"].str.lower().str.contains(ql) | sub["industry"].str.lower().str.contains(ql) ]
    sub = sub.reset_index(drop=True).head(limit)
    return sub[["founder_id","startup_id","founder_name","industry"]].to_dict(orient="records")

class TopKResponse(BaseModel):
    query_index: int
    founder: dict
    matches: list

@app.get("/api/topk", response_model=TopKResponse)
def topk(i: int = Query(..., ge=0), k: int = Query(5, ge=1, le=50)):
    n = len(DF)
    if i >= n:
        raise HTTPException(400, f"index i must be < {n}")
    sims = E_NEEDS[i] @ E_GIVES.T  # cosine since L2-normalized
    # mask self if same set
    sims[i] = -1e9
    top_idx = np.argpartition(-sims, k)[:k]
    top_idx = top_idx[np.argsort(-sims[top_idx])]

    rows = []
    for j in top_idx:
        rows.append({
            "rank": len(rows)+1,
            "index": int(j),
            "score": float(sims[j]),
            "founder_id": DF.iloc[j]["founder_id"],
            "founder_name": DF.iloc[j]["founder_name"],
            "industry": DF.iloc[j]["industry"],
            "gives_text": DF.iloc[j]["__gives_text__"][:160],
        })

    me = DF.iloc[i]
    return TopKResponse(
        query_index=i,
        founder={
            "founder_id": me["founder_id"],
            "founder_name": me["founder_name"],
            "industry": me["industry"],
            "needs_text": me["__needs_text__"][:200],
        },
        matches=rows
    )
    
@app.get("/api/health")
def health():
    return {"ok": True, "rows": len(DF), "dims": int(E_NEEDS.shape[1]), "manifest": MANIFEST}

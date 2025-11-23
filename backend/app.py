from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import pandas as pd
import os, json
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer


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


#explanation generator
#download NLTK resources
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('wordnet', quiet=True)
nltk.download('omw-1.4', quiet=True)


lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))


#preprocess text function
def preprocess_text(text: str) -> str:
    words = nltk.word_tokenize(str(text))
    words = [lemmatizer.lemmatize(w) for w in words if w.lower() not in stop_words]
    return " ".join(words)


@app.on_event("startup")
def startup_event():
    load_artifacts()


@app.get("/api/health")
def health():
    return {"ok": True, "rows": len(DF), "dims": int(E_NEEDS.shape[1]), "manifest": MANIFEST}


@app.get("/api/founders")
def founders(limit: int = Query(100, ge=1, le=1000), q: str | None = None):
    sub = DF.copy()
    if q:
        ql = q.lower()
        sub = sub[
            sub["founder_name"].str.lower().str.contains(ql, na=False) |
            sub.get("industry", pd.Series([""]*len(sub))).str.lower().str.contains(ql, na=False)
        ]
    # keep original DF index so frontend can use it to query topk
    sub = sub.reset_index()  # original DF index becomes column "index"
    sub = sub.head(limit)
    out = []
    for _, row in sub.iterrows():
        out.append({
            "index": int(row["index"]),  # global DF index
            "founder_id": row.get("founder_id"),
            "startup_id": row.get("startup_id"),
            "founder_name": row.get("founder_name"),
            "industry": row.get("industry"),
            "needs_text": row.get("__needs_text__", "")[:200] if "__needs_text__" in row else "",
            "gives_text": row.get("__gives_text__", "")[:160] if "__gives_text__" in row else ""
        })
    return out

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
   
@app.get("/api/explain")
def explain(founder_index: int = Query (..., ge=0), k:int=Query(5, ge=1, le=50)):
    #text explanation for top-k matches of given founder
    if founder_index >= len(DF):
        raise HTTPException(400, f"index must be < {len(DF)}")
   
    #compute similarities
    sims = E_NEEDS[founder_index] @ E_GIVES.T
    sims[founder_index] = -1e9
    top_idx = np.argpartition(-sims, k)[:k]
    top_idx = top_idx[np.argsort(-sims[top_idx])]
   
    #explanations array
    explanations=[]
   
    needs_text = preprocess_text(str(DF.iloc[founder_index]["__needs_text__"]))
    for j in top_idx:
        gives_text = preprocess_text(str(DF.iloc[j]["__gives_text__"]))
       
        explanations.append({
            "founder_name": DF.iloc[j]["founder_name"],
            "industry": DF.iloc[j]["industry"],
            "similarity_score": float(sims[j]),
            "explanation": f"Match based on overlap between founder needs: '{needs_text}' and gives: '{gives_text}'"
        })
   
    #return explanations
    return {
        "query_index": founder_index,
        "founder": {
            "founder_name": DF.iloc[founder_index]["founder_name"],
            "industry": DF.iloc[founder_index]["industry"],
        },
        "explanations": explanations
    }


   
# --- Health: explicit GET + explicit HEAD ---
@app.get("/api/health")
def health_get():
    return {"ok": True, "rows": len(DF), "dims": int(E_NEEDS.shape[1]), "manifest": MANIFEST}


@app.head("/api/health")
def health_head():
    # Lightweight 200 for HEAD checks
    return Response(status_code=200)


# Optional: alternate ping that accepts both GET/HEAD with a single route
@app.api_route("/api/ping", methods=["GET", "HEAD"])
def ping():
    return {"ok": True}



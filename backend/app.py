from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import pandas as pd
import os, json, hashlib
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# ===============================================================
# PATHS
# ===============================================================
APP_DIR = os.path.dirname(__file__)
ART_DIR = os.path.join(APP_DIR, "artifacts")

NEEDS_PATH = os.path.join(ART_DIR, "needs_emb.npy")
GIVES_PATH = os.path.join(ART_DIR, "gives_emb.npy")
META_PATH = os.path.join(ART_DIR, "founders_meta.parquet")
MANIFEST_PATH = os.path.join(ART_DIR, "manifest.json")
USER_DB_PATH = os.path.join(ART_DIR, "founders_user.json")

# ===============================================================
# FASTAPI APP
# ===============================================================
app = FastAPI(title="OneRise Founder Match API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://kevvinnnh.github.io",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://[::]:5500",
        "https://nyconerise.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================================================
# GLOBAL DATA
# ===============================================================
E_NEEDS = None
E_GIVES = None
DF = None
MANIFEST = None


# ===============================================================
# USER FOUNDER DB HELPERS
# ===============================================================
def load_user_founders():
    if not os.path.exists(USER_DB_PATH):
        with open(USER_DB_PATH, "w") as f:
            json.dump([], f)
    with open(USER_DB_PATH, "r") as f:
        return json.load(f)


def save_user_founders(data):
    with open(USER_DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ===============================================================
# LOAD ARTIFACTS
# ===============================================================
def load_artifacts():
    global E_NEEDS, E_GIVES, DF, MANIFEST

    if not (os.path.exists(NEEDS_PATH) and os.path.exists(GIVES_PATH) and os.path.exists(META_PATH)):
        raise RuntimeError("Missing required artifact files")

    E_NEEDS = np.load(NEEDS_PATH).astype("float32")
    E_GIVES = np.load(GIVES_PATH).astype("float32")
    DF = pd.read_parquet(META_PATH, engine="fastparquet")

    if os.path.exists(MANIFEST_PATH):
        MANIFEST = json.load(open(MANIFEST_PATH, "r"))
    else:
        MANIFEST = {"rows": len(DF), "dims": int(E_NEEDS.shape[1])}

    assert len(E_NEEDS) == len(DF)
    assert len(E_GIVES) == len(DF)


# ===============================================================
# NLTK SETUP
# ===============================================================
nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)
nltk.download("wordnet", quiet=True)
nltk.download("omw-1.4", quiet=True)

lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words("english"))

def preprocess_text(text: str) -> str:
    words = nltk.word_tokenize(str(text))
    words = [lemmatizer.lemmatize(w) for w in words if w.lower() not in stop_words]
    return " ".join(words)


# ===============================================================
# STARTUP
# ===============================================================
@app.on_event("startup")
def startup_event():
    load_artifacts()


# ===============================================================
# HEALTH / PING
# ===============================================================
@app.get("/api/health")
def health():
    return {"ok": True, "rows": len(DF), "dims": int(E_NEEDS.shape[1])}

@app.head("/api/health")
def health_head():
    return Response(status_code=200)

@app.api_route("/api/ping", methods=["GET", "HEAD"])
def ping():
    return {"ok": True}


# ===============================================================
# GET /api/founders
# ===============================================================
@app.get("/api/founders")
def founders(limit: int = Query(100, ge=1, le=1000), q: str | None = None):

    # parquet founders
    sub = DF.copy()
    if q:
        ql = q.lower()
        sub = sub[
            sub["founder_name"].str.lower().str.contains(ql, na=False)
            | sub.get("industry", pd.Series([""] * len(sub))).str.lower().str.contains(ql, na=False)
        ]

    sub = sub.reset_index()
    parquet_items = []
    for _, row in sub.iterrows():
        parquet_items.append({
            "index": int(row["index"]),
            "founder_id": row.get("founder_id"),
            "startup_id": row.get("startup_id"),
            "founder_name": row.get("founder_name"),
            "industry": row.get("industry", ""),
            "needs_text": row.get("__needs_text__", "")[:200],
            "gives_text": row.get("__gives_text__", "")[:160],
        })

    # user founders
    user = load_user_founders()
    offset = len(DF)
    user_items = []
    for j, f in enumerate(user):
        user_items.append({
            "index": offset + j,
            "founder_id": None,
            "startup_id": None,
            "founder_name": f["founder_name"],
            "industry": f.get("industry", ""),
            "needs_text": f.get("needs_text", "")[:200],
            "gives_text": f.get("gives_text", "")[:160],
        })

    merged = parquet_items + user_items
    return merged[:limit]


# ===============================================================
# POST /api/founders  (ADD NEW)
# ===============================================================
class FounderInput(BaseModel):
    founder_name: str
    industry: str = ""
    needs_text: str
    gives_text: str

@app.post("/api/founders")
def add_founder(data: FounderInput):
    users = load_user_founders()
    users.append(data.dict())
    save_user_founders(users)
    return {"success": True}


# ===============================================================
# GET /api/topk (MATCHING LOGIC)
# ===============================================================
class TopKResponse(BaseModel):
    query_index: int
    founder: dict
    matches: list

@app.get("/api/topk", response_model=TopKResponse)
def topk(i: int = Query(..., ge=0), k: int = Query(5, ge=1, le=50)):

    parquet_count = len(DF)
    user_founders = load_user_founders()
    total = parquet_count + len(user_founders)

    if i >= total:
        raise HTTPException(400, f"index must be < {total}")

    # -----------------------------------------------------------
    # CASE 1: PARQUET FOUNDER — use REAL embeddings
    # -----------------------------------------------------------
    if i < parquet_count:
        sims = E_NEEDS[i] @ E_GIVES.T
        sims[i] = -1e9  # exclude self

        top_idx = np.argpartition(-sims, k)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]

        me = DF.iloc[i]
        matches = []
        for j in top_idx:
            matches.append({
                "rank": len(matches) + 1,
                "index": int(j),
                "score": float(sims[j]),
                "founder_id": DF.iloc[j]["founder_id"],
                "founder_name": DF.iloc[j]["founder_name"],
                "industry": DF.iloc[j]["industry"],
                "gives_text": DF.iloc[j]["__gives_text__"][:160],
            })

        return TopKResponse(
            query_index=i,
            founder={
                "founder_id": me.get("founder_id"),
                "founder_name": me["founder_name"],
                "industry": me["industry"],
                "needs_text": me["__needs_text__"][:200],
            },
            matches=matches,
        )

    # -----------------------------------------------------------
    # CASE 2: USER-ADDED FOUNDER (NO EMBEDDINGS)
    # safe similarity, no 0.99 scores
    # -----------------------------------------------------------
    user_i = i - parquet_count
    user = user_founders[user_i]
    raw_text = user["needs_text"].strip()

    # ----------------------------
    # 1. Empty → neutral similarity
    # ----------------------------
    if raw_text == "":
        sims = 0.35 + 0.20 * np.random.rand(parquet_count)

    else:
        # ----------------------------
        # 2. Hash-based pseudo-embedding
        # ----------------------------
        h = int(hashlib.md5(raw_text.encode()).hexdigest(), 16)
        base = h % 10000

        sims = np.abs(
            (base - np.arange(parquet_count) * 1315423911) % 10000 / 10000
        )

        # scale to safe window
        sims = 0.25 + 0.50 * sims

    # hard safety clip — prevents 0.99 / 1.00 scores
    sims = np.clip(sims.astype("float32"), 0.15, 0.85)

    # ----------------------------
    # 3. Select top-K
    # ----------------------------
    top_idx = np.argsort(-sims)[:k]

    matches = []
    for j in top_idx:
        matches.append({
            "rank": len(matches) + 1,
            "index": int(j),
            "score": float(sims[j]),
            "founder_id": DF.iloc[j]["founder_id"],
            "founder_name": DF.iloc[j]["founder_name"],
            "industry": DF.iloc[j]["industry"],
            "gives_text": DF.iloc[j]["__gives_text__"][:160],
        })

    return TopKResponse(
        query_index=i,
        founder={
            "founder_name": user["founder_name"],
            "industry": user.get("industry", ""),
            "needs_text": user["needs_text"][:200],
        },
        matches=matches,
    )



# ============================================================
#  /api/explain
# ============================================================
@app.get("/api/explain")
def explain(founder_index: int = Query(..., ge=0), k:int=Query(5, ge=1, le=50)):

    if founder_index >= len(DF):
        raise HTTPException(400, f"index must be < {len(DF)}")

    sims = E_NEEDS[founder_index] @ E_GIVES.T
    sims[founder_index] = -1e9
    top_idx = np.argpartition(-sims, k)[:k]
    top_idx = top_idx[np.argsort(-sims[top_idx])]

    explanations = []
    needs_text = preprocess_text(str(DF.iloc[founder_index]["__needs_text__"]))

    for j in top_idx:
        gives_text = preprocess_text(str(DF.iloc[j]["__gives_text__"]))
        explanations.append({
            "founder_name": DF.iloc[j]["founder_name"],
            "industry": DF.iloc[j]["industry"],
            "similarity_score": float(sims[j]),
            "explanation": f"Match based on overlap between founder needs: '{needs_text}' and gives: '{gives_text}'"
        })

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



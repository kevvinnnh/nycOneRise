from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import pandas as pd
import os, json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

APP_DIR = os.path.dirname(__file__)
ART_DIR = os.path.join(APP_DIR, "artifacts")

NEEDS_PATH = os.path.join(ART_DIR, "needs_emb.npy")
GIVES_PATH = os.path.join(ART_DIR, "gives_emb.npy")
META_PATH  = os.path.join(ART_DIR, "founders_meta.parquet")
MANIFEST_PATH = os.path.join(ART_DIR, "manifest.json")
FOUNDERS_USER_PATH = os.path.join(ART_DIR, "founders_user.json")  # NEW

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

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

# ------------- GLOBAL STATE -------------
E_NEEDS = None
E_GIVES = None
DF_BASE = None     # original parquet founders
DF_USER = None     # user-added founders from JSON
DF = None          # combined
MANIFEST = None
N_BASE = 0         # number of base founders


def ensure_user_columns(df_user: pd.DataFrame, like_df: pd.DataFrame) -> pd.DataFrame:
    """Make sure DF_USER has all columns used in DF_BASE."""
    if df_user is None or df_user.empty:
        return pd.DataFrame(columns=like_df.columns)
    for col in like_df.columns:
        if col not in df_user.columns:
            df_user[col] = None
    return df_user[like_df.columns]


def load_artifacts():
    global E_NEEDS, E_GIVES, DF_BASE, DF_USER, DF, MANIFEST, N_BASE

    if not (os.path.exists(NEEDS_PATH) and os.path.exists(GIVES_PATH) and os.path.exists(META_PATH)):
        raise RuntimeError("Missing artifacts. Ensure needs_emb.npy, gives_emb.npy, founders_meta.parquet exist.")

    # base embeddings + metadata
    E_NEEDS = np.load(NEEDS_PATH).astype("float32")
    E_GIVES = np.load(GIVES_PATH).astype("float32")
    DF_BASE = pd.read_parquet(META_PATH, engine="fastparquet")

    N_BASE = len(DF_BASE)

    # user founders (JSON) – may not exist yet
    if os.path.exists(FOUNDERS_USER_PATH):
        DF_USER = pd.read_json(FOUNDERS_USER_PATH)
    else:
        DF_USER = pd.DataFrame(columns=DF_BASE.columns)

    # ensure same columns/order
    DF_USER = ensure_user_columns(DF_USER, DF_BASE)

    # combined DF
    DF = pd.concat([DF_BASE, DF_USER], ignore_index=True)

    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r") as f:
            MANIFEST = json.load(f)
        # update rows to reflect combined data
        MANIFEST["rows"] = len(DF)
    else:
        MANIFEST = {"rows": len(DF), "dims": int(E_NEEDS.shape[1])}

    # sanity checks only for base part
    assert E_NEEDS.shape[0] == len(DF_BASE)
    assert E_GIVES.shape[0] == len(DF_BASE)


@app.on_event("startup")
def startup_event():
    load_artifacts()

# ------------- MODELS -------------

class TopKResponse(BaseModel):
    query_index: int
    founder: dict
    matches: list

class ExplanationRequest(BaseModel):
    seeker_name: str
    seeker_needs: str
    match_name: str
    match_gives: str

class ExplanationResponse(BaseModel):
    explanation: str

class NewFounder(BaseModel):
    founder_name: str
    industry: str
    needs_text: str
    gives_text: str

# ------------- HEALTH -------------

@app.get("/api/health")
def health_get():
    return {
        "ok": True,
        "rows": len(DF),
        "base_rows": int(N_BASE),
        "dims": int(E_NEEDS.shape[1]),
        "manifest": MANIFEST,
    }

@app.head("/api/health")
def health_head():
    return Response(status_code=200)

@app.api_route("/api/ping", methods=["GET", "HEAD"])
def ping():
    return {"ok": True}

# ------------- FOUNDERS LIST -------------

@app.get("/api/founders")
def founders(limit: int = Query(100, ge=1, le=1000), q: str | None = None):
    """
    Return combined founders:
    - First N_BASE rows are 'real' embedded founders
    - Remaining rows (if any) are user-added founders
    """
    sub = DF
    if q:
        ql = q.lower()
        if "industry" in sub.columns:
            sub = sub[
                sub["founder_name"].str.lower().str.contains(ql)
                | sub["industry"].fillna("").str.lower().str.contains(ql)
            ]
        else:
            sub = sub[sub["founder_name"].str.lower().str.contains(ql)]

    sub = sub.reset_index(drop=True).head(limit)

    out = sub[["founder_id", "startup_id", "founder_name", "industry"]].copy()
    # attach global DF index
    out["index"] = sub.index
    return out.to_dict(orient="records")

# ------------- ADD FOUNDER (NO EMBEDDINGS) -------------

@app.post("/api/founders", status_code=201)
def add_founder(f: NewFounder):
    """
    Add a new founder to founders_user.json only.
    No embeddings; matches will be simulated when /api/topk is called on them.
    """
    global DF_BASE, DF_USER, DF, MANIFEST, N_BASE

    if DF_BASE is None:
        raise HTTPException(500, "Base founders not loaded")

    # build new row
    all_df = DF if DF is not None else DF_BASE
    if "founder_id" in all_df.columns and pd.api.types.is_numeric_dtype(all_df["founder_id"]):
        new_founder_id = int(all_df["founder_id"].max()) + 1
    else:
        new_founder_id = len(all_df)

    if "startup_id" in all_df.columns and pd.api.types.is_numeric_dtype(all_df["startup_id"]):
        new_startup_id = int(all_df["startup_id"].max()) + 1
    else:
        new_startup_id = len(all_df)

    new_row = {
        "founder_id": new_founder_id,
        "startup_id": new_startup_id,
        "founder_name": f.founder_name,
        "industry": f.industry,
        "__needs_text__": f.needs_text,
        "__gives_text__": f.gives_text,
    }

    # append to DF_USER
    DF_USER = pd.concat([DF_USER, pd.DataFrame([new_row])], ignore_index=True)
    DF_USER = ensure_user_columns(DF_USER, DF_BASE)

    # persist to JSON
    os.makedirs(ART_DIR, exist_ok=True)
    DF_USER.to_json(FOUNDERS_USER_PATH, orient="records", indent=2)

    # rebuild combined DF
    DF = pd.concat([DF_BASE, DF_USER], ignore_index=True)

    # update manifest
    MANIFEST["rows"] = len(DF)
    with open(MANIFEST_PATH, "w") as fjson:
        json.dump(MANIFEST, fjson)

    # global DF index of the new founder (last row)
    new_index = len(DF) - 1

    return {
        "ok": True,
        "index": new_index,       # global DF index → /api/topk?i=index
        "founder_id": new_founder_id,
        "startup_id": new_startup_id,
    }

# ------------- EXPLAIN MATCH -------------

@app.post("/api/explain", response_model=ExplanationResponse)
async def explain_match(req: ExplanationRequest):
    """Generate an AI explanation for why two founders are a good match."""
    if client is None:
        raise HTTPException(500, "OpenAI client not configured.")

    try:
        prompt = f"""
        You are an expert at analyzing founder connections and partnerships.
        Explain why these two founders are a good match.

        SEEKER: {req.seeker_name}
        NEEDS: {req.seeker_needs}

        MATCH: {req.match_name}
        OFFERS: {req.match_gives}

        Provide a concise 2–3 sentence explanation focusing on:
        - how the match's offerings align with the seeker's needs
        - any complementary skills or synergies
        - potential value created by the partnership
        """

        resp = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )

        explanation = resp.output_text.strip()
        return ExplanationResponse(explanation=explanation)

    except Exception as e:
        raise HTTPException(500, f"Error generating explanation: {str(e)}")

# ------------- TOP-K MATCHES -------------

@app.get("/api/topk", response_model=TopKResponse)
def topk(i: int = Query(..., ge=0), k: int = Query(5, ge=1, le=50)):
    """
    If i < N_BASE: use real embeddings (E_NEEDS/E_GIVES) among base founders.
    If i >= N_BASE: simulated matches using random base founders only.
    """
    global DF_BASE, DF_USER, DF, N_BASE

    n_total = len(DF)
    if i >= n_total:
        raise HTTPException(400, f"index i must be < {n_total}")

    me = DF.iloc[i]

    # --- case 1: base founder → real embedding search ---
    if i < N_BASE:
        sims = E_NEEDS[i] @ E_GIVES.T  # cosine since L2-normalized
        sims[i] = -1e9  # mask self

        k_eff = min(k, N_BASE)
        top_idx = np.argpartition(-sims, k_eff)[:k_eff]
        top_idx = top_idx[np.argsort(-sims[top_idx])]

        rows = []
        for j in top_idx:
            rows.append({
                "rank": len(rows) + 1,
                "index": int(j),  # global index among base (0..N_BASE-1)
                "score": float(sims[j]),
                "founder_id": DF_BASE.iloc[j]["founder_id"],
                "founder_name": DF_BASE.iloc[j]["founder_name"],
                "industry": DF_BASE.iloc[j].get("industry", "—"),
                "gives_text": DF_BASE.iloc[j].get("__gives_text__", "")[:160],
                "gives_text_full": DF_BASE.iloc[j].get("__gives_text__", ""),
            })

        founder_payload = {
            "founder_id": me["founder_id"],
            "founder_name": me["founder_name"],
            "industry": me.get("industry", "—"),
            "needs_text": me.get("__needs_text__", "")[:200],
            "needs_text_full": me.get("__needs_text__", ""),
        }

        return TopKResponse(
            query_index=i,
            founder=founder_payload,
            matches=rows
        )

    # --- case 2: user-added founder → simulate matches ---
    # pick random base founders as matches
    rng = np.random.default_rng(seed=int(me.get("founder_id", i)))
    k_eff = min(k, N_BASE)
    if k_eff == 0:
        return TopKResponse(
            query_index=i,
            founder={
                "founder_id": me.get("founder_id"),
                "founder_name": me.get("founder_name"),
                "industry": me.get("industry", "—"),
                "needs_text": me.get("__needs_text__", "")[:200],
                "needs_text_full": me.get("__needs_text__", ""),
            },
            matches=[]
        )

    base_indices = rng.choice(N_BASE, size=k_eff, replace=False)

    rows = []
    for rank, j in enumerate(base_indices, start=1):
        # fake score in [0.7, 0.99]
        score = float(rng.uniform(0.7, 0.99))
        base_row = DF_BASE.iloc[j]
        rows.append({
            "rank": rank,
            "index": int(j),  # base index
            "score": score,
            "founder_id": base_row["founder_id"],
            "founder_name": base_row["founder_name"],
            "industry": base_row.get("industry", "—"),
            "gives_text": base_row.get("__gives_text__", "")[:160],
            "gives_text_full": base_row.get("__gives_text__", ""),
        })

    founder_payload = {
        "founder_id": me.get("founder_id"),
        "founder_name": me.get("founder_name"),
        "industry": me.get("industry", "—"),
        "needs_text": me.get("__needs_text__", "")[:200],
        "needs_text_full": me.get("__needs_text__", ""),
    }

    return TopKResponse(
        query_index=i,
        founder=founder_payload,
        matches=rows
    )


    
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
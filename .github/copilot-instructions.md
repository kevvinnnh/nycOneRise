# Copilot / AI Agent Instructions — nycOneRise

Summary
- Purpose: small single-page frontend + FastAPI backend that serves founder-match results using precomputed embeddings.
- Layout: frontend files (JS/HTML/CSS) live at the repo root; backend is in `backend/` and reads runtime artifacts from `backend/artifacts/`.

Quick run (developer):
- Create a Python venv and install backend deps:
  - `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r backend/requirements.txt`
- Run the API server (dev):
  - `uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000`
- Open the frontend by opening `index.html` in the browser (the SPA auto-detects `http://127.0.0.1:8000`).

Key files and what matters
- `backend/app.py`: main FastAPI app. Important behaviors:
  - Loads artifacts from `backend/artifacts/` on startup: `needs_emb.npy`, `gives_emb.npy`, and `founders_meta.parquet`. If these are missing the app raises a `RuntimeError`.
  - Exposes endpoints: `GET /api/health`, `HEAD /api/health`, `GET /api/founders?q=...`, `GET /api/topk?i=<index>&k=<k>` and `GET/HEAD /api/ping`.
  - CORS origins are declared in `app.add_middleware(...)` — update here when adding new frontends.
  - Embeddings are expected as L2-normalized `float32` NumPy arrays; `E_NEEDS.shape[0]` must equal number of rows in the parquet metadata.
- `backend/artifacts/`: contains `needs_emb.npy`, `gives_emb.npy`, `founders_meta.parquet`, and `manifest.json` (optional). `manifest.json` if present should contain `{"rows": <int>, "dims": <int>}`.
- `app.js` (frontend): uses `apiBase` logic — defaults to local `http://127.0.0.1:8000` for localhost and `https://nyconerise.onrender.com` otherwise. The UI reads/writes `localStorage.apiBase` and exposes a settings modal.

Service boundaries and data flow
- Precompute embeddings offline → place `.npy` and parquet files into `backend/artifacts/`.
- Backend loads embeddings into memory at startup and serves similarity queries (`E_NEEDS @ E_GIVES.T`) for fast response.
- Frontend calls `GET /api/founders` to get list and `GET /api/topk` with a global index to get matches. Keep `i` as the global row index in the parquet.

Developer conventions & gotchas
- Parquet reading uses `fastparquet` (see pinned version `fastparquet==2024.5.0`) — ensure that package is installed in the environment used to run the API.
- The server expects artifacts to be present at startup; adding a local dev helper to create small fake artifacts is helpful for unit/feature testing.
- CORS is explicit: update `backend/app.py` `allow_origins` list to permit new frontend origins.
- Top-K retrieval masks the self-index (`sims[i] = -1e9`) and uses `np.argpartition` + `argsort` for efficient top-k.

Useful commands / checks
- Health check (curl): `curl -i http://127.0.0.1:8000/api/health`
- Example TopK call: `curl "http://127.0.0.1:8000/api/topk?i=0&k=5"`
- If you see `RuntimeError: Missing artifacts.` — verify files exist in `backend/artifacts/` and that `founders_meta.parquet` rows match `*.npy` rows.

If you need more details
- I merged repository discovery; `README.md` is currently empty — ask the maintainer for any missing project goals or CI preferences.
- If you want I can add a small `dev_artifacts.py` script to generate dummy embeddings/parquet for local dev testing.

Ask me if anything is unclear or you'd like the instructions expanded (CI, tests, or a dev artifacts generator).

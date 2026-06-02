# Deployment Guide

This project can be deployed as a free preview with:

- Frontend on Vercel
- Backend on Render

That split matches the current codebase:

- `frontend/` is a Vite React app and builds to static files cleanly.
- `backend/` is a FastAPI service that needs Python packages, longer-running refresh jobs, and a writable `data/` directory.

## Free Preview Architecture

Frontend:

- Provider: Vercel
- Root: repository root
- Build command: `npm --prefix frontend run build`
- Output directory: `frontend/dist`
- Install command: `npm --prefix frontend install`

Backend:

- Provider: Render Web Service
- Runtime: Python
- Plan: Free
- Build command: `pip install -r requirements.txt`
- Start command: `python run_backend.py --host 0.0.0.0 --port $PORT --no-reload`
- Data directory: `/tmp/ashare-watchlist-data`

Important: Render free services do not provide persistent disks. Watchlists, holdings, cache, status, and generated results can be lost after restart, sleep, or redeploy.

## Backend Environment Variables

Set these in Render:

```env
APP_DATA_DIR=/tmp/ashare-watchlist-data
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=replace-with-your-key
AI_MODEL=deepseek-v4-flash
CORS_ALLOW_ORIGINS=https://your-frontend-domain.vercel.app
```

Notes:

- `APP_DATA_DIR=/tmp/ashare-watchlist-data` is for free preview deployments only. It is not durable storage.
- `CORS_ALLOW_ORIGINS` should match the final Vercel production domain. Multiple origins can be comma-separated.

## Frontend Environment Variables

Set this in Vercel:

```env
VITE_API_BASE_URL=https://your-backend-domain.onrender.com
```

## Deploy Order

1. Deploy backend on Render first.
2. Copy the backend public URL.
3. Deploy frontend on Vercel with `VITE_API_BASE_URL` pointing to that backend URL.
4. Copy the Vercel production URL.
5. Update Render `CORS_ALLOW_ORIGINS` to the final Vercel URL if needed.

## Local Verification Before Deploy

```powershell
python -m unittest discover backend/tests
npm run build
```

## Persistence Notes

The app stores local state under `data/`, including:

- watchlist
- holdings
- refresh status
- cached stock pool
- generated screening results
- ambush pipeline snapshots

On the free Render preview, those files live under `/tmp/ashare-watchlist-data` and can be cleared by the platform.

For a durable production deployment, use a Render paid service with a persistent disk mounted at `/data`, then set:

```env
APP_DATA_DIR=/data
```

## Security Notes

- Do not commit `.env`.
- Do not commit real API keys.
- Do not commit personal holdings or local cache files.
- If a key was ever exposed, rotate it in the provider console before deployment.

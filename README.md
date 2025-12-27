# Duufy

Delt indkobsliste-app med AI-drevet stemmeindtastning.

## Tech Stack
- Python 3.11 + FastAPI
- Supabase (PostgreSQL + Auth)  
- httpx (async HTTP client)
- Anthropic Claude (AI parsing)
- Fly.io (deployment)

## Installation

1. Klon: git clone https://github.com/DIT-BRUGERNAVN/duufy.git
2. Venv: python -m venv .venv && .venv/Scripts/activate
3. Deps: pip install -r requirements.txt
4. .env: Opret med Supabase + API keys
5. SQL: Kor supabase_schema.sql i Supabase

## Kor lokalt
uvicorn main:app --reload --port 8000

## Deploy til Fly.io
fly auth login
fly launch --no-deploy
fly secrets set SUPABASE_URL=...
fly deploy

## Licens
MIT

# Duufy Project Context

## Hvad er Duufy?
Duufy er en delt indkøbsliste-app med AI-drevet stemmeindtastning. Brugere kan tale deres indkøbsliste, og AI'en parser det til strukturerede varer.

## Tech Stack
- **Backend:** Python 3.11 + FastAPI
- **Database:** Supabase (PostgreSQL + Auth)
- **HTTP Client:** httpx (async)
- **AI:** Anthropic Claude (til parsing af stemme/tekst)
- **Email:** Resend (invitationer)
- **Deployment:** Fly.io (auto-deploy via GitHub Actions)
- **Frontend:** Vanilla JS PWA

## Vigtige filer
| Fil | Formål |
|-----|--------|
| `main.py` | FastAPI app + alle endpoints |
| `supabase_client.py` | HTTP-baseret Supabase client (sync + async) |
| `supabase_schema.sql` | Database schema med RLS policies |
| `ai_parser.py` | Claude AI parsing af indkøbstekst |
| `invitations.py` | Email-invitation system |
| `fly.toml` | Fly.io deployment config |
| `Dockerfile` | Production container |

## Database (Supabase)
- **Project ID:** fozbtpdhfepniaxrfcwo
- **Region:** Frankfurt (eu-central-1)
- **Tabeller:** profiles, groups, group_members, shopping_lists, list_items, invitations, analytics_events, error_logs

## URLs
- **Production:** https://duufy.fly.dev
- **PWA:** https://duufy.fly.dev/app
- **GitHub:** https://github.com/grumskull-art/Duufy
- **Supabase Dashboard:** https://supabase.com/dashboard/project/fozbtpdhfepniaxrfcwo

## Kodekonventioner
- Brug `async`/`await` hvor muligt
- Type hints på alle funktioner
- Danske bruger-beskeder, engelsk kode
- Log fejl til `error_logs` tabel via `log_error()`
- Brug `ApiResponse` TypedDict for database-svar

## Lokalt udviklingsmiljø
```powershell
cd "c:\Users\Grums\test python"
C:\Users\Grums\Documents\App_projekt_python\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables (.env)
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Public anon key
- `SUPABASE_SERVICE_ROLE_KEY` - Server-side key
- `ANTHROPIC_API_KEY` - Claude API
- `RESEND_API_KEY` - Email sending

## CI/CD
- Push til `main` → GitHub Actions → Fly.io deploy
- Supabase test før deploy
- Secrets i GitHub + Fly.io

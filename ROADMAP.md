\# Duufy – Roadmap (MVP)



\## Status

\- Fly.io deploy: done

\- Prod endpoints verified: done



\## Mål (MVP)

Delt indkøbsliste der synker ved app-start.



\## Backend (FastAPI)

\### P0

\- \[x] /health

\- \[x] /docs + OpenAPI

\- \[ ] GET /items

\- \[ ] POST /items

\- \[ ] POST /sync (last-write-wins)

\- \[ ] Returnér JSON ved alle fejl

\- \[ ] Logging (basic)



\### P1

\- \[ ] Auth (enkelt – token/header)

\- \[ ] Household / shared list

\- \[ ] Soft delete på items



\## Storage

\- \[ ] Lokal JSON (prod-safe)

\- \[ ] Struktur klar til Firestore senere



\## Frontend

\- \[ ] Simpel liste

\- \[ ] Tilføj vare (tekst)

\- \[ ] Sync ved load



\## Næste fokus

Implementér `GET /items`.




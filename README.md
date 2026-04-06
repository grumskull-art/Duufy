# Duufy

Delt indkobsliste-app med AI-drevet stemmeindtastning.

## Tech Stack
- Python 3.11 + FastAPI
- Supabase (PostgreSQL + Auth)  
- httpx (async HTTP client)
- Anthropic Claude (AI parsing)
- Fly.io (deployment)

## Ubuntu Quickstart

```bash
git clone https://github.com/grumskull-art/Duufy.git
cd Duufy
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Node/Vite toolchain (Ubuntu):

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm install --lts
nvm use --lts
npm install
```

## Kør Lokalt

```bash
npm run start
```

Alternativt direkte:

```bash
. .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Kvalitetstjek

```bash
npm run test
npm run build
```

## Git Flow (commit/push/PR)

```bash
git checkout -b feat/navn-paa-aendring
git add .
git commit -m "feat: kort beskrivelse"
git push -u origin HEAD
```

PR via CLI (uden ekstra login):

```bash
./scripts/ghx pr create --fill
```

Alternativt: brug compare-linket på GitHub efter `git push`.

## Deploy til Fly.io
fly auth login
fly launch --no-deploy
fly secrets set SUPABASE_URL=...
fly deploy

## Licens
MIT

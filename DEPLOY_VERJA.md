# Duufy On `duufy.verja.dev`

## Fly.io app config
- `fly.toml` now defaults to:
  - `DUUFY_PUBLIC_APP_URL=https://duufy.verja.dev`
  - `ALLOWED_ORIGINS=https://duufy.verja.dev,capacitor://localhost,ionic://localhost`

## Required Fly secrets
Run these before the first real deploy:

```bash
fly secrets set \
  SUPABASE_URL=... \
  SUPABASE_ANON_KEY=... \
  SUPABASE_SERVICE_ROLE_KEY=... \
  RESEND_API_KEY=... \
  DUUFY_INVITE_FROM_EMAIL="Duufy <noreply@verja.dev>"
```

## Custom domain
Attach the domain on Fly:

```bash
fly certs add duufy.verja.dev
fly certs show duufy.verja.dev
```

Then add the DNS record at your DNS provider using the target Fly gives you.

## First deploy
```bash
fly deploy
fly status
fly logs
```

## Smoke checks
After deploy, verify:

```bash
curl -s https://duufy.verja.dev/health
curl -s https://duufy.verja.dev/config
```

Open `https://duufy.verja.dev/app` on:
- iPhone Safari
- Android Chrome

Check these flows:
- install app / add to home screen
- sign up / sign in
- create group
- invite by email
- accept invite link
- add item
- voice input
- sync across two phones

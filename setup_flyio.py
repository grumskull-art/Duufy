#!/usr/bin/env python3
"""
🚀 DUUFY DEPLOYMENT GUIDE
=========================

Dette script guider dig gennem setup af:
1. GitHub Repository
2. Fly.io Account + App
3. Automatisk deployment

GRATIS STACK:
- Fly.io: 3 VMs gratis (256MB RAM hver)
- GitHub Actions: 2000 min/måned gratis
- Supabase: 500MB + 50k users gratis
"""

import subprocess
import sys
import os

def run_cmd(cmd, capture=False):
    """Kør kommando og vis output"""
    try:
        if capture:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, shell=True, check=True)
            return True
    except:
        return False

def check_tools():
    """Check om nødvendige tools er installeret"""
    print("\n📋 CHECKER TOOLS...")
    
    tools = {
        'git': 'git --version',
        'flyctl': 'flyctl version',
        'docker': 'docker --version'
    }
    
    missing = []
    for name, cmd in tools.items():
        result = run_cmd(cmd, capture=True)
        if result:
            print(f"  ✅ {name}: {result.split()[-1] if result else 'OK'}")
        else:
            print(f"  ❌ {name}: MANGLER")
            missing.append(name)
    
    return missing

def install_flyctl():
    """Installer Fly.io CLI"""
    print("\n📦 INSTALLERER FLY.IO CLI...")
    
    if sys.platform == 'win32':
        cmd = 'powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"'
    else:
        cmd = 'curl -L https://fly.io/install.sh | sh'
    
    run_cmd(cmd)
    print("  → Genstart terminal efter installation!")

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                   🚀 DUUFY DEPLOYMENT                        ║
║                                                              ║
║  Lokal dev (ngrok) → Push til GitHub → Auto-deploy Fly.io   ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Check tools
    missing = check_tools()
    
    if 'flyctl' in missing:
        print("\n⚠️  Fly.io CLI mangler!")
        install = input("   Vil du installere nu? (j/n): ")
        if install.lower() == 'j':
            install_flyctl()
            print("\n   🔄 Kør dette script igen efter installation")
            return
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    📝 SETUP STEPS                            ║
╚══════════════════════════════════════════════════════════════╝

STEP 1: GITHUB REPO
───────────────────
1. Gå til https://github.com/new
2. Opret nyt repo: "duufy" (private anbefales)
3. Kør disse kommandoer i terminal:

   cd "c:\\Users\\Grums\\test python"
   git init
   git add .
   git commit -m "Initial commit - Duufy shopping app"
   git branch -M main
   git remote add origin https://github.com/DIT-BRUGERNAVN/duufy.git
   git push -u origin main


STEP 2: FLY.IO SETUP
────────────────────
1. Gå til https://fly.io og opret gratis konto
2. Kør i terminal:

   flyctl auth login
   cd "c:\\Users\\Grums\\test python"
   flyctl launch --no-deploy
   
   (Svar: Yes til existing fly.toml, vælg Amsterdam region)


STEP 3: SECRETS
───────────────
Tilføj dine API keys til Fly.io (de er sikre der):

   flyctl secrets set ANTHROPIC_API_KEY="din-key"
   flyctl secrets set RESEND_API_KEY="re_7Fqnwzbj_..."
   flyctl secrets set SUPABASE_URL="https://xxx.supabase.co"
   flyctl secrets set SUPABASE_ANON_KEY="eyJ..."


STEP 4: GITHUB ACTIONS TOKEN
────────────────────────────
1. Kør: flyctl tokens create deploy
2. Kopiér token
3. Gå til GitHub repo → Settings → Secrets → Actions
4. New secret: FLY_API_TOKEN = (din token)


STEP 5: TEST DEPLOY
───────────────────
   flyctl deploy

   Eller bare push til GitHub - det deployer automatisk!
   git add .
   git commit -m "Update"
   git push


📱 EFTER DEPLOY
───────────────
Din app kører på: https://duufy-app.fly.dev

PWA App:          https://duufy-app.fly.dev/app
API Docs:         https://duufy-app.fly.dev/docs
Health Check:     https://duufy-app.fly.dev/health
Analytics:        https://duufy-app.fly.dev/admin/analytics


🔧 NYTTIGE KOMMANDOER
─────────────────────
flyctl status          # Se app status
flyctl logs            # Se logs
flyctl ssh console     # SSH ind i container
flyctl secrets list    # Se secrets (ikke værdier)
flyctl scale count 1   # Kør altid 1 instance (ingen cold start)


💡 WORKFLOW
───────────
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Lokal dev  │────▶│  git push   │────▶│   Fly.io    │
│  + ngrok    │     │   GitHub    │     │  Production │
└─────────────┘     └─────────────┘     └─────────────┘
      ↓                    ↓                    ↓
   Test hurtigt      Auto-deploy        Altid online
   Hot-reload        GitHub Actions     Gratis 24/7
""")
    
    print("\n✅ Filerne er klar!")
    print("   - Dockerfile")
    print("   - fly.toml")
    print("   - .github/workflows/deploy.yml")
    print("   - .dockerignore")
    print("\n🎯 Start med STEP 1 ovenfor!")

if __name__ == "__main__":
    main()

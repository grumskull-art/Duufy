"""
🚀 DUUFY SUPABASE SETUP GUIDE
=============================

Følg disse trin for at få Supabase op at køre (5 minutter):


STEP 1: Opret Supabase Projekt (GRATIS)
---------------------------------------
1. Gå til: https://supabase.com/dashboard
2. Klik "New Project" (gratis)
3. Vælg et navn: "duufy"
4. Vælg region: "West EU (Frankfurt)" - tættest på Danmark
5. Sæt et database password (GEM DET!)
6. Klik "Create new project"
7. Vent 2 minutter mens projektet oprettes


STEP 2: Hent API Keys
---------------------
1. Gå til: Settings → API (i venstre menu)
2. Under "Project URL" - kopier URL'en
3. Under "Project API keys" - kopier "anon public" key
4. Opdater .env filen:

   SUPABASE_URL=https://xxxx.supabase.co  (din URL)
   SUPABASE_ANON_KEY=eyJxxx...            (din anon key)


STEP 3: Opret Database Tabeller
-------------------------------
1. Gå til: SQL Editor (i venstre menu)
2. Klik "New query"
3. Copy/paste HELE indholdet fra: supabase_schema.sql
4. Klik "Run" (eller Ctrl+Enter)
5. Du skulle se "Success. No rows returned"


STEP 4: Enable Email Auth
-------------------------
1. Gå til: Authentication → Providers
2. Email provider er enabled by default ✅
3. (Optional) Gå til: Authentication → URL Configuration
4. Sæt "Site URL" til din ngrok URL


STEP 5: Test det!
-----------------
Kør dette script for at teste:

    python test_supabase.py


🎉 FÆRDIG! Nu har du:
- ✅ PostgreSQL database (500 MB gratis)
- ✅ User authentication
- ✅ Row Level Security
- ✅ Real-time capabilities
- ✅ Auto-generated REST API

Alt sammen GRATIS! 🚀
"""

# Quick test script
if __name__ == "__main__":
    print("🧪 Testing Supabase connection...\n")
    
    try:
        from supabase_client import get_supabase
        
        client = get_supabase()
        print("✅ Supabase connected!")
        
        # Test database
        result = client.table("profiles").select("*").limit(1).execute()
        print(f"✅ Database accessible! (profiles table exists)")
        
        print("\n🎉 Alt virker! Du kan nu bruge Supabase.")
        
    except ValueError as e:
        print(f"⚠️  {e}")
        print("\n👉 Følg instruktionerne ovenfor for at sætte Supabase op.")
        
    except Exception as e:
        error_msg = str(e)
        if "relation" in error_msg and "does not exist" in error_msg:
            print(f"⚠️  Database tabeller mangler!")
            print("👉 Kør SQL schema: Copy/paste supabase_schema.sql i SQL Editor")
        else:
            print(f"❌ Fejl: {e}")
            print("\n👉 Tjek at SUPABASE_URL og SUPABASE_ANON_KEY er korrekte i .env")

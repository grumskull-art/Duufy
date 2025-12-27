# HEYLOBS - SHOPPING LIST APP
## Projekt Oversigt

### Arkitektur
- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla JavaScript (Single Page App)
- **Database**: JSON files (groups.json, invitations.json)
- **AI**: Claude Haiku (via Anthropic API)
- **External Access**: Ngrok tunnel

### Filer:
1. main.py - FastAPI server med alle endpoints
2. ai_parser.py - Intelligent parsing af indkøbslister
3. invitations.py - Email invitation system
4. index.html - Komplet frontend (2700+ linjer)
5. requirements.txt - Python dependencies
6. .env - API keys (ANTHROPIC_API_KEY, RESEND_API_KEY)

### Features:
 Multi-gruppe shopping lists
 Swipe gestures (købt/slet med 1 sek hold)
 Speech-to-text (dansk)
 AI parsing af naturligt sprog
 Email invitations via Resend
 Ngrok external access
 Duplicate detection
 Mobile-first responsive design

### API Endpoints:
- GET /  Index page
- GET /groups  List all groups
- POST /group  Create group
- POST /group/{id}/item  Add item
- DELETE /group/{id}/item/{name}  Delete item
- POST /ai/parse  AI parse shopping text
- POST /invite/send  Send invitation email
- GET /invite/{token}  Show invitation page
- POST /invite/{token}/accept  Accept invitation

Se PROJEKT_KOMPLET.txt for komplet kode!

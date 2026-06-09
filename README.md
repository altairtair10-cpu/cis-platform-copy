# CIS Platform

Internal company OS for Caspian Integrated Services LLP.
Replaces Documentolog. Integrates with 1С and SharePoint.
Trilingual: Russian / English / Kazakh.

## Local Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/YOUR_USERNAME/cis-platform
cd cis-platform

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env with your values

# 5. Initialize database
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# 6. Seed with test data
flask seed

# 7. Run
flask run
```

Open http://localhost:5000

**Test logins:**
- IT Admin: `admin@cis.kz` / `admin123`
- Dept Head: `zhanibek@cis.kz` / `zhanibek123`
- Mechanic: `mechanic@cis.kz` / `mechanic123`

## Deploy to Railway

1. Push to GitHub
2. Connect repo in Railway
3. Add PostgreSQL plugin
4. Set environment variables:
   - `SECRET_KEY` — long random string
   - `DATABASE_URL` — auto-set by Railway PostgreSQL
   - `FLASK_ENV=production`
5. Railway auto-deploys on every push

## Project Structure

```
cis-platform/
  app/
    __init__.py          # App factory
    models.py            # All database models
    decorators.py        # RBAC decorators
    blueprints/
      auth/              # Login, logout, language switch
      dashboard/         # Main dashboard
      documents/         # Purchase requisitions, document management
      equipment/         # Equipment tracker
      transport/         # Transport runs
      hr/                # HR system, PTO, work log
      errors/            # 403, 404, 500 pages
    templates/           # Jinja2 HTML templates
    static/
      css/main.css       # All styles
      js/main.js         # Client-side JS
  config/config.py       # Environment configs
  run.py                 # Entry point + seed command
  requirements.txt
  Procfile               # Railway/Heroku deploy
```

## Modules (current → planned)

- [x] Auth + RBAC (role-based access)
- [x] Dashboard
- [x] Document management (Documentolog replacement)
- [x] Equipment tracker
- [x] Transport
- [x] HR skeleton
- [ ] Purchase requisition workflow (next)
- [ ] 1С OData integration
- [ ] SharePoint integration
- [ ] AI agents (Anthropic API)
- [ ] Morning briefing bot
- [ ] Telegram bridge

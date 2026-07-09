# Database backup & restore runbook

## How backups work

Two independent layers:

1. **Railway built-in backups** — enable in Railway: Postgres service → *Backups* tab → daily. First line of defense, restores with one click.
2. **Nightly off-platform dump** — GitHub Actions (`.github/workflows/db-backup.yml`) runs `pg_dump` every night at 06:00 Atyrau time, encrypts the dump (AES-256), and stores it as a workflow artifact for 30 days. This protects against losing the Railway account/project itself.

### One-time setup (GitHub repo → Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `BACKUP_DATABASE_URL` | Railway → Postgres service → *Connect* tab → **Public** connection URL (`postgresql://...proxy.rlwy.net:PORT/railway`). The private `railway.internal` URL will NOT work from GitHub. |
| `BACKUP_PASSPHRASE` | Any long random string (30+ chars). **Store a copy in a password manager — without it, backups cannot be decrypted.** |

Then run it once manually to verify: repo → *Actions* → *Nightly DB backup* → *Run workflow* → expect a green run with an artifact attached.

## How to restore

1. Download the artifact from the workflow run (repo → Actions → pick the run → Artifacts) and unzip it to get `backup.dump.enc`.
2. Decrypt:
   ```bash
   openssl enc -d -aes-256-cbc -pbkdf2 -in backup.dump.enc -out backup.dump -pass pass:YOUR_PASSPHRASE
   ```
3. Restore into a database (this OVERWRITES matching tables — restore into an empty/new DB when in doubt):
   ```bash
   pg_restore --clean --if-exists --no-owner -d "postgresql://TARGET_DB_URL" backup.dump
   ```
4. Point the app's `DATABASE_URL` at the restored database and redeploy.

## Quarterly drill (put it in the calendar)

Restore the latest backup into a scratch database and open the app against it once per quarter. A backup that has never been restored is a hope, not a backup.

## Error monitoring (Sentry)

The app reports unhandled exceptions to Sentry when the `SENTRY_DSN` env var is set (see `app/__init__.py`). Setup: create a free account at sentry.io → create a Flask project → copy the DSN → add `SENTRY_DSN` variable in Railway. No DSN set = Sentry silently disabled (e.g. locally).

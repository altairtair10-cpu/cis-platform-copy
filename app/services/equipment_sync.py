"""Sync the Equipment table from the equipment-status Google Sheet.

The sheet (tab «База») is the source of truth, maintained by the Telegram bot.
The platform pulls it into Postgres so equipment can be referenced by documents,
maintenance logs, filters, etc. Manual platform edits to synced fields are
overwritten on the next sync by design.
"""
from datetime import datetime

# header → attribute mapping (matched case-insensitively, by "contains")
HEADER_MAP = [
    ('код',              'unit_id'),
    ('категор',          'eq_type'),
    ('марка',            'name'),
    ('гос',              'gos_number'),
    ('текущая локация',  'location'),
    ('проект',           'project'),
    ('статус',           'sheet_status'),
    ('текущее состояние','condition'),
    ('примечан',         'notes'),
]

STATUS_MAP = {
    'в работе':  'deployed',
    'в ремонте': 'maintenance',
    'в резерве': 'idle',
    'ожидание':  'idle',
    'новая':     'idle',
}


def fetch_rows():
    """Read raw values from the configured sheet. Separated for easy testing."""
    from app.models import AppSetting
    from app.services.gsheets import get_client

    spreadsheet_id = AppSetting.get('equipment_spreadsheet_id')
    if not spreadsheet_id:
        raise RuntimeError('Equipment spreadsheet ID is not set (Admin → Integrations)')
    sheet_name = AppSetting.get('equipment_sheet_name', 'База')
    ws = get_client().open_by_key(spreadsheet_id).worksheet(sheet_name)
    return ws.get_all_values()


def sync_equipment(rows=None):
    """Upsert Equipment from sheet rows. Returns (created, updated) counts."""
    from app import db
    from app.models import Equipment, AppSetting

    if rows is None:
        rows = fetch_rows()
    if not rows:
        return 0, 0

    headers = [h.strip().lower() for h in rows[0]]
    col_for = {}
    for needle, attr in HEADER_MAP:
        for i, h in enumerate(headers):
            if needle in h and attr not in col_for.values():
                col_for[i] = attr
                break

    if 'unit_id' not in col_for.values():
        raise RuntimeError('Could not find the «Код техники» column in the sheet')

    created = updated = 0
    now = datetime.utcnow()
    existing = {e.unit_id: e for e in Equipment.query.all()}

    for row in rows[1:]:
        data = {}
        for i, attr in col_for.items():
            if i < len(row):
                data[attr] = (row[i] or '').strip() or None
        code = data.get('unit_id')
        if not code:
            continue   # blank/category separator rows

        eq = existing.get(code)
        if eq is None:
            eq = Equipment(unit_id=code)
            db.session.add(eq)
            existing[code] = eq
            created += 1
        else:
            updated += 1

        eq.name         = data.get('name') or eq.name or code
        eq.eq_type      = data.get('eq_type') or eq.eq_type
        eq.location     = data.get('location') or eq.location
        eq.gos_number   = data.get('gos_number')
        eq.project      = data.get('project')
        eq.condition    = data.get('condition')
        eq.sheet_status = data.get('sheet_status')
        eq.notes        = data.get('notes')
        eq.status       = STATUS_MAP.get((data.get('sheet_status') or '').lower(),
                                         eq.status or 'idle')
        eq.synced_at    = now

    AppSetting.set('equipment_last_sync', now.isoformat())
    db.session.commit()
    return created, updated


def last_sync_dt():
    from app.models import AppSetting
    raw = AppSetting.get('equipment_last_sync')
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def sync_if_stale(max_age_minutes=10):
    """Best-effort background-ish sync on page load; never raises."""
    from app.models import AppSetting
    if not AppSetting.get('equipment_spreadsheet_id'):
        return False
    last = last_sync_dt()
    if last and (datetime.utcnow() - last).total_seconds() < max_age_minutes * 60:
        return False
    try:
        sync_equipment()
        return True
    except Exception:
        return False

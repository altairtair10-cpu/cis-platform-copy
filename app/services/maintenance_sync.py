"""Sync ТО/ремонт records from the maintenance register Google Sheet.

Register layout: one worksheet per unit (standard form CIS-TS-DP-001-WI-005-F-002):
a title row containing the unit name + gos number, a header row starting with
«Дата», a column-number row (1,2,3...), then work rows. Column 2 holds the work
kind («ТО», «ТО 1», «ТО2», «Р»), column 6 «Пробег / Моточас».

Units are matched to Equipment by gos_number found inside the worksheet title.
"""
import hashlib
import re
from datetime import datetime

SKIP_TABS = {'пустая форма'}


def _norm(s):
    return re.sub(r'\s+', '', (s or '')).upper()


def _parse_reading(value):
    """'12481' / '12 481,5' / 'НП' / '' -> float or None"""
    v = (value or '').strip().replace(' ', '').replace(',', '.')
    if not v or not re.match(r'^\d+(\.\d+)?$', v):
        return None
    return float(v)


def _parse_date(value):
    v = (value or '').strip()
    for fmt in ('%d.%m.%Y', '%d.%m.%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _classify(kind_raw):
    k = _norm(kind_raw)
    if k.startswith('ТО') or k.startswith('TO'):
        return 'ТО'
    if k.startswith('Р') or k.startswith('P'):
        return 'Р'
    return None


def fetch_register():
    """Return {tab_title: rows} for every unit tab. Separated for testing."""
    from app.models import AppSetting
    from app.services.gsheets import get_client

    spreadsheet_id = AppSetting.get('maintenance_spreadsheet_id')
    if not spreadsheet_id:
        raise RuntimeError('Maintenance register spreadsheet ID is not set (Admin → Integrations)')
    ss = get_client().open_by_key(spreadsheet_id)
    titles = [ws.title for ws in ss.worksheets()
              if ws.title.strip().lower() not in SKIP_TABS]
    result = {}
    ranges = [f"'{t}'!A1:Q300" for t in titles]
    data = ss.values_batch_get(ranges)
    for title, block in zip(titles, data.get('valueRanges', [])):
        result[title] = block.get('values', [])
    return result


def _tokens(text):
    """Candidate registration-number tokens from words and adjacent-word joins.

    «№1 Насос 882AHDE» -> {'882AHDE', ...}; «Насос 882 AHDE» -> {'882AHDE', ...}
    """
    words = [w for w in re.split(r'[^0-9A-ZА-ЯЁ]+', (text or '').upper()) if w]
    cands = set()
    for i, w in enumerate(words):
        combos = [w]
        if i + 1 < len(words):
            combos.append(w + words[i + 1])
        if i + 2 < len(words):
            combos.append(w + words[i + 1] + words[i + 2])
        for c in combos:
            if (4 <= len(c) <= 12
                    and re.search(r'[0-9]', c)
                    and re.search(r'[A-ZА-ЯЁ]', c)):
                cands.add(c)
    return cands


def _match_equipment(tab_title, equipment_list, tab_map=None):
    """Match a worksheet to Equipment: manual map first, then gos-number tokens.

    Tokens tolerate formatting differences: «882 AHDE 06» vs «882AHDE» match
    because one normalized token is a prefix of the other.
    """
    if tab_map:
        m = tab_map.get(tab_title.strip())
        if m is not None:
            return m   # may be an Equipment or 'IGNORE'

    t = _norm(tab_title)
    title_tokens = _tokens(tab_title)
    best = None
    for eq in equipment_list:
        g = _norm(eq.gos_number or '')
        if not g:
            continue
        if g in t:
            return eq
        for tok in title_tokens:
            if len(tok) >= 4 and (tok.startswith(g) or g.startswith(tok)):
                best = best or eq
    return best


def sync_maintenance(register=None):
    """Upsert ServiceRecords. Returns (new_records, matched_tabs, unmatched_titles)."""
    from app import db
    from app.models import Equipment, ServiceRecord, AppSetting

    if register is None:
        register = fetch_register()

    from app.models import MaintenanceTabMap
    equipment_list = Equipment.query.all()
    existing_hashes = {h for (h,) in db.session.query(ServiceRecord.row_hash).all()}
    tab_map = {}
    for m in MaintenanceTabMap.query.all():
        tab_map[m.tab_title.strip()] = 'IGNORE' if m.is_ignored else m.equipment

    new_records = 0
    matched = 0
    unmatched = []

    for title, rows in register.items():
        eq = _match_equipment(title, equipment_list, tab_map)
        if eq == 'IGNORE':
            continue
        if eq is None:
            unmatched.append(title)
            continue
        matched += 1

        # find the header row («Дата...») and start after the 1,2,3… row
        start = None
        for i, row in enumerate(rows):
            if row and (row[0] or '').strip().lower().startswith('дата'):
                start = i + 1
                break
        if start is None:
            continue
        if start < len(rows) and (rows[start][0] or '').strip() in ('', '1'):
            # skip P/N sub-header and the column-number row
            while start < len(rows) and _parse_date(rows[start][0]) is None:
                start += 1
                if start - 2 > 20:
                    break

        for row in rows[start:]:
            if not row or _parse_date(row[0]) is None:
                continue
            kind_raw = (row[1] if len(row) > 1 else '').strip()
            kind = _classify(kind_raw)
            if kind is None:
                continue
            date = _parse_date(row[0])
            description = (row[4] if len(row) > 4 else '').strip() or None
            reading = _parse_reading(row[5] if len(row) > 5 else '')
            if reading is None and len(row) > 9:
                reading = _parse_reading(row[9])
            executor = (row[15] if len(row) > 15 else '').strip() or None

            basis = f'{eq.id}|{date}|{kind_raw}|{(description or "")[:120]}'
            row_hash = hashlib.sha1(basis.encode('utf-8')).hexdigest()
            if row_hash in existing_hashes:
                continue
            existing_hashes.add(row_hash)
            db.session.add(ServiceRecord(
                equipment_id=eq.id, date=date, kind=kind, kind_raw=kind_raw[:16],
                description=description, reading=reading, executor=executor,
                row_hash=row_hash,
            ))
            new_records += 1

    db.session.flush()
    _update_aggregates(equipment_list)
    import json as _json
    AppSetting.set('maintenance_unmatched_tabs', _json.dumps(unmatched, ensure_ascii=False))
    AppSetting.set('maintenance_last_sync', datetime.utcnow().isoformat())
    db.session.commit()
    return new_records, matched, unmatched


def _update_aggregates(equipment_list):
    """Refresh per-unit: current reading, last ТО date/reading, last repair date."""
    from app.models import ServiceRecord

    for eq in equipment_list:
        records = ServiceRecord.query.filter_by(equipment_id=eq.id).all()
        if not records:
            continue
        readings = [r.reading for r in records if r.reading is not None]
        eq.current_reading = max(readings) if readings else None

        tos = [r for r in records if r.kind == 'ТО' and r.date]
        if tos:
            last_to = max(tos, key=lambda r: r.date)
            new_reading = last_to.reading
            if last_to.date != eq.last_to_date or new_reading != eq.last_to_reading:
                eq.to_notified_at = None    # new ТО happened → allow future alerts
            eq.last_to_date = last_to.date
            eq.last_to_reading = new_reading

        reps = [r for r in records if r.kind == 'Р' and r.date]
        if reps:
            eq.last_repair_date = max(r.date for r in reps)


def check_maintenance_due():
    """Create notifications for units whose ТО interval is exceeded.
    Returns list of (equipment, overdue_by) that are due."""
    from app import db
    from app.models import (Equipment, MaintenancePolicy, Notification,
                            User, AppSetting)

    policies = {p.eq_type: p for p in MaintenancePolicy.query.all()}
    due = []
    for eq in Equipment.query.all():
        pol = policies.get(eq.eq_type)
        if not pol or pol.mode == 'repair_only' or not pol.interval:
            continue
        if eq.current_reading is None or eq.last_to_reading is None:
            continue
        used = eq.current_reading - eq.last_to_reading
        if used >= pol.interval and eq.to_notified_at is None:
            due.append((eq, used - pol.interval))

    if not due:
        return []

    # recipients: all active mechanics + configured extra users
    recipients = {u.id for u in User.query.filter_by(role='mechanic', is_active=True).all()}
    extra = AppSetting.get('maintenance_notify_user_ids', '')
    for part in (extra or '').split(','):
        part = part.strip()
        if part.isdigit():
            recipients.add(int(part))

    unit = {'hours': 'м/ч', 'km': 'км'}
    for eq, overdue in due:
        pol = policies[eq.eq_type]
        u = unit.get(pol.mode, '')
        for uid in recipients:
            db.session.add(Notification(
                user_id=uid,
                title=f'ТО пора: {eq.unit_id} {eq.name or ""}'.strip(),
                body=(f'Наработка с последнего ТО: '
                      f'{eq.current_reading - eq.last_to_reading:.0f} {u} '
                      f'(норма {pol.interval} {u}, превышение {overdue:.0f} {u})'),
                link=f'/equipment/{eq.id}',
                is_read=False,
            ))
        eq.to_notified_at = datetime.utcnow()
    db.session.commit()
    return due


def to_status(eq):
    """('ok'|'soon'|'due'|'none', used, interval, mode) for templates."""
    from app.models import MaintenancePolicy
    pol = MaintenancePolicy.query.filter_by(eq_type=eq.eq_type).first()
    if not pol or pol.mode == 'repair_only' or not pol.interval:
        return ('none', None, None, pol.mode if pol else None)
    if eq.current_reading is None or eq.last_to_reading is None:
        return ('none', None, pol.interval, pol.mode)
    used = eq.current_reading - eq.last_to_reading
    if used >= pol.interval:
        return ('due', used, pol.interval, pol.mode)
    if used >= pol.interval * 0.85:
        return ('soon', used, pol.interval, pol.mode)
    return ('ok', used, pol.interval, pol.mode)

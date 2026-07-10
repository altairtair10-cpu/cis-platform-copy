"""Live-platform tools for AI agents (Anthropic tool-use format).

Each tool respects only read access; agents never modify data.
"""
import json

TOOLS_SPEC = [
    {
        'name': 'get_equipment_status',
        'description': 'Статус единицы техники по коду (A1, Б7...) или части названия/гос.номера: '
                       'статус, локация, проект, состояние, наработка, ТО, открытые дефекты.',
        'input_schema': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'код, название или гос.номер'}},
            'required': ['query'],
        },
    },
    {
        'name': 'list_overdue_to',
        'description': 'Список техники, у которой ТО просрочено или скоро (по политикам интервалов).',
        'input_schema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'list_open_defects',
        'description': 'Все открытые дефектные акты: код (Б1-ДА1), техника, описание, дата.',
        'input_schema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_service_history',
        'description': 'Последние записи ТО/ремонтов по единице техники из реестра.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'код, название или гос.номер'},
                'limit': {'type': 'integer', 'description': 'сколько записей, по умолчанию 10'},
            },
            'required': ['query'],
        },
    },
]


def _find_equipment(query):
    from app.models import Equipment
    q = (query or '').strip()
    if not q:
        return None
    unit = Equipment.query.filter(Equipment.unit_id.ilike(q)).first()
    if unit:
        return unit
    like = f'%{q}%'
    return Equipment.query.filter(
        (Equipment.unit_id.ilike(like)) | (Equipment.name.ilike(like))
        | (Equipment.gos_number.ilike(like))).first()


def _equipment_payload(eq):
    from app.models import Document
    from app.services.maintenance_sync import to_status
    state, used, interval, mode = to_status(eq)
    defects = Document.query.filter_by(equipment_id=eq.id, doc_type='defect_act',
                                       defect_closed=False).all()
    return {
        'code': eq.unit_id, 'name': eq.name, 'category': eq.eq_type,
        'gos_number': eq.gos_number, 'location': eq.location, 'project': eq.project,
        'status': eq.sheet_status or eq.status, 'condition': eq.condition,
        'current_reading': eq.current_reading,
        'last_to_date': eq.last_to_date.isoformat() if eq.last_to_date else None,
        'to_state': {'ok': 'в норме', 'soon': 'скоро', 'due': 'просрочено',
                     'none': 'не отслеживается'}.get(state, state),
        'to_used': used, 'to_interval': interval,
        'open_defects': [{'code': d.event_code or d.doc_number,
                          'description': (d.purpose or d.title or '')[:200],
                          'date': d.created_at.strftime('%d.%m.%Y')} for d in defects],
    }


def run_tool(name, args):
    """Execute a tool; always returns a JSON string."""
    from app.models import Equipment, Document, ServiceRecord, MaintenancePolicy

    try:
        if name == 'get_equipment_status':
            eq = _find_equipment(args.get('query', ''))
            if eq is None:
                return json.dumps({'error': 'техника не найдена'}, ensure_ascii=False)
            return json.dumps(_equipment_payload(eq), ensure_ascii=False)

        if name == 'list_overdue_to':
            from app.services.maintenance_sync import to_status
            out = []
            for eq in Equipment.query.all():
                state, used, interval, mode = to_status(eq)
                if state in ('due', 'soon'):
                    out.append({'code': eq.unit_id, 'name': eq.name,
                                'state': 'просрочено' if state == 'due' else 'скоро',
                                'used': used, 'interval': interval,
                                'unit': 'км' if mode == 'km' else 'м/ч'})
            return json.dumps(out, ensure_ascii=False)

        if name == 'list_open_defects':
            docs = Document.query.filter_by(doc_type='defect_act', defect_closed=False)\
                                 .order_by(Document.created_at.desc()).limit(50).all()
            return json.dumps([{
                'code': d.event_code or d.doc_number,
                'equipment': d.equipment.unit_id if d.equipment else None,
                'description': (d.purpose or d.title or '')[:200],
                'date': d.created_at.strftime('%d.%m.%Y'),
            } for d in docs], ensure_ascii=False)

        if name == 'get_service_history':
            eq = _find_equipment(args.get('query', ''))
            if eq is None:
                return json.dumps({'error': 'техника не найдена'}, ensure_ascii=False)
            limit = min(int(args.get('limit') or 10), 30)
            recs = ServiceRecord.query.filter_by(equipment_id=eq.id)\
                                      .order_by(ServiceRecord.date.desc()).limit(limit).all()
            return json.dumps([{
                'date': r.date.isoformat() if r.date else None,
                'kind': r.kind_raw or r.kind, 'description': r.description,
                'reading': r.reading, 'executor': r.executor,
            } for r in recs], ensure_ascii=False)

        return json.dumps({'error': f'неизвестный инструмент {name}'}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({'error': str(exc)}, ensure_ascii=False)

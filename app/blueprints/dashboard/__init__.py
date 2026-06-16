from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models import Document, Equipment, User

dashboard = Blueprint('dashboard', __name__,
                      template_folder='../../app/templates/dashboard')

@dashboard.route('/')
@dashboard.route('/dashboard')
@login_required
def index():
    stats = {
        'equipment_total':    Equipment.query.count(),
        'equipment_deployed': Equipment.query.filter_by(status='deployed').count(),
        'equipment_idle':     Equipment.query.filter_by(status='idle').count(),
        'equipment_maint':    Equipment.query.filter_by(status='maintenance').count(),
        'docs_total':         Document.query.count(),
        'docs_pending':       Document.query.filter_by(status='pending').count(),
        'docs_approved':      Document.query.filter_by(status='approved').count(),
        'staff_total':        User.query.filter_by(is_active=True).count(),
        'staff_role':         User.query.filter_by(role=current_user.role, is_active=True).count(),
    }
    recent_docs = Document.query.order_by(Document.created_at.desc()).limit(8).all()
    return render_template('dashboard.html', stats=stats, recent_docs=recent_docs)


@dashboard.route('/briefing')
@login_required
def briefing():
    from datetime import datetime
    import anthropic
    import os

    pending_docs       = Document.query.filter_by(status='pending').count()
    total_docs         = Document.query.count()
    equipment_maint    = Equipment.query.filter_by(status='maintenance').count()
    equipment_total    = Equipment.query.count()
    equipment_deployed = Equipment.query.filter_by(status='deployed').count()
    staff_total        = User.query.filter_by(is_active=True).count()

    recent_docs = Document.query.order_by(Document.created_at.desc()).limit(5).all()
    doc_lines = []
    for doc in recent_docs:
        doc_lines.append(f"- {doc.doc_number}: {doc.title[:60]} ({doc.status})")

    today = datetime.now().strftime('%d.%m.%Y')
    lang  = current_user.language

    prompts = {
        'ru': f"""Ты — корпоративный ИИ-ассистент компании Caspian Integrated Services (CIS), нефтесервисная компания в Атырау, Казахстан.
Сгенерируй утренний брифинг на {today} для {current_user.full_name} ({current_user.role_display}).

Данные системы:
- Документов на согласовании: {pending_docs}
- Всего документов: {total_docs}
- Оборудование: {equipment_total} единиц, {equipment_deployed} в работе, {equipment_maint} на ТО
- Активных сотрудников: {staff_total}
- Последние документы:
{chr(10).join(doc_lines) if doc_lines else '- Нет документов'}

Напиши краткий профессиональный утренний брифинг на русском языке. 4-6 пунктов. Начни с приветствия. Выдели что требует внимания. Закончи мотивирующей фразой.""",

        'en': f"""You are the AI assistant for Caspian Integrated Services (CIS), an oilfield services company in Atyrau, Kazakhstan.
Generate a morning briefing for {today} for {current_user.full_name} ({current_user.role_display}).

System data:
- Documents pending approval: {pending_docs}
- Total documents: {total_docs}
- Equipment: {equipment_total} units, {equipment_deployed} deployed, {equipment_maint} in maintenance
- Active staff: {staff_total}
- Recent documents:
{chr(10).join(doc_lines) if doc_lines else '- No documents'}

Write a concise professional morning briefing in English. 4-6 bullet points. Start with a greeting. Highlight what needs immediate attention. End with a motivating note.""",

        'kz': f"""Сіз — Caspian Integrated Services (CIS) компаниясының ЖИ-көмекшісісіз.
{today} күніне {current_user.full_name} үшін таңғы брифинг жасаңыз.

Жүйе деректері:
- Келісімдегі құжаттар: {pending_docs}
- Барлық құжаттар: {total_docs}
- Жабдықтар: {equipment_total} бірлік, {equipment_deployed} жұмыста, {equipment_maint} ТО-да
- Белсенді қызметкерлер: {staff_total}

Қазақ тілінде қысқа кәсіби таңғы брифинг жазыңыз. 4-6 тармақ."""
    }

    briefing_text = None
    error = None

    try:
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompts.get(lang, prompts['ru'])}]
        )
        briefing_text = message.content[0].text
    except Exception as e:
        error = str(e)

    return render_template('dashboard/briefing.html',
        briefing_text=briefing_text,
        error=error,
        today=today,
        stats={
            'pending_docs':    pending_docs,
            'equipment_maint': equipment_maint,
            'staff_total':     staff_total,
        }
    )
@dashboard.route('/assistant', methods=['GET', 'POST'])
@login_required
def assistant():
    import anthropic
    import os

    answer = None
    question = None

    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if question:
            # Gather context
            equipment_total = Equipment.query.count()
            equipment_list = Equipment.query.all()
            docs_pending = Document.query.filter_by(status='pending').count()
            staff = User.query.filter_by(is_active=True).all()

            equip_lines = [f"- {e.unit_id}: {e.name}, статус: {e.status}, локация: {e.location}" for e in equipment_list]
            staff_lines = [f"- {u.full_name} ({u.role_display}, {u.department})" for u in staff]

            system_prompt = f"""Ты — ИИ-ассистент компании Caspian Integrated Services (CIS), нефтесервисная компания в Атырау, Казахстан.
Отвечай на вопросы сотрудников на языке вопроса (русский, английский или казахский).

Данные компании:

Оборудование ({equipment_total} единиц):
{chr(10).join(equip_lines)}

Документов на согласовании: {docs_pending}

Сотрудники:
{chr(10).join(staff_lines)}

Отвечай кратко, профессионально, по делу. Если не знаешь ответ — скажи честно."""

            try:
                client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
                message = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=600,
                    system=system_prompt,
                    messages=[{"role": "user", "content": question}]
                )
                answer = message.content[0].text
            except Exception as e:
                answer = f"Ошибка: {str(e)}"

    return render_template('dashboard/assistant.html', answer=answer, question=question)
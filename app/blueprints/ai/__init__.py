import json
import os
from flask import (Blueprint, render_template, request, jsonify, abort)
from flask_login import login_required, current_user
from app import db
from app.models import AiAgent
from app.audit import log_action
from app.services.agent_tools import TOOLS_SPEC, run_tool

ai = Blueprint('ai', __name__, url_prefix='/ai',
               template_folder='../../app/templates/ai')

MAX_FILE_CHARS = 40_000       # на один файл знаний
MAX_TOTAL_CHARS = 150_000     # суммарно в системный промпт
MAX_TOOL_ROUNDS = 5


def _visible_agents():
    return [a for a in AiAgent.query.filter_by(is_active=True).order_by(AiAgent.name).all()
            if a.role_allowed(current_user)]


@ai.route('/')
@login_required
def index():
    return render_template('ai/index.html', agents=_visible_agents())


@ai.route('/<int:agent_id>')
@login_required
def chat_page(agent_id):
    agent = AiAgent.query.get_or_404(agent_id)
    if not agent.role_allowed(current_user):
        abort(403)
    return render_template('ai/chat.html', agent=agent)


def _build_system_prompt(agent):
    parts = [agent.system_prompt or '']
    lang = {'ru': 'Отвечай на русском.', 'en': 'Reply in English.',
            'kz': 'Қазақ тілінде жауап бер.'}.get(current_user.language, '')
    parts.append(lang)
    total = 0
    knowledge = []
    for f in agent.files.order_by('created_at'):
        text = (f.extracted_text or '').strip()
        if not text:
            continue
        text = text[:MAX_FILE_CHARS]
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        total += len(text)
        knowledge.append(f'=== ДОКУМЕНТ: {f.original_filename} ===\n{text}')
    if knowledge:
        parts.append('База знаний (отвечай в первую очередь по этим документам):\n\n'
                     + '\n\n'.join(knowledge))
    return '\n\n'.join(p for p in parts if p)


def _anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))


@ai.route('/<int:agent_id>/chat', methods=['POST'])
@login_required
def chat(agent_id):
    agent = AiAgent.query.get_or_404(agent_id)
    if not agent.role_allowed(current_user):
        abort(403)
    payload = request.get_json(silent=True) or {}
    message = (payload.get('message') or '').strip()
    history = payload.get('history') or []   # [{role, content}] plain text only
    if not message:
        return jsonify({'error': 'empty message'}), 400

    messages = []
    for h in history[-10:]:
        if h.get('role') in ('user', 'assistant') and isinstance(h.get('content'), str):
            messages.append({'role': h['role'], 'content': h['content']})
    messages.append({'role': 'user', 'content': message})

    kwargs = {
        'model': agent.model,
        'max_tokens': 1500,
        'system': _build_system_prompt(agent),
        'messages': messages,
    }
    if agent.use_platform_tools:
        kwargs['tools'] = TOOLS_SPEC

    try:
        client = _anthropic_client()
        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.messages.create(**kwargs)
            if resp.stop_reason != 'tool_use':
                break
            tool_results = []
            assistant_content = []
            for block in resp.content:
                if block.type == 'text':
                    assistant_content.append({'type': 'text', 'text': block.text})
                elif block.type == 'tool_use':
                    assistant_content.append({'type': 'tool_use', 'id': block.id,
                                              'name': block.name, 'input': block.input})
                    tool_results.append({
                        'type': 'tool_result', 'tool_use_id': block.id,
                        'content': run_tool(block.name, block.input or {}),
                    })
            kwargs['messages'] = kwargs['messages'] + [
                {'role': 'assistant', 'content': assistant_content},
                {'role': 'user', 'content': tool_results},
            ]
        reply = ''.join(b.text for b in resp.content if b.type == 'text').strip()
        log_action('ai_chat', 'ai_agent', agent.id)
        db.session.commit()
        return jsonify({'reply': reply or '(пустой ответ)'})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 502

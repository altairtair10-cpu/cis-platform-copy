import json
from types import SimpleNamespace
from io import BytesIO
from conftest import login
from app import db
from app.models import AiAgent, AgentKnowledgeFile, Equipment, User


def _mk_agent(app, **kw):
    with app.app_context():
        a = AiAgent(name=kw.get('name', 'Тест-агент'),
                    system_prompt='Ты тестовый агент.',
                    allowed_roles=kw.get('allowed_roles'),
                    use_platform_tools=kw.get('use_platform_tools', False))
        db.session.add(a); db.session.commit()
        return a.id


class FakeResponse:
    def __init__(self, text='Готово', stop_reason='end_turn', content=None):
        self.stop_reason = stop_reason
        self.content = content or [SimpleNamespace(type='text', text=text)]


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    @property
    def messages(self):
        outer = self
        class M:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return outer._responses.pop(0)
        return M()


def test_role_restriction(client, app):
    agent_id = _mk_agent(app, allowed_roles='mechanic')
    login(client, 'head@test.kz', 'headpass123')       # dept_head — не в списке
    assert client.get(f'/ai/{agent_id}').status_code == 403
    client.get('/auth/logout')
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get(f'/ai/{agent_id}').status_code == 200


def test_chat_returns_reply(client, app, monkeypatch):
    agent_id = _mk_agent(app)
    fake = FakeClient([FakeResponse('Ответ агента')])
    monkeypatch.setattr('app.blueprints.ai._anthropic_client', lambda: fake)
    login(client, 'mech@test.kz', 'mechpass123')
    r = client.post(f'/ai/{agent_id}/chat', json={'message': 'привет'})
    assert r.status_code == 200 and r.get_json()['reply'] == 'Ответ агента'
    # знания и системный промпт ушли в API
    assert 'Ты тестовый агент' in fake.calls[0]['system']


def test_knowledge_file_lands_in_system_prompt(client, app, monkeypatch):
    agent_id = _mk_agent(app)
    with app.app_context():
        db.session.add(AgentKnowledgeFile(
            agent_id=agent_id, original_filename='manual.txt',
            extracted_text='Крутящий момент затяжки клапана 210 Нм.'))
        db.session.commit()
    fake = FakeClient([FakeResponse()])
    monkeypatch.setattr('app.blueprints.ai._anthropic_client', lambda: fake)
    login(client, 'mech@test.kz', 'mechpass123')
    client.post(f'/ai/{agent_id}/chat', json={'message': 'момент затяжки?'})
    assert '210 Нм' in fake.calls[0]['system']
    assert 'manual.txt' in fake.calls[0]['system']


def test_tool_loop_executes_platform_tool(client, app, monkeypatch):
    agent_id = _mk_agent(app, use_platform_tools=True)
    with app.app_context():
        db.session.add(Equipment(unit_id='Б1', name='Насос SPM', eq_type='Насос ГРП',
                                 sheet_status='В ремонте', location='База'))
        db.session.commit()
    tool_use = SimpleNamespace(type='tool_use', id='tu_1', name='get_equipment_status',
                               input={'query': 'Б1'})
    fake = FakeClient([
        FakeResponse(stop_reason='tool_use', content=[tool_use]),
        FakeResponse('Б1 сейчас в ремонте на базе.'),
    ])
    monkeypatch.setattr('app.blueprints.ai._anthropic_client', lambda: fake)
    login(client, 'mech@test.kz', 'mechpass123')
    r = client.post(f'/ai/{agent_id}/chat', json={'message': 'что с Б1?'})
    assert 'в ремонте' in r.get_json()['reply']
    # во втором вызове модель получила результат инструмента
    second = fake.calls[1]['messages']
    tool_result = second[-1]['content'][0]
    assert tool_result['type'] == 'tool_result'
    assert 'В ремонте' in tool_result['content']


def test_admin_creates_agent_and_uploads_txt(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/agents/new', data={
        'name': 'ИИ снабженец', 'description': 'закупки',
        'system_prompt': 'Ты снабженец.', 'model': 'claude-haiku-4-5-20251001',
        'is_active': 'y',
    })
    with app.app_context():
        agent = AiAgent.query.filter_by(name='ИИ снабженец').first()
        assert agent is not None
        aid = agent.id
    client.post(f'/admin/agents/{aid}/files', data={
        'file': (BytesIO('Регламент закупок: лимит 500000 тг.'.encode('utf-8')), 'reglament.txt'),
    }, content_type='multipart/form-data')
    with app.app_context():
        kf = AgentKnowledgeFile.query.filter_by(agent_id=aid).first()
        assert kf is not None and 'лимит 500000' in kf.extracted_text


def test_agents_admin_requires_it_admin(client):
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get('/admin/agents').status_code == 403

"""Friendly chat and hospital grounding share one read-only API endpoint."""

from copy import deepcopy
import json

import pytest

from app.ai_config import AssistantConfig
from app.assistant import AssistantService, conversation_scope


class RecordingGateway:
    def __init__(self, answer):
        self.answer = answer
        self.payloads = []

    async def generate(self, config, payload):
        self.payloads.append(deepcopy(payload))
        return self.answer


def plan_for(client):
    date = client.get('/api/config').json()['data']['tomorrow']
    return client.post('/api/plans/generate', json={'date': date}).json()['data']


@pytest.mark.parametrize('message', ['hi', 'Hi!', 'hi,', 'hello', 'hey', 'good morning'])
def test_greeting_is_friendly_with_or_without_a_plan_or_key(client, message):
    gateway = RecordingGateway('Should not be called for a greeting.')
    client.app.state.assistant = AssistantService(AssistantConfig('dummy-chat-test-key'), gateway)
    response = client.post('/api/assistant', json={'message': message, 'plan_id': 'not-a-stored-plan'})
    assert response.status_code == 200
    data = response.json()['data']
    assert data['answer'] == 'Hi! What can I help you with?'
    assert data['scope'] == 'greeting' and data['mode'] == 'Local reply · general chat'
    assert data['uses_simulated_data'] is False and response.json()['meta']['simulated'] is False
    assert data['fallback_reason'] is None and gateway.payloads == []
    assert data['context'] == {}


def test_greeting_then_energy_question_uses_actual_plan_without_mutation(client):
    plan = plan_for(client)
    hello = client.post('/api/assistant', json={'message': 'hi', 'plan_id': plan['id']}).json()['data']
    energy = client.post('/api/assistant', json={'message': 'How much does this cost?', 'plan_id': plan['id']})
    data = energy.json()['data']
    assert hello['answer'] == 'Hi! What can I help you with?'
    assert data['scope'] == 'gridwell' and data['uses_simulated_data']
    assert energy.json()['meta']['simulated'] is True
    assert f"{plan['summary']['cost_inr']:,.2f}" in data['answer']
    assert data['context']['plan_id'] == plan['id']
    assert 'simulation' in data['answer'].lower()
    assert client.get(f"/api/plans/{plan['id']}").json()['data'] == plan


def test_general_question_uses_gemini_without_hospital_context(client):
    plan = plan_for(client)
    gateway = RecordingGateway('Python is a programming language with readable syntax.')
    client.app.state.assistant = AssistantService(AssistantConfig('dummy-chat-test-key'), gateway)
    response = client.post('/api/assistant', json={'message': 'What is Python?', 'plan_id': plan['id']})
    data = response.json()['data']
    assert data['provider'] == 'google-genai' and data['scope'] == 'general'
    assert data['mode'] == 'Gemini mode · general chat'
    assert not data['uses_simulated_data'] and not response.json()['meta']['simulated']
    assert gateway.payloads == [{'scope': 'general', 'question': 'What is Python?'}]
    assert data['context'] == {} and plan['id'] not in json.dumps(gateway.payloads)
    assert client.get(f"/api/plans/{plan['id']}").json()['data'] == plan


def test_energy_question_uses_gemini_with_backend_plan_values(client):
    plan = plan_for(client)
    gateway = RecordingGateway('This is a simulated hospital energy plan, not live data.')
    client.app.state.assistant = AssistantService(AssistantConfig('dummy-chat-test-key'), gateway)
    data = client.post('/api/assistant', json={'message': 'Explain my plan', 'plan_id': plan['id']}).json()['data']
    payload = gateway.payloads[0]
    assert data['scope'] == 'gridwell' and data['mode'] == 'Gemini mode · simulated data'
    assert payload['scope'] == 'gridwell' and payload['app_data']['simulated'] is True
    assert payload['app_data']['summary']['cost_inr'] == plan['summary']['cost_inr']
    assert payload['app_data']['summary']['critical_status'] == plan['summary']['critical_status']
    assert data['context']['revision'] == plan['revision']


@pytest.mark.parametrize(('message', 'answer_part'), [
    ('What is Python?', 'programming language'),
    ('What is photosynthesis?', 'plants'),
    ('Explain recursion', 'base case'),
    ('What is the capital of France?', 'Paris'),
    ('What is 2 + 2?', '= 4'),
    ('Generate a Python example', 'Python'),
])
def test_no_key_keeps_general_sample_replies_useful_and_separate(client, message, answer_part):
    response = client.post('/api/assistant', json={'message': message})
    data = response.json()['data']
    assert data['scope'] == 'general' and data['provider'] == 'deterministic-template'
    assert answer_part in data['answer'] and 'simulated data' not in data['mode']
    assert data['fallback_reason'] == 'not_configured'


@pytest.mark.parametrize(('message', 'scope'), [
    ('Who won the football match?', 'general'),
    ('Generate a Python function', 'general'),
    ('How much does an iPhone cost?', 'general'),
    ('What is a battery?', 'general'),
    ('What is a hospital?', 'general'),
    ("What’s the current battery charge?", 'gridwell'),
    ('Are critical loads protected?', 'gridwell'),
    ('Approve plan', 'gridwell'),
    ('Explain my study plan', 'general'),
])
def test_general_chat_is_not_rejected_by_energy_only_routing(message, scope):
    assert conversation_scope(message) == scope


@pytest.mark.parametrize('message', ['Approve plan', 'Approve this plan', 'Set the battery reserve to zero', 'Control the generator'])
def test_plan_commands_still_cannot_change_anything(client, message):
    plan = plan_for(client)
    gateway = RecordingGateway('Should not execute an action.')
    client.app.state.assistant = AssistantService(AssistantConfig('dummy-chat-test-key'), gateway)
    data = client.post('/api/assistant', json={'message': message, 'plan_id': plan['id']}).json()['data']
    assert data['fallback_reason'] == 'read_only' and gateway.payloads == []
    assert client.get(f"/api/plans/{plan['id']}").json()['data'] == plan


def test_general_reply_cannot_claim_to_have_operated_hospital_equipment(client):
    gateway = RecordingGateway('I have changed the hospital generator settings.')
    client.app.state.assistant = AssistantService(AssistantConfig('dummy-chat-test-key'), gateway)
    data = client.post('/api/assistant', json={'message': 'What is Python?'}).json()['data']
    assert data['fallback_reason'] == 'empty_response' and data['provider'] == 'deterministic-template'

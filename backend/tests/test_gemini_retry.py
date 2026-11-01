"""Temporary provider failures retry once; no real key or network is used."""

from copy import deepcopy
import json
import logging
from unittest.mock import AsyncMock

from google import genai
import httpx
import pytest

from app import assistant as assistant_module
from app.ai_config import AssistantConfig
from app.ai_diagnostics import LOGGER
from app.assistant import AssistantService, GeminiGateway

KEY = 'dummy-retry-test-credential'
SYMBOLS = {503: 'UNAVAILABLE', 504: 'DEADLINE_EXCEEDED'}


def events(caplog):
    return [json.loads(record.args[0]) for record in caplog.records if record.name == LOGGER.name]


def test_startup_reports_timeout_and_retry_policy_without_secrets(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    AssistantService(AssistantConfig(KEY)).log_configuration()
    policy = next(event for event in events(caplog) if event['event'] == 'request_policy')
    assert policy['http_timeout'] == '45 seconds' and policy['overall_deadline'] == '100 seconds'
    assert policy['maximum_attempts'] == '2' and policy['retry_delay'] == '2 seconds'
    assert policy['retry_http_statuses'] == '503, 504'
    assert KEY not in caplog.text


@pytest.mark.parametrize('status', [503, 504])
def test_real_sdk_temporary_error_waits_then_recovers_with_same_plan(client, monkeypatch, caplog, status):
    original_client = genai.Client
    requests = []
    delay = AsyncMock()
    monkeypatch.setattr(assistant_module.asyncio, 'sleep', delay)

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(status, json={'error': {
                'code': status, 'status': SYMBOLS[status],
                'message': f'Temporary provider error. api_key={KEY}',
            }})
        return httpx.Response(200, json={'candidates': [{
            'content': {'role': 'model', 'parts': [{'text': 'These plan values are simulated estimates.'}]},
            'finishReason': 'STOP',
        }]})

    def factory(**kwargs):
        options = kwargs['http_options']
        assert options.timeout == 45000 and options.retry_options.attempts == 1
        options.httpx_client = httpx.Client(transport=httpx.MockTransport(handle))
        options.httpx_async_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        return original_client(**kwargs)

    monkeypatch.setattr(genai, 'Client', factory)
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    date = client.get('/api/config').json()['data']['tomorrow']
    plan = client.post('/api/plans/generate', json={'date': date}).json()['data']
    client.app.state.assistant = AssistantService(AssistantConfig(KEY), GeminiGateway())
    response = client.post('/api/assistant', json={'message': 'Explain my plan', 'plan_id': plan['id']})
    data = response.json()['data']

    assert response.status_code == 200 and data['mode'] == 'Gemini mode · simulated data'
    assert data['fallback_reason'] is None
    assert len(requests) == 2 and requests[0].content == requests[1].content
    assert requests[0].url == requests[1].url
    delay.assert_awaited_once_with(2)
    diagnostic = next(event for event in events(caplog) if event['event'] == 'gemini_retry')
    assert diagnostic['http_status'] == status and diagnostic['api_status'] == SYMBOLS[status]
    assert diagnostic['next_attempt'] == '2 of 2' and diagnostic['retry_delay'] == '2 seconds'
    assert '[REDACTED]' in diagnostic['message']
    assert any(event['event'] == 'gemini_success' for event in events(caplog))
    assert KEY not in caplog.text and KEY not in response.text
    assert client.get(f"/api/plans/{plan['id']}").json()['data'] == plan


@pytest.mark.parametrize(('statuses', 'reason'), [([503, 504], 'timeout'), ([504, 503], 'unavailable')])
def test_second_error_uses_sample_without_third_attempt(client, monkeypatch, caplog, statuses, reason):
    class FailingGateway:
        calls = []

        async def generate(self, config, payload):
            self.calls.append(deepcopy(payload))
            status = statuses[len(self.calls) - 1]
            raise genai.errors.ServerError(status, {'error': {
                'code': status, 'status': SYMBOLS[status], 'message': f'Temporary error with {KEY}',
            }})

    delay = AsyncMock()
    monkeypatch.setattr(assistant_module.asyncio, 'sleep', delay)
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    gateway = FailingGateway()
    client.app.state.assistant = AssistantService(AssistantConfig(KEY), gateway)
    response = client.post('/api/assistant', json={'message': 'What is Python?'})
    data = response.json()['data']
    assert data['mode'] == 'Sample mode · general chat' and data['fallback_reason'] == reason
    assert len(gateway.calls) == 2 and gateway.calls[0] == gateway.calls[1]
    delay.assert_awaited_once_with(2)
    diagnostic = next(event for event in events(caplog) if event['event'] == 'gemini_error')
    assert diagnostic['http_status'] == statuses[-1]
    assert diagnostic['api_status'] == SYMBOLS[statuses[-1]]
    assert KEY not in caplog.text and KEY not in response.text


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429])
def test_permanent_or_quota_errors_do_not_wait_or_retry(client, monkeypatch, status):
    gateway = AsyncMock()
    gateway.generate.side_effect = genai.errors.ClientError(status, {'error': {
        'code': status, 'message': 'Request rejected.',
    }})
    delay = AsyncMock()
    monkeypatch.setattr(assistant_module.asyncio, 'sleep', delay)
    client.app.state.assistant = AssistantService(AssistantConfig(KEY), gateway)
    response = client.post('/api/assistant', json={'message': 'What is Python?'})
    assert response.json()['data']['provider'] == 'deterministic-template'
    gateway.generate.assert_awaited_once()
    delay.assert_not_awaited()


def test_total_deadline_includes_retry_delay_and_prevents_later_attempt(client, monkeypatch, caplog):
    gateway = AsyncMock()
    gateway.generate.side_effect = genai.errors.ServerError(504, {'error': {
        'code': 504, 'status': 'DEADLINE_EXCEEDED', 'message': 'Temporary deadline exceeded.',
    }})
    monkeypatch.setattr(assistant_module, 'REQUEST_TIMEOUT_SECONDS', 0.01)
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    client.app.state.assistant = AssistantService(AssistantConfig(KEY), gateway)
    response = client.post('/api/assistant', json={'message': 'What is Python?'})
    assert response.json()['data']['fallback_reason'] == 'timeout'
    gateway.generate.assert_awaited_once()
    assert any(event['event'] == 'gemini_retry' for event in events(caplog))
    assert any(event.get('error_type') == 'TimeoutError' for event in events(caplog))

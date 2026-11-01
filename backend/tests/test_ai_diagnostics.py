"""Terminal diagnostics must be useful without leaking a key, prompt or body."""

from copy import deepcopy
import json
import logging
from urllib.parse import quote, quote_plus

import httpx
import pytest
from google import genai
from google.genai import errors, types

from app import ai_config
from app.ai_config import AssistantConfig
from app.ai_diagnostics import LOGGER, GeminiResponseError, emit, error_details, redact
from app.assistant import AssistantService, GeminiGateway, gemini_response_text

KEY = "unit-test-private-key+/?=only"


def diagnostic_records(caplog):
    return [json.loads(r.args[0]) for r in caplog.records if r.name == LOGGER.name]


@pytest.mark.parametrize('message', [
    f'Invalid key {KEY}; check the request.',
    f'Invalid key {quote(KEY, safe="")}; check the request.',
    f'Invalid key {quote_plus(KEY)}; check the request.',
])
def test_known_credentials_are_removed_before_logging(message, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    emit(AssistantConfig(KEY), 'gemini_error', level=logging.WARNING, http_status=400, message=message)
    assert KEY not in caplog.text and quote(KEY, safe='') not in caplog.text
    assert KEY not in repr(caplog.records[0].args)
    record = diagnostic_records(caplog)[0]
    assert record['http_status'] == 400 and '[REDACTED]' in record['message']


@pytest.mark.parametrize(('message', 'private_value'), [
    ('API key=unrelated-private-value quota exceeded', 'unrelated-private-value'),
    ('GEMINI_API_KEY="unrelated-private-value" quota exceeded', 'unrelated-private-value'),
    ('Authorization: Bearer unrelated-private-value quota exceeded', 'unrelated-private-value'),
    ('{"password":"unrelated-private-value"} quota exceeded', 'unrelated-private-value'),
    ('Proxy socks5://someone:private-password@proxy.invalid:123 failed', 'private-password'),
    ('See https://service.invalid/?key=unrelated-private-value&token=abc for quota', 'unrelated-private-value'),
    ('Access token=unrelated-private-value expired', 'unrelated-private-value'),
    ('Key AIzaSy-not-a-real-google-key-private-value rejected', 'AIzaSy-not-a-real-google-key-private-value'),
    ('Email person@example.com about project 123456789012', 'person@example.com'),
])
def test_other_common_secrets_and_identifiers_are_redacted(message, private_value):
    assert private_value not in redact(message)


def test_environment_secrets_and_terminal_injection_are_redacted(monkeypatch):
    monkeypatch.setenv('ANOTHER_SERVICE_TOKEN', 'a-different-secret-value')
    text = redact('Quota: a-different-secret-value\n\x1b[31mFAKE LOG\x00', KEY)
    assert 'a-different-secret-value' not in text
    assert '\n' not in text and '\x1b' not in text and '\x00' not in text


def test_config_diagnostics_confirm_root_file_key_source_and_model_without_key(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    monkeypatch.setattr(ai_config, 'PROJECT_ROOT', tmp_path)
    (tmp_path / '.env').write_text(f'GEMINI_API_KEY={KEY}\nGEMINI_MODEL=gemini-2.5-flash\n')
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    config = AssistantConfig.from_environment()
    AssistantService(config).log_configuration()
    record = diagnostic_records(caplog)[0]
    assert record['key_present'] is True and record['key_source'] == '.env'
    assert record['env_file_status'] == 'present'
    assert record['model'] == 'gemini-2.5-flash' and record['model_source'] == '.env'
    assert KEY not in caplog.text
    assert KEY not in json.dumps(config.public_status())


def test_empty_environment_override_is_diagnosed(tmp_path, monkeypatch, caplog):
    (tmp_path / '.env').write_text(f'GEMINI_API_KEY={KEY}\n')
    monkeypatch.setenv('GEMINI_API_KEY', '')
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    config = AssistantConfig.from_environment(tmp_path / '.env')
    AssistantService(config).log_configuration()
    records = diagnostic_records(caplog)
    assert records[0]['key_present'] is False and records[0]['key_source'] == 'environment'
    assert records[1]['event'] == 'configuration_hint' and 'overrides' in records[1]['message']
    assert KEY not in caplog.text


def test_sdk_error_uses_real_http_status_and_only_selected_message():
    error = errors.ClientError(404, {'error': {'code': 404, 'status': 'NOT_FOUND', 'message': 'Configured model unavailable.'}, 'extra': 'do-not-log-full-body'}, response=httpx.Response(403))
    fields = error_details(error)
    assert fields['http_status'] == 403
    assert fields['message'] == 'Configured model unavailable.'
    assert 'do-not-log-full-body' not in json.dumps(fields)
    missing = error_details(errors.ClientError(400, {'error': {'code': 400, 'unknown': 'do-not-log-full-body'}}))
    assert 'do-not-log-full-body' not in missing['message']


def sdk_response(parts=None, finish='STOP', feedback=None, thoughts=0):
    return types.GenerateContentResponse.model_validate({
        'candidates': [{'content': {'role': 'model', 'parts': parts or []}, 'finishReason': finish}],
        'promptFeedback': feedback,
        'usageMetadata': {'thoughtsTokenCount': thoughts},
    })


@pytest.mark.parametrize('block', [None, 'BLOCKED_REASON_UNSPECIFIED'])
@pytest.mark.parametrize('finish', ['STOP', None, 'FINISH_REASON_UNSPECIFIED'])
def test_current_sdk_response_joins_only_visible_primary_text(block, finish):
    response = sdk_response([{'text': 'hidden-thought-data', 'thought': True}, {'text': 'The simulated '}, {'text': 'plan is protected.'}], finish=finish, feedback={'blockReason': block} if block else None)
    assert gemini_response_text(response) == 'The simulated plan is protected.'
    response.candidates.append(types.Candidate(finish_reason='MAX_TOKENS'))
    assert gemini_response_text(response) == 'The simulated plan is protected.'


@pytest.mark.parametrize(('response', 'finish', 'block', 'message_part'), [
    (sdk_response([{'text': 'unfinished'}], finish='MAX_TOKENS', thoughts=1500), 'MAX_TOKENS', None, 'max_output_tokens'),
    (sdk_response([], finish='SAFETY'), 'SAFETY', None, 'did not complete'),
    (sdk_response([{'text': 'unfinished'}], finish='CONTINUATION'), 'CONTINUATION', None, 'did not complete'),
    (types.GenerateContentResponse.model_validate({'promptFeedback': {'blockReason': 'SAFETY'}}), None, 'SAFETY', 'blocked'),
    (sdk_response([{'text': 'hidden-thought-data', 'thought': True}]), 'STOP', None, 'no non-thinking text'),
    (types.GenerateContentResponse(), None, None, 'no response candidates'),
    (sdk_response([{'functionCall': {'name': 'approve_plan', 'args': {}}}]), 'STOP', None, 'tool/code'),
])
def test_unusable_responses_report_exact_outcome_without_text(response, finish, block, message_part):
    with pytest.raises(GeminiResponseError) as found:
        gemini_response_text(response)
    diagnostic = found.value.diagnostic
    assert diagnostic['finish_reason'] == finish and diagnostic['block_reason'] == block
    assert message_part in diagnostic['message']
    assert 'hidden-thought-data' not in json.dumps(diagnostic)
    assert 'unfinished' not in json.dumps(diagnostic)


@pytest.mark.parametrize(('status', 'symbol', 'message'), [
    (400, 'INVALID_ARGUMENT', 'Unsupported generation parameter.'),
    (401, 'UNAUTHENTICATED', 'The credential was rejected.'),
    (403, 'PERMISSION_DENIED', 'This project cannot access inference.'),
    (404, 'NOT_FOUND', 'Configured model unavailable.'),
    (429, 'RESOURCE_EXHAUSTED', 'Quota exceeded for the selected model.'),
    (503, 'UNAVAILABLE', 'The service is temporarily unavailable.'),
    (504, 'DEADLINE_EXCEEDED', 'The request exceeded its deadline.'),
])
def test_real_sdk_errors_are_reported_safely_only_in_terminal(client, monkeypatch, caplog, status, symbol, message):
    monkeypatch.setattr('app.assistant.RETRY_DELAY_SECONDS', 0)
    original_client = genai.Client
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={'error': {'code': status, 'status': symbol, 'message': message + f' Credential: {KEY}'}, 'extra': 'do-not-log-full-body'})
    def factory(**kwargs):
        kwargs['http_options'].httpx_client = httpx.Client(transport=httpx.MockTransport(handle))
        kwargs['http_options'].httpx_async_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        return original_client(**kwargs)
    monkeypatch.setattr(genai, 'Client', factory)
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    client.app.state.assistant = AssistantService(AssistantConfig(KEY, 'gemini-2.5-flash'), GeminiGateway())
    result = client.post('/api/assistant', json={'message': 'Explain the forecast', 'date': '2026-11-01'})
    assert result.status_code == 200 and result.json()['data']['provider'] == 'deterministic-template'
    record = next(r for r in diagnostic_records(caplog) if r['event'] == 'gemini_error')
    assert record['http_status'] == status and record['api_status'] == symbol
    assert message in record['message'] and record['model'] == 'gemini-2.5-flash'
    assert KEY not in caplog.text and KEY not in result.text
    assert 'do-not-log-full-body' not in caplog.text
    assert message not in result.text  # provider detail stays in server Terminal
    assert len(requests) == (2 if status in {503, 504} else 1)
    assert '/models/gemini-2.5-flash:' in requests[0].url.path


def test_transport_error_has_no_invented_http_status(client, caplog):
    class FailedGateway:
        async def generate(self, config, payload):
            raise ImportError('Using SOCKS proxy, but the socksio package is not installed.')
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    client.app.state.assistant = AssistantService(AssistantConfig(KEY), FailedGateway())
    result = client.post('/api/assistant', json={'message': 'Explain the forecast', 'date': '2026-11-01'})
    assert result.json()['data']['provider'] == 'deterministic-template'
    record = next(r for r in diagnostic_records(caplog) if r['event'] == 'gemini_error')
    assert record['http_status'] == 'not_reported' and record['error_type'] == 'ImportError'
    assert 'socksio' in record['message']


def test_max_tokens_and_thought_counts_are_logged_without_private_response(client, caplog):
    class TruncatedGateway:
        async def generate(self, config, payload):
            return gemini_response_text(sdk_response([{'text': 'hidden-thought-data', 'thought': True}], finish='MAX_TOKENS', thoughts=1500))
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    client.app.state.assistant = AssistantService(AssistantConfig(KEY), TruncatedGateway())
    result = client.post('/api/assistant', json={'message': 'Explain the forecast', 'date': '2026-11-01'})
    assert result.json()['data']['fallback_reason'] == 'empty_response'
    record = next(r for r in diagnostic_records(caplog) if r['event'] == 'generation_unusable')
    assert record['finish_reason'] == 'MAX_TOKENS' and record['thoughts_tokens'] == 1500
    assert 'hidden-thought-data' not in caplog.text and 'hidden-thought-data' not in result.text

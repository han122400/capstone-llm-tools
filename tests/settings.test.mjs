import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { ollamaParameters, modelfileParameterValues, parameterInputValue, replaceModelfileParameter } from '../ollama-parameters.js';

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
function extractSource(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first + start.length);
  assert.ok(first >= 0 && last > first, `Cannot locate production functions: ${start}`);
  return source.slice(first, last);
}
const settingsSource = extractSource('function modelfileFromRange(', 'function bindPageEvents(');
const routeSource = extractSource('function route()', "window.addEventListener('hashchange'");
const connectionSource = extractSource('async function refreshConnection(', 'function toast(');
const rawFile = '\r\n# Project settings\r\n  FROM\told-model:8b  \r\nSYSTEM """\r\n  Keep this prompt.\r\nFROM is an example inside the prompt.\r\n"""\r\nPARAMETER temperature 0.1\r\nPARAMETER stop "END"\r\n';
const savedSettings = {
  ollama_url: 'http://127.0.0.1:11434', model: 'old-model:8b', modelfile: rawFile,
  keep_alive: '5m', revision: 'rev-1', options: { temperature: 0.1, stop: ['END'] },
  generation_timeout_seconds: 300,
};
const response = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' },
});

test('Parameter fields use the same bounds as backend validation', () => {
  const backend = readFileSync(new URL('../backend/settings.py', import.meta.url), 'utf8');
  for (const [name, spec] of Object.entries(ollamaParameters)) {
    const match = backend.match(new RegExp(`"${name}": \\((float|int), ([\\d-]+), ([\\d-]+)\\)`));
    assert.ok(match, `Missing backend limits for ${name}`);
    assert.equal(spec.min, Number(match[2]));
    assert.equal(spec.max, Number(match[3]));
    assert.equal(spec.step, match[1] === 'int' ? 1 : 'any');
  }
});

test('Basic defaults and advanced fallbacks do not add missing lines or make a loaded draft dirty', () => {
  const h = harness();
  assert.equal(parameterInputValue('temperature'), '0.1');
  assert.equal(parameterInputValue('num_ctx'), '16384');
  assert.equal(parameterInputValue('num_predict'), '4096');
  assert.equal(parameterInputValue('top_p'), '0.95');
  assert.equal(parameterInputValue('repeat_penalty'), '1');
  assert.equal(parameterInputValue('seed'), '');
  assert.equal(parameterInputValue('top_k'), '');
  assert.equal(h.state().draft.modelfile, rawFile);
  assert.equal(h.ollamaSettingsDirty(), false);
});

test('Parameter edits preserve CRLF, indentation, SYSTEM, comments, stop, and trailing spaces', () => {
  const original = '# PARAMETER temperature 2\r\nFROM local:8b\r\n  PARAMETER\ttemperature\t"0.1"  \r\nPARAMETER stop "DONE"\r\nSYSTEM """\r\nPARAMETER temperature 9\r\nPARAMETER num_predict 7\r\n"""\r\n';
  const next = replaceModelfileParameter(original, 'temperature', '0.25');
  assert.equal(next, original.replace('"0.1"', '"0.25"'));
  assert.equal(modelfileParameterValues(next).temperature, '0.25');
  assert.equal(Object.hasOwn(modelfileParameterValues(next), 'num_predict'), false);
  assert.equal(modelfileParameterValues(next).stop, 'DONE');
});

test('New parameters are inserted outside SYSTEM and retain the newline style', () => {
  const original = '# Keep me\r\nFROM local:8b\r\n\r\nSYSTEM """\r\nPARAMETER num_predict 8\r\n"""\r\n';
  assert.equal(replaceModelfileParameter(original, 'num_predict', '4096'), original.replace('SYSTEM """', 'PARAMETER num_predict 4096\r\nSYSTEM """'));
  assert.equal(replaceModelfileParameter('FROM local:8b', 'num_ctx', '16384'), 'FROM local:8b\nPARAMETER num_ctx 16384\n');
});

test('Disabling seed and clearing top_k remove only the actual directives', () => {
  const original = 'FROM local:8b\nPARAMETER seed 42\nSYSTEM """\nPARAMETER seed 7\nPARAMETER top_k 2\n"""\nPARAMETER top_k 40\nPARAMETER stop "END"\n';
  const next = replaceModelfileParameter(replaceModelfileParameter(original, 'seed', null), 'top_k', null);
  assert.equal(next, original.replace('PARAMETER seed 42\n', '').replace('PARAMETER top_k 40\n', ''));
  assert.equal(Object.hasOwn(modelfileParameterValues(next), 'seed'), false);
  assert.equal(Object.hasOwn(modelfileParameterValues(next), 'top_k'), false);
});

test('Inline SYSTEM closure comments and case insensitive commands remain correctly parsed', () => {
  const original = 'SYSTEM """inline""" # """\nparameter TOP_P 0.8\n';
  assert.equal(modelfileParameterValues(original).top_p, '0.8');
  assert.equal(replaceModelfileParameter(original, 'top_p', '0.95'), original.replace('0.8', '0.95'));
});

test('Malformed values remain in the raw file and cannot masquerade as a valid numeric input', () => {
  for (const value of ['', 'NaN', 'Infinity', '0x10', 'false', '0.1 # comment']) {
    assert.equal(parameterInputValue('temperature', value), '');
    const next = replaceModelfileParameter(rawFile, 'temperature', value);
    assert.equal(modelfileParameterValues(next).temperature, value);
  }
  assert.equal(parameterInputValue('temperature', '.25'), '0.25');
  assert.equal(parameterInputValue('num_ctx', '1.6384e4'), '16384');
  const duplicate = 'PARAMETER temperature 0.1\nPARAMETER temperature 0.2\n';
  assert.equal(replaceModelfileParameter(duplicate, 'temperature', '0.3'), duplicate.replace('0.1', '0.3'));
  assert.throws(() => replaceModelfileParameter(rawFile, 'stop', 'END'), /지원하지/);
});

test('Control edits save through Modelfile only and preserve the prompt and other settings', async () => {
  const h = harness(async (url, options) => url.includes('/settings/') ? response({ ...savedSettings, ...JSON.parse(options.body), revision: 'rev-2' }) : response({ models: [] }));
  h.setOllamaParameter('num_predict', '8192');
  h.setOllamaParameter('seed', '42');
  h.setOllamaParameter('seed', null);
  assert.equal(h.state().draft.modelfile, rawFile.replace('SYSTEM """', 'PARAMETER num_predict 8192\r\nSYSTEM """'));
  await h.submit();
  const call = h.effects.calls.find(call => call.method === 'PUT');
  assert.deepEqual(Object.keys(call.payload).sort(), ['keep_alive', 'modelfile', 'ollama_url', 'revision']);
  assert.equal(modelfileParameterValues(call.payload.modelfile).num_predict, '8192');
  assert.equal(h.effects.renders, 0);
});

test('An invalid advanced setting is revealed before validation and never sent to the API', async () => {
  const h = harness();
  h.setOllamaParameter('top_p', '1.5');
  const advanced = { open: false };
  await h.saveOllamaSettings({ preventDefault() {}, target: {
    querySelector: () => ({ closest: () => advanced }),
    reportValidity: () => { assert.equal(advanced.open, true); return false; },
  } });
  assert.equal(h.effects.calls.length, 0);
  assert.equal(h.state().saved.modelfile, rawFile);
  assert.equal(modelfileParameterValues(h.state().draft.modelfile).top_p, '1.5');
});

function harness(fetcher = async () => response(savedSettings), saved = savedSettings) {
  const effects = { calls: [], renders: 0, hydrates: 0, health: 0, updates: 0 };
  const deps = {
    AbortSignal, document: { querySelector: () => null, querySelectorAll: () => [] },
    fetch: async (url, options) => {
      effects.calls.push({ url, method: options?.method || 'GET', payload: options?.body ? JSON.parse(options.body) : null });
      return fetcher(url, options);
    },
    refreshConnection: async () => { effects.health++; },
    update: () => { effects.updates++; }, hydrate: () => { effects.hydrates++; },
    render: () => { effects.renders++; }, window: { scrollTo() {} },
    saved, location: { hash: '#settings' }, icon: () => '',
    ollamaParameters, modelfileParameterValues, parameterInputValue, replaceModelfileParameter,
    esc: value => String(value ?? '').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  };
  return {
    ...runInNewContext(`
      const { AbortSignal, document, fetch, refreshConnection, render, window, location, icon, esc } = deps;
      const { ollamaParameters, modelfileParameterValues, parameterInputValue, replaceModelfileParameter } = deps;
      let generating = false, page = 'settings';
      let ollamaSettings = { saved: deps.saved, draft: null, loading: false, saving: false, error: '', notice: '', models: { url: null, loading: false, checked: false, available: false, names: [], message: '' }, probe: { loading: false, message: '', connected: false } };
      ${settingsSource}
      ${routeSource}
      updateSettingsUI = deps.update;
      hydrateSettingsInputs = deps.hydrate;
      if (ollamaSettings.saved) ollamaSettings.draft = draftFromSettings(ollamaSettings.saved);
      ({ modelFromModelfile, replaceModelfileModel, setOllamaDraft, setOllamaParameter, ollamaSettingsDirty,
         loadOllamaSettings, saveOllamaSettings, refreshOllamaModels, probeOllamaDraft,
         ollamaModelOptions, savedOllamaSummary, route, location,
         generating: value => { generating = value; }, state: () => ollamaSettings });
    `, { deps }),
    effects,
    submit() { return this.saveOllamaSettings({ preventDefault() {}, target: { reportValidity: () => true } }); },
  };
}

test('Model selection preserves original CRLF, whitespace, prompt, parameters, and final newline', () => {
  const h = harness();
  const next = h.replaceModelfileModel(rawFile, 'installed-model:latest');
  assert.equal(next, rawFile.replace('old-model:8b', 'installed-model:latest'));
  assert.equal(h.modelFromModelfile(next), 'installed-model:latest');
  assert.match(next, /FROM is an example inside the prompt/);
});

test('FROM parsing skips model-like text inside multiline SYSTEM', () => {
  const h = harness();
  const file = 'SYSTEM """\nFROM prompt-only:8b\n"""\n\tFROM actual:8b  \nPARAMETER seed 42\n';
  assert.equal(h.modelFromModelfile(file), 'actual:8b');
  assert.equal(h.replaceModelfileModel(file, 'new:8b'), file.replace('actual:8b', 'new:8b'));
});

test('Quoted FROM names are decoded for selection and keep their quoting when replaced', () => {
  const h = harness();
  const file = '  FROM "model-name:8b"  \r\nSYSTEM "prompt"\r\n';
  assert.equal(h.modelFromModelfile(file), 'model-name:8b');
  assert.equal(h.replaceModelfileModel(file, 'another:latest'), file.replace('"model-name:8b"', '"another:latest"'));
});

test('Triple quotes in a comment after SYSTEM closure do not hide a real FROM command', () => {
  const h = harness();
  assert.equal(h.modelFromModelfile('SYSTEM """inline prompt""" # """\nFROM local:8b\n'), 'local:8b');
  assert.equal(h.modelFromModelfile('SYSTEM """\nPrompt\n""" # """\nFROM local:8b\n'), 'local:8b');
});

test('Selecting a model when FROM is absent prepends a line using the original line ending', () => {
  const h = harness();
  const file = '# Comment\r\nSYSTEM """\r\nKeep me\r\n"""\r\n';
  assert.equal(h.replaceModelfileModel(file, 'local:8b'), `FROM local:8b\r\n${file}`);
});

test('Textarea edits retain CRLF style and a typed FROM name stays selected without inventing installed models', () => {
  const h = harness();
  const edited = rawFile.replace('old-model:8b', 'typed-model:8b').replaceAll('\r\n', '\n');
  h.setOllamaDraft('modelfile', edited);
  assert.equal(h.state().draft.modelfile, rawFile.replace('old-model:8b', 'typed-model:8b'));
  assert.equal(h.ollamaSettingsDirty(), true);
  assert.equal(h.ollamaModelOptions().model, 'typed-model:8b');
  assert.deepEqual(JSON.parse(JSON.stringify(h.ollamaModelOptions().entries)), [
    { value: 'typed-model:8b', label: 'typed-model:8b · 설치 여부 미확인' },
  ]);
  assert.equal(h.effects.hydrates, 0, 'Editing must not hydrate or recreate the textarea');
  assert.equal(h.effects.renders, 0, 'Editing must not rerender the page');
});

test('Installed model options contain only real names plus an honestly labelled configured model', async () => {
  const h = harness(async () => response({ ollama_available: true, models: [{ name: 'installed:8b' }, { name: 'installed:8b' }, { name: 'other:latest' }], message: '' }));
  await h.refreshOllamaModels();
  assert.deepEqual(JSON.parse(JSON.stringify(h.ollamaModelOptions().entries)), [
    { value: 'old-model:8b', label: 'old-model:8b · 미설치' },
    { value: 'installed:8b', label: 'installed:8b' }, { value: 'other:latest', label: 'other:latest' },
  ]);
  h.setOllamaDraft('ollama_url', 'http://localhost:11435');
  assert.equal(h.ollamaModelOptions().entries.length, 1, 'A list from a previous URL must not masquerade as the draft server');
  assert.match(h.ollamaModelOptions().entries[0].label, /미확인/);
});

test('Offline model listing keeps the configured FROM and editable file', async () => {
  const h = harness(async () => response({ ollama_available: false, models: [], message: 'Ollama가 실행되지 않았습니다.' }));
  await h.refreshOllamaModels();
  assert.equal(h.ollamaModelOptions().model, savedSettings.model);
  assert.match(h.ollamaModelOptions().entries[0].label, /미확인/);
  assert.equal(h.state().draft.modelfile, rawFile);
  assert.equal(h.state().models.message, 'Ollama가 실행되지 않았습니다.');
});

test('Saving sends the full raw Modelfile, revision, URL, and keep_alive without a competing model field', async () => {
  const changed = rawFile.replace('old-model:8b', 'new-model:8b');
  const applied = { ...savedSettings, model: 'new-model:8b', modelfile: changed, revision: 'rev-2' };
  const h = harness(async () => response(applied));
  h.setOllamaDraft('modelfile', changed);
  await h.submit();
  assert.deepEqual(h.effects.calls, [{
    url: '/api/settings/ollama', method: 'PUT',
    payload: { ollama_url: savedSettings.ollama_url, modelfile: changed, keep_alive: '5m', revision: 'rev-1' },
  }]);
  assert.equal(h.effects.health, 1);
  assert.equal(h.state().saved.revision, 'rev-2');
  assert.equal(h.ollamaSettingsDirty(), false);
  assert.match(h.state().notice, /다음 보고서/);
});

for (const [status, message] of [[422, 'SYSTEM 삼중 따옴표가 닫히지 않았습니다.'], [409, '저장된 설정이 변경되었습니다. 최신 설정을 불러오세요.'], [503, 'Modelfile 저장에 실패했습니다.']]) {
  test(`HTTP ${status} retains the draft and its revision without changing saved connection state`, async () => {
    const h = harness(async () => response({ detail: message }, status));
    const changed = rawFile.replace('old-model:8b', 'my-draft:8b');
    h.setOllamaDraft('modelfile', changed);
    await h.submit();
    assert.equal(h.state().draft.modelfile, changed);
    assert.equal(h.state().draft.revision, 'rev-1');
    assert.equal(h.state().saved.modelfile, rawFile);
    assert.equal(h.effects.health, 0);
    assert.equal(h.state().saving, false);
    assert.equal(h.ollamaSettingsDirty(), true);
    assert.ok(h.state().error.includes(message));
    assert.match(h.state().error, /수정한 내용은 유지/);
  });
}

test('Revert after a stale revision explicitly loads the latest stored file and revision', async () => {
  const latest = { ...savedSettings, revision: 'rev-other', modelfile: 'FROM latest:8b\nSYSTEM latest\n' };
  const h = harness(async (_url, options) => options?.method === 'PUT' ? response({ detail: '설정이 변경되었습니다.' }, 409) : response(latest));
  h.setOllamaDraft('modelfile', 'FROM my-unsaved:8b\n');
  await h.submit();
  assert.equal(h.state().draft.modelfile, 'FROM my-unsaved:8b\r\n');
  // Avoid unrelated model listing in this saved-settings fetch test.
  h.state().models = { ...h.state().models, checked: true, url: savedSettings.ollama_url };
  await h.loadOllamaSettings(true);
  assert.equal(h.state().draft.modelfile, latest.modelfile);
  assert.equal(h.state().draft.revision, 'rev-other');
  assert.equal(h.state().error, '');
  assert.equal(h.ollamaSettingsDirty(), false);
});

test('Navigating away and back preserves the exact draft and does not load over it', async () => {
  const h = harness();
  const changed = rawFile.replace('old-model:8b', 'route-draft:8b');
  h.setOllamaDraft('modelfile', changed);
  h.location.hash = '#dashboard'; h.route();
  h.location.hash = '#settings'; h.route();
  await h.loadOllamaSettings();
  assert.equal(h.state().draft.modelfile, changed);
  assert.equal(h.effects.calls.length, 0);
  assert.equal(h.effects.renders, 2);
});

test('Background health checks update the actual connection without overwriting a draft', async () => {
  const state = runInNewContext(`
    const document = { querySelectorAll: () => [] };
    const AbortSignal = deps.AbortSignal;
    let connection = { model: 'old:8b' };
    const draft = { ollama_url: 'http://localhost:11435', modelfile: 'FROM unsaved:8b\\n' };
    const fetch = async () => deps.response;
    const updateSettingsUI = () => {};
    const connectionLabel = () => connection.model;
    ${connectionSource}
    ({ refreshConnection, draft, state: () => connection });
  `, { deps: { AbortSignal, response: response({ model: 'saved:8b', ollama_url: 'http://localhost:11434', model_connected: true }) } });
  await state.refreshConnection();
  assert.equal(state.state().model, 'saved:8b');
  assert.equal(state.draft.modelfile, 'FROM unsaved:8b\n');
  assert.equal(state.draft.ollama_url, 'http://localhost:11435');
});

test('Draft probe reads the current URL and FROM without saving or refreshing the actual connection', async () => {
  const h = harness(async () => response({ model_connected: true, message: '지정한 모델이 설치되어 있습니다.' }));
  h.setOllamaDraft('ollama_url', 'http://localhost:11435');
  h.setOllamaDraft('modelfile', 'FROM probe-model:8b\nSYSTEM probe\n');
  await h.probeOllamaDraft();
  assert.deepEqual(h.effects.calls, [{ url: '/api/ollama/check', method: 'POST', payload: { ollama_url: 'http://localhost:11435', model: 'probe-model:8b' } }]);
  assert.equal(h.effects.health, 0);
  assert.equal(h.state().saved.model, 'old-model:8b');
  assert.equal(h.state().probe.connected, true);
  assert.match(h.state().probe.message, /현재 입력값/);
});

test('Read-only actions and save remain blocked during report generation while edits survive', async () => {
  const h = harness();
  h.generating(true);
  h.setOllamaDraft('modelfile', 'FROM later:8b\nSYSTEM new prompt\n');
  await h.probeOllamaDraft(); await h.refreshOllamaModels(); await h.submit();
  assert.equal(h.effects.calls.length, 0);
  assert.equal(h.state().draft.modelfile, 'FROM later:8b\r\nSYSTEM new prompt\r\n');
  assert.match(h.state().error, /생성이 끝난 뒤/);
});

test('Effective option summary remains saved-only while the Modelfile draft changes', () => {
  const h = harness();
  h.setOllamaDraft('modelfile', 'FROM draft:8b\nPARAMETER temperature 0.9\n');
  const summary = h.savedOllamaSummary();
  assert.ok(summary.includes('old-model:8b'));
  assert.ok(summary.includes('0.1'));
  assert.equal(summary.includes('draft:8b'), false);
  assert.equal(summary.includes('0.9'), false);
});

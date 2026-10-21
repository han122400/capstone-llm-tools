import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { classifications } from '../data.js';

// Exercise the production functions without booting the app or touching a browser.
const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
function extractSource(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first + start.length);
  assert.ok(first >= 0 && last > first, `Cannot locate production functions: ${start}`);
  return source.slice(first, last);
}
const streamSource = extractSource('function createSseParser(', 'function validGeneratedReport(');
const generationSource = extractSource('function createSseParser(', 'function modal(');
const { createSseParser, readGenerationStream } = runInNewContext(
  `${streamSource}\n({ createSseParser, readGenerationStream });`,
  { TextDecoder },
);

const encoder = new TextEncoder();
const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
const wire = ': keepalive\r\nevent: thinking\r\ndata: {"text":"한글😀<script>"}\r\n\r\nevent: result\ndata: {"report":{"id":"RPT-TEST"}}\n\n';

function streamedResponse(text, chunkSize = 1) {
  const bytes = encoder.encode(text);
  let offset = 0;
  return new Response(new ReadableStream({
    pull(controller) {
      if (offset >= bytes.length) controller.close();
      else {
        controller.enqueue(bytes.slice(offset, offset + chunkSize));
        offset += chunkSize;
      }
    },
  }), { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } });
}

for (const chunkSize of [1, 2, 3, 7, 19, 1024]) {
  test(`SSE parser preserves UTF-8 text and event boundaries in ${chunkSize}-byte chunks`, () => {
    const events = [];
    const parser = createSseParser((name, value) => events.push([name, JSON.parse(value)]));
    const bytes = encoder.encode(wire);
    const decoder = new TextDecoder();
    for (let i = 0; i < bytes.length; i += chunkSize) {
      parser.push(decoder.decode(bytes.slice(i, i + chunkSize), { stream: true }));
    }
    parser.push(decoder.decode());
    assert.equal(parser.finish(), true);
    assert.deepEqual(events, [
      ['thinking', { text: '한글😀<script>' }],
      ['result', { report: { id: 'RPT-TEST' } }],
    ]);
  });
}

test('SSE parser supports standalone CR endings and multiline data', () => {
  const events = [];
  const parser = createSseParser((name, value) => events.push([name, value]));
  parser.push('event: status\rdata: first\rdata: second\r\r');
  assert.equal(parser.finish(), true);
  assert.deepEqual(events, [['status', 'first\nsecond']]);
});

test('SSE parser does not dispatch an event missing its final blank line', () => {
  const events = [];
  const parser = createSseParser((name, value) => events.push([name, value]));
  parser.push('event: result\ndata: {"report":{}}\n');
  assert.equal(parser.finish(), false);
  assert.deepEqual(events, []);
});

test('Stream reader decodes split UTF-8 and completes only after the result event', async () => {
  const events = [];
  await readGenerationStream(streamedResponse(wire), (name, data) => {
    events.push([name, data]);
    return name === 'result';
  });
  assert.equal(events.length, 2);
  assert.equal(events[0][0], 'thinking');
  assert.equal(events[0][1].text, '한글😀<script>');
  assert.equal(events[1][0], 'result');
  assert.equal(events[1][1].report.id, 'RPT-TEST');
});

test('Stream reader rejects EOF without a final result after retaining received thinking', async () => {
  const received = [];
  await assert.rejects(readGenerationStream(
    streamedResponse(event('thinking', { text: 'partial thinking' })),
    (name, data) => { received.push(data.text); return false; },
  ), /최종 보고서를/);
  assert.deepEqual(received, ['partial thinking']);
});

test('Stream reader rejects an unterminated result at EOF', async () => {
  let dispatched = false;
  await assert.rejects(readGenerationStream(
    streamedResponse('event: result\ndata: {"report":{}}'),
    () => { dispatched = true; return true; },
  ), /최종 보고서를/);
  assert.equal(dispatched, false);
});

test('Stream reader propagates the server error event', async () => {
  await assert.rejects(readGenerationStream(
    streamedResponse(event('error', { message: '실제 서버 오류' })),
    (name, data) => { throw new Error(data.message); },
  ), /실제 서버 오류/);
});

test('Stream reader rejects malformed JSON event data', async () => {
  await assert.rejects(readGenerationStream(
    streamedResponse('event: thinking\ndata: invalid\n\n'),
    () => false,
  ), /스트리밍 이벤트/);
});

test('Stream reader rejects a non-SSE successful response', async () => {
  await assert.rejects(readGenerationStream(
    new Response('{}', { headers: { 'Content-Type': 'application/json' } }),
    () => true,
  ), /스트리밍 응답 형식/);
});

const originalInput = { title: '  테스트 제목  ', input_data: '\n  입력 원문 😀 <script>  \n' };
const report = {
  id: 'RPT-TEST', title: originalInput.title, classification: 'INFORMATIONAL',
  findings: [], thinking: '테스트 thinking 원문 <script>안전</script>', input_data: originalInput.input_data,
};

function generationHarness(stream, pageValue = 'dashboard') {
  const actions = { save: 0, render: 0, open: [], request: null };
  const deps = {
    classifications, AbortSignal, TextDecoder, pageValue,
    fetch: async (url, options) => {
      actions.request = { url, payload: JSON.parse(options.body) };
      return streamedResponse(stream, 3);
    },
    save: () => { actions.save++; },
    render: () => { actions.render++; },
    openReport: id => actions.open.push(id),
    toast: () => {}, refreshConnection: () => {}, updateGenerationForm: () => {},
    updateGenerationUI: () => {}, queueGenerationUI: () => {}, cancelAnimationFrame: () => {},
    location: { hash: `#${pageValue}` },
  };
  const api = runInNewContext(`
    const { classifications, AbortSignal, TextDecoder, fetch, save, render, openReport,
      toast, refreshConnection, updateGenerationForm, updateGenerationUI,
      queueGenerationUI, cancelAnimationFrame, location, pageValue } = deps;
    let generating = false, generationError = '', generation = {}, generationFrame = null;
    let editorDraft = {}, reports = [], filter = 'all', statusFilter = 'all', search = '', page = pageValue;
    ${generationSource}
    ({ generateReport, state: () => ({ generating, generationError, generation, editorDraft, reports }), location });
  `, { deps });
  const form = {
    reportValidity: () => true,
    elements: { title: { value: originalInput.title }, input_data: { value: originalInput.input_data } },
  };
  return { ...api, actions, form, submit: () => api.generateReport({ preventDefault() {}, target: form }) };
}

test('Dashboard completion preserves request bytes, saves only the result, and never opens a modal', async () => {
  const h = generationHarness(
    event('status', { stage: 'thinking', message: '테스트 서버 상태' })
    + event('thinking', { text: report.thinking })
    + event('content', { text: '{}' })
    + event('result', { report }),
  );
  await h.submit();
  assert.deepEqual(h.actions.request, { url: '/api/reports/generate/stream', payload: originalInput });
  assert.equal(h.actions.save, 1);
  assert.equal(h.actions.open.length, 0);
  assert.equal(h.location.hash, '#dashboard');
  assert.equal(h.state().reports.length, 1);
  assert.equal(h.state().reports[0].thinking, report.thinking);
  assert.equal(h.state().generation.phase, 'complete');
  assert.equal(h.state().generation.statuses[0].message, '테스트 서버 상태');
});

test('Server errors retain actual thinking and original input without saving a report', async () => {
  const h = generationHarness(event('thinking', { text: '중단 전 원문' }) + event('error', { message: 'Ollama 테스트 오류' }));
  await h.submit();
  assert.equal(h.actions.save, 0);
  assert.equal(h.state().reports.length, 0);
  assert.equal(h.state().generation.phase, 'error');
  assert.equal(h.state().generation.thinking, '중단 전 원문');
  assert.equal(h.state().generationError, 'Ollama 테스트 오류');
  assert.deepEqual({ ...h.state().editorDraft }, originalInput);
  assert.equal(h.form.elements.input_data.value, originalInput.input_data);
});

test('Premature EOF retains received thinking and inputs and rejects report completion', async () => {
  const h = generationHarness(event('thinking', { text: '불완전한 스트림' }));
  await h.submit();
  assert.equal(h.actions.save, 0);
  assert.equal(h.actions.open.length, 0);
  assert.equal(h.state().reports.length, 0);
  assert.match(h.state().generationError, /최종 보고서를/);
  assert.equal(h.state().generation.thinking, '불완전한 스트림');
  assert.deepEqual({ ...h.state().editorDraft }, originalInput);
});

test('Completion without thinking keeps the log empty and preserves the create-page success flow', async () => {
  const h = generationHarness(event('result', { report: { ...report, thinking: '' } }), 'create');
  await h.submit();
  assert.equal(h.state().generation.phase, 'complete');
  assert.equal(h.state().generation.thinking, '');
  assert.equal(h.state().reports[0].thinking, '');
  assert.equal(h.actions.save, 1);
  assert.deepEqual(h.actions.open, ['RPT-TEST']);
  assert.equal(h.location.hash, 'reports');
});

test('Malformed final reports never save or discard the user draft', async () => {
  const h = generationHarness(event('result', {
    report: { ...report, findings: [{ classification: 'INFORMATIONAL', evidence: 'invalid' }] },
  }));
  await h.submit();
  assert.equal(h.actions.save, 0);
  assert.equal(h.actions.open.length, 0);
  assert.equal(h.state().reports.length, 0);
  assert.equal(h.state().generation.phase, 'error');
  assert.deepEqual({ ...h.state().editorDraft }, originalInput);
});

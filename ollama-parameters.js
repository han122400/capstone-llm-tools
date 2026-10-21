// These are application input limits, not universal Ollama or model limits.
export const ollamaParameters = {
  temperature: { label: '온도', min: 0, max: 2, step: 'any', initial: 0.1, recommended: '0.1', description: '낮을수록 출력의 다양성이 줄어듭니다.', guide: '정형 보고서는 0.1부터 시작하세요. 높은 값은 출력의 변동을 늘립니다.' },
  num_ctx: { label: '컨텍스트 크기', min: 512, max: 131072, step: 1, initial: 16384, recommended: '16,384', unit: '토큰', description: '긴 입력과 생성에 사용할 문맥 공간입니다.', guide: '16,384부터 시작하세요. 값을 늘릴수록 메모리 사용량이 커지며, 실제 한도는 모델과 RAM·VRAM에 따라 달라집니다.' },
  num_predict: { label: '최대 생성 토큰', min: 1, max: 32768, step: 1, initial: 4096, recommended: '4,096', unit: '토큰', description: '생각 로그와 보고서의 생성 길이를 제한합니다.', guide: '4,096부터 시작하세요. 너무 작으면 JSON 보고서가 완성되기 전에 끊길 수 있고, 큰 값은 생성 시간을 늘릴 수 있습니다.' },
  top_p: { label: '출력 후보 확률', min: 0, max: 1, step: 'any', initial: 0.95, recommended: '0.95', description: '누적 확률로 출력 후보의 범위를 조절합니다.', guide: '0.95부터 시작하세요. 낮추면 후보가 줄고, 높이면 출력의 다양성이 늘어납니다.' },
  repeat_penalty: { label: '반복 페널티', min: 0, max: 10, step: 'any', initial: 1, recommended: '1.0', description: '같은 표현이 반복되는 정도를 조절합니다.', guide: '1.0부터 시작하세요. 반복이 심하면 조금씩 높이세요. 과도한 값은 필요한 반복 표현에도 영향을 줄 수 있습니다.' },
  seed: { label: '시드', min: 0, max: 2147483647, step: 1, optional: true, initial: 42, recommended: '예: 42', description: '같은 설정의 결과를 비교할 때 사용합니다.', guide: '고정하면 같은 숫자를 사용해 결과를 비교할 수 있습니다. 해제하면 앱에서 seed를 지정하지 않습니다. 완전히 동일한 결과를 보장하는 설정은 아닙니다.' },
  top_k: { label: '출력 후보 수', min: 0, max: 2000, step: 1, optional: true, initial: 40, recommended: '40', description: '출력 후보의 개수를 추가로 조절합니다.', guide: '필요할 때 40부터 시작하세요. 낮추면 후보가 줄고, 높이면 다양성이 늘어납니다. 비워두면 모델 기본값을 사용합니다.' },
};

// Commands inside SYSTEM are prompt text and must never be edited as parameters.
function commands(text) {
  const result = [];
  let multiline = false;
  for (const match of text.matchAll(/([^\r\n]*)(\r\n|\n|\r|$)/g)) {
    const line = match[1];
    if (multiline) { if (line.includes('"""')) multiline = false; continue; }
    const system = line.match(/^\s*SYSTEM\s+(.*)$/i)?.[1];
    if (system != null) {
      result.push({ command: 'SYSTEM', start: match.index });
      if (system.startsWith('"""') && !system.slice(3).includes('"""')) multiline = true;
      continue;
    }
    const parameter = line.match(/^([ \t]*PARAMETER[ \t]+)(\S+)([ \t]+)(.*?)([ \t]*)$/i);
    if (!parameter) continue;
    const valueStart = match.index + parameter[1].length + parameter[2].length + parameter[3].length;
    result.push({ command: 'PARAMETER', name: parameter[2].toLowerCase(), value: parameter[4], valueStart, valueEnd: valueStart + parameter[4].length, start: match.index, end: match.index + match[0].length });
  }
  return result;
}

export function modelfileParameterValues(text) {
  const values = {};
  for (const item of commands(text)) {
    if (item.command !== 'PARAMETER' || Object.hasOwn(values, item.name)) continue;
    let value = item.value;
    if (value.startsWith('"')) {
      try { const decoded = JSON.parse(value); if (typeof decoded === 'string') value = decoded; } catch { /* Leave invalid text for validation. */ }
    }
    values[item.name] = value;
  }
  return values;
}

export function parameterInputValue(name, value) {
  const spec = ollamaParameters[name];
  if (value == null) return spec.optional ? '' : String(spec.initial);
  const number = Number(value);
  return /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value.trim()) && Number.isFinite(number) ? String(number) : '';
}

export function replaceModelfileParameter(text, name, value) {
  if (!Object.hasOwn(ollamaParameters, name)) throw new Error('지원하지 않는 설정입니다.');
  const lines = commands(text);
  const matching = lines.filter(item => item.command === 'PARAMETER' && item.name === name);
  if (value == null) {
    for (const item of matching.reverse()) text = text.slice(0, item.start) + text.slice(item.end);
    return text;
  }
  const current = matching[0];
  if (current) {
    const encoded = current.value.startsWith('"') && current.value.endsWith('"') ? JSON.stringify(String(value)) : String(value);
    return text.slice(0, current.valueStart) + encoded + text.slice(current.valueEnd);
  }
  const newline = text.match(/\r\n|\n|\r/)?.[0] || '\n';
  const position = lines.find(item => item.command === 'SYSTEM')?.start ?? text.length;
  const prefix = text.slice(0, position);
  return prefix + (prefix && !/[\r\n]$/.test(prefix) ? newline : '') + `PARAMETER ${name} ${value}${newline}` + text.slice(position);
}

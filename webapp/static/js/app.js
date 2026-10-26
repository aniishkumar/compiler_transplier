(() => {
  const $ = (id) => document.getElementById(id);
  const sourceLanguage = $('source-language');
  const targetLanguage = $('target-language');
  const sourceCode = $('source-code');
  const generatedCode = $('generated-code');
  const notice = $('notice');
  const pipelineEl = $('pipeline');
  const labels = { c: 'C', python: 'Python', javascript: 'JavaScript' };
  const phaseDefinitions = [
    ['preprocessing', 'Preprocessing', 'Normalize accepted source conventions and handle supported C headers.'],
    ['lexical', 'Lexical Analysis', 'Turn source characters into positioned tokens such as names, literals, and operators.'],
    ['syntax', 'Syntax Analysis', 'Check token order against the supported grammar and build the program structure.'],
    ['ast', 'AST Construction', 'Show the parsed program as a tree of statements and expressions.'],
    ['semantic', 'Semantic Analysis', 'Check supported declarations, names, arrays, constants, and function calls.'],
    ['ir', 'Intermediate Representation', 'Lower the AST into language-neutral operations used by target code generation.'],
    ['generation', 'Code Generation', 'Render the intermediate operations as source code in the selected target language.'],
    ['validation', 'Validation', 'Check generated target syntax when the required validator is installed; do not execute it.']
  ];
  const phaseDescriptions = Object.fromEntries(phaseDefinitions.map(([id, , description]) => [id, description]));
  let examples = [];
  let currentResult = null;
  let testing = false;

  const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[char]);

  function highlight(text) {
    const pattern = /(\/\/[^\n]*|#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b(?:int|float|double|char|bool|void|string|let|const|var|if|else|while|function|def|return|print|True|False|true|false|null|None|and|or|not)\b|[+*/%<>=!&|^-]+)/g;
    let html = ''; let cursor = 0; let match;
    while ((match = pattern.exec(text)) !== null) {
      html += escapeHtml(text.slice(cursor, match.index));
      const token = match[0];
      let cls = 'tok-op';
      if (/^(\/\/|#)/.test(token)) cls = 'tok-comment';
      else if (/^["']/.test(token)) cls = 'tok-string';
      else if (/^\d/.test(token)) cls = 'tok-number';
      else if (/^[A-Za-z]/.test(token)) cls = 'tok-key';
      html += `<span class="${cls}">${escapeHtml(token)}</span>`;
      cursor = pattern.lastIndex;
    }
    html += escapeHtml(text.slice(cursor));
    return html + (text.endsWith('\n') ? ' ' : '');
  }

  function updateEditor(editorId, text, language) {
    const editor = $(editorId); const wrap = $(editorId === 'source-code' ? 'source-editor' : 'output-editor');
    const lines = Math.max(1, text.split('\n').length);
    wrap.querySelector('.line-gutter').textContent = Array.from({ length: lines }, (_, i) => i + 1).join('\n');
    wrap.querySelector('.highlight-layer code').innerHTML = highlight(text);
    if (editorId === 'source-code') {
      $('source-count').textContent = `${lines} ${lines === 1 ? 'line' : 'lines'} · ${text.length.toLocaleString()} characters`;
      $('source-mode').textContent = labels[language];
    } else {
      $('output-count').textContent = text ? `${lines} ${lines === 1 ? 'line' : 'lines'} · ${text.length.toLocaleString()} characters` : 'Ready to translate';
      $('target-mode').textContent = labels[language];
    }
  }

  function syncScroll(editorId) {
    const editor = $(editorId); const wrap = $(editorId === 'source-code' ? 'source-editor' : 'output-editor');
    const highlightLayer = wrap.querySelector('.highlight-layer');
    const gutter = wrap.querySelector('.line-gutter');
    editor.addEventListener('scroll', () => { highlightLayer.scrollTop = editor.scrollTop; highlightLayer.scrollLeft = editor.scrollLeft; gutter.scrollTop = editor.scrollTop; });
  }

  function setNotice(message, type = 'success') {
    notice.textContent = message; notice.className = `notice ${type}`; notice.hidden = !message;
  }

  function setBusy(busy) {
    testing = busy;
    $('transpile').disabled = busy;
    $('run-matrix').disabled = busy;
    $('transpile').innerHTML = busy ? '<span class="spinner" aria-hidden="true"></span> Translating…' : '<span class="play-icon">▶</span> Transpile Code';
  }

  function pretty(value) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2); }

  function phaseState(status) {
    if (status === 'completed') return 'Completed';
    if (status === 'completed_with_warnings') return 'Completed with warnings';
    if (status === 'failed') return 'Failed';
    if (status === 'pending' || status === 'running') return 'Pending';
    return 'Not Run';
  }

  function renderPipeline(phases = []) {
    pipelineEl.replaceChildren();
    phases.forEach((phase, index) => {
      const button = document.createElement('button');
      const description = phase.description || phaseDescriptions[phase.id] || 'Compiler phase.';
      const stateLabel = phaseState(phase.status);
      button.type = 'button'; button.className = 'pipeline-step'; button.dataset.status = phase.status || 'not_reached';
      button.setAttribute('aria-pressed', 'false');
      const name = phase.name || phase.id || 'Compiler phase';
      button.setAttribute('aria-label', `Phase ${index + 1}. ${name}: ${stateLabel}. ${description}`);
      button.title = description;
      button.innerHTML = `<div class="step-top"><span class="step-index">${String(index + 1).padStart(2, '0')}</span><span class="step-state">${escapeHtml(stateLabel)}</span></div><h3>${escapeHtml(name)}</h3>`;
      button.addEventListener('click', () => selectPhase(phase, button, index + 1));
      pipelineEl.append(button);
    });
  }

  const astStmtLabels = {
    group: 'Statement Group', decl: 'Variable Declaration', array_decl: 'Array Declaration', assign: 'Assignment',
    array_assign: 'Array Element Assignment', compound_assign: 'Compound Assignment', print: 'Output Statement',
    if: 'Conditional', while: 'While Loop', for: 'For Loop', function: 'Function Definition',
    return: 'Return Statement', call: 'Function Call'
  };
  const astExprLabels = {
    literal: 'Literal', char: 'Character Literal', name: 'Variable', binary: 'Binary Expression',
    unary: 'Unary Expression', call: 'Function Call', array: 'Array Literal', index: 'Array Access',
    params: 'Parameters', update: 'Loop Update', for_init: 'Loop Initialization', operator: 'Operator'
  };

  function astLines(node, depth = 0, forcedLabel = null) {
    const pad = '  '.repeat(depth);
    if (Array.isArray(node)) return node.flatMap((child) => astLines(child, depth));
    if (!node || typeof node !== 'object') return [`${pad}${String(node ?? '—')}`];
    const isProgram = Array.isArray(node.body) && !node.kind;
    const isStatement = Boolean(node.kind && ('exprs' in node || 'otherwise' in node || node.kind === 'group'));
    const label = forcedLabel || (isProgram ? 'Program' : isStatement ? astStmtLabels[node.kind] || node.kind : astExprLabels[node.kind] || node.kind || 'Node');
    const details = [];
    if (node.value !== null && node.value !== undefined && !['group','params','array','for_init'].includes(node.kind)) details.push(String(node.value));
    if (node.declared_type) details.push(`type: ${node.declared_type}`);
    if (node.line) details.push(`line ${node.line}`);
    const lines = [`${pad}${label}${details.length ? ` — ${details.join(' · ')}` : ''}`];
    if (node.kind === 'params') {
      const types = Array.isArray(node.value) ? node.value : [];
      (node.children || []).forEach((name, index) => lines.push(`${'  '.repeat(depth + 1)}Parameter: ${name}${types[index] ? ` (${types[index]})` : ''}`));
      return lines;
    }
    if (isProgram) {
      (node.body || []).forEach((child) => lines.push(...astLines(child, depth + 1)));
      return lines;
    }
    if (Array.isArray(node.exprs) && node.exprs.length) {
      const role = node.kind === 'function' ? 'Parameters' : node.kind === 'if' ? 'Condition' : node.kind === 'while' ? 'Condition' : node.kind === 'for' ? 'Loop Parts' : 'Expression';
      node.exprs.forEach((child, index) => lines.push(...astLines(child, depth + 1, `${role}${node.exprs.length > 1 ? ` ${index + 1}` : ''}`)));
    }
    if (Array.isArray(node.children) && node.children.length) node.children.forEach((child) => lines.push(...astLines(child, depth + 1)));
    if (Array.isArray(node.body) && node.body.length) {
      lines.push(`${'  '.repeat(depth + 1)}Body`);
      node.body.forEach((child) => lines.push(...astLines(child, depth + 2)));
    }
    if (Array.isArray(node.otherwise) && node.otherwise.length) {
      lines.push(`${'  '.repeat(depth + 1)}Else`);
      node.otherwise.forEach((child) => lines.push(...astLines(child, depth + 2)));
    }
    return lines;
  }

  function astCompact(node) {
    if (!node || typeof node !== 'object') return String(node ?? '—');
    if (!node.kind) return 'Program';
    const statement = astStmtLabels[node.kind];
    const expression = astExprLabels[node.kind] || node.kind;
    const label = statement || expression;
    const named = ['function','decl','array_decl','assign','array_assign','compound_assign','name','call','index'].includes(node.kind) && node.value != null ? ` ${node.value}` : '';
    if (node.kind === 'binary') return `BinaryExpression(${node.value}: ${astCompact(node.children?.[0])}, ${astCompact(node.children?.[1])})`;
    if (node.kind === 'literal' || node.kind === 'char') return `${label}(${node.value})`;
    if (node.kind === 'name') return `Variable(${node.value})`;
    const expressions = Array.isArray(node.exprs) ? node.exprs : [];
    const primary = expressions.length ? ` ← ${expressions.slice(0, 2).map(astCompact).join(', ')}` : '';
    const count = Array.isArray(node.body) && node.body.length ? ` [${node.body.length} body statement(s)]` : '';
    return `${label}${named}${primary}${count}`;
  }

  const irLabels = {
    DECLARE_VARIABLE: 'Declare variable', DECLARE_ARRAY: 'Declare integer array', ASSIGN_VARIABLE: 'Assign variable',
    COMPOUND_ASSIGN: 'Compound assignment', WRITE_INDEX: 'Write array element', OUTPUT: 'Output', BRANCH: 'Conditional branch',
    LOOP_WHILE: 'While loop', LOOP_FOR: 'Counted loop', FUNCTION: 'Function', RETURN: 'Return', CALL_STATEMENT: 'Call function',
    CONSTANT: 'Constant', READ_VARIABLE: 'Read variable', BINARY_OPERATION: 'Binary operation', UNARY_OPERATION: 'Unary operation',
    CALL: 'Call function', ARRAY_LITERAL: 'Array literal', READ_INDEX: 'Read array element', UPDATE: 'Update',
    INITIALIZE_LOOP_VARIABLE: 'Initialize loop variable', OPERATOR: 'Operator', SEQUENCE: 'Instruction sequence'
  };

  function irLines(node, depth = 0, role = null) {
    const pad = '  '.repeat(depth);
    if (Array.isArray(node)) return node.flatMap((child) => irLines(child, depth));
    if (!node || typeof node !== 'object') return [`${pad}${String(node ?? '—')}`];
    const op = node.op;
    let title = irLabels[op] || op || 'IR node';
    if (node.name) title += ` ${node.name}`;
    if (node.variable) title += ` ${node.variable}`;
    if (node.array) title += ` ${node.array}`;
    if (node.function) title += ` ${node.function}()`;
    if (node.operator) title += ` [${node.operator}]`;
    if (node.type) title += ` : ${node.type}`;
    if (node.literal_kind === 'literal' || node.literal_kind === 'char') title += ` ${node.value}`;
    if (role) title = `${role}: ${title}`;
    if (node.line) title += ` · line ${node.line}`;
    const lines = [`${pad}${title}`];
    const childFields = [
      ['initializer','Initializer'], ['value','Value'], ['left','Left operand'], ['right','Right operand'],
      ['operand','Operand'], ['condition','Condition'], ['index','Index'], ['update','Update'],
      ['arguments','Arguments'], ['elements','Elements'], ['instructions','Instructions'], ['parameters','Parameters'],
      ['then','Then'], ['else','Else'], ['body','Body']
    ];
    for (const [key, label] of childFields) {
      const value = node[key];
      if (value === null || value === undefined) continue;
      if (Array.isArray(value)) {
        if (!value.length) continue;
        lines.push(`${'  '.repeat(depth + 1)}${label}`);
        value.forEach((child) => lines.push(...irLines(child, depth + 2)));
      } else if (typeof value === 'object') lines.push(...irLines(value, depth + 1, label));
      else if (key === 'value') lines.push(`${'  '.repeat(depth + 1)}Value: ${value}`);
    }
    if (node.declares_variable !== undefined) lines.push(`${'  '.repeat(depth + 1)}Declares variable: ${node.declares_variable ? 'yes' : 'no'}`);
    if (node.style) lines.push(`${'  '.repeat(depth + 1)}Output style: ${node.style}`);
    return lines;
  }

  function semanticLines(report) {
    if (!report || typeof report !== 'object') return pretty(report);
    const lines = [report.status === 'passed_with_warnings' ? 'Semantic checks passed with warnings.' : 'Supported semantic checks passed.', report.message || ''];
    const checks = Array.isArray(report.checks) ? report.checks : [];
    const symbols = Array.isArray(report.symbols) ? report.symbols : [];
    const functions = Array.isArray(report.functions) ? report.functions : [];
    const warnings = Array.isArray(report.warnings) ? report.warnings : [];
    if (checks.length) lines.push('', 'Checks performed:', ...checks.map((check) => `  ✓ ${check}`));
    lines.push('', 'Variables:');
    if (symbols.length) symbols.forEach((symbol) => lines.push(`  ${symbol.name || 'unnamed'} — ${symbol.type || 'type not inferred'} (${symbol.kind || 'symbol'}${symbol.line ? `, line ${symbol.line}` : ''})`));
    else lines.push('  No variable declarations were recorded.');
    lines.push('', 'Functions:');
    if (functions.length) functions.forEach((fn) => {
      const params = (Array.isArray(fn.parameters) ? fn.parameters : []).map((param) => `${param.name || 'parameter'}: ${param.type || 'not declared'}`).join(', ') || 'no parameters';
      lines.push(`  ${fn.name || 'unnamed'}(${params}) → ${fn.return_type || 'not declared'}${fn.line ? ` (line ${fn.line})` : ''}`);
    });
    else lines.push('  No function definitions were recorded.');
    if (warnings.length) lines.push('', 'Warnings:', ...warnings.map((warning) => `  ⚠ ${warning}`));
    return lines.filter((line) => line !== undefined).join('\n');
  }

  function renderPhaseOutput(phase) {
    const output = phase.output;
    if (output === null || output === undefined) return 'This phase did not run for the current input.';
    if (phase.status === 'failed' && output.message) {
      return `${output.category || phase.name} error${output.line ? ` on line ${output.line}` : ''}${output.column ? `, column ${output.column}` : ''}: ${output.message}`;
    }
    if (phase.id === 'ast' && output.tree) {
      const lines = [output.explanation || 'AST: program structure as a tree.', '', 'AST tree:', ...astLines(output.tree)];
      if (output.example?.node) lines.push('', 'Example mapping:', `  ${output.example.source}`, `  → ${astCompact(output.example.node)}`);
      return lines.join('\n');
    }
    if (phase.id === 'semantic' && typeof output === 'object') return semanticLines(output);
    if (phase.id === 'ir' && Array.isArray(output.body)) return [
      `IR v${output.ir_version} · source dialect metadata: ${output.source_language || 'unspecified'}`,
      'Each named operation is an input to the existing target generator.',
      '', 'Instruction tree:', ...output.body.flatMap((instruction) => irLines(instruction))
    ].join('\n');
    if (phase.id === 'generation' && typeof output === 'string') return output;
    return pretty(output);
  }

  function selectPhase(phase, button, number) {
    pipelineEl.querySelectorAll('.pipeline-step').forEach((step) => { step.classList.remove('selected'); step.setAttribute('aria-pressed', 'false'); });
    if (button) { button.classList.add('selected'); button.setAttribute('aria-pressed', 'true'); }
    const name = phase.name || phase.id || 'Compiler phase';
    $('phase-title').textContent = `Phase ${String(number).padStart(2, '0')} — ${name}`;
    $('phase-description').textContent = phase.description || phaseDescriptions[phase.id] || 'Compiler phase.';
    const state = phaseState(phase.status);
    const badge = $('phase-status'); badge.textContent = state;
    badge.className = 'phase-badge ' + (phase.status === 'completed' ? 'good' : phase.status === 'failed' ? 'bad' : phase.status === 'completed_with_warnings' ? 'warn' : phase.status === 'pending' ? 'pending' : 'neutral');
    $('phase-output').textContent = renderPhaseOutput(phase);
    $('phase-output').dataset.phase = phase.id;
  }

  function pendingPhases() {
    return phaseDefinitions.map(([id, name, description]) => ({ id, name, description, status: 'pending', output: null }));
  }

  function resetAfterInput(message = 'Source or target changed. Run a new conversion to refresh the result.') {
    currentResult = null; generatedCode.value = '';
    updateEditor('output-code', '', targetLanguage.value);
    $('copy-code').disabled = true; $('download-code').disabled = true;
    renderPipeline(pendingPhases().map((phase) => ({ ...phase, status: 'not_reached' })));
    $('pipeline-summary').textContent = 'Run a conversion to inspect the phases';
    $('phase-title').textContent = 'Select a phase'; $('phase-description').textContent = 'Choose a phase to learn its purpose and inspect its result.';
    $('phase-status').textContent = 'Not Run'; $('phase-status').className = 'phase-badge neutral';
    $('phase-output').textContent = 'Phase outputs will be available after a conversion.';
    setNotice(message, message ? 'warning' : 'success');
  }

  function setConversion(result) {
    currentResult = result;
    generatedCode.value = result.success ? (result.generated_code || '') : '';
    updateEditor('output-code', generatedCode.value, targetLanguage.value);
    const canCopy = Boolean(generatedCode.value);
    $('copy-code').disabled = !canCopy; $('download-code').disabled = !canCopy;
    const phases = Array.isArray(result.phases) ? result.phases : [];
    renderPipeline(phases);
    $('pipeline-summary').textContent = result.success ? (result.warnings?.length ? 'Translation completed with warnings' : 'All reached phases completed') : `Stopped in ${result.error?.phase || 'request'}`;
    const failedIndex = phases.findIndex((phase) => phase.status === 'failed');
    const selectedIndex = failedIndex >= 0 ? failedIndex : Math.max(0, phases.length - 1);
    if (phases.length) selectPhase(phases[selectedIndex], pipelineEl.children[selectedIndex], selectedIndex + 1);
    if (!result.success) setNotice(`${result.error?.category || 'Compiler'} error${result.error?.line ? ` on line ${result.error.line}` : ''}: ${result.error?.message || 'Translation failed.'}`, 'error');
    else if (result.warnings?.length) setNotice(result.warnings.join(' '), 'warning');
    else {
      const validation = phases.find((phase) => phase.id === 'validation')?.output;
      setNotice(validation?.status === 'unavailable' ? 'Translation completed. No target syntax checker is installed.' : 'Translation completed and generated target syntax passed validation.', validation?.status === 'unavailable' ? 'warning' : 'success');
    }
  }

  async function jsonRequest(url, payload) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    let data;
    try { data = await response.json(); } catch { throw new Error(`Server returned HTTP ${response.status} without a JSON response.`); }
    if (!response.ok && !data.error) throw new Error(data.error?.message || `Request failed (HTTP ${response.status}).`);
    return data;
  }

  async function transpile() {
    if (testing) return;
    setBusy(true); setNotice(''); generatedCode.value = ''; currentResult = null;
    updateEditor('output-code', '', targetLanguage.value);
    $('copy-code').disabled = true; $('download-code').disabled = true;
    const pending = pendingPhases(); renderPipeline(pending); $('pipeline-summary').textContent = 'Translation in progress';
    try {
      const result = await jsonRequest('/api/transpile', { source_language: sourceLanguage.value, target_language: targetLanguage.value, source_code: sourceCode.value });
      setConversion(result);
    } catch (error) {
      resetAfterInput(''); $('pipeline-summary').textContent = 'Request failed before compiler phases completed';
      setNotice(error.message, 'error');
    } finally { setBusy(false); }
  }

  async function runMatrix() {
    if (testing) return;
    setBusy(true); setNotice('Running the nine sample translation and syntax checks…');
    try {
      const response = await fetch('/api/test-matrix', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || `Request failed (HTTP ${response.status}).`);
      const skipped = data.skipped ? `, ${data.skipped} unavailable` : '';
      setNotice(`${data.passed}/9 routes passed, ${data.failed} failed${skipped}. Sample programs were not executed.`, data.failed ? 'error' : data.skipped ? 'warning' : 'success');
    } catch (error) { setNotice(`Matrix check failed: ${error.message}`, 'error'); }
    finally { setBusy(false); }
  }

  async function loadExamples() {
    try {
      const response = await fetch('/api/examples');
      if (!response.ok) throw new Error('Examples unavailable');
      examples = await response.json();
      $('example-select').innerHTML = '<option value="">Examples</option>' + examples.map((example) => `<option value="${escapeHtml(example.id)}">${escapeHtml(example.name)}</option>`).join('');
    } catch { $('example-select').innerHTML = '<option value="">Examples unavailable</option>'; }
  }

  function loadSelectedExample() {
    const example = examples.find((item) => item.id === $('example-select').value);
    if (!example) { setNotice('Choose a sample program first.', 'warning'); return; }
    resetAfterInput('Example loaded. Run a conversion to generate fresh output.');
    sourceLanguage.value = example.language; sourceCode.value = example.source_code;
    updateEditor('source-code', sourceCode.value, sourceLanguage.value); setNotice(example.description, 'success'); sourceCode.focus();
  }

  async function copyCode() {
    try { await navigator.clipboard.writeText(generatedCode.value); setNotice('Generated code copied to clipboard.', 'success'); }
    catch { generatedCode.focus(); generatedCode.select(); document.execCommand('copy'); setNotice('Generated code copied.', 'success'); }
  }

  function downloadCode() {
    const extensions = { c: 'c', python: 'py', javascript: 'js' };
    const blob = new Blob([generatedCode.value], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = `transpiled.${extensions[targetLanguage.value]}`; link.click(); URL.revokeObjectURL(url);
  }

  async function checkHealth() {
    const pill = $('backend-status');
    try {
      const response = await fetch('/api/health'); const data = await response.json();
      const available = response.ok && data.available === true;
      pill.className = available ? 'status-pill online' : 'status-pill offline'; pill.innerHTML = `<b></b> <span>${available ? 'Compiler available' : 'Backend unavailable'}</span>`;
    } catch { pill.className = 'status-pill offline'; pill.innerHTML = '<b></b> Backend unavailable'; }
  }

  sourceCode.addEventListener('input', () => { resetAfterInput('Source changed. Run a new conversion to refresh the result.'); updateEditor('source-code', sourceCode.value, sourceLanguage.value); });
  sourceLanguage.addEventListener('change', () => { resetAfterInput(); updateEditor('source-code', sourceCode.value, sourceLanguage.value); });
  targetLanguage.addEventListener('change', () => { resetAfterInput(); updateEditor('output-code', generatedCode.value, targetLanguage.value); });
  $('transpile').addEventListener('click', transpile);
  $('run-matrix').addEventListener('click', runMatrix);
  $('load-example').addEventListener('click', loadSelectedExample);
  $('clear-source').addEventListener('click', () => { resetAfterInput('Source cleared.'); sourceCode.value = ''; updateEditor('source-code', '', sourceLanguage.value); sourceCode.focus(); });
  $('clear-output').addEventListener('click', () => { generatedCode.value = ''; updateEditor('output-code', '', targetLanguage.value); $('copy-code').disabled = true; $('download-code').disabled = true; });
  $('copy-code').addEventListener('click', copyCode);
  $('download-code').addEventListener('click', downloadCode);
  $('swap-languages').addEventListener('click', () => { const source = sourceLanguage.value; resetAfterInput(); sourceLanguage.value = targetLanguage.value; targetLanguage.value = source; updateEditor('source-code', sourceCode.value, sourceLanguage.value); updateEditor('output-code', generatedCode.value, targetLanguage.value); });
  sourceCode.addEventListener('keydown', (event) => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); transpile(); } });
  syncScroll('source-code'); syncScroll('generated-code');
  updateEditor('source-code', sourceCode.value, sourceLanguage.value); updateEditor('output-code', generatedCode.value, targetLanguage.value);
  renderPipeline(pendingPhases().map((phase) => ({ ...phase, status: 'not_reached' })));
  loadExamples(); checkHealth();
})();

(() => {
  const alertsRoot = document.getElementById('alerts');
  if (!alertsRoot) return;

  const isStaticDemo = !['localhost', '127.0.0.1'].includes(window.location.hostname);
  const apiBase = `${window.location.protocol}//${window.location.hostname}:8091`;

  const actionLabels = {
    manual_review: '人工复核',
    step_up_auth: '升级验证',
    block_recommended: '建议拦截',
    allow_with_monitoring: '放行并监控'
  };

  const actionTakenMap = {
    manual_review: 'manual_review',
    step_up_auth: 'step_up_auth',
    block_recommended: 'blocked',
    allow_with_monitoring: 'allowed'
  };

  const drawer = document.createElement('aside');
  drawer.className = 'copilot-drawer';
  drawer.id = 'copilotDrawer';
  drawer.setAttribute('aria-live', 'polite');
  drawer.innerHTML = `
    <div class="copilot-head">
      <div>
        <small>AI RISK COPILOT</small>
        <h2>告警调查助手</h2>
      </div>
      <button type="button" id="copilotClose" aria-label="关闭">×</button>
    </div>
    <p class="copilot-status" id="copilotStatus">选择一条告警开始分析</p>
    <div class="copilot-body" id="copilotBody"></div>
  `;
  document.body.appendChild(drawer);

  document.getElementById('copilotClose').addEventListener('click', () => {
    drawer.classList.remove('open');
  });

  function visibleAlerts() {
    if (!dashboardData || !Array.isArray(dashboardData.alerts)) return [];
    const rows = selectedRule === 'ALL'
      ? dashboardData.alerts
      : dashboardData.alerts.filter(alert => alert.rule_id === selectedRule);
    return rows.slice(0, 16);
  }

  function addListSection(parent, title, values) {
    if (!Array.isArray(values) || !values.length) return;
    const section = document.createElement('section');
    const heading = document.createElement('h3');
    heading.textContent = title;
    section.appendChild(heading);
    const list = document.createElement('ul');
    values.forEach(value => {
      const item = document.createElement('li');
      item.textContent = String(value);
      list.appendChild(item);
    });
    section.appendChild(list);
    parent.appendChild(section);
  }

  async function submitFeedback(requestId, feedback, controls) {
    [...controls.querySelectorAll('button')].forEach(button => { button.disabled = true; });
    const state = controls.querySelector('.copilot-feedback-state');
    state.textContent = '正在记录人工判定…';
    try {
      const response = await fetch(`${apiBase}/v1/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, ...feedback })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.textContent = '人工判定已写入审计记录，可用于后续质量评测。';
      state.classList.add('saved');
    } catch (error) {
      state.textContent = `反馈保存失败，可重试（${error.name || 'Error'}）。`;
      [...controls.querySelectorAll('button')].forEach(button => { button.disabled = false; });
    }
  }

  function renderFeedbackControls(parent, requestId, explanation) {
    if (!requestId || isStaticDemo) return;
    const controls = document.createElement('section');
    controls.className = 'copilot-feedback';
    const heading = document.createElement('h3');
    heading.textContent = '人工处置反馈';
    controls.appendChild(heading);

    const hint = document.createElement('p');
    hint.textContent = '反馈不会改变实时规则结果，只用于审计和评测 AI 建议质量。';
    controls.appendChild(hint);

    const grid = document.createElement('div');
    grid.className = 'copilot-feedback-grid';
    const recommendation = explanation.recommended_action || 'manual_review';
    const options = [
      {
        label: '确认风险并采纳',
        payload: {
          verdict: 'true_positive',
          accepted_recommendation: true,
          action_taken: actionTakenMap[recommendation] || 'manual_review'
        }
      },
      {
        label: '确认风险但改判',
        payload: {
          verdict: 'true_positive',
          accepted_recommendation: false,
          action_taken: 'escalated'
        }
      },
      {
        label: '判定为误报',
        payload: {
          verdict: 'false_positive',
          accepted_recommendation: false,
          action_taken: 'allowed'
        }
      },
      {
        label: '信息不足',
        payload: {
          verdict: 'uncertain',
          accepted_recommendation: false,
          action_taken: 'manual_review'
        }
      }
    ];
    options.forEach(option => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = option.label;
      button.addEventListener('click', () => submitFeedback(requestId, option.payload, controls));
      grid.appendChild(button);
    });
    controls.appendChild(grid);

    const state = document.createElement('p');
    state.className = 'copilot-feedback-state';
    state.textContent = `审计请求：${requestId.slice(0, 8)}…`;
    controls.appendChild(state);
    parent.appendChild(controls);
  }

  function renderExplanation(explanation, latencyMs = null, requestId = null) {
    const status = document.getElementById('copilotStatus');
    const body = document.getElementById('copilotBody');
    body.replaceChildren();

    const meta = document.createElement('div');
    meta.className = 'copilot-meta';
    const source = explanation.source || 'unknown';
    const action = actionLabels[explanation.recommended_action] || explanation.recommended_action || '待确认';
    meta.textContent = `${source} · ${action}${latencyMs == null ? '' : ` · ${Number(latencyMs).toFixed(1)} ms`}`;
    body.appendChild(meta);

    const summary = document.createElement('p');
    summary.className = 'copilot-summary';
    summary.textContent = explanation.summary || '暂无摘要';
    body.appendChild(summary);

    if (typeof explanation.confidence === 'number') {
      const confidence = document.createElement('p');
      confidence.className = 'copilot-confidence';
      confidence.textContent = `置信度字段：${Math.round(explanation.confidence * 100)}%（仅作辅助，不代表校准概率）`;
      body.appendChild(confidence);
    }

    addListSection(body, '关键证据', explanation.key_evidence);
    addListSection(body, '调查步骤', explanation.investigation_steps);
    addListSection(body, '限制', explanation.limitations);
    renderFeedbackControls(body, requestId, explanation);

    status.textContent = source === 'llm' ? '模型解释已返回，等待人工判定' : '当前使用可审计降级解释，等待人工判定';
  }

  function staticDemoExplanation(alert) {
    const level = String(alert.risk_level || 'UNKNOWN').toUpperCase();
    const action = alert.rule_id === 'R006'
      ? 'block_recommended'
      : level === 'HIGH' || level === 'CRITICAL'
        ? 'manual_review'
        : 'allow_with_monitoring';
    return {
      summary: `规则 ${alert.rule_id || 'UNKNOWN'} 命中：${alert.reason || alert.rule_name || '风险事件'}。公网版本只展示静态降级路径，不执行模型调用。`,
      recommended_action: action,
      confidence: 0.6,
      key_evidence: [
        `rule_id=${alert.rule_id || 'UNKNOWN'}`,
        `risk_level=${level}`,
        alert.reason || alert.rule_name || '风险规则命中'
      ],
      investigation_steps: [
        '核对原始交易与窗口统计，排除重复或迟到数据影响。',
        '检查关联用户、设备、卡和商户的近期活动。',
        '由人工分析员结合账户历史决定最终处置。'
      ],
      limitations: ['静态 Vercel Demo 不保存模型密钥或人工反馈；本地运行 `make ai` 后可进入完整审计闭环。'],
      source: 'static-demo'
    };
  }

  async function analyze(alert) {
    drawer.classList.add('open');
    const status = document.getElementById('copilotStatus');
    const body = document.getElementById('copilotBody');
    body.replaceChildren();

    if (isStaticDemo) {
      renderExplanation(staticDemoExplanation(alert));
      return;
    }

    status.textContent = '正在生成结构化调查解释…';
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 9000);
    try {
      const response = await fetch(`${apiBase}/v1/explanations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alert, language: 'zh-CN' }),
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      renderExplanation(payload.explanation || {}, payload.latency_ms, payload.request_id);
    } catch (error) {
      status.textContent = 'AI Copilot 当前不可达';
      const message = document.createElement('p');
      message.className = 'copilot-error';
      message.textContent = `请先运行 \`make ai\`。本次请求未影响实时规则检测。(${error.name || 'Error'})`;
      body.appendChild(message);
    } finally {
      window.clearTimeout(timer);
    }
  }

  function decorateAlerts() {
    const rows = [...alertsRoot.querySelectorAll('.alert-item')];
    rows.forEach((row, index) => {
      if (row.querySelector('.copilot-trigger')) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'copilot-trigger';
      button.textContent = 'AI 调查';
      button.addEventListener('click', event => {
        event.stopPropagation();
        const alert = visibleAlerts()[index];
        if (alert) analyze(alert);
      });
      row.appendChild(button);
    });
  }

  new MutationObserver(decorateAlerts).observe(alertsRoot, { childList: true });
  decorateAlerts();
})();

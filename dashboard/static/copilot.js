(() => {
  const alertsRoot = document.getElementById('alerts');
  if (!alertsRoot) return;

  const isStaticDemo = !['localhost', '127.0.0.1'].includes(window.location.hostname);
  const apiUrl = `${window.location.protocol}//${window.location.hostname}:8091/v1/explanations`;

  const actionLabels = {
    manual_review: '人工复核',
    step_up_auth: '升级验证',
    block_recommended: '建议拦截',
    allow_with_monitoring: '放行并监控'
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

  function renderExplanation(explanation, latencyMs = null) {
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

    status.textContent = source === 'llm' ? '模型解释已返回' : '当前使用可审计降级解释';
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
      limitations: ['静态 Vercel Demo 不保存模型密钥；本地运行 `make ai` 后可调用 Copilot API。'],
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
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alert, language: 'zh-CN' }),
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      renderExplanation(payload.explanation || {}, payload.latency_ms);
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

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

  const statusLabels = {
    open: '待处理',
    investigating: '调查中',
    resolved: '已结案'
  };

  const priorityLabels = {
    critical: '紧急',
    high: '高',
    medium: '中',
    low: '低'
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

  const workbench = document.createElement('aside');
  workbench.className = 'case-workbench';
  workbench.id = 'caseWorkbenchDrawer';
  workbench.setAttribute('aria-live', 'polite');
  workbench.innerHTML = `
    <div class="copilot-head">
      <div>
        <small>ANALYST WORKBENCH</small>
        <h2>风险案件工作台</h2>
      </div>
      <button type="button" id="caseWorkbenchClose" aria-label="关闭">×</button>
    </div>
    <div class="case-toolbar">
      <label>分析员标识<input id="caseAnalystRef" maxlength="64" placeholder="例如 analyst-a"></label>
      <label>状态
        <select id="caseStatusFilter">
          <option value="">全部</option>
          <option value="open">待处理</option>
          <option value="investigating">调查中</option>
          <option value="resolved">已结案</option>
        </select>
      </label>
      <label>优先级
        <select id="casePriorityFilter">
          <option value="">全部</option>
          <option value="critical">紧急</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
        </select>
      </label>
      <button type="button" id="caseRefresh">刷新</button>
    </div>
    <div class="case-summary" id="caseSummary"></div>
    <p class="copilot-status" id="caseWorkbenchStatus">案件按优先级和 SLA 到期时间排序</p>
    <div class="case-list" id="caseList"></div>
  `;
  document.body.appendChild(workbench);

  const workbenchLauncher = document.createElement('button');
  workbenchLauncher.type = 'button';
  workbenchLauncher.className = 'case-workbench-launcher';
  workbenchLauncher.id = 'caseWorkbenchLauncher';
  workbenchLauncher.textContent = '案件工作台';
  document.body.appendChild(workbenchLauncher);

  const analystInput = document.getElementById('caseAnalystRef');
  analystInput.value = window.localStorage.getItem('finguardAnalystRef') || '';
  analystInput.addEventListener('change', () => {
    window.localStorage.setItem('finguardAnalystRef', analystInput.value.trim());
  });

  function analystRef() {
    return analystInput.value.trim() || null;
  }

  document.getElementById('copilotClose').addEventListener('click', () => {
    drawer.classList.remove('open');
  });

  document.getElementById('caseWorkbenchClose').addEventListener('click', () => {
    workbench.classList.remove('open');
  });

  workbenchLauncher.addEventListener('click', () => {
    drawer.classList.remove('open');
    workbench.classList.add('open');
    loadCases();
  });

  document.getElementById('caseRefresh').addEventListener('click', loadCases);
  document.getElementById('caseStatusFilter').addEventListener('change', loadCases);
  document.getElementById('casePriorityFilter').addEventListener('change', loadCases);

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

  async function apiRequest(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, options);
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      try {
        error.payload = await response.json();
      } catch (_) {
        error.payload = null;
      }
      throw error;
    }
    return response.json();
  }

  async function submitFeedback(requestId, feedback, controls) {
    [...controls.querySelectorAll('button')].forEach(button => { button.disabled = true; });
    const state = controls.querySelector('.copilot-feedback-state');
    state.textContent = '正在记录人工判定…';
    try {
      await apiRequest('/v1/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, ...feedback })
      });
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
    hint.textContent = '轻量反馈用于模型质量评测；需要持续跟踪时请建立案件。';
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

  function renderCaseCreate(parent, requestId) {
    if (!requestId || isStaticDemo) return;
    const section = document.createElement('section');
    section.className = 'case-create';
    const heading = document.createElement('h3');
    heading.textContent = '持续调查';
    section.appendChild(heading);
    const hint = document.createElement('p');
    hint.textContent = '需要跨时间跟踪、分派或 SLA 管理时，将本次调查升级为案件。';
    section.appendChild(hint);
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '建立风险案件';
    const state = document.createElement('p');
    state.className = 'copilot-feedback-state';
    button.addEventListener('click', async () => {
      button.disabled = true;
      state.textContent = '正在建立案件…';
      try {
        const payload = { request_id: requestId };
        if (analystRef()) payload.assignee_ref = analystRef();
        const record = await apiRequest('/v1/cases', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        state.textContent = `${record.case_id} 已建立 · ${priorityLabels[record.priority]}优先级`;
        button.textContent = '打开案件工作台';
        button.disabled = false;
        button.onclick = () => {
          drawer.classList.remove('open');
          workbench.classList.add('open');
          loadCases();
        };
        refreshCaseSummary();
      } catch (error) {
        state.textContent = `建案失败，可重试（HTTP ${error.status || 'error'}）。`;
        button.disabled = false;
      }
    });
    section.appendChild(button);
    section.appendChild(state);
    parent.appendChild(section);
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
    renderCaseCreate(body, requestId);
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
      limitations: ['静态 Vercel Demo 不保存模型密钥、案件或人工反馈；本地运行 `make ai` 后可进入完整工作流。'],
      source: 'static-demo'
    };
  }

  async function analyze(alert) {
    workbench.classList.remove('open');
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
      const payload = await apiRequest('/v1/explanations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alert, language: 'zh-CN' }),
        signal: controller.signal
      });
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

  function formatTime(value) {
    if (!value) return '--';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', { hour12: false });
  }

  async function patchCase(caseRecord, changes) {
    const actor = analystRef();
    const payload = {
      expected_version: caseRecord.version,
      actor_ref: actor,
      ...changes
    };
    try {
      await apiRequest(`/v1/cases/${caseRecord.case_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      await loadCases();
    } catch (error) {
      const state = document.getElementById('caseWorkbenchStatus');
      if (error.status === 409) {
        state.textContent = '案件已被其他操作更新，已刷新最新版本。';
        await loadCases();
      } else {
        state.textContent = `案件更新失败（HTTP ${error.status || 'error'}）。`;
      }
    }
  }

  function caseActionButton(label, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.addEventListener('click', handler);
    return button;
  }

  function renderCaseCard(caseRecord) {
    const card = document.createElement('article');
    card.className = `case-card priority-${caseRecord.priority}${caseRecord.sla_breached ? ' sla-breached' : ''}`;

    const head = document.createElement('div');
    head.className = 'case-card-head';
    const title = document.createElement('strong');
    title.textContent = `${caseRecord.rule_id || 'UNKNOWN'} · ${caseRecord.case_id}`;
    const badges = document.createElement('span');
    badges.textContent = `${statusLabels[caseRecord.status]} · ${priorityLabels[caseRecord.priority]}`;
    head.appendChild(title);
    head.appendChild(badges);
    card.appendChild(head);

    const meta = document.createElement('p');
    meta.className = 'case-card-meta';
    meta.textContent = `负责人：${caseRecord.assignee_ref || '未分派'} · SLA：${formatTime(caseRecord.due_at)}${caseRecord.sla_breached ? ' · 已超时' : ''}`;
    card.appendChild(meta);

    const decision = document.createElement('p');
    decision.textContent = `AI 建议：${actionLabels[caseRecord.recommended_action] || caseRecord.recommended_action} · 来源：${caseRecord.source}`;
    card.appendChild(decision);

    if (caseRecord.resolution_verdict) {
      const resolution = document.createElement('p');
      resolution.className = 'case-resolution';
      resolution.textContent = `结论：${caseRecord.resolution_verdict} · 实际动作：${caseRecord.action_taken}`;
      card.appendChild(resolution);
    }

    const actions = document.createElement('div');
    actions.className = 'case-actions';
    if (caseRecord.status === 'open') {
      actions.appendChild(caseActionButton('开始调查', () => patchCase(caseRecord, {
        status: 'investigating',
        assignee_ref: analystRef()
      })));
    } else if (caseRecord.status === 'investigating') {
      actions.appendChild(caseActionButton('按建议结案', () => patchCase(caseRecord, {
        status: 'resolved',
        assignee_ref: analystRef() || caseRecord.assignee_ref,
        resolution_verdict: 'true_positive',
        accepted_recommendation: true,
        action_taken: actionTakenMap[caseRecord.recommended_action] || 'manual_review'
      })));
      actions.appendChild(caseActionButton('误报结案', () => patchCase(caseRecord, {
        status: 'resolved',
        assignee_ref: analystRef() || caseRecord.assignee_ref,
        resolution_verdict: 'false_positive',
        accepted_recommendation: false,
        action_taken: 'allowed'
      })));
    } else {
      actions.appendChild(caseActionButton('重新调查', () => patchCase(caseRecord, {
        status: 'investigating',
        assignee_ref: analystRef() || caseRecord.assignee_ref
      })));
    }
    card.appendChild(actions);
    return card;
  }

  async function refreshCaseSummary() {
    if (isStaticDemo) {
      workbenchLauncher.textContent = '案件工作台 · 本地';
      return;
    }
    try {
      const summary = await apiRequest('/v1/cases/summary');
      const active = Number(summary.open_count || 0) + Number(summary.investigating_count || 0);
      workbenchLauncher.textContent = `案件工作台 · ${active}`;
      const root = document.getElementById('caseSummary');
      root.innerHTML = `
        <span>待处理 <b>${summary.open_count}</b></span>
        <span>调查中 <b>${summary.investigating_count}</b></span>
        <span>超 SLA <b>${summary.sla_breached_count}</b></span>
        <span>未分派 <b>${summary.unassigned_count}</b></span>
      `;
    } catch (_) {
      workbenchLauncher.textContent = '案件工作台 · --';
    }
  }

  async function loadCases() {
    const statusRoot = document.getElementById('caseWorkbenchStatus');
    const list = document.getElementById('caseList');
    list.replaceChildren();

    if (isStaticDemo) {
      statusRoot.textContent = '公网静态 Demo 不持久化案件；本地运行 AI Copilot 后可使用案件工作台。';
      return;
    }

    statusRoot.textContent = '正在加载案件…';
    const params = new URLSearchParams();
    const status = document.getElementById('caseStatusFilter').value;
    const priority = document.getElementById('casePriorityFilter').value;
    if (status) params.set('status', status);
    if (priority) params.set('priority', priority);
    params.set('limit', '50');

    try {
      const payload = await apiRequest(`/v1/cases?${params.toString()}`);
      if (!payload.items.length) {
        statusRoot.textContent = '当前筛选条件下暂无案件。';
      } else {
        statusRoot.textContent = `共 ${payload.total} 个案件；列表优先展示高风险与临近 SLA 的案件。`;
        payload.items.forEach(item => list.appendChild(renderCaseCard(item)));
      }
      await refreshCaseSummary();
    } catch (error) {
      statusRoot.textContent = `案件工作台不可达（HTTP ${error.status || 'error'}）。`;
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
  refreshCaseSummary();
})();
const palette = ['#41e8ff', '#6aa8ff', '#72ffb7', '#ffd36a', '#ff5377', '#b38cff'];
const cnFont = '"Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif';
const charts = {};
let dashboardData = null;
let selectedRule = 'ALL';

const filters = {
  risk: 'ALL',
  channel: 'ALL',
  amountPct: 0
};

const riskNameMap = {
  HIGH: '高风险',
  MEDIUM: '中风险',
  LOW: '低风险',
  CRITICAL: '极高风险',
  NO_ALERT: '暂无告警',
  NORMAL: '正常',
  AML_LAUNDERING: '反洗钱命中',
  MODEL_ALERT: '模型告警',
  HIGH_MODEL_SCORE: '模型高分',
  BLACK_DEVICE: '黑名单设备',
  LARGE_AMOUNT: '大额交易'
};

const channelNameMap = {
  APP: '移动端',
  H5: '网页端',
  API: '开放接口',
  POS: '收单终端',
  MINI_PROGRAM: '小程序'
};

const cityNameMap = {
  'San Francisco': '旧金山',
  Frankfurt: '法兰克福',
  Singapore: '新加坡',
  London: '伦敦',
  Paris: '巴黎',
  Tokyo: '东京',
  Sydney: '悉尼',
  Toronto: '多伦多',
  Shanghai: '上海',
  Beijing: '北京',
  AE: '阿联酋',
  NL: '荷兰',
  HK: '香港',
  CH: '瑞士',
  GB: '英国'
};

function cnRisk(value) {
  return riskNameMap[value] || value || '未知';
}

function cnChannel(value) {
  return channelNameMap[value] || value || '未知';
}

function cnCity(value) {
  return cityNameMap[value] || value || '未知';
}

function fmtNumber(value) {
  const num = Number(value || 0);
  if (num >= 1_000_000_000) return `${(num / 1_000_000_000).toFixed(2)}B`;
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(2)}K`;
  return num.toLocaleString('zh-CN');
}

function fmtBytes(value) {
  const num = Number(value || 0);
  if (num >= 1024 ** 3) return `${(num / 1024 ** 3).toFixed(2)}GB`;
  if (num >= 1024 ** 2) return `${(num / 1024 ** 2).toFixed(2)}MB`;
  return `${num.toFixed(0)}B`;
}

function updateClock() {
  document.getElementById('clock').textContent = new Date().toLocaleString('zh-CN', { hour12: false });
}

function ensureChart(id) {
  if (!charts[id]) {
    charts[id] = echarts.init(document.getElementById(id), null, { renderer: 'canvas' });
  }
  return charts[id];
}

function baseText() {
  return {
    color: '#eefcff',
    fontFamily: cnFont
  };
}

function applyFiltersToScatter(scatter) {
  const amountFloor = Number(filters.amountPct || 0) / 100 * 10;
  return scatter.filter(point => {
    const channelOk = filters.channel === 'ALL' || point[3] === filters.channel;
    const riskOk = filters.risk === 'ALL' || point[4] === filters.risk;
    const amountOk = Number(point[1]) >= amountFloor;
    return channelOk && riskOk && amountOk;
  });
}

function renderKpis(data, filteredScatter) {
  const overview = data.overview;
  const items = [
    ['样本交易量', fmtNumber(overview.event_sample_count), '当前大屏采样窗口'],
    ['风险告警数', fmtNumber(overview.alert_count), '规则实时命中'],
    ['高风险告警', fmtNumber(overview.high_alert_count), '优先处置队列'],
    ['样本交易金额', fmtNumber(overview.sample_amount), '窗口金额合计'],
    ['综合风险脉冲', `${overview.avg_risk_score}/100`, '智能评分'],
    ['原始数据规模', fmtBytes(overview.enterprise_source_size_bytes), '企业级数据集']
  ];
  if (filteredScatter.length !== data.scatter.length) {
    items[0] = ['联动筛选结果', fmtNumber(filteredScatter.length), '三维星图子集'];
  }
  document.getElementById('coreScore').textContent = overview.avg_risk_score;
  document.getElementById('kpis').innerHTML = items.map(([label, value, hint]) => `
    <article class="kpi">
      <label>${label}</label>
      <strong>${value}</strong>
      <span>${hint}</span>
    </article>
  `).join('');
}

function populateFilters(data) {
  const riskSelect = document.getElementById('riskFilter');
  const channelSelect = document.getElementById('channelFilter');
  const risks = data.heatmap.labels || [];
  const channels = data.heatmap.channels || [];
  const currentRisk = riskSelect.value || 'ALL';
  const currentChannel = channelSelect.value || 'ALL';

  riskSelect.innerHTML = '<option value="ALL">全部风险标签</option>' + risks.map(item => `<option value="${item}">${cnRisk(item)}</option>`).join('');
  channelSelect.innerHTML = '<option value="ALL">全部支付通道</option>' + channels.map(item => `<option value="${item}">${cnChannel(item)}</option>`).join('');
  riskSelect.value = risks.includes(currentRisk) ? currentRisk : 'ALL';
  channelSelect.value = channels.includes(currentChannel) ? currentChannel : 'ALL';
  filters.risk = riskSelect.value;
  filters.channel = channelSelect.value;
}

function renderTimeSeries(data) {
  const rows = data.time_series;
  ensureChart('timeSeriesChart').setOption({
    color: palette,
    textStyle: baseText(),
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(4,12,18,.94)', borderColor: '#41e8ff', textStyle: baseText() },
    legend: { top: 0, right: 8, textStyle: { color: '#8fb6c2', fontFamily: cnFont } },
    grid: { left: 52, right: 28, top: 42, bottom: 48 },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 10, borderColor: 'rgba(65,232,255,.24)', textStyle: { color: '#8fb6c2' } }],
    xAxis: { type: 'category', data: rows.map(row => row.time), axisLine: { lineStyle: { color: '#41e8ff' } }, axisLabel: { color: '#8fb6c2' } },
    yAxis: [
      { type: 'value', name: '交易量', axisLabel: { color: '#8fb6c2' }, splitLine: { lineStyle: { color: 'rgba(65,232,255,.14)' } } },
      { type: 'value', name: '风险分', min: 0, max: 100, axisLabel: { color: '#8fb6c2' }, splitLine: { show: false } }
    ],
    series: [
      {
        name: '交易流量',
        type: 'line',
        smooth: true,
        symbolSize: 7,
        data: rows.map(row => row.count),
        lineStyle: { width: 3, shadowBlur: 16, shadowColor: '#41e8ff' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(65,232,255,.34)' }, { offset: 1, color: 'rgba(65,232,255,0)' }]) }
      },
      { name: '风险脉冲', type: 'line', yAxisIndex: 1, smooth: true, data: rows.map(row => row.risk), lineStyle: { width: 3, shadowBlur: 16, shadowColor: '#ff5377' } },
      { name: '失败交易', type: 'bar', data: rows.map(row => row.failed), barMaxWidth: 12, itemStyle: { borderRadius: 4, color: '#ff5377' } }
    ],
    animationDurationUpdate: 900
  }, true);
}

function renderRisk(data) {
  const rows = data.risk_levels.length ? data.risk_levels : [{ name: 'NO_ALERT', value: 1 }];
  const chart = ensureChart('riskLevelChart');
  chart.setOption({
    color: palette,
    textStyle: baseText(),
    tooltip: { trigger: 'item', backgroundColor: 'rgba(4,12,18,.94)', borderColor: '#41e8ff', textStyle: baseText(), formatter: p => `${cnRisk(p.name)}<br/>数量：${p.value}` },
    legend: { bottom: 0, formatter: cnRisk, textStyle: { color: '#8fb6c2', fontFamily: cnFont } },
    series: [{
      name: '风险等级',
      type: 'pie',
      radius: ['42%', '72%'],
      center: ['50%', '45%'],
      roseType: 'radius',
      label: { color: '#eefcff', formatter: p => cnRisk(p.name), fontFamily: cnFont },
      itemStyle: { borderColor: 'rgba(255,255,255,.2)', borderWidth: 1, shadowBlur: 18, shadowColor: '#41e8ff' },
      data: rows,
      animationDurationUpdate: 900
    }]
  }, true);
  chart.off('click');
  chart.on('click', params => {
    filters.risk = params.name === 'NO_ALERT' ? 'ALL' : params.name;
    const select = document.getElementById('riskFilter');
    if ([...select.options].some(option => option.value === filters.risk)) select.value = filters.risk;
    renderAll();
  });
}

function renderScatter(data, filteredScatter) {
  ensureChart('scatterChart').setOption({
    color: palette,
    textStyle: baseText(),
    tooltip: {
      backgroundColor: 'rgba(4,12,18,.96)',
      borderColor: '#41e8ff',
      textStyle: baseText(),
      formatter: params => {
        const p = params.value;
        return `小时：${p[0]}<br>金额层级：${p[1]}<br>风险分：${p[2]}<br>通道：${cnChannel(p[3])}<br>标签：${cnRisk(p[4])}<br>${p[5]}`;
      }
    },
    grid3D: {
      boxWidth: 120,
      boxDepth: 86,
      boxHeight: 78,
      axisLine: { lineStyle: { color: '#41e8ff' } },
      axisPointer: { lineStyle: { color: '#ffd36a' } },
      viewControl: { autoRotate: true, autoRotateSpeed: 2, distance: 156, rotateSensitivity: 1, zoomSensitivity: 1 },
      light: { main: { intensity: 1.25, shadow: true }, ambient: { intensity: 0.36 } }
    },
    xAxis3D: { type: 'value', name: '小时', min: 0, max: 23 },
    yAxis3D: { type: 'value', name: '金额层级' },
    zAxis3D: { type: 'value', name: '风险分', min: 0, max: 100 },
    series: [{
      type: 'scatter3D',
      name: '交易星点',
      data: filteredScatter,
      symbolSize: value => Math.max(5, Math.min(18, value[2] / 6)),
      itemStyle: { opacity: 0.9, borderWidth: 1, borderColor: 'rgba(255,255,255,.22)' },
      emphasis: { itemStyle: { color: '#ffd36a', opacity: 1 } },
      animationDurationUpdate: 900
    }]
  }, true);
}

function renderMerchant(data) {
  const rows = data.merchant_amount.slice(0, 10);
  ensureChart('merchantChart').setOption({
    color: palette,
    textStyle: baseText(),
    tooltip: { backgroundColor: 'rgba(4,12,18,.96)', borderColor: '#41e8ff', textStyle: baseText(), formatter: p => `${p.data.name}<br>收款金额：${fmtNumber(p.value[2])}` },
    grid3D: {
      boxWidth: 118,
      boxDepth: 30,
      boxHeight: 72,
      viewControl: { autoRotate: true, autoRotateSpeed: 1.4, distance: 170, zoomSensitivity: 1 },
      light: { main: { intensity: 1.3 }, ambient: { intensity: 0.5 } }
    },
    xAxis3D: { type: 'category', data: rows.map((_, index) => `商户${index + 1}`), name: '商户' },
    yAxis3D: { type: 'category', data: ['金额'], name: '' },
    zAxis3D: { type: 'value', name: '收款' },
    series: [{
      type: 'bar3D',
      shading: 'lambert',
      bevelSize: 0.25,
      data: rows.map((row, index) => ({ value: [index, 0, row.value], name: row.name })),
      itemStyle: { opacity: 0.92 },
      label: { show: false },
      animationDurationUpdate: 900
    }]
  }, true);
}

function renderFlow(data) {
  const links = (data.flow_links || []).slice(0, 14);
  const chart = ensureChart('flowChart');
  const maxValue = Math.max(1, ...links.map(link => Number(link.value || 0)));
  const nodes = new Map();

  links.forEach(link => {
    const source = cnCity(link.source || 'UNKNOWN');
    const target = link.target || 'UNKNOWN';
    const weight = Number(link.value || 0);
    if (!nodes.has(source)) {
      nodes.set(source, { name: source, category: 0, value: weight, symbolSize: 24 });
    } else {
      nodes.get(source).value += weight;
    }
    if (!nodes.has(target)) {
      nodes.set(target, { name: target, category: 1, value: weight, symbolSize: 18 + Math.min(26, weight / maxValue * 26) });
    } else {
      nodes.get(target).value += weight;
      nodes.get(target).symbolSize = Math.max(nodes.get(target).symbolSize, 18 + Math.min(26, weight / maxValue * 26));
    }
  });

  const graphLinks = links.map(link => ({
    source: cnCity(link.source || 'UNKNOWN'),
    target: link.target || 'UNKNOWN',
    value: Number(link.value || 0),
    lineStyle: {
      width: 1.2 + Math.min(5, Number(link.value || 0) / maxValue * 5),
      opacity: 0.78,
      curveness: 0.26
    }
  }));

  chart.setOption({
    color: ['#4fe5ff', '#ff5476'],
    textStyle: baseText(),
    tooltip: {
      backgroundColor: 'rgba(4,12,18,.96)',
      borderColor: '#4fe5ff',
      textStyle: baseText(),
      formatter: params => {
        if (params.dataType === 'edge') {
          return `${params.data.source} → ${params.data.target}<br>交易金额：${fmtNumber(params.data.value)}`;
        }
        return `${params.name}<br>关联强度：${fmtNumber(params.value || 0)}`;
      }
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      left: 0,
      right: 0,
      top: 4,
      bottom: 4,
      categories: [{ name: '城市' }, { name: '商户' }],
      data: [...nodes.values()].map(node => ({
        ...node,
        label: {
          show: node.category === 0,
          color: '#eefcff',
          fontFamily: cnFont,
          fontSize: 11
        }
      })),
      links: graphLinks,
      force: {
        repulsion: 86,
        edgeLength: [34, 88],
        gravity: 0.12
      },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 6,
      lineStyle: {
        color: 'source',
        shadowBlur: 12,
        shadowColor: '#4fe5ff'
      },
      itemStyle: {
        borderColor: 'rgba(255,255,255,.28)',
        borderWidth: 1,
        shadowBlur: 18,
        shadowColor: '#4fe5ff'
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 5 }
      },
      animationDurationUpdate: 900
    }]
  }, true);
}

function renderHeatmap(data) {
  const heat = data.heatmap;
  const max = Math.max(1, ...heat.data.map(item => item[2]));
  const chart = ensureChart('heatmapChart');
  chart.setOption({
    textStyle: baseText(),
    tooltip: {
      position: 'top',
      backgroundColor: 'rgba(4,12,18,.96)',
      borderColor: '#41e8ff',
      textStyle: baseText(),
      formatter: params => `${cnChannel(heat.channels[params.value[0]])}<br>${cnRisk(heat.labels[params.value[1]])}：${params.value[2]}`
    },
    grid: { left: 78, right: 24, top: 28, bottom: 54 },
    xAxis: { type: 'category', data: heat.channels.map(cnChannel), axisLabel: { color: '#8fb6c2', fontFamily: cnFont }, axisLine: { lineStyle: { color: '#41e8ff' } } },
    yAxis: { type: 'category', data: heat.labels.map(cnRisk), axisLabel: { color: '#8fb6c2', fontFamily: cnFont }, axisLine: { lineStyle: { color: '#41e8ff' } } },
    visualMap: { min: 0, max, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, textStyle: { color: '#8fb6c2', fontFamily: cnFont }, inRange: { color: ['#0a2a35', '#1ecad3', '#ffd36a', '#ff5377'] } },
    series: [{
      type: 'heatmap',
      data: heat.data,
      label: { show: true, color: '#eefcff', fontFamily: cnFont },
      emphasis: { itemStyle: { shadowBlur: 18, shadowColor: '#41e8ff' } },
      animationDurationUpdate: 900
    }]
  }, true);
  chart.off('click');
  chart.on('click', params => {
    filters.channel = heat.channels[params.value[0]] || 'ALL';
    filters.risk = heat.labels[params.value[1]] || 'ALL';
    document.getElementById('channelFilter').value = filters.channel;
    const riskSelect = document.getElementById('riskFilter');
    if ([...riskSelect.options].some(option => option.value === filters.risk)) riskSelect.value = filters.risk;
    renderAll();
  });
}

function renderCity(data) {
  const rows = data.city_amount.slice(0, 10);
  ensureChart('cityChart').setOption({
    color: palette,
    textStyle: baseText(),
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(4,12,18,.96)', borderColor: '#41e8ff', textStyle: baseText() },
    grid: { left: 48, right: 22, top: 26, bottom: 54 },
    xAxis: { type: 'category', data: rows.map(row => cnCity(row.name)), axisLabel: { color: '#8fb6c2', rotate: 22, fontFamily: cnFont }, axisLine: { lineStyle: { color: '#41e8ff' } } },
    yAxis: { type: 'value', axisLabel: { color: '#8fb6c2' }, splitLine: { lineStyle: { color: 'rgba(65,232,255,.14)' } } },
    dataZoom: [{ type: 'inside' }],
    series: [{
      name: '交易金额',
      type: 'bar',
      data: rows.map(row => row.value),
      barMaxWidth: 24,
      itemStyle: {
        borderRadius: [6, 6, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#72ffb7' }, { offset: 0.55, color: '#41e8ff' }, { offset: 1, color: 'rgba(65,232,255,.18)' }]),
        shadowBlur: 16,
        shadowColor: '#41e8ff'
      },
      animationDurationUpdate: 900
    }]
  }, true);
}

function renderRules(data) {
  const ruleName = {
    R001: '用户高频',
    R002: '用户大额',
    R003: '设备多用户',
    R004: '卡多用户',
    R005: '连续失败',
    R006: '黑名单设备',
    R007: '金额突增',
    R008: '商户突增'
  };
  const rows = data.rules.length ? data.rules : [{ name: 'R000', value: 0 }];
  const chart = ensureChart('ruleChart');
  chart.setOption({
    color: palette,
    textStyle: baseText(),
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(4,12,18,.96)', borderColor: '#41e8ff', textStyle: baseText() },
    grid: { left: 82, right: 20, top: 20, bottom: 34 },
    xAxis: { type: 'value', axisLabel: { color: '#8fb6c2' }, splitLine: { lineStyle: { color: 'rgba(65,232,255,.14)' } } },
    yAxis: { type: 'category', data: rows.map(row => ruleName[row.name] || row.name), axisLabel: { color: '#8fb6c2', fontFamily: cnFont }, axisLine: { lineStyle: { color: '#41e8ff' } } },
    series: [{ type: 'bar', data: rows.map(row => row.value), barMaxWidth: 18, itemStyle: { borderRadius: 4, color: '#ff5377', shadowBlur: 14, shadowColor: '#ff5377' }, animationDurationUpdate: 900 }]
  }, true);
  chart.off('click');
  chart.on('click', params => {
    const raw = rows[params.dataIndex];
    selectedRule = raw ? raw.name : 'ALL';
    renderAlerts(data);
  });
}

function renderInsights(data) {
  document.getElementById('insights').innerHTML = data.insights.map(item => `<li>${item}</li>`).join('');
}

function renderAlerts(data) {
  let alerts = data.alerts || [];
  if (selectedRule !== 'ALL') alerts = alerts.filter(alert => alert.rule_id === selectedRule);
  if (!alerts.length) {
    alerts = [{ rule_id: selectedRule, rule_name: '当前层级暂无告警', risk_level: 'INFO', reason: '可启动企业级 Kafka Producer 注入更多实时交易流。' }];
  }
  document.getElementById('alerts').innerHTML = alerts.slice(0, 16).map(alert => `
    <article class="alert-item">
      <strong>${alert.rule_id || '-'} / ${alert.rule_name || '未知规则'} / ${cnRisk(alert.risk_level || '-')}</strong>
      <span>${alert.reason || ''}</span>
      <span>${alert.user_id || alert.device_id || alert.merchant_id || alert.card_id || alert.event_id || ''}</span>
    </article>
  `).join('');
}

function renderAll() {
  if (!dashboardData) return;
  const filteredScatter = applyFiltersToScatter(dashboardData.scatter);
  renderKpis(dashboardData, filteredScatter);
  renderTimeSeries(dashboardData);
  renderRisk(dashboardData);
  renderScatter(dashboardData, filteredScatter);
  renderMerchant(dashboardData);
  renderFlow(dashboardData);
  renderHeatmap(dashboardData);
  renderCity(dashboardData);
  renderRules(dashboardData);
  renderInsights(dashboardData);
  renderAlerts(dashboardData);
}

async function refresh() {
  const response = await fetch('/api/dashboard', { cache: 'no-store' });
  dashboardData = await response.json();
  populateFilters(dashboardData);
  renderAll();
}

function initFilters() {
  document.getElementById('riskFilter').addEventListener('change', event => {
    filters.risk = event.target.value;
    renderAll();
  });
  document.getElementById('channelFilter').addEventListener('change', event => {
    filters.channel = event.target.value;
    renderAll();
  });
  document.getElementById('amountRange').addEventListener('input', event => {
    filters.amountPct = Number(event.target.value);
    document.getElementById('amountValue').textContent = filters.amountPct ? `P${filters.amountPct}` : '全部';
    renderAll();
  });
  document.getElementById('resetView').addEventListener('click', () => {
    filters.risk = 'ALL';
    filters.channel = 'ALL';
    filters.amountPct = 0;
    selectedRule = 'ALL';
    document.getElementById('riskFilter').value = 'ALL';
    document.getElementById('channelFilter').value = 'ALL';
    document.getElementById('amountRange').value = 0;
    document.getElementById('amountValue').textContent = '全部';
    renderAll();
  });
}

function initSpace() {
  const canvas = document.getElementById('space');
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(62, window.innerWidth / window.innerHeight, 0.1, 1800);
  camera.position.set(0, 0, 450);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);

  const particleCount = 1100;
  const positions = new Float32Array(particleCount * 3);
  const colors = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i += 1) {
    const idx = i * 3;
    positions[idx] = (Math.random() - 0.5) * 980;
    positions[idx + 1] = (Math.random() - 0.5) * 560;
    positions[idx + 2] = (Math.random() - 0.5) * 980;
    const hot = Math.random() > 0.86;
    colors[idx] = hot ? 1 : 0.25;
    colors[idx + 1] = hot ? 0.36 : 0.92;
    colors[idx + 2] = hot ? 0.48 : 1;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({ size: 2.2, vertexColors: true, transparent: true, opacity: 0.84 });
  const particles = new THREE.Points(geometry, material);
  scene.add(particles);

  const grid = new THREE.GridHelper(960, 48, 0x41e8ff, 0x16404c);
  grid.rotation.x = Math.PI / 2;
  grid.position.z = -230;
  grid.material.transparent = true;
  grid.material.opacity = 0.2;
  scene.add(grid);

  const ringMaterial = new THREE.MeshBasicMaterial({ color: 0x41e8ff, transparent: true, opacity: 0.36 });
  const rings = [150, 210, 270].map(radius => {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.7, 8, 180), ringMaterial);
    ring.position.z = -130;
    scene.add(ring);
    return ring;
  });

  function animate() {
    requestAnimationFrame(animate);
    particles.rotation.y += 0.0009;
    particles.rotation.x += 0.00045;
    grid.rotation.z += 0.0008;
    rings.forEach((ring, index) => {
      ring.rotation.z += 0.002 + index * 0.0006;
      ring.rotation.x = Math.sin(Date.now() * 0.00045 + index) * 0.24;
      ring.rotation.y = Math.cos(Date.now() * 0.00035 + index) * 0.18;
    });
    renderer.render(scene, camera);
  }
  animate();

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
}

window.addEventListener('resize', () => Object.values(charts).forEach(chart => chart.resize()));
setInterval(updateClock, 1000);
setInterval(refresh, 10000);
initSpace();
initFilters();
updateClock();
refresh();

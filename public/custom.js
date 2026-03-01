// MeowDev 自定义脚本 - 立即执行
// 修复头像尺寸为 56px

(function() {
  function injectStyle() {
    if (document.getElementById('meowdev-avatar-fix')) return;

    const style = document.createElement('style');
    style.id = 'meowdev-avatar-fix';
    style.textContent = `
      /* 头像尺寸修复 - Chainlit 2.x */
      span.rounded-full.h-5.w-5,
      span[class*="h-5"][class*="w-5"][class*="rounded-full"] {
        width: 56px !important;
        height: 56px !important;
        min-width: 56px !important;
        min-height: 56px !important;
      }
      img[src*="/avatars/"] {
        width: 56px !important;
        height: 56px !important;
      }
    `;

    (document.head || document.documentElement).appendChild(style);
    console.log('[MeowDev] Avatar style injected');
  }

  // 立即尝试注入
  injectStyle();

  // DOM 就绪后再次注入
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectStyle);
  }

  // 延迟注入（处理 SPA）
  setTimeout(injectStyle, 100);
  setTimeout(injectStyle, 500);
  setTimeout(injectStyle, 1000);

  // 监听 DOM 变化
  const observer = new MutationObserver(injectStyle);
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();


// ── 猫猫统计抽屉 (一比一还原 token_use.html) ─────────────────────────────────────

(function() {
  const CATS = {
    arch:  { name: 'Arch酱',  badge: 'Soft Blue Theme' },
    stack: { name: 'Stack喵', badge: 'Warm Orange Theme' },
    pixel: { name: 'Pixel咪', badge: 'Soft Pink Theme' },
  };
  const CAT_ORDER = ['arch', 'stack', 'pixel'];

  function getActiveRange() {
    const active = document.querySelector('.time-range-btn.active');
    return active ? active.dataset.range : 'week';
  }

  function createDrawer() {
    if (document.getElementById('meowdev-drawer')) return;

    // 创建主布局容器
    const layoutContainer = document.createElement('div');
    layoutContainer.id = 'meowdev-layout';
    document.body.appendChild(layoutContainer);

    // 创建内容包装器（用于包裹 Chainlit 的主内容）
    const contentWrapper = document.createElement('div');
    contentWrapper.id = 'meowdev-content-wrapper';

    // 将 #root 移动到 contentWrapper 中
    const root = document.getElementById('root');
    if (root) {
      layoutContainer.appendChild(contentWrapper);
      contentWrapper.appendChild(root);
    }

    // 创建抽屉
    const drawer = document.createElement('div');
    drawer.id = 'meowdev-drawer';
    drawer.innerHTML = `
      <header class="drawer-header">
        <div class="drawer-header-left">
          <span class="material-symbols-outlined">dashboard</span>
          <h3>用量统计</h3>
        </div>
        <div class="drawer-header-actions">
          <button class="drawer-header-btn refresh" id="refresh-stats" title="刷新">
            <span class="material-symbols-outlined">refresh</span>
          </button>
          <button class="drawer-header-btn close" id="close-drawer" title="关闭">
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>
      </header>
      <div class="time-range-selector">
        <div class="time-range-buttons">
          <button class="time-range-btn" data-range="day">当天</button>
          <button class="time-range-btn active" data-range="week">一周</button>
          <button class="time-range-btn" data-range="month">一个月</button>
        </div>
      </div>
      <div class="drawer-content">
        <div id="cat-stats"><div class="empty-state">加载中...</div></div>
      </div>
    `;
    layoutContainer.appendChild(drawer);

    document.getElementById('close-drawer').onclick = () => {
      document.getElementById('meowdev-drawer').classList.remove('open');
      document.body.classList.remove('drawer-open');
    };
    document.getElementById('refresh-stats').onclick = fetchStats;

    drawer.querySelectorAll('.time-range-btn').forEach(btn => {
      btn.onclick = (e) => {
        drawer.querySelectorAll('.time-range-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        fetchStats();
      };
    });

    const btn = document.createElement('button');
    btn.id = 'drawer-toggle';
    btn.innerHTML = '<span class="material-symbols-outlined">monitoring</span>';
    btn.title = '用量统计';
    btn.onclick = toggleDrawer;
    document.body.appendChild(btn);
  }

  window.toggleDrawer = function() {
    const drawer = document.getElementById('meowdev-drawer');
    if (drawer) {
      const wasClosed = !drawer.classList.contains('open');
      drawer.classList.toggle('open');
      document.body.classList.toggle('drawer-open', wasClosed);
      if (wasClosed) fetchStats();
    }
  };

  async function fetchStats() {
    const container = document.getElementById('cat-stats');
    if (container) container.innerHTML = '<div class="empty-state">加载中...</div>';

    const range = getActiveRange();

    try {
      const res = await fetch('/api/stats?range=' + range);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      renderCatStats(data.stats || {});
    } catch (e) {
      console.error('[MeowDev] Failed to fetch stats:', e.message);
      if (container) {
        container.innerHTML = '<div class="empty-state">加载失败<br><small>' + e.message + '</small></div>';
      }
    }
  }

  function fmt(n) { return (n || 0).toLocaleString(); }

  function renderCatStats(stats) {
    const container = document.getElementById('cat-stats');
    if (!container) return;

    const hasData = CAT_ORDER.some(id => stats[id] && stats[id].call_count > 0);
    if (!hasData) {
      container.innerHTML = '<div class="empty-state">暂无使用数据</div>';
      return;
    }

    container.innerHTML = '<div class="usage-container"></div>';
    const wrap = container.querySelector('.usage-container');

    CAT_ORDER.forEach(catId => {
      const d = stats[catId];
      if (!d) return;
      const cfg = CATS[catId];
      const card = document.createElement('div');
      card.className = 'usage-card ' + catId;
      card.innerHTML =
        '<div class="usage-card-header">' +
          '<img class="usage-card-avatar" src="/public/avatars/' + catId + '.png" alt="' + cfg.name + '">' +
          '<div class="usage-card-info">' +
            '<h3>' + cfg.name + '</h3>' +
            '<span class="usage-card-theme">' + cfg.badge + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="usage-card-stats">' +
          '<div class="usage-stat-item"><div class="usage-stat-label">Input</div><div class="usage-stat-value">' + fmt(d.input_tokens) + '</div></div>' +
          '<div class="usage-stat-item"><div class="usage-stat-label">Output</div><div class="usage-stat-value">' + fmt(d.output_tokens) + '</div></div>' +
          '<div class="usage-stat-item"><div class="usage-stat-label">Cache</div><div class="usage-stat-value">' + fmt(d.cache_read_tokens) + '</div></div>' +
        '</div>' +
        '<div class="usage-card-cost">' +
          '<span class="usage-card-cost-label">费用 (Cost)</span>' +
          '<span class="usage-card-cost-value">$' + (d.cost_usd || 0).toFixed(4) + '</span>' +
        '</div>';
      wrap.appendChild(card);
    });
  }

  function init() {
    createDrawer();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  setTimeout(init, 500);
  setTimeout(init, 1000);
})();

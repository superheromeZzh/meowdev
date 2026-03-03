// MeowDev 自定义脚本
// 模块: 品牌页隐藏 + 头像修复 / 会话恢复 / 统计抽屉

// ── 品牌页隐藏（初始加载 + SPA 导航）+ 头像修复 ────────────────────
(function() {
  var style = document.createElement('style');
  style.id = 'meowdev-critical';
  style.textContent =
    'span.rounded-full.h-5.w-5,' +
    'span[class*="h-5"][class*="w-5"][class*="rounded-full"]{' +
    'width:56px!important;height:56px!important;min-width:56px!important;min-height:56px!important}' +
    'img[src*="/avatars/"]{width:56px!important;height:56px!important}' +
    '#root.meowdev-hide{opacity:0!important}' +
    '#root.meowdev-ready{opacity:1!important;transition:opacity .15s ease}';
  (document.head || document.documentElement).appendChild(style);

  var currentThread = null;
  var timer = null, obs = null, timeout = null;

  function getThreadId() {
    var m = window.location.pathname.match(/\/thread\/([^/?]+)/);
    return m ? m[1] : null;
  }

  function cleanup() {
    if (timer) { clearInterval(timer); timer = null; }
    if (obs) { obs.disconnect(); obs = null; }
    if (timeout) { clearTimeout(timeout); timeout = null; }
  }

  function hide() {
    var root = document.getElementById('root');
    if (root) {
      root.classList.remove('meowdev-ready');
      root.classList.add('meowdev-hide');
    }
  }

  function reveal() {
    var root = document.getElementById('root');
    if (root) {
      root.classList.remove('meowdev-hide');
      root.classList.add('meowdev-ready');
    }
    cleanup();
  }

  function hasContent() {
    var root = document.getElementById('root');
    if (!root) return false;
    return root.querySelectorAll(
      '[class*="step"], [class*="Step"], [class*="message"], [class*="Message"]'
    ).length > 0;
  }

  function pollForContent() {
    if (hasContent()) { reveal(); return; }
    timer = setInterval(function() {
      if (hasContent()) reveal();
    }, 50);
    var root = document.getElementById('root');
    if (root) {
      obs = new MutationObserver(function() {
        if (hasContent()) reveal();
      });
      obs.observe(root, { childList: true, subtree: true });
    }
    timeout = setTimeout(reveal, 5000);
  }

  // 初始加载：如果在 thread 页面，立即隐藏等消息
  if (getThreadId()) {
    currentThread = getThreadId();
    hide();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', pollForContent);
    } else {
      pollForContent();
    }
  }

  // SPA 导航：监听 URL 变化
  var lastPath = window.location.pathname;

  function onRouteChange() {
    var threadId = getThreadId();
    if (threadId && threadId !== currentThread) {
      cleanup();
      currentThread = threadId;
      hide();
      // 等 React 卸载旧内容（300ms），再开始检测新内容
      setTimeout(pollForContent, 300);
    } else if (!threadId) {
      currentThread = null;
      reveal();
    }
  }

  function checkRoute() {
    if (window.location.pathname !== lastPath) {
      lastPath = window.location.pathname;
      onRouteChange();
    }
  }

  var origPush = history.pushState;
  history.pushState = function() {
    origPush.apply(this, arguments);
    setTimeout(checkRoute, 0);
  };
  var origReplace = history.replaceState;
  history.replaceState = function() {
    origReplace.apply(this, arguments);
    setTimeout(checkRoute, 0);
  };
  window.addEventListener('popstate', function() { setTimeout(checkRoute, 0); });
  setInterval(checkRoute, 300);
})();


// ── 会话恢复模块 ─────────────────────────────────────────────────
(function() {
  var STORAGE_KEY = 'meowdev_last_thread_id';

  function tryRestore() {
    if (window.location.pathname !== '/') return false;

    var isReload = false;
    try {
      var navEntries = performance.getEntriesByType('navigation');
      if (navEntries.length > 0 && navEntries[0].type === 'reload') isReload = true;
    } catch(e) {}
    if (!isReload && performance.navigation && performance.navigation.type === 1) isReload = true;
    if (!isReload && sessionStorage.getItem('meowdev_was_loaded')) isReload = true;

    if (!isReload) {
      sessionStorage.setItem('meowdev_was_loaded', '1');
      return false;
    }

    var lastThread = localStorage.getItem(STORAGE_KEY);
    if (!lastThread) return false;

    history.replaceState({}, '', '/thread/' + lastThread);
    return true;
  }

  tryRestore();
  sessionStorage.setItem('meowdev_was_loaded', '1');

  function saveCurrentThread() {
    var m = window.location.pathname.match(/\/thread\/([^/?]+)/);
    if (m) localStorage.setItem(STORAGE_KEY, m[1]);
  }

  var lastPath = window.location.pathname;
  setInterval(function() {
    if (window.location.pathname !== lastPath) {
      lastPath = window.location.pathname;
      saveCurrentThread();
    }
  }, 500);
  saveCurrentThread();
})();


// ── 猫猫统计抽屉 ─────────────────────────────────────────────────────────────
(function() {
  var CATS = {
    arch:  { name: 'Arch酱',  badge: 'Soft Blue Theme' },
    stack: { name: 'Stack喵', badge: 'Warm Orange Theme' },
    pixel: { name: 'Pixel咪', badge: 'Soft Pink Theme' },
  };
  var CAT_ORDER = ['arch', 'stack', 'pixel'];

  function getActiveRange() {
    var active = document.querySelector('.time-range-btn.active');
    return active ? active.dataset.range : 'week';
  }

  window.toggleDrawer = function() {
    var drawer = document.getElementById('meowdev-drawer');
    if (drawer) {
      var wasClosed = !drawer.classList.contains('open');
      drawer.classList.toggle('open');
      document.body.classList.toggle('drawer-open', wasClosed);
      if (wasClosed) fetchStats();
    }
  };

  function createDrawer() {
    if (document.getElementById('meowdev-drawer')) return;

    var drawer = document.createElement('div');
    drawer.id = 'meowdev-drawer';
    drawer.innerHTML =
      '<header class="drawer-header">' +
        '<div class="drawer-header-left">' +
          '<span class="material-symbols-outlined">dashboard</span>' +
          '<h3>用量统计</h3>' +
        '</div>' +
        '<div class="drawer-header-actions">' +
          '<button class="drawer-header-btn refresh" id="refresh-stats" title="刷新">' +
            '<span class="material-symbols-outlined">refresh</span>' +
          '</button>' +
          '<button class="drawer-header-btn close" id="close-drawer" title="关闭">' +
            '<span class="material-symbols-outlined">close</span>' +
          '</button>' +
        '</div>' +
      '</header>' +
      '<div class="time-range-selector">' +
        '<div class="time-range-buttons">' +
          '<button class="time-range-btn" data-range="day">当天</button>' +
          '<button class="time-range-btn active" data-range="week">一周</button>' +
          '<button class="time-range-btn" data-range="month">一个月</button>' +
        '</div>' +
      '</div>' +
      '<div class="drawer-content">' +
        '<div id="cat-stats"><div class="empty-state">加载中...</div></div>' +
      '</div>';
    document.body.appendChild(drawer);

    document.getElementById('close-drawer').onclick = function() {
      document.getElementById('meowdev-drawer').classList.remove('open');
      document.body.classList.remove('drawer-open');
    };
    document.getElementById('refresh-stats').onclick = fetchStats;

    drawer.querySelectorAll('.time-range-btn').forEach(function(btn) {
      btn.onclick = function(e) {
        drawer.querySelectorAll('.time-range-btn').forEach(function(b) { b.classList.remove('active'); });
        e.target.classList.add('active');
        fetchStats();
      };
    });

    var btn = document.createElement('button');
    btn.id = 'drawer-toggle';
    btn.innerHTML = '<span class="material-symbols-outlined">monitoring</span>';
    btn.title = '用量统计';
    btn.onclick = window.toggleDrawer;
    document.body.appendChild(btn);
  }

  function fetchStats() {
    var container = document.getElementById('cat-stats');
    if (container) container.innerHTML = '<div class="empty-state">加载中...</div>';

    var range = getActiveRange();

    fetch('/api/stats?range=' + range)
      .then(function(res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function(data) { renderCatStats(data.stats || {}); })
      .catch(function(e) {
        if (container) {
          container.innerHTML = '<div class="empty-state">加载失败<br><small>' + e.message + '</small></div>';
        }
      });
  }

  function fmt(n) { return (n || 0).toLocaleString(); }

  function renderCatStats(stats) {
    var container = document.getElementById('cat-stats');
    if (!container) return;

    var hasData = CAT_ORDER.some(function(id) { return stats[id] && stats[id].call_count > 0; });
    if (!hasData) {
      container.innerHTML = '<div class="empty-state">暂无使用数据</div>';
      return;
    }

    container.innerHTML = '<div class="usage-container"></div>';
    var wrap = container.querySelector('.usage-container');

    CAT_ORDER.forEach(function(catId) {
      var d = stats[catId];
      if (!d) return;
      var cfg = CATS[catId];
      var card = document.createElement('div');
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

  function init() { createDrawer(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  setTimeout(init, 500);
  setTimeout(init, 1000);
})();

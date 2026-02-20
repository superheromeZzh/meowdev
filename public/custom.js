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

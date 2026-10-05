document.addEventListener('DOMContentLoaded', () => {
  if (window.parent !== window && new URLSearchParams(location.search).get('embedded') === '1') return;
  const home = document.createElement('a');
  home.href = '/'; home.textContent = '← 返回项目主页'; home.className = 'site-home-link';
  home.style.cssText = 'color:inherit;text-decoration:none;font-size:12px;border:1px solid #d8cabc;padding:8px 12px;border-radius:4px;white-space:nowrap';
  document.querySelector('.topbar-status')?.prepend(home);
  const style = document.createElement('style');
  style.textContent = '@media(max-width:800px){.topbar{flex-wrap:wrap;gap:10px}.topbar-status{display:flex;margin-left:auto}.topbar-status .site-home-link{font-size:10px!important;padding:5px 9px!important}}';
  document.head.append(style);
});

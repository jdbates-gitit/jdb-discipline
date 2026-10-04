(() => {
  const header = document.getElementById('jdb-site-navigation');
  if (!header) return;
  const menu = header.querySelector('.jdb-grouped-nav');
  const button = header.querySelector('.jdb-hamburger');
  const groups = [...header.querySelectorAll('details')];
  const mobile = window.matchMedia('(max-width:800px)');
  const closeGroups = except => groups.forEach(group => { if (group !== except) group.open = false; });
  const closeMenu = () => {
    closeGroups(); menu.classList.remove('jdb-open');
    button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-label', 'Open menu');
  };
  groups.forEach(group => group.addEventListener('toggle', () => { if (group.open) closeGroups(group); }));
  button.addEventListener('click', () => {
    const open = menu.classList.toggle('jdb-open');
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    if (!open) closeGroups();
  });
  header.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
  document.addEventListener('click', event => { if (!header.contains(event.target)) closeMenu(); });
  header.addEventListener('focusout', () => {
    setTimeout(() => { if (!header.contains(document.activeElement)) closeMenu(); }, 0);
  });
  header.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const group = groups.find(item => item.open);
    const wasOpen = menu.classList.contains('jdb-open');
    closeMenu();
    if (mobile.matches && wasOpen) button.focus();
    else if (group) group.querySelector('summary').focus();
  });
  mobile.addEventListener('change', closeMenu);
  header.setAttribute('data-enhanced', 'true');
})();

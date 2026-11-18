(() => {
  const stack = document.getElementById('django-messages');
  if (!stack) return;

  const header = document.querySelector('.topbar');
  const positionMessages = () => {
    if (header) stack.style.setProperty('--message-header-height', `${header.getBoundingClientRect().height}px`);
  };
  positionMessages();
  const observer = header && typeof ResizeObserver !== 'undefined' ? new ResizeObserver(positionMessages) : null;
  if (observer) observer.observe(header);
  window.addEventListener('resize', positionMessages);

  stack.addEventListener('click', event => {
    const button = event.target.closest('[data-dismiss-message]');
    if (!button || !stack.contains(button)) return;
    const notice = button.closest('.site-message');
    const focused = notice.contains(document.activeElement);
    const nextFocus = notice.nextElementSibling?.querySelector('[data-dismiss-message]')
      || notice.previousElementSibling?.querySelector('[data-dismiss-message]')
      || document.querySelector('.topbar a');
    notice.remove();
    if (focused && nextFocus) nextFocus.focus({preventScroll: true});
    if (!stack.childElementCount) {
      observer?.disconnect();
      window.removeEventListener('resize', positionMessages);
      stack.remove();
    }
  });
})();

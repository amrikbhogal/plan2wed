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

  // Manual popovers keep feedback above native modal dialogs without taking
  // focus away from the form. Older browsers retain the normal fixed stack.
  const activeDialog = () => Array.from(document.querySelectorAll('dialog[open]')).at(-1);
  const raiseMessages = () => {
    if (!stack.isConnected || typeof stack.showPopover !== 'function') return;
    if (stack.matches(':popover-open')) stack.hidePopover();
    // Remain within the active modal's interactive subtree, while the popover
    // puts the fixed notification panel back in viewport coordinates.
    const host = activeDialog() || document.body;
    if (stack.parentElement !== host) host.append(stack);
    stack.setAttribute('popover', 'manual');
    stack.showPopover();
  };
  const onDialogToggle = event => {
    if (event.target.matches?.('dialog')) raiseMessages();
  };
  raiseMessages();
  document.addEventListener('toggle', onDialogToggle, true);

  stack.addEventListener('click', event => {
    const button = event.target.closest('[data-dismiss-message]');
    if (!button || !stack.contains(button)) return;
    const notice = button.closest('.site-message');
    const focused = notice.contains(document.activeElement);
    const nextFocus = notice.nextElementSibling?.querySelector('[data-dismiss-message]')
      || notice.previousElementSibling?.querySelector('[data-dismiss-message]')
      || activeDialog()?.querySelector('[aria-invalid="true"], input:not([type="hidden"]), select, textarea')
      || document.querySelector('.topbar a');
    notice.remove();
    if (focused && nextFocus) nextFocus.focus({preventScroll: true});
    if (!stack.childElementCount) {
      observer?.disconnect();
      window.removeEventListener('resize', positionMessages);
      document.removeEventListener('toggle', onDialogToggle, true);
      stack.remove();
    }
  });
})();

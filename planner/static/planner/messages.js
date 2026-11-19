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

  const successTimers = new Map();
  const dismissMessage = notice => {
    clearTimeout(successTimers.get(notice));
    successTimers.delete(notice);
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
  };

  stack.addEventListener('click', event => {
    const button = event.target.closest('[data-dismiss-message]');
    if (button && stack.contains(button)) dismissMessage(button.closest('.site-message'));
  });

  // Give successes six seconds to read. Hovering or focusing a notice keeps it
  // available; leaving starts a fresh interval. Errors remain until dismissed.
  stack.querySelectorAll('.site-message[data-level="success"]').forEach(notice => {
    const pause = () => {
      clearTimeout(successTimers.get(notice));
      successTimers.delete(notice);
    };
    const resume = () => {
      pause();
      if (!notice.isConnected || notice.matches(':hover') || notice.contains(document.activeElement)) return;
      successTimers.set(notice, setTimeout(() => dismissMessage(notice), 6000));
    };
    notice.addEventListener('mouseenter', pause);
    notice.addEventListener('mouseleave', resume);
    notice.addEventListener('focusin', pause);
    notice.addEventListener('focusout', () => queueMicrotask(resume));
    resume();
  });
})();

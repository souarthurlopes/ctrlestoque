/* Instalação progressiva; dados e tokens nunca são guardados em Cache Storage. */
(() => {
  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js', {updateViaCache:'none'}).catch(() => {});
    });
  }
  let pending = null;
  const button = document.createElement('button');
  button.className = 'b pwa-install';button.textContent='Instalar app';button.hidden=true;
  button.style.cssText='position:fixed;bottom:calc(18px + env(safe-area-inset-bottom,0px));right:18px;z-index:10;box-shadow:0 4px 18px #20345b22';
  document.body.append(button);
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();pending=event;
    button.hidden=window.matchMedia('(display-mode: standalone)').matches;
  });
  button.addEventListener('click', async () => {
    if (!pending) return;
    const prompt = pending;pending=null;button.hidden=true;
    try {await prompt.prompt();await prompt.userChoice;} catch (_) {}
  });
  window.addEventListener('appinstalled', () => {pending=null;button.hidden=true;});
})();

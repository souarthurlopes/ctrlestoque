/* Não armazena estoque, pedidos, senhas ou respostas da API em cache. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate' || event.request.method !== 'GET' || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).catch(() => new Response(`<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ControlAI · Sem conexão</title><style>body{font:16px/1.6 system-ui;background:#f5f7fb;color:#18243b;margin:0;padding:32px;min-height:80vh;display:grid;place-content:center}main{max-width:420px}h1{font-size:24px}a{display:inline-block;background:#3267ed;color:white;text-decoration:none;padding:10px 20px;border-radius:8px}</style><main><h1>Você está sem conexão</h1><p>O ControlAI precisa de internet para consultar o estoque atualizado e salvar as movimentações.</p><a href="/">Tentar novamente</a></main></html>`, {status:503,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}})));
});

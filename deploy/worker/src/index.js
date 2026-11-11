// Porta de entrada pública do Escritório Veraneio (….workers.dev).
// Repassa tudo (páginas, API e WebSocket) ao sistema no PC pelo Workers VPC: binding ESCRITORIO →
// Cloudflare Tunnel → http://127.0.0.1:8000. Sem domínio próprio e sem porta aberta no roteador.

const PAGINA_FORA_DO_AR = `<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Escritório Veraneio</title>
<body style="margin:0;display:grid;place-items:center;height:100vh;background:#1b1e24;color:#e9ecef;font-family:system-ui">
<div style="text-align:center;max-width:420px;padding:24px"><h1 style="color:#f4a261;font-size:1.3rem">Escritório Veraneio fora do ar</h1>
<p>O computador que hospeda o sistema pode estar desligado ou sem internet. Tente de novo em alguns minutos.</p></div></body></html>`;

// Rotas que só o trabalhador do Max usa (chave de operador, dentro do PC): pela internet, 404 antes de chegar ao PC.
// Manter igual a CAMINHOS_INTERNOS em backend/borda.py (o backend repete a trava, caso este Worker fique antigo).
export const ROTAS_INTERNAS = new RegExp([
  /^\/api\/producao\/proxima\/?$/,
  /^\/api\/producao\/\d+\/(?:progresso|concluir|bloqueios|devolver|falhar|folha)\/?$/,
  /^\/api\/producao\/trabalhos\/\d+\/(?:concluir|status|falhar)\/?$/,
  /^\/api\/cerebro\/ingerir\/?$/,
  /^\/api\/integracoes\/monday\/criativos\/\d+\/?$/,
].map((r) => r.source).join('|'));

export function rotaInterna(caminho) {
  // Normaliza como o servidor faria (barras repetidas e %2F não driblam a trava).
  let normal = caminho;
  try { normal = decodeURIComponent(caminho); } catch { /* caminho malformado: compara como veio */ }
  return ROTAS_INTERNAS.test(normal.replace(/\/{2,}/g, '/'));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (rotaInterna(url.pathname)) return Response.json({ detail: 'Not Found' }, { status: 404 });
    // O host é só um rótulo: quem decide o destino é o VPC Service.
    const destino = new URL(url.pathname + url.search, 'http://escritorio.interno');
    const cabecalhos = new Headers(request.headers);
    cabecalhos.set('X-Forwarded-For', request.headers.get('CF-Connecting-IP') || '');
    cabecalhos.set('X-Forwarded-Proto', 'https');
    cabecalhos.set('X-Forwarded-Host', url.host);
    // Marca de "veio da internet": o backend recusa a chave de operador e as rotas do trabalhador (backend/borda.py).
    cabecalhos.set('X-Escritorio-Borda', 'worker');
    const temCorpo = !['GET', 'HEAD'].includes(request.method);
    try {
      return await env.ESCRITORIO.fetch(destino, {
        method: request.method, headers: cabecalhos, body: temCorpo ? request.body : null, redirect: 'manual',
      });
    } catch (erro) {
      console.error('Escritório inacessível:', erro);
      const html = (request.headers.get('Accept') || '').includes('text/html');
      return html
        ? new Response(PAGINA_FORA_DO_AR, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } })
        : Response.json({ detail: 'Escritório fora do ar no momento.' }, { status: 503 });
    }
  },
};

/** Página HTML mínima mostrada quando o servidor da UI falha. */
export function renderErrorPage(): string {
  return `<!doctype html>
<html lang="pt">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Erro</title>
  </head>
  <body style="font-family: sans-serif; text-align: center; padding: 4rem 1rem">
    <h1>Algo correu mal</h1>
    <p>Atualize a página. Se o problema continuar, reinicie a aplicação.</p>
  </body>
</html>`;
}

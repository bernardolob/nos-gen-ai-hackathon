"""Servidor MCP para o Lovable ver o nosso backend e trabalhar na UI.

O Lovable liga-se a este servidor (Connectors > Custom MCP) e consulta, em
**só leitura** e com **dados fictícios**:

- ``describe_backend``: as rotas da API da revisão, o que enviam e devolvem
  e os erros possíveis (gerado a partir da aplicação real);
- ``sample_response``: exemplos de resposta de cada passo da revisão (sem
  documento, depois de enviar, depois de rejeitar, aprovado e erros);
- ``frontend_brief``: o que a UI faz hoje, onde estão os ficheiros e o que
  se pode melhorar.

Nunca processa documentos reais nem chama o Gemini: os exemplos vêm de um
documento fictício e de um modelo falso. O token (``MCP_TOKEN``) é
obrigatório em todos os pedidos; sem ele definido, gera-se um aleatório.

Arranque, a partir de ``submission/solution/src``::

    python mcp_server.py            # http://127.0.0.1:8765/mcp

Como o Lovable corre na cloud, é preciso expor este endereço por HTTPS (por
exemplo um túnel); ver MCP.md.
"""

import hmac
import json
import os
import secrets
import sys

import user_validation
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

HOST = "127.0.0.1"
PORT = 8765
PATH = "/mcp"
BACKEND_URL = "http://127.0.0.1:%d" % user_validation.PORT

SAMPLE_DOCUMENT = "\n".join([
    "Relatório de consulta",
    "Nome: Ana Silva",
    "NIF: 123456789",
    "Email: ana.silva@exemplo.pt",
    "Cidade: Porto",
    "Diagnóstico: diabetes tipo 2",
])
SAMPLE_REASON = "Não mascares a informação médica."
STEPS = ("empty", "uploaded", "rejected", "approved", "errors")


def _item(line, text, category):
    return {"line": line, "text": text, "category": category,
            "reason": "Exemplo.", "confidence": "certo"}


def fake_model(system_prompt, content):
    """Modelo falso: sem pedido do utilizador mascara também a saúde."""
    items = [_item(2, "Ana Silva", "identificacao"),
             _item(5, "Porto", "quasi_identificador")]
    if "<user_instructions>" not in content:
        items.append(_item(6, "diabetes tipo 2", "saude"))
    return json.dumps(items)


def sample_responses():
    """Respostas de exemplo de cada passo, geradas pelo backend real."""
    session = user_validation.ReviewSession(fake_model)
    out = {"empty": session.snapshot()}
    lines = SAMPLE_DOCUMENT.split("\n")
    session.load(lines)
    out["uploaded"] = session.snapshot()
    session.reject(user_validation.RejectedVersion(
        attempt=1, text="", reason=SAMPLE_REASON))
    out["rejected"] = session.snapshot()
    session.approve()
    out["approved"] = dict(
        session.snapshot(), status="approved")
    out["errors"] = ERRORS
    return out


ERRORS = {
    "format": "Todos os erros são {\"detail\": \"mensagem em português\"}.",
    "codes": {
        "409": "Sem documento ainda, ou a tentativa enviada já não é a atual.",
        "413": "Documento com mais de 10 MB.",
        "415": "Content-Type não é application/pdf nem text/plain.",
        "422": "Documento sem texto, PDF ilegível, texto que não é UTF-8, "
               "ou observações com mais de 2000 caracteres.",
        "502": "O modelo ou o gateway falharam. A versão atual não mudou: "
               "mostrar a mensagem e deixar tentar outra vez.",
    },
    "example": {"detail": "A versão em revisão já mudou."},
}

ENDPOINTS = [
    {"method": "POST", "path": "/api/document",
     "summary": "Envia o documento e começa uma revisão nova (substitui a "
                "anterior).",
     "request": "Corpo cru: o PDF (Content-Type: application/pdf) ou texto "
                "UTF-8 (Content-Type: text/plain). Não é JSON.",
     "response": "Snapshot (ver sample_response 'uploaded').",
     "notes": "Com o Gemini demora cerca de 8 s."},
    {"method": "GET", "path": "/api/current",
     "summary": "Estado atual da revisão.",
     "request": "Sem corpo.",
     "response": "Snapshot. Com has_document=false a UI deve pedir o "
                 "documento."},
    {"method": "POST", "path": "/api/reject",
     "summary": "Rejeita a versão atual com observações e gera a seguinte.",
     "request": "JSON {attempt: int, text: str, reason: str}. 'attempt' tem "
                "de ser a tentativa atual; 'text' é ignorado; 'reason' é o "
                "pedido em texto livre (mais ou menos máscara).",
     "response": "Snapshot com attempt+1 e a versão rejeitada no history.",
     "notes": "Demora cerca de 8 s com o Gemini. Se falhar (502) nada muda."},
    {"method": "POST", "path": "/api/approve",
     "summary": "Aprova a versão atual.",
     "request": "Sem corpo.",
     "response": "Snapshot mais {status: 'approved'}."},
]

SNAPSHOT_FIELDS = {
    "has_document": "bool: já há um documento em revisão.",
    "attempt": "int a partir de 1: a tentativa atual.",
    "text": "str: o texto mascarado, linhas separadas por \\n; cada palavra "
            "sensível é um '*'.",
    "approved": "bool.",
    "history": "lista de {attempt, text, reason} das versões rejeitadas, "
               "da mais antiga para a mais recente.",
    "mode": "'model' (Gemini + regras) ou 'rules' (só regras de segurança; "
            "as observações não mudam o texto).",
    "warnings": "int: itens que não se aplicaram, para rever.",
    "issues": "int: problemas da verificação (0 é o normal).",
}

FRONTEND_BRIEF = """\
UI atual (React + TanStack Start + Vite + Tailwind + shadcn), em
submission/solution/Lovable_UI_JunctionX/ :

- src/components/review-workspace.tsx: a tela toda (cabeçalho, etapas na
  barra lateral, documento com os '*' destacados, aprovar/rejeitar,
  histórico de versões, diálogos de envio e de rejeição).
- src/styles.css: estilos (.document-paper, .mask-token, .workflow-step...).
- src/routes/index.tsx e __root.tsx: a rota e o esqueleto.
- src/components/ui/: componentes shadcn genéricos.
- O endereço do backend vem de VITE_API_URL (por defeito
  http://127.0.0.1:8000). O CORS só aceita localhost/127.0.0.1 nas portas
  8080, 5173 e 3000.

Fluxo: enviar documento -> ver o texto anonimizado -> aprovar, ou rejeitar
com observações (a prompt do utilizador: mascarar mais ou menos) -> nova
tentativa, com o histórico das anteriores. O utilizador tem a palavra final.

Restrições a respeitar:
- Textos em português europeu. Nada de dados reais nos exemplos.
- Gerar uma versão demora cerca de 8 s com o Gemini: mostrar estado de
  espera e desativar os botões; tratar o 502 sem perder a versão atual.
- Uma só sessão em memória: um documento de cada vez.
- O texto mascarado mantém a formatação (uma linha de saída por linha de
  entrada); mostrar sempre com fonte monoespaçada e quebras de linha.
- Não há (ainda) rota para o relatório (categorias e razões de cada item) nem
  para o texto original. Se a UI precisar deles, é trabalho de backend.

Ideias: mostrar o relatório; ver original e mascarado lado a lado; contar
palavras mascaradas por categoria; atalhos de teclado; modo escuro.
"""


def build_server():
    """Cria o servidor MCP com as três ferramentas de leitura."""
    server = MCPServer(
        "nos-anonimizador",
        instructions=(
            "Descreve o backend de anonimização (API de revisão) e a UI, "
            "só de leitura e com dados fictícios. Comece por "
            "frontend_brief e describe_backend."),
    )

    @server.tool()
    def describe_backend() -> dict:
        """Rotas da API da revisão, campos das respostas e erros."""
        return {
            "base_url": BACKEND_URL,
            "endpoints": ENDPOINTS,
            "snapshot_fields": SNAPSHOT_FIELDS,
            "errors": ERRORS,
            "openapi_paths": sorted(
                user_validation.create_app().openapi()["paths"]),
        }

    @server.tool()
    def sample_response(step: str) -> dict:
        """Resposta de exemplo de um passo: empty, uploaded, rejected,
        approved ou errors."""
        if step not in STEPS:
            return {"error": "step desconhecido", "steps": list(STEPS)}
        return {"step": step, "example": sample_responses()[step]}

    @server.tool()
    def frontend_brief() -> str:
        """O que a UI faz hoje, onde estão os ficheiros e restrições."""
        return FRONTEND_BRIEF

    return server


class BearerAuth:
    """Middleware ASGI: só deixa passar pedidos com o token certo."""

    def __init__(self, app, token):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not self._allowed(scope):
            body = b'{"detail":"Token em falta ou invalido."}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"www-authenticate", b"Bearer"),
                            (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)

    def _allowed(self, scope):
        header = dict(scope["headers"]).get(b"authorization", b"")
        prefix = b"Bearer "
        if not header.startswith(prefix):
            return False
        given = header[len(prefix):]
        return hmac.compare_digest(given, self.token.encode())


def allowed_hosts(environ=None):
    """Hosts aceites no cabeçalho Host (protege contra DNS rebinding)."""
    env = os.environ if environ is None else environ
    extra = [h.strip() for h in env.get("MCP_ALLOWED_HOSTS", "").split(",")
             if h.strip()]
    if "*" in extra:
        raise ValueError("MCP_ALLOWED_HOSTS não pode conter *.")
    return ["127.0.0.1:*", "localhost:*"] + extra


def build_app(token, environ=None):
    """A aplicação ASGI: o servidor MCP atrás do token."""
    server = build_server()
    app = server.streamable_http_app(
        streamable_http_path=PATH,
        stateless_http=True,
        json_response=True,
        host=HOST,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts(environ),
            allowed_origins=[]),
    )
    return BearerAuth(app, token)


def main():
    import uvicorn
    token = os.environ.get("MCP_TOKEN", "").strip()
    generated = not token
    if generated:
        token = secrets.token_urlsafe(32)
    app = build_app(token)
    print("Servidor MCP em http://%s:%d%s (só leitura, dados fictícios)"
          % (HOST, PORT, PATH))
    if generated:
        print("MCP_TOKEN não definido: token desta sessão (mostrado uma vez):")
        print(token)
    sys.stdout.flush()
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()

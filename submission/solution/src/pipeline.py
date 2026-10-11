"""Ponto de entrada: liga a extração, a deteção, as regras, o mascaramento,
a verificação e o relatório.

Uso, a partir da raiz do repositório::

    cd submission/solution/src
    python pipeline.py ../../../raw_data/document_to_anonymize.pdf --no-model
    python pipeline.py documento.pdf --no-model --out saida

Sem ``--out`` nada é escrito: mostra só o resumo (ensaio). Com ``--out DIR``
escreve ``DIR/submission.txt`` (o documento mascarado) e ``DIR/report.md``.

O modelo entra como a função ``generate(instrução_de_sistema, conteúdo)`` do
``detection.detect``. Pela linha de comandos vem do gateway Cloudflare
(``gateway.from_env``, variáveis ``GEMINI_GATEWAY_URL`` e
``GEMINI_GATEWAY_ORIGIN``); com ``--no-model`` só correm as regras de
segurança. Em código, passa-se o ``generate`` a ``run``.

Códigos de saída: 0 sem problemas, 1 a verificação encontrou problemas,
2 erro (ficheiro, argumentos ou deteção).
"""

import argparse
import os
import sys
from pathlib import Path

import detection
import gateway
import labels
import gemini_adapter
import masking
import report
import safety_rules
import verification
import visibility

EXIT_OK = 0
EXIT_VERIFICATION = 1
EXIT_ERROR = 2

MAX_INSTRUCTIONS = 2000  # o pedido ao gateway tem um limite total
SUBMISSION_FILE = "submission.txt"
REPORT_FILE = "report.md"


def read_lines(path):
    """Lê o documento (PDF ou texto) e devolve as linhas, sem linhas vazias.

    As linhas ficam em NFC, como a deteção espera.
    """
    import pdf_extractor  # importa o PyMuPDF, por isso só aqui
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("o documento não existe: %s" % path)
    if path.suffix.lower() == ".pdf":
        text = pdf_extractor.extract_and_prepare_text(str(path))
    else:
        text = pdf_extractor.remove_empty_lines(
            path.read_text(encoding="utf-8"))
    if not text:
        return []
    return detection.normalize_lines(text.split("\n"))


def read_instructions(text=None, path=None):
    """Instruções do utilizador, do texto ou de um ficheiro (UTF-8).

    Devolve ``None`` se não houver nenhuma. Levanta ``ValueError`` se forem
    mais compridas que ``MAX_INSTRUCTIONS``; a mensagem nunca as inclui.
    """
    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    if text is None or not text.strip():
        return None
    text = text.strip()
    if len(text) > MAX_INSTRUCTIONS:
        raise ValueError(
            "As instruções têm %d caracteres; o máximo é %d."
            % (len(text), MAX_INSTRUCTIONS))
    return text


def run(lines, generate=None, user_instructions=None, include_values=False):
    """Corre o pipeline sobre as linhas e devolve um dicionário.

    Com ``generate=None`` só se usam as regras de segurança. Chaves:
    ``masked`` (linhas), ``items``, ``warnings``, ``issues`` (da
    verificação), ``label_changes`` (itens do modelo corrigidos para deixar a
    etiqueta visível, ver ``labels.py``), ``kept_visible`` (itens que o
    utilizador pediu para deixar visíveis, ver ``visibility.py``) e
    ``report`` (Markdown).

    Levanta ``detection.DetectionError`` se a resposta do modelo não se
    puder usar.
    """
    rule_items = safety_rules.find_sensitive(lines)
    model_items, warnings = [], []
    if generate is not None:
        model_items, warnings = detection.detect(
            lines, generate, user_instructions=user_instructions)
        warnings = warnings + detection.empty_answer_warnings(
            model_items, rule_items)
    model_items, visible = visibility.split_visible(model_items)
    if visible and not user_instructions:
        warnings = warnings + [{
            "index": None, "line": None, "text": None,
            "problem": "o modelo pediu para deixar valores visíveis sem "
                       "instruções do utilizador; foi ignorado"}]
        visible = []
    kept_visible = 0
    if visible:
        model_items, dropped = visibility.drop_overlapping(
            lines, model_items, visible)
        rule_items, dropped_rules = visibility.drop_overlapping(
            lines, rule_items, visible)
        kept_visible = dropped + dropped_rules
    model_items, label_changes = labels.keep_labels(lines, model_items)
    items = model_items + rule_items
    masked, mask_warnings = masking.mask_lines(lines, items)
    warnings = warnings + mask_warnings
    return {
        "masked": masked,
        "items": items,
        "warnings": warnings,
        "label_changes": label_changes,
        "kept_visible": kept_visible,
        "issues": verification.compare_lines(lines, masked),
        "report": report.build_report(items, warnings, include_values),
    }


def write_outputs(result, out_dir):
    """Escreve ``submission.txt`` e ``report.md`` em ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SUBMISSION_FILE).write_text(
        "\n".join(result["masked"]), encoding="utf-8", newline="\n")
    (out_dir / REPORT_FILE).write_text(
        result["report"], encoding="utf-8", newline="\n")


def summary(result):
    """Resumo de uma linha por tema, sem valores sensíveis."""
    rows = [
        "linhas: %d" % len(result["masked"]),
        "itens mascarados: %d" % len(result["items"]),
        "avisos: %d" % len(result["warnings"]),
        "problemas na verificação: %d" % len(result["issues"]),
    ]
    if result["kept_visible"]:
        rows.append(
            "deixados visíveis a pedido do utilizador: %d"
            % result["kept_visible"])
    if result["label_changes"]:
        rows.append(
            "etiquetas deixadas visíveis: %d" % result["label_changes"])
    return "\n".join(rows)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Anonimiza um documento: cada palavra sensível passa a *.")
    parser.add_argument("document", help="PDF ou ficheiro de texto")
    parser.add_argument(
        "--no-model", action="store_true",
        help="só as regras de segurança, sem o Gemini")
    instructions = parser.add_mutually_exclusive_group()
    instructions.add_argument(
        "--instructions", help="instruções do utilizador, em texto livre")
    instructions.add_argument(
        "--instructions-file", metavar="FICHEIRO",
        help="ficheiro de texto (UTF-8) com as instruções do utilizador")
    parser.add_argument(
        "--out", metavar="DIR",
        help="escreve submission.txt e report.md aqui (sem isto, ensaio)")
    parser.add_argument(
        "--include-values", action="store_true",
        help="mostra os valores originais no relatório")
    parser.add_argument(
        "--use-cache", action="store_true",
        help="usa o cliente SDK com context caching em vez do gateway")
    return parser


def main(argv=None, generate=None):
    """Corre o pipeline pela linha de comandos e devolve o código de saída."""
    args = build_parser().parse_args(argv)
    try:
        if args.no_model:
            generate = None
        elif generate is None:
            use_cache = args.use_cache or (
                os.environ.get("USE_CACHE", "").lower() in ("1", "true", "yes")
            )
            if use_cache:
                generate = gemini_adapter.make_cached_generate()
            else:
                generate = (
                    gateway.from_env() or gemini_adapter.make_cached_generate()
                )
            if generate is None:
                print("Erro: falta ligar ao Gemini. Defina "
                      "GEMINI_GATEWAY_URL e GEMINI_GATEWAY_ORIGIN "
                      "(gateway), ou GEMINI_API_KEY (SDK com cache), "
                      "ou use --no-model para correr só as regras de "
                      "segurança.",
                      file=sys.stderr)
                return EXIT_ERROR
        instructions = read_instructions(
            args.instructions, args.instructions_file)
        lines = read_lines(args.document)
        result = run(lines, generate, instructions, args.include_values)
    except (OSError, RuntimeError, ValueError, detection.DetectionError,
            gateway.GatewayError) as error:
        print("Erro: %s" % error, file=sys.stderr)
        return EXIT_ERROR
    if args.out:
        write_outputs(result, args.out)
    print(summary(result))
    if not args.out:
        print("(ensaio: nada foi escrito; use --out DIR)")
    return EXIT_VERIFICATION if result["issues"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

import fitz  # PyMuPDF


def remove_empty_lines(text: str) -> str:
    """
    Remove as linhas vazias ou só com espaços em branco.

    Junta as restantes com uma quebra de linha, mantendo a formatação
    e os acentos.
    """
    # .splitlines() divide o texto onde há quebras de linha
    # line.strip() verifica se a linha tem conteúdo real
    linhas_validas = [line.rstrip() for line in text.splitlines() if line.strip() != ""]

    # Volta a unir o texto apenas com as linhas que têm conteúdo
    return "\n".join(linhas_validas)


def extract_and_prepare_text(pdf_path: str) -> str:
    """
    Extrai o texto original do PDF, preservando pontuação e acentos,
    mas aplicando a regra do desafio: sem linhas vazias.
    """
    raw_text = ""

    # 1. Extração do texto original do PDF
    with fitz.open(pdf_path) as doc:
        for page in doc:
            raw_text += page.get_text()

    # 2. Aplicação da regra
    final_text = remove_empty_lines(raw_text)

    return final_text


if __name__ == "__main__":
    # Caminho do ficheiro na vossa estrutura de pastas
    pdf_path = "raw_data/document_to_anonymize.pdf"

    print("A extrair o texto...")

    # Executa a função
    texto_final = extract_and_prepare_text(pdf_path)

    # Imprime no terminal para veres imediatamente o resultado
    print("\n--- PREVIEW DO TEXTO ---")
    print(texto_final)
    print("------------------------------------------\n")

    # Guarda num ficheiro .txt para poderes inspecionar com calma
    path_output = "raw_data/extracted_text.txt"
    with open(path_output, "w", encoding="utf-8") as f:
        f.write(texto_final)

    print(f"✅ Teste concluído! O texto foi guardado em {path_output}.")

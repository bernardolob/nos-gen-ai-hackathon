"""Layout-preserving PDF/DOCX adapters for the local review workflow."""

from .common import DocumentError

PDF_TYPE = "application/pdf"
DOCX_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def open_document(path, content_type, folder):
    mime = content_type.split(";", 1)[0].strip().lower()
    try:
        if mime == PDF_TYPE:
            from .pdf import PdfDocument
            return PdfDocument(path, folder)
        if mime == DOCX_TYPE:
            from .word import WordDocument
            return WordDocument(path, folder)
    except DocumentError:
        raise
    except Exception:
        label = "PDF" if mime == PDF_TYPE else "Word .docx"
        raise DocumentError("Não foi possível ler o %s." % label) from None
    raise DocumentError("Envie um PDF ou documento Word .docx.")

# PDF and Word image censorship

The local review API now retains PDF and DOCX files, anonymizes their native
text with the existing text pipeline, and analyzes each unique embedded image
with the existing multimodal image pipeline. The browser provides Text and
Images tabs. Image masks can be drawn, moved, resized or removed and are saved
before approval. Reused images are reviewed once; edits apply to every placement.

Scanned PDF pages work as images even without extractable text. Sensitive text
inside scans is pixelated through visual regions; it is not converted into an
OCR transcript. For PDFs with an OCR layer, text beneath visual masks is removed,
and hidden text is scrubbed during export.

## Running locally

Install `requirements.txt` (including the new `lxml` dependency), configure the
existing text gateway and `GEMINI_MEDIA_MODEL` as described in [MEDIA.md](MEDIA.md),
and run `src/user_validation.py`. Set the frontend's `VITE_API_URL` to that local
backend before starting Vite. Documents containing images require the multimodal
processor; text-only PDFs/DOCX files can use the existing rules-only mode.

Demo mode shows a clearly identified sample document and supports mask editing,
but cannot produce real PDF/DOCX downloads. Local processing uses the real file.

## API contract

- `POST /api/document`: raw PDF or DOCX bytes with their standard content type
  and optional URL-encoded `X-File-Name`; returns a processing snapshot.
- `GET /api/current`: `kind: "document"` with a `document` descriptor containing
  `id`, `format`, `filename`, `images` and `output_url`. Each image has `id`,
  `source_url`, `width`, `height`, placement labels and `regions`. Other review
  kinds return `document: null`.
- `GET /api/document/images/{id}?attempt=N`: temporary original image used by
  the canvas mask preview. The document/image ID and attempt guard stale requests.
- `PUT /api/document/images/{id}/regions`: `{ "attempt": N, "regions": [...] }`.
  Regions use the existing media schema, exactly one keyframe, and zero times.
- `POST /api/reject`: existing feedback fields plus `document_id`; reanalyzes
  text and images from the original file using accumulated instructions.
- `POST /api/approve`: `{ "attempt": N, "document_id": "..." }` for documents.
  Starts export. Other review kinds retain their existing approval request.
- `GET /api/document/output`: the approved PDF or editable DOCX; unavailable
  while processing, after failure, or before approval.

The browser polls while processing/exporting. Only a successful export sets
`approved: true` and exposes `document.output_url`. All returned files use
`Cache-Control: no-store`. Files are removed on replacement or server shutdown.

## Export behavior

PDFs retain page geometry and unaffected selectable text. Native text masks are
physically applied using the exact offsets from the masking engine. Images are
replaced in the file rather than covered by annotations. Pages containing inline
images without a usable object reference are rebuilt as censored page images;
those pages no longer have selectable text. Exports use a fresh save with garbage
collection and scrub metadata, thumbnails, links, attachments and annotations.

DOCX exports edit text nodes inside the existing package, covering body text,
tables, text boxes, headers, footers, footnotes and endnotes. Drawings, cropping,
wrapping and formatting remain. Text replacement may change line wrapping or
pagination. Raster images are replaced with sanitized PNGs and their relationship
targets/content types are updated. Comments, revision history, preview thumbnails,
image descriptions, hyperlinks and obsolete original media are removed.

Limits: 10,000,000 upload bytes; 100,000,000 expanded DOCX bytes; 2,048 package
members; 25 megapixels per image and 100 megapixels of unique images per document.
Animated raster images, vector image encodings, externally linked images, macros,
embedded documents/OLE objects and custom XML data stores are rejected rather
than silently retained. Legacy `.doc` is unsupported. Analysis/export failures
never produce an approved partial document.

The command-line text submission pipeline keeps its existing TXT/report output.

## Validation

`tests/test_document_images.py` covers actual exported content, image reuse,
transparency, rotation, scanned PDFs, OCR layers, inline images, split Word runs,
NFC normalization, Word story parts, package limits, stale requests, failures
and cleanup. Frontend document tests cover tabs, pending edits, approval order
and failed saves. No live provider calls are required for these tests.

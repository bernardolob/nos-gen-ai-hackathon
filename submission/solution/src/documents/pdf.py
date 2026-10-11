"""PDF text coordinates, image placements and physical export redactions."""

import io

import pymupdf as fitz
from PIL import Image

from media.regions import Box, Point, RegionKeyframe
from .common import DocumentAdapter, DocumentError, mapped_lines, redact_image
from media.pipeline import MAX_IMAGE_PIXELS


class PdfDocument(DocumentAdapter):
    format = "pdf"

    def __init__(self, path, folder):
        super().__init__(path, folder)
        raw, references = [], []
        with fitz.open(path) as document:
            if document.needs_pass or not document.is_pdf:
                raise DocumentError("PDF protegido ou inválido.")
            for page in document:
                infos = {i["number"]: i for i in
                         page.get_image_info(xrefs=True)}
                blocks = page.get_text(
                    "rawdict", clip=fitz.INFINITE_RECT())["blocks"]
                for block in blocks:
                    if block["type"] == 1:
                        if block["width"] * block["height"] > MAX_IMAGE_PIXELS:
                            raise DocumentError("Imagem demasiado grande.")
                        info = infos.get(block["number"], {})
                        xref = info.get("xref", 0)
                        data = block["image"]
                        if xref:
                            pixmap = fitz.Pixmap(document, xref)
                            mask = document.extract_image(xref).get("smask")
                            if mask:
                                pixmap = fitz.Pixmap(
                                    pixmap, fitz.Pixmap(document, mask))
                            if pixmap.colorspace.n > 3:
                                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                            data = pixmap.tobytes("png")
                        elif block.get("mask"):
                            with Image.open(io.BytesIO(data)) as image:
                                image = image.convert("RGBA")
                                mask_image = Image.open(
                                    io.BytesIO(block["mask"]))
                                with mask_image as m:
                                    image.putalpha(m.convert("L"))
                                encoded = io.BytesIO()
                                image.save(encoded, "PNG")
                                data = encoded.getvalue()
                        self.add_image(data, {
                            "page": page.number, "xref": xref,
                            "matrix": block["transform"],
                            "label": "Page %d" % (page.number + 1),
                        })
                    elif block["type"] == 0:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                for char in span["chars"]:
                                    raw.append(char["c"])
                                    references.extend([{
                                        "page": page.number,
                                        "bbox": char["bbox"],
                                        "origin": char["origin"],
                                        "size": span["size"],
                                        "dir": line["dir"],
                                    }] * len(char["c"]))
                            raw.append("\n")
                            references.append(None)
        self.lines, self.maps = mapped_lines("".join(raw), references)
        if not self.lines and not self.images:
            raise DocumentError("O documento não tem texto nem imagens.")

    def render(self, output, edits, regions):
        image_data = self.redacted_images(regions)
        with fitz.open(self.path) as document:
            text_edits = {}
            for edit in edits:
                refs = [ref for group in self.maps[edit["line"] - 1][
                    edit["start"]:edit["end"]] for ref in group if ref]
                if not refs:
                    raise DocumentError(
                        "Não foi possível localizar uma máscara.")
                pages = {r["page"] for r in refs}
                if len(pages) != 1:
                    raise DocumentError("Uma máscara atravessa páginas.")
                rect = fitz.Rect(refs[0]["bbox"])
                for ref in refs[1:]:
                    rect |= fitz.Rect(ref["bbox"])
                page = document[refs[0]["page"]]
                page.add_redact_annot(rect, fill=None, cross_out=False)
                text_edits.setdefault(page.number, []).append((refs[0], edit))

            inline_pages, replaced = set(), set()
            for image in self.images:
                for placement in image.placements:
                    page = document[placement["page"]]
                    xref = placement["xref"]
                    if xref and xref not in replaced:
                        page.replace_image(xref, stream=image_data[image.id])
                        replaced.add(xref)
                    elif not xref:
                        inline_pages.add(page.number)
                    # Remove OCR/text behind visual masks, including shared
                    # images displayed with different scale or rotation.
                    for region in regions[image.id]:
                        box = region.box_at(0)
                        rect = fitz.Rect(box.x, box.y, box.x + box.width,
                                         box.y + box.height)
                        rect = rect * fitz.Matrix(placement["matrix"])
                        page.add_redact_annot(
                            rect, fill=None, cross_out=False)

            for page in document:
                page.apply_redactions(images=0, graphics=0)
                for first, edit in text_edits.get(page.number, []):
                    direction = first["dir"]
                    rotation = {(1, 0): 0, (0, -1): 90,
                                (-1, 0): 180, (0, 1): 270}.get(
                                    tuple(round(v) for v in direction))
                    if rotation is None:
                        raise DocumentError("Texto com rotação não suportada.")
                    page.insert_text(first["origin"], edit["replacement"],
                                     fontsize=first["size"], rotate=rotation)

            # Inline image streams cannot be replaced by xref. Rebuild only
            # affected pages; no original page resources enter the new page.
            for number in sorted(inline_pages):
                page = document[number]
                scale = min(2, (MAX_IMAGE_PIXELS / (
                    page.rect.width * page.rect.height)) ** 0.5)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                                         alpha=False)
                preview = self.folder / ("inline-%d.png" % number)
                preview.write_bytes(pixmap.tobytes("png"))
                mapped = []
                for image in self.images:
                    for placement in image.placements:
                        if (placement["page"] != number or
                                placement["xref"]):
                            continue
                        for region in regions[image.id]:
                            box = region.box_at(0)
                            rect = fitz.Rect(box.x, box.y, box.x + box.width,
                                             box.y + box.height)
                            rect *= fitz.Matrix(placement["matrix"])
                            rect *= page.rotation_matrix
                            rect &= page.rect
                            if rect.is_empty:
                                continue
                            polygon = region.polygon_at(0)
                            if polygon is None:
                                corners = [(box.x, box.y),
                                           (box.x + box.width, box.y),
                                           (box.x + box.width,
                                            box.y + box.height),
                                           (box.x, box.y + box.height)]
                                polygon = [Point(
                                    x=start[0] +
                                    (end[0] - start[0]) * step / 8,
                                    y=start[1] +
                                    (end[1] - start[1]) * step / 8)
                                    for start, end in zip(
                                        corners, corners[1:] + corners[:1])
                                    for step in range(8)]
                            transformed = [
                                fitz.Point(p.x, p.y) * fitz.Matrix(
                                    placement["matrix"]) * page.rotation_matrix
                                for p in polygon]
                            contour = [Point(
                                x=p.x / page.rect.width,
                                y=p.y / page.rect.height) for p in transformed
                                ] if all(page.rect.contains(p)
                                         for p in transformed) else None
                            mapped.append(region.model_copy(update={
                                "keyframes": [RegionKeyframe(
                                    time_ms=0, box=Box(
                                        x=rect.x0 / page.rect.width,
                                        y=rect.y0 / page.rect.height,
                                        width=rect.width / page.rect.width,
                                        height=rect.height /
                                        page.rect.height), polygon=contour)],
                            }))
                data = redact_image(preview, mapped)
                width, height = page.rect.width, page.rect.height
                document.delete_page(number)
                fresh = document.new_page(pno=number, width=width,
                                          height=height)
                fresh.insert_image(fresh.rect, stream=data)
                preview.unlink(missing_ok=True)

            document.scrub(hidden_text=True, redactions=False,
                           reset_fields=True, reset_responses=True)
            # Remove annotation contents and appearance streams as well.
            for page in document:
                for annot in list(page.annots() or []):
                    page.delete_annot(annot)
            document.save(output, garbage=4, clean=True, deflate=True)

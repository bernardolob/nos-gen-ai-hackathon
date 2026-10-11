"""Document exports must replace sensitive data in the actual file."""

import io
import threading
import time
import zipfile

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient
from lxml import etree as ET
from PIL import Image

import masking
import pipeline
import user_validation
from documents import DOCX_TYPE, DocumentError, open_document
from documents.common import mapped_lines, redact_image
from documents.word import W
from media.regions import Box, MediaRegion, Point, RegionKeyframe


def picture(alpha=False):
    image = Image.new("RGBA" if alpha else "RGB", (120, 100))
    image.putdata([
        ((x * 37 + y * 9) % 256, (x * 11 + y * 47) % 256,
         (x * 61 + y * 23) % 256, 90) if alpha else
        ((x * 37 + y * 9) % 256, (x * 11 + y * 47) % 256,
         (x * 61 + y * 23) % 256)
        for y in range(100) for x in range(120)])
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


def region():
    return MediaRegion(
        id="mask", category="identificacao", kind="text",
        reason="Sensitive data", confidence="certo", source="user",
        start_ms=0, end_ms=0,
        keyframes=[RegionKeyframe(time_ms=0, box=Box(
            x=0.1, y=0.1, width=0.5, height=0.5))])


def make_pdf(path, text=True, repeated=True, rotate=False, alpha=False,
             ocr=False):
    with fitz.open() as document:
        page = document.new_page(width=400, height=500)
        if text:
            page.insert_text((25, 30), "Nome: Ana Silva")
            page.insert_text((25, 50), "Safe text preserved")
        xref = page.insert_image(fitz.Rect(50, 100, 290, 300),
                                 stream=picture(alpha))
        if ocr:
            page.insert_text((80, 140), "HIDDEN SECRET", render_mode=3)
        if rotate:
            page.set_rotation(90)
        if repeated:
            page = document.new_page(width=400, height=500)
            page.insert_image(fitz.Rect(50, 100, 170, 200), xref=xref)
        document.set_metadata({"author": "Sensitive author"})
        document.save(path)


def make_docx(path, external=False, unsupported=False):
    basens = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    root = f'''<w:document xmlns:w="{W}"
      xmlns:r="{basens}"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:wp="WP_NAMESPACE">
      <w:body><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Nome: Ana</w:t></w:r>
      <w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve"> Silva</w:t>
      <w:drawing><wp:anchor>
      <wp:docPr id="1" name="Photo" descr="Secret"/>
      <a:srcRect l="10000"/><a:blip r:embed="pic"/>
      </wp:anchor></w:drawing></w:r>
      </w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>NIF: 123456789</w:t></w:r>
      </w:p></w:tc></w:tr></w:tbl>
      <w:p><w:r><w:t>Safe text</w:t></w:r>
      <w:del><w:r><w:delText>Deleted secret</w:delText></w:r></w:del>
      <w:ins w:author="Secret"><w:r><w:t> accepted</w:t></w:r></w:ins></w:p>
      <w:p><w:r><w:pict><w:txbxContent><w:p><w:r><w:t>Box text</w:t></w:r>
      </w:p></w:txbxContent></w:pict></w:r></w:p>
      <w:sectPr><w:headerReference w:type="default" r:id="head"/>
      </w:sectPr>
      </w:body></w:document>'''
    root = root.replace("WP_NAMESPACE", "http://schemas.openxmlformats.org/"
                        "drawingml/2006/wordprocessingDrawing")
    relns = "http://schemas.openxmlformats.org/package/2006/relationships"
    mode = 'TargetMode="External"' if external else ""
    target = ("https://example.test/private.png" if external
              else "media/original.png")
    header = f'''<w:hdr xmlns:w="{W}" xmlns:r="{basens}"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <w:p><w:r><w:t>Header: Ana Silva</w:t><w:drawing><a:blip r:embed="pic"/>
      </w:drawing></w:r></w:p></w:hdr>'''
    types = '''<Types
      xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels"
      ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Default Extension="png" ContentType="image/png"/>
      <Override PartName="/word/document.xml"
      ContentType="DOC_CONTENT_TYPE"/>
      <Override PartName="/word/header1.xml"
      ContentType="HEADER_CONTENT_TYPE"/>
      <Override PartName="/word/comments.xml"
      ContentType="COMMENT_CONTENT_TYPE"/>
      </Types>'''
    base = "application/vnd.openxmlformats-officedocument.wordprocessingml."
    types = types.replace("DOC_CONTENT_TYPE", base + "document.main+xml")
    types = types.replace("HEADER_CONTENT_TYPE", base + "header+xml")
    types = types.replace("COMMENT_CONTENT_TYPE", base + "comments+xml")
    parts = {
        "[Content_Types].xml": types,
        "_rels/.rels": (
            f'<Relationships xmlns="{relns}"><Relationship Id="doc" '
            f'Type="{basens}/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'),
        "word/document.xml": root,
        "word/header1.xml": header,
        "word/_rels/document.xml.rels": (
            f'<Relationships xmlns="{relns}"><Relationship Id="pic" '
            f'Type="{basens}/image" Target="{target}" {mode}/>'
            f'<Relationship Id="head" Type="{basens}/header" '
            'Target="header1.xml"/></Relationships>'),
        "word/_rels/header1.xml.rels": (
            f'<Relationships xmlns="{relns}"><Relationship Id="pic" '
            f'Type="{basens}/image" Target="{target}" {mode}/>'
            '</Relationships>'),
        "word/comments.xml": (
            f'<w:comments xmlns:w="{W}"><w:comment><w:p><w:r>'
            '<w:t>Comment secret</w:t></w:r></w:p></w:comment></w:comments>'),
        "docProps/core.xml": '<properties>Secret author</properties>',
        "docProps/thumbnail.png": picture(),
        "word/media/original.png": b"<svg/>" if unsupported else picture(),
        "word/media/unused.png": picture(),
        "word/media/censored-old.png": picture(),
    }
    with zipfile.ZipFile(path, "w") as package:
        for name, data in parts.items():
            package.writestr(name, data)


def sensitive_items(lines):
    return [{"line": index + 1, "text": "Ana Silva"}
            for index, line in enumerate(lines) if "Ana Silva" in line]


@pytest.mark.parametrize("rotate,alpha,ocr", [
    (False, False, False), (True, True, True)])
def test_pdf_export_removes_text_and_original_images(
        tmp_path, rotate, alpha, ocr):
    source = tmp_path / "source.pdf"
    make_pdf(source, rotate=rotate, alpha=alpha, ocr=ocr)
    adapter = open_document(source, "application/pdf", tmp_path)
    assert adapter.lines[:2] == ["Nome: Ana Silva", "Safe text preserved"]
    assert len(adapter.images) == 1
    assert len(adapter.images[0].placements) == 2
    edits, _ = masking.plan_masks(
        adapter.lines, sensitive_items(adapter.lines))
    output = tmp_path / "output.pdf"
    adapter.render(output, edits, {adapter.images[0].id: [region()]})
    with fitz.open(output) as document:
        text = "".join(page.get_text() for page in document)
        assert "Ana" not in text and "Silva" not in text
        assert "HIDDEN SECRET" not in text
        assert "Safe text preserved" in text and "* *" in text
        assert document[0].rotation == (90 if rotate else 0)
        assert not document.metadata["author"]
        for page in document:
            assert len(page.get_image_info()) == 1
            xref = page.get_image_info(xrefs=True)[0]["xref"]
            data = document.extract_image(xref)["image"]
            assert data != picture(alpha)
            with Image.open(io.BytesIO(data)) as censored:
                with Image.open(io.BytesIO(picture(alpha))) as original:
                    assert censored.convert("RGB").getpixel((30, 30)) != (
                        original.convert("RGB").getpixel((30, 30)))


def test_docx_export_preserves_drawings_and_replaces_all_parts(tmp_path):
    source = tmp_path / "source.docx"
    make_docx(source)
    adapter = open_document(source, DOCX_TYPE, tmp_path)
    assert adapter.lines.count("Box text") == 1
    assert len(adapter.images) == 1
    assert len(adapter.images[0].placements) == 2
    result = pipeline.run(adapter.lines)
    edits, _ = masking.plan_masks(
        adapter.lines, sensitive_items(adapter.lines))
    output = tmp_path / "output.docx"
    adapter.render(output, result["edits"] + edits,
                   {adapter.images[0].id: [region()]})
    with zipfile.ZipFile(output) as package:
        names = package.namelist()
        assert "word/media/original.png" not in names
        assert "word/media/unused.png" not in names
        assert not any(n.startswith("docProps/") for n in names)
        assert "word/comments.xml" not in names
        body = package.read("word/document.xml")
        header = package.read("word/header1.xml")
        assert b"Ana" not in body + header
        assert b"Silva" not in body + header
        assert b"123456789" not in body
        assert b"Deleted secret" not in body
        assert b"descr=" not in body
        root = ET.fromstring(body)
        assert len(root.findall(".//{%s}drawing" % W)) == 1
        assert len(root.findall(".//{%s}b" % W)) == 1
        assert len(root.findall(".//{%s}i" % W)) == 1
        assert b"srcRect" in body and b"anchor" in body
        assert b"* *" in header and b"Safe text" in body
        images = [n for n in names if n.startswith("word/media/")]
        assert len(images) == 1
        assert package.read(images[0]) != picture()
    reopened = open_document(output, DOCX_TYPE, tmp_path)
    assert "Nome: * *" in reopened.lines
    assert "NIF: *" in reopened.lines


def test_inline_image_page_is_rebuilt_and_original_pixels_disappear(tmp_path):
    source = tmp_path / "inline.pdf"
    with fitz.open() as document:
        page = document.new_page(width=300, height=400)
        page.insert_text((20, 30), "Safe text")
        with Image.open(io.BytesIO(picture())) as image:
            pixels = image.tobytes().hex().encode()
        stream = (document.xref_stream(page.get_contents()[0]) +
                  b"\nq\n120 0 0 100 50 180 cm\n"
                  b"BI /W 120 /H 100 /CS /RGB /BPC 8 /F /AHx ID\n" +
                  pixels + b">\nEI\nQ\n")
        xref = document.get_new_xref()
        document.update_object(xref, "<<>>")
        document.update_stream(xref, stream)
        page.set_contents(xref)
        document.save(source)
    adapter = open_document(source, "application/pdf", tmp_path)
    assert adapter.images[0].placements[0]["xref"] == 0
    output = tmp_path / "inline-output.pdf"
    adapter.render(output, [], {adapter.images[0].id: [region()]})
    with fitz.open(output) as document:
        assert document[0].rect == fitz.Rect(0, 0, 300, 400)
        assert document[0].get_text() == ""
        assert len(document[0].get_image_info()) == 1
        for xref in range(1, document.xref_length()):
            if document.xref_get_key(xref, "Subtype")[1] == "/Image":
                assert document.extract_image(xref)["width"] != 120


def test_word_nfc_split_runs_and_all_story_parts(tmp_path):
    source = tmp_path / "stories.docx"
    make_docx(source)
    with zipfile.ZipFile(source) as package:
        parts = {n: package.read(n) for n in package.namelist()}
    for name in ("footer1", "footnotes", "endnotes"):
        parts["word/%s.xml" % name] = (
            f'<w:root xmlns:w="{W}"><w:p><w:r><w:t>Jose</w:t></w:r>'
            '<w:r><w:t>\u0301 Silva</w:t></w:r></w:p></w:root>').encode()
    with zipfile.ZipFile(source, "w") as package:
        for name, data in parts.items():
            package.writestr(name, data)
    adapter = open_document(source, DOCX_TYPE, tmp_path)
    assert adapter.lines.count("José Silva") == 3
    edits, _ = masking.plan_masks(adapter.lines, [{
        "line": adapter.lines.index("José Silva") + 1, "text": "José Silva"}])
    output = tmp_path / "stories-output.docx"
    adapter.render(output, edits, {image.id: [] for image in adapter.images})
    reopened = open_document(output, DOCX_TYPE, tmp_path)
    assert reopened.lines.count("* *") == 3
    with zipfile.ZipFile(output) as package:
        assert "word/media/censored-old.png" not in package.namelist()


def test_word_decompression_and_xml_limits(tmp_path, monkeypatch):
    from documents import word
    source = tmp_path / "source.docx"
    make_docx(source)
    monkeypatch.setattr(word, "MAX_EXPANDED_BYTES", 10)
    with pytest.raises(DocumentError, match="demasiado grande"):
        open_document(source, DOCX_TYPE, tmp_path)
    with pytest.raises(DocumentError, match="DTD"):
        word.xml(b'<!DOCTYPE root [<!ENTITY value "SECRET">]>'
                 b'<root>&value;</root>')


@pytest.mark.parametrize("external,unsupported", [
    (True, False), (False, True)])
def test_docx_does_not_skip_unsupported_images(
        tmp_path, external, unsupported):
    source = tmp_path / "source.docx"
    make_docx(source, external=external, unsupported=unsupported)
    with pytest.raises(DocumentError):
        open_document(source, DOCX_TYPE, tmp_path)


def test_nfc_maps_every_original_character():
    lines, maps = mapped_lines("\nJose\u0301  \n", list(range(9)))
    assert lines == ["José"]
    assert maps[0][-1] == [4, 5]


def test_polygon_export_preserves_transparency_outside_mask(tmp_path):
    source = tmp_path / "transparent.png"
    source.write_bytes(picture(alpha=True))
    item = region()
    corners = [(.1, .1), (.6, .1), (.6, .6), (.1, .6)]
    item.keyframes[0].polygon = [Point(
        x=left[0] + (right[0] - left[0]) * step / 8,
        y=left[1] + (right[1] - left[1]) * step / 8)
        for left, right in zip(corners, corners[1:] + corners[:1])
        for step in range(8)]
    with Image.open(io.BytesIO(redact_image(source, [item]))) as censored:
        assert censored.getpixel((30, 30))[3] == 255
        assert censored.getpixel((72, 20))[3] == 90
        assert censored.getpixel((10, 10))[3] == 90


class FakeMedia:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def analyze(self, path, content_type, progress, instructions):
        self.calls.append(instructions)
        if self.fail:
            raise RuntimeError("PRIVATE DATA must not appear in errors")

        class Identity:
            def as_dict(self):
                return {"id": "test-model"}
        return "image", {}, [region()], Identity()

    def close(self):
        pass


def wait_document(api):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snapshot = api.get("/api/current").json()
        if snapshot["status"] not in {"processing", "exporting"}:
            return snapshot
        time.sleep(0.01)
    pytest.fail("Document processing timed out")


def test_document_api_review_export_feedback_and_cleanup(tmp_path):
    source = tmp_path / "source.pdf"
    make_pdf(source, text=False)
    processor = FakeMedia()
    app = user_validation.create_app(media_processor=processor)
    with TestClient(app) as api:
        response = api.post("/api/document", content=source.read_bytes(),
                            headers={"Content-Type": "application/pdf"})
        assert response.status_code == 200
        ready = wait_document(api)
        assert ready["kind"] == "document" and ready["text"] == ""
        image = ready["document"]["images"][0]
        image_url = image["source_url"] + "?attempt=1"
        preview = api.get(image_url)
        assert preview.status_code == 200
        assert preview.headers["cache-control"] == "no-store"
        assert api.get("/api/document/output").status_code == 409
        path = app.state.session.document.images[0].path
        manifest = {"attempt": 1, "regions": image["regions"]}
        route = image["source_url"] + "/regions"
        assert api.put(route, json=manifest).status_code == 200
        assert api.post("/api/reject", json={
            "attempt": 1, "reason": "Hide the signature",
            "document_id": ready["document"]["id"]}).status_code == 200
        ready = wait_document(api)
        assert ready["attempt"] == 2
        assert "Hide the signature" in processor.calls[-1]
        assert ready["history"][0]["regions"] == 1
        assert api.put(route, json=manifest).status_code == 409
        assert api.get(image_url).status_code == 409
        assert api.post("/api/approve", json={
            "attempt": 2,
            "document_id": ready["document"]["id"]}).status_code == 200
        approved = wait_document(api)
        assert approved["approved"], approved
        output = api.get("/api/document/output")
        assert output.status_code == 200
        assert output.headers["content-type"] == "application/pdf"
        assert api.put(route, json={
            **manifest, "attempt": 2}).status_code == 409
        api.post("/api/document", content=b"New text",
                 headers={"Content-Type": "text/plain"})
        assert not path.exists()
        assert api.get("/api/document/output").status_code == 409


def test_missing_model_and_analysis_failure_block_output(tmp_path):
    source = tmp_path / "source.pdf"
    make_pdf(source)
    for processor, expected in [(None, 503), (FakeMedia(fail=True), 200)]:
        app = user_validation.create_app(media_processor=processor)
        with TestClient(app) as api:
            response = api.post("/api/document", content=source.read_bytes(),
                                headers={"Content-Type": "application/pdf"})
            assert response.status_code == expected
            if processor:
                failed = wait_document(api)
                assert failed["status"] == "failed"
                assert "PRIVATE DATA" not in failed["error"]
            assert api.post("/api/approve").status_code == 409
            assert api.get("/api/document/output").status_code == 409


def test_export_failure_and_stale_approval_block_output(tmp_path):
    source = tmp_path / "source.pdf"
    make_pdf(source, text=False)
    app = user_validation.create_app(media_processor=FakeMedia())
    with TestClient(app) as api:
        def upload():
            api.post("/api/document", content=source.read_bytes(),
                     headers={"Content-Type": "application/pdf"})
            ready = wait_document(api)
            return {"attempt": ready["attempt"],
                    "document_id": ready["document"]["id"]}

        original_version = upload()
        current_version = upload()
        response = api.post("/api/approve", json=original_version)
        assert response.status_code == 409
        assert api.post("/api/reject", json={
            **original_version, "reason": "Old feedback"}).status_code == 409
        assert api.get("/api/current").json()["approved"] is False

        def fail_export(output, *args):
            output.write_bytes(b"Partial output")
            raise RuntimeError("PRIVATE ORIGINAL DATA")

        app.state.session.document.render = fail_export
        api.post("/api/approve", json=current_version)
        failed = wait_document(api)
        assert failed["status"] == "failed"
        assert failed["approved"] is False
        assert "PRIVATE" not in failed["error"]
        assert api.get("/api/document/output").status_code == 409
        output = app.state.session.document.folder / "anonymized.pdf"
        assert not output.exists()


def test_failure_on_second_image_does_not_commit_partial_masks(tmp_path):
    source = tmp_path / "source.pdf"
    make_pdf(source, text=False)
    with fitz.open(source) as document:
        second = io.BytesIO()
        Image.new("RGB", (100, 100), "red").save(second, "PNG")
        document[0].insert_image(fitz.Rect(300, 100, 390, 190),
                                 stream=second.getvalue())
        body = document.tobytes()

    class FailSecond(FakeMedia):
        def analyze(self, *args):
            if self.calls:
                raise RuntimeError("Second image failed")
            return super().analyze(*args)

    app = user_validation.create_app(media_processor=FailSecond())
    with TestClient(app) as api:
        api.post("/api/document", content=body,
                 headers={"Content-Type": "application/pdf"})
        failed = wait_document(api)
        assert failed["status"] == "failed"
        assert all(not image["regions"]
                   for image in failed["document"]["images"])
        assert api.get("/api/document/output").status_code == 409


def test_superseded_analysis_cannot_replace_new_session(tmp_path):
    source = tmp_path / "source.pdf"
    make_pdf(source)
    entered, release = threading.Event(), threading.Event()

    class SlowMedia(FakeMedia):
        def analyze(self, *args):
            entered.set()
            release.wait(3)
            return super().analyze(*args)

    app = user_validation.create_app(media_processor=SlowMedia())
    with TestClient(app) as api:
        api.post("/api/document", content=source.read_bytes(),
                 headers={"Content-Type": "application/pdf"})
        assert entered.wait(2)
        api.post("/api/document", content=b"New text",
                 headers={"Content-Type": "text/plain"})
        release.set()
        time.sleep(0.05)
        current = api.get("/api/current").json()
        assert current["kind"] == "text"
        assert current["text"] == "New text"

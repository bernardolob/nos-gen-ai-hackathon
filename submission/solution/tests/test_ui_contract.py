"""O contrato entre o backend da revisão e a UI.

A UI (``Lovable_UI_JunctionX/src/lib/review/``) e o backend
(``src/user_validation.py``) são escritos por equipas e ferramentas
diferentes. Estes testes leem os tipos e as chamadas TypeScript e confirmam
que coincidem com o backend, para uma mudança de um lado sem o outro falhar
aqui em vez de falhar no browser.
"""

import re
import sys
from pathlib import Path

import pytest

SOLUTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOLUTION / "src"))

pytest.importorskip("fastapi")
pytest.importorskip("fitz")

import user_validation  # noqa: E402

REVIEW = SOLUTION / "Lovable_UI_JunctionX" / "src" / "lib" / "review"
TYPES = REVIEW / "types.ts"
API = REVIEW / "api.ts"

pytestmark = pytest.mark.skipif(
    not TYPES.exists(), reason="a UI não está nesta cópia")


def interface_fields(name):
    """Os nomes dos campos de uma ``interface`` do types.ts."""
    source = TYPES.read_text(encoding="utf-8")
    match = re.search(
        r"export interface %s \{(.*?)\n\}" % name, source, re.DOTALL)
    assert match, "interface %s não encontrada" % name
    body = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)
    body = re.sub(r"//.*", "", body)
    return set(re.findall(r"^\s*(\w+)\??\s*:", body, re.MULTILINE))


def test_the_snapshot_fields_are_the_backends():
    backend = set(user_validation.ReviewSession().snapshot())
    assert interface_fields("Snapshot") == backend


def test_the_history_entry_fields_are_the_backends():
    backend = set(user_validation.RejectedVersion.model_fields)
    assert interface_fields("HistoryEntry") == backend


def test_every_route_the_ui_calls_exists_in_the_backend():
    app = user_validation.create_app()
    backend = {route.path for route in app.routes}
    called = set(re.findall(r'"(/api/[a-z/]+)"', API.read_text("utf-8")))
    assert called, "a UI não chama nenhuma rota?"
    assert called <= backend, called - backend


def test_the_ui_audio_limit_is_the_backends():
    types = TYPES.read_text(encoding="utf-8")
    ui = int(re.search(r"MAX_AUDIO_BYTES = (\d+) \* 1024 \* 1024", types)
             .group(1))
    assert ui * 1024 * 1024 <= user_validation.MAX_AUDIO_BYTES * 1.1
    assert ui * 1024 * 1024 >= user_validation.MAX_AUDIO_BYTES * 0.9


def test_the_ui_document_limit_is_the_backends():
    types = TYPES.read_text(encoding="utf-8")
    ui = int(re.search(r"MAX_UPLOAD_BYTES = (\d+) \* 1024 \* 1024", types)
             .group(1))
    assert ui * 1024 * 1024 <= user_validation.MAX_DOCUMENT_BYTES * 1.1
    assert ui * 1024 * 1024 >= user_validation.MAX_DOCUMENT_BYTES * 0.9


def test_the_ui_reason_limit_is_the_backends():
    import pipeline

    types = TYPES.read_text(encoding="utf-8")
    ui = int(re.search(r"MAX_REASON_CHARS = (\d+)", types).group(1))
    assert ui == pipeline.MAX_INSTRUCTIONS


def test_the_content_types_the_ui_sends_are_accepted():
    api = API.read_text(encoding="utf-8")
    sent = set(re.findall(r'"(audio/[a-z0-9-]+)"', api))
    sent_audio = {t for t in sent if t in ("audio/mpeg", "audio/mp4",
                                           "audio/wav")}
    assert sent_audio == {"audio/mpeg", "audio/mp4", "audio/wav"}
    for kind in sent_audio:
        assert kind in user_validation.AUDIO_TYPES


def test_the_ui_image_and_video_limits_are_the_backends():
    types = TYPES.read_text(encoding="utf-8")
    image = int(re.search(r"MAX_IMAGE_BYTES = (\d+) \* 1024 \* 1024", types)
                .group(1))
    video = int(re.search(r"MAX_VIDEO_BYTES = (\d+) \* 1024 \* 1024", types)
                .group(1))
    assert image * 1024 * 1024 <= user_validation.MAX_IMAGE_BYTES * 1.1
    assert image * 1024 * 1024 >= user_validation.MAX_IMAGE_BYTES * 0.9
    assert video * 1024 * 1024 <= user_validation.MAX_VIDEO_BYTES * 1.1
    assert video * 1024 * 1024 >= user_validation.MAX_VIDEO_BYTES * 0.9
    seconds = int(re.search(r"MAX_VIDEO_SECONDS = (\d+)", types).group(1))
    from media.pipeline import MAX_VIDEO_DURATION_MS
    assert seconds * 1000 == MAX_VIDEO_DURATION_MS


def test_the_ui_region_vocabulary_is_the_backends():
    from categories import CONFIDENCE_LEVELS
    from media.regions import REGION_KINDS, REGION_SOURCES
    types = TYPES.read_text(encoding="utf-8")

    def union(name):
        body = re.search(r"export type %s =(.*?);" % name, types,
                         re.DOTALL).group(1)
        return set(re.findall(r'"(\w+)"', body))

    assert union("RegionKind") == REGION_KINDS
    assert union("RegionSource") == REGION_SOURCES
    assert union("Confidence") == set(CONFIDENCE_LEVELS)


def test_the_media_region_fields_are_the_backends():
    from media.regions import MediaRegion
    assert interface_fields("MediaRegion") == set(MediaRegion.model_fields)

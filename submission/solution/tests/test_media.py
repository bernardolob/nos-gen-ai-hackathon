"""Multimodal capability, geometry and review API tests."""

import json
import base64
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.analyzer import (  # noqa: E402
    GeminiMediaAnalyzer,
    ProviderDetection,
    _to_region,
)
from media.capabilities import (  # noqa: E402
    MediaConfigurationError,
    MediaModel,
    media_model_from_env,
)
from media.regions import (  # noqa: E402
    Box,
    MediaRegion,
    Point,
    RegionKeyframe,
    padded_box,
    transform_polygon,
)
from media.pipeline import (  # noqa: E402
    MediaProcessor,
    _capture_time_ms,
    _extend_face_tracks_to_edges,
    _link_regions,
    _merge_face_regions,
    _merge_image_regions,
    _pixelate_video_regions,
    _polygon_from_face_classes,
    _prefer_detected_faces,
    _probe_video,
    _refine_region_polygons,
    _refine_model_image_faces,
    _render_image,
    _render_video,
    _segment_box_polygon,
    _track_manual_region,
    _track_video_objects,
    _time_regions,
    _smooth_region,
)


def face_polygon(center_x=0.4, center_y=0.4, radius_x=0.2,
                 radius_y=0.25):
    return [Point(
        x=center_x + math.sin(index * 2 * math.pi / 32) * radius_x,
        y=center_y - math.cos(index * 2 * math.pi / 32) * radius_y,
    ) for index in range(32)]


def region(source="user"):
    return MediaRegion(
        category="identificacao", kind="other",
        reason="Região de teste.", confidence="certo", source=source,
        start_ms=0, end_ms=1000,
        keyframes=[
            RegionKeyframe(time_ms=0, box=Box(
                x=0.1, y=0.2, width=0.2, height=0.2)),
            RegionKeyframe(time_ms=1000, box=Box(
                x=0.3, y=0.4, width=0.2, height=0.2)),
        ],
    )


def test_only_allowlisted_multimodal_models_are_accepted():
    model = media_model_from_env({
        "GEMINI_GATEWAY_URL": "https://gateway.example",
        "GEMINI_GATEWAY_ORIGIN": "http://localhost:5173",
        "GEMINI_MEDIA_MODEL": "gemini-3.5-flash-lite",
    })
    assert model.capabilities == ("image", "video", "structured_output")
    with pytest.raises(MediaConfigurationError):
        media_model_from_env({
            "GEMINI_GATEWAY_URL": "https://gateway.example",
            "GEMINI_GATEWAY_ORIGIN": "http://localhost:5173",
            "GEMINI_MEDIA_MODEL": "text-only-model",
        })
    with pytest.raises(MediaConfigurationError):
        media_model_from_env({"GEMINI_MEDIA_MODEL": "gemini-3.5-flash-lite"})


def test_boxes_are_padded_clamped_and_interpolated():
    expanded = padded_box(Box(x=0, y=0.9, width=0.1, height=0.1))
    assert expanded.x == 0
    assert expanded.y + expanded.height == pytest.approx(1)
    middle = region().box_at(500)
    assert middle is not None
    assert middle.x == pytest.approx(0.2)
    assert middle.y == pytest.approx(0.3)
    assert region().box_at(1001) is None


def test_face_polygons_validate_interpolate_and_transform():
    polygon = face_polygon()
    item = region(source="face_detector")
    item.kind = "face"
    item.keyframes = [
        RegionKeyframe(
            time_ms=0, box=Box(x=0.2, y=0.15, width=0.4, height=0.5),
            polygon=polygon),
        RegionKeyframe(
            time_ms=1000, box=Box(x=0.4, y=0.25, width=0.4, height=0.5),
            polygon=[Point(x=point.x + 0.2, y=point.y + 0.1)
                     for point in polygon]),
    ]
    middle = item.polygon_at(500)
    assert middle is not None and len(middle) == 32
    assert middle[0].x == pytest.approx(polygon[0].x + 0.1)
    assert middle[0].y == pytest.approx(polygon[0].y + 0.05)
    moved = transform_polygon(
        polygon, item.keyframes[0].box,
        Box(x=0.3, y=0.2, width=0.2, height=0.25))
    assert moved is not None and len(moved) == 32
    assert moved[0].x == pytest.approx(0.4)
    item.keyframes[0].polygon = None
    assert item.polygon_at(500) is None
    assert item.polygon_at(1000) is not None
    with pytest.raises(ValueError, match="exactly 32"):
        RegionKeyframe(
            time_ms=0, box=item.keyframes[0].box, polygon=polygon[:-1])
    with pytest.raises(ValueError, match="fallback box"):
        RegionKeyframe(
            time_ms=0, box=Box(x=0.3, y=0.2, width=0.2, height=0.2),
            polygon=polygon)


def test_face_parser_mask_becomes_a_safe_clockwise_polygon():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    classes = np.zeros((100, 100), dtype=np.uint8)
    cv2.ellipse(classes, (50, 50), (24, 34), 0, 0, 360, 1, -1)
    polygon = _polygon_from_face_classes(
        classes, (0, 0, 100, 100),
        Box(x=0.25, y=0.16, width=0.5, height=0.68),
        100, 100, cv2, np)
    assert polygon is not None and len(polygon) == 32
    assert polygon[0].y == min(point.y for point in polygon)
    signed_area = sum(
        point.x * polygon[(index + 1) % 32].y -
        polygon[(index + 1) % 32].x * point.y
        for index, point in enumerate(polygon))
    assert signed_area > 0

    classes[:, :28] = 1
    assert _polygon_from_face_classes(
        classes, (0, 0, 100, 100),
        Box(x=0.25, y=0.16, width=0.5, height=0.68),
        100, 100, cv2, np) is None


def test_generic_region_is_refined_to_a_fixed_close_fit_polygon():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    frame = np.full((160, 200, 3), 220, dtype=np.uint8)
    cv2.ellipse(frame, (100, 80), (45, 55), 15, 0, 360,
                (30, 60, 180), -1)
    broad = Box(x=0.22, y=0.12, width=0.56, height=0.76)
    polygon = _segment_box_polygon(
        frame, broad, "other", cv2, np)
    assert polygon is not None and len(polygon) == 32
    assert min(point.x for point in polygon) > broad.x
    assert max(point.x for point in polygon) < broad.x + broad.width
    assert min(point.y for point in polygon) > broad.y
    assert max(point.y for point in polygon) < broad.y + broad.height


def test_generic_refinement_keeps_rectangle_when_segmentation_is_uncertain():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    encoded, jpeg = cv2.imencode(".jpg", frame)
    assert encoded
    item = region(source="gemini")
    item.keyframes = [RegionKeyframe(
        time_ms=0,
        box=Box(x=0.2, y=0.2, width=0.6, height=0.6))]
    original_box = item.keyframes[0].box
    _refine_region_polygons(jpeg.tobytes(), [item])
    assert item.keyframes[0].polygon is None
    assert item.keyframes[0].box == original_box


def test_face_detector_replaces_a_whole_image_model_face_box():
    _, broad = _to_region(ProviderDetection(
        frame_id=0, box_2d=[70, 30, 980, 970],
        category="biometrico", kind="face",
        reason="Rosto visível.", confidence="certo"))
    _, document = _to_region(ProviderDetection(
        frame_id=0, box_2d=[100, 100, 300, 300],
        category="identificacao", kind="identity_document",
        reason="Documento visível.", confidence="certo"))
    detected = region(source="face_detector")
    detected.kind = "face"
    detected.start_ms = detected.end_ms = 0
    detected.keyframes = [RegionKeyframe(
        time_ms=0, box=Box(x=0.28, y=0.32, width=0.25, height=0.25))]
    kept = _prefer_detected_faces([broad, document], [detected])
    assert kept == [document]
    _, tight = _to_region(ProviderDetection(
        frame_id=0, box_2d=[300, 300, 500, 500],
        category="biometrico", kind="face",
        reason="Rosto visível.", confidence="certo"))
    assert tight.keyframes[0].box.width == pytest.approx(0.208)


@pytest.mark.parametrize("first_kind,residual_kind", [
    ("identity_document", None),
    (None, None),
    ("face", None),
    (None, "face"),
])
def test_image_masks_require_model_detection_and_receive_instructions(
        tmp_path, monkeypatch, first_kind, residual_kind):
    from media import pipeline
    Image = pytest.importorskip("PIL.Image")
    path = tmp_path / "scene.png"
    Image.new("RGB", (200, 200), "white").save(path)
    local = region(source="face_detector")
    local.kind = "face"
    local.start_ms = local.end_ms = 0
    local.keyframes = [RegionKeyframe(
        time_ms=0, box=Box(x=0.7, y=0.7, width=0.1, height=0.1))]
    monkeypatch.setattr(pipeline, "_detect_image_faces", lambda _: [local])

    class Analyzer:
        def __init__(self):
            self.calls = []

        def verify(self):
            return MediaModel("gemini-3.5-flash-lite",
                              ("image", "video", "structured_output"), True)

        def analyze(self, frames, *, residual=False, instructions=None):
            self.calls.append((residual, instructions))
            kind = residual_kind if residual else first_kind
            if kind is None:
                return []
            item = region(source="gemini")
            item.kind = kind
            item.start_ms = item.end_ms = 0
            item.keyframes = [item.keyframes[0]]
            return [(0, item)]

    analyzer = Analyzer()
    _, _, masks, _ = MediaProcessor(analyzer).analyze(
        path, "image/png", instructions="Respect reviewer corrections.")
    expected = [kind for kind in (first_kind, residual_kind) if kind]
    assert [mask.kind for mask in masks] == expected
    assert all(mask.source == "gemini" for mask in masks)
    assert analyzer.calls == [
        (False, "Respect reviewer corrections."),
        (True, "Respect reviewer corrections."),
    ]


def test_image_face_refinement_keeps_model_confidence_and_unmatched_faces():
    model = region(source="gemini")
    model.kind = "face"
    model.confidence = "incerto"
    model.start_ms = model.end_ms = 0
    model.keyframes = [model.keyframes[0]]
    local = model.model_copy(deep=True)
    local.source = "face_detector"
    local.confidence = "certo"
    local.keyframes[0].box = Box(x=0.11, y=0.21, width=0.18, height=0.18)
    unrelated = local.model_copy(deep=True)
    unrelated.keyframes[0].box = Box(x=0.7, y=0.7, width=0.1, height=0.1)
    refined, = _refine_model_image_faces([model], [local, unrelated])
    assert refined.keyframes[0].box == local.keyframes[0].box
    assert refined.source == "gemini"
    assert refined.confidence == "incerto"
    assert refined.reason == model.reason
    assert model.keyframes[0].box != refined.keyframes[0].box
    assert _refine_model_image_faces([model], [unrelated]) == [model]


def test_face_deduplication_uses_the_detector_box_at_model_time():
    detected = region(source="face_detector")
    detected.kind = "face"
    detected.keyframes = [
        RegionKeyframe(
            time_ms=0,
            box=Box(x=0.1, y=0.1, width=0.2, height=0.2)),
        RegionKeyframe(
            time_ms=1000,
            box=Box(x=0.5, y=0.5, width=0.2, height=0.2)),
    ]
    model = region(source="gemini")
    model.kind = "face"
    model.start_ms, model.end_ms = 750, 1000
    model.keyframes = [RegionKeyframe(
        time_ms=1000,
        box=Box(x=0.52, y=0.52, width=0.16, height=0.16))]
    assert _prefer_detected_faces([model], [detected]) == []


def test_face_track_covers_first_and_final_display_intervals():
    face = region(source="face_detector")
    face.kind = "face"
    face.start_ms, face.end_ms = 33, 1267
    face.keyframes = [RegionKeyframe(
        time_ms=1167, box=Box(x=0.3, y=0.45, width=0.3, height=0.3))]
    _extend_face_tracks_to_edges([face], 1267, 1300, 30)
    assert face.box_at(0) is not None
    assert face.box_at(1300) == face.keyframes[0].box
    assert face.start_ms == 0
    assert face.end_ms == 1300

    lost_early = face.model_copy(deep=True)
    lost_early.end_ms = 500
    _extend_face_tracks_to_edges([lost_early], 1267, 1300, 30)
    assert lost_early.end_ms == 500


def test_face_tracks_do_not_merge_different_detection_sources():
    detected = region(source="face_detector")
    detected.kind = "face"
    detected.start_ms = detected.end_ms = 0
    model = detected.model_copy(deep=True)
    model.source = "gemini"
    model.start_ms = model.end_ms = 500
    model.keyframes[0].time_ms = 500
    assert len(_link_regions([detected, model], 1300)) == 2


def test_overlapping_detection_windows_link_by_observation_time():
    first = region(source="gemini")
    first.kind = "text"
    first.start_ms, first.end_ms = 0, 750
    first.keyframes = [RegionKeyframe(
        time_ms=0, box=Box(x=0.1, y=0.2, width=0.2, height=0.2))]
    second = first.model_copy(deep=True)
    second.start_ms, second.end_ms = 250, 1250
    second.keyframes = [RegionKeyframe(
        time_ms=500, box=Box(x=0.14, y=0.2, width=0.2, height=0.2))]
    tracks = _link_regions([first, second], 1300)
    assert len(tracks) == 1
    assert [key.time_ms for key in tracks[0].keyframes] == [0, 500]


def test_video_detection_does_not_activate_before_its_observed_frame():
    item = region(source="gemini")
    item.kind = "identity_document"
    observed, = _time_regions(
        [(7, item)], [(7, 2000, b"jpeg")], {"duration_ms": 4000})
    assert observed.box_at(1999) is None
    assert observed.start_ms == observed.end_ms == 2000
    assert observed.keyframes[0].time_ms == 2000


def test_residual_duplicates_merge_without_losing_existing_keyframes():
    item = region(source="gemini")
    item.kind = "identity_document"
    item.start_ms, item.end_ms = 1000, 2000
    item.keyframes = [RegionKeyframe(
        time_ms=time_ms, box=Box(x=x, y=0.3, width=0.2, height=0.2))
        for time_ms, x in [(1000, 0.1), (1500, 0.15), (2000, 0.2)]]
    residual = item.model_copy(deep=True)
    residual.start_ms = residual.end_ms = 1500
    residual.keyframes = [RegionKeyframe(
        time_ms=1500, box=Box(x=0.17, y=0.3, width=0.2, height=0.2))]
    tracks = _link_regions([item, residual], 3000)
    assert len(tracks) == 1
    assert [key.time_ms for key in tracks[0].keyframes] == [1000, 1500, 2000]
    middle = tracks[0].box_at(1500)
    assert middle.x == pytest.approx(0.15)
    assert middle.x + middle.width == pytest.approx(0.37)


def test_document_bounds_do_not_shrink_or_move_to_future_positions():
    Image = pytest.importorskip("PIL.Image")
    import io
    image = Image.new("RGB", (100, 100), "white")
    for x in range(40, 65):
        for y in range(20, 80):
            image.putpixel((x, y), (10, 80, 150))
    data = io.BytesIO()
    image.save(data, format="JPEG")
    item = region(source="gemini")
    item.kind = "identity_document"
    item.keyframes[0].box = Box(x=0.15, y=0.15, width=0.55, height=0.7)
    original = item.model_copy(deep=True)
    _refine_region_polygons(data.getvalue(), [item])
    assert item == original
    assert _smooth_region(item) == original


def test_video_object_flow_follows_motion_and_stops_when_object_disappears(
        tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    source = tmp_path / "appearing-card.mp4"
    writer = cv2.VideoWriter(
        str(source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 100))
    if not writer.isOpened():
        pytest.skip("OpenCV video writer is unavailable")
    texture = np.random.default_rng(12).integers(
        30, 255, (32, 48, 3), dtype=np.uint8)
    for index in range(30):
        frame = np.zeros((100, 160, 3), dtype=np.uint8)
        if 10 <= index < 25:
            left = 20 + (index - 10) * 2
            frame[30:62, left:left + 48] = texture
        writer.write(frame)
    writer.release()
    item = region(source="gemini")
    item.kind = "identity_document"
    item.start_ms, item.end_ms = 1200, 1800
    item.keyframes = [
        RegionKeyframe(time_ms=time_ms, box=Box(
            x=left / 160, y=0.3, width=48 / 160, height=0.32))
        for time_ms, left in [(1200, 24), (1800, 36)]
    ]
    uncertain_times = set()
    tracked, = _track_video_objects(
        source, [item], {"fps": 10, "duration_ms": 3000},
        uncertain_times=uncertain_times)
    assert tracked.box_at(1199) is None
    assert tracked.box_at(1500).x == pytest.approx(30 / 160, abs=0.015)
    assert tracked.box_at(2200).x == pytest.approx(44 / 160, abs=0.015)
    assert tracked.box_at(2600) is None
    assert tracked.end_ms <= 2500
    assert len(tracked.keyframes) >= 10
    assert 2500 in uncertain_times
    assert min(uncertain_times) >= 1200

    class NegativeRecoveryAnalyzer:
        def __init__(self):
            self.frames = []

        def analyze(self, frames, **options):
            self.frames.extend(frames)
            return []

    analyzer = NegativeRecoveryAnalyzer()
    recovered, = MediaProcessor(analyzer)._recover_video_objects(
        source, [item], [item], [], [(0, 1200, b""), (1, 1800, b"")],
        {"fps": 10, "duration_ms": 3000}, [], None, lambda *args: None)
    assert analyzer.frames
    assert all(frame[1].startswith(b"\xff\xd8") for frame in analyzer.frames)
    assert recovered.box_at(2600) is None


def test_tracking_assignment_is_one_to_one_and_stops_at_scene_cuts():
    def observed(time_ms, x):
        item = region(source="face_detector")
        item.kind = "face"
        item.start_ms = item.end_ms = time_ms
        item.keyframes = [RegionKeyframe(
            time_ms=time_ms,
            box=Box(x=x, y=0.2, width=0.12, height=0.12))]
        return item

    tracks = _link_regions([
        observed(0, 0.1), observed(0, 0.6),
        observed(100, 0.12), observed(100, 0.58),
    ], 500)
    assert len(tracks) == 2
    assert sorted(len(track.keyframes) for track in tracks) == [2, 2]
    split = _link_regions([
        observed(0, 0.1), observed(100, 0.11),
    ], 500, scene_cuts=[50])
    assert len(split) == 2


def test_decoder_timestamp_is_preferred_with_monotonic_fallback():
    class Capture:
        def __init__(self, value):
            self.value = value

        def get(self, _property):
            return self.value

    assert _capture_time_ms(Capture(123.4), 4, 30, 100) == 123
    assert _capture_time_ms(Capture(0), 4, 30, 100) == 133


def test_manual_box_tracks_motion_forward_and_backward(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    source = tmp_path / "moving.mp4"
    writer = cv2.VideoWriter(
        str(source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 100))
    if not writer.isOpened():
        pytest.skip("OpenCV video writer is unavailable")
    for index in range(30):
        frame = np.zeros((100, 160, 3), dtype=np.uint8)
        left = 10 + index * 2
        for row in range(4):
            for column in range(4):
                color = 255 if (row + column) % 2 else 80
                frame[25 + row * 7:32 + row * 7,
                      left + column * 7:left + 7 + column * 7] = color
        writer.write(frame)
    writer.release()
    item = region(source="user")
    item.start_ms, item.end_ms = 0, 2900
    item.keyframes = [RegionKeyframe(
        time_ms=1500,
        box=Box(x=40 / 160, y=25 / 100, width=28 / 160, height=28 / 100))]
    tracked = _track_manual_region(source, item, 3000, 1500)
    assert len(tracked.keyframes) >= 20
    assert tracked.keyframes[0].box.x < tracked.keyframes[-1].box.x
    assert tracked.keyframes[-1].box.x - tracked.keyframes[0].box.x > 0.2
    assert tracked.start_ms == 0
    assert tracked.end_ms == 3000


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_probe_video_uses_display_orientation(tmp_path):
    pytest.importorskip("cv2")
    raw, rotated = tmp_path / "raw.mp4", tmp_path / "rotated.mp4"
    assert subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        "testsrc2=s=64x32:d=0.3:r=10", "-c:v", "libx264", str(raw),
    ], capture_output=True).returncode == 0
    assert subprocess.run([
        "ffmpeg", "-y", "-display_rotation:v:0", "90",
        "-i", str(raw), "-c", "copy", str(rotated),
    ], capture_output=True).returncode == 0
    info = _probe_video(rotated)
    assert (info["width"], info["height"]) == (32, 64)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self):
        return self.payload


class FakeOpener:
    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if request.full_url.endswith("/capabilities"):
            return FakeResponse({"model": {
                "id": "gemini-3.5-flash-lite",
                "capabilities": ["image", "video", "structured_output"],
                "verified": True,
            }})
        return FakeResponse({"detections": [{
            "frame_id": 7,
            "box_2d": [100, 200, 400, 600],
            "category": "identificacao",
            "kind": "identity_document",
            "reason": "Documento de identificação visível.",
            "confidence": "certo",
        }]})


def test_media_analyzer_uses_image_parts_and_structured_output():
    opener = FakeOpener()
    analyzer = GeminiMediaAnalyzer(MediaModel(
        "gemini-3.5-flash-lite",
        ("image", "video", "structured_output")),
        gateway_url="https://gateway.example",
        origin="http://localhost:5173",
        opener=opener)
    found = analyzer.analyze([(7, b"\xff\xd8\xffjpeg")])
    assert found[0][0] == 7
    assert found[0][1].kind == "identity_document"
    assert opener.requests[0][0].full_url.endswith(
        "/api/v1/media/capabilities")
    request = opener.requests[1][0]
    assert request.full_url.endswith("/api/v1/media/analyze")
    assert request.headers["Origin"] == "http://localhost:5173"
    payload = json.loads(request.data)
    assert set(payload) == {"prompt", "frames"}
    assert payload["frames"][0]["frame_id"] == 7
    assert base64.b64decode(payload["frames"][0]["data"]) == (
        b"\xff\xd8\xffjpeg")
    assert "GEMINI_API_KEY" not in request.headers


def test_image_render_pixelates_inside_region_and_strips_metadata(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    np = pytest.importorskip("numpy")
    source, output = tmp_path / "source.jpg", tmp_path / "output.jpg"
    image = Image.new("RGB", (100, 80), "white")
    for x in range(10, 60):
        for y in range(8, 48):
            base = ((180, 70, 55), (65, 150, 95), (55, 95, 180))[
                min(2, (x - 10) // 17)]
            noise = 25 if (x + y) % 2 else -25
            image.putpixel((x, y), tuple(
                max(0, min(255, channel + noise)) for channel in base))
    exif = Image.Exif()
    exif[315] = "Pessoa identificável"
    image.save(source, "JPEG", exif=exif)
    item = region()
    item.start_ms = item.end_ms = 0
    item.keyframes = [RegionKeyframe(
        time_ms=0,
        box=Box(x=0.1, y=0.1, width=0.5, height=0.5))]
    _render_image(source, output, [item], "image/jpeg")
    with Image.open(output) as result:
        with Image.open(source) as original:
            assert result.getpixel((30, 30)) != original.getpixel((30, 30))
        pixels = np.asarray(result.convert("RGB"))
        # Adjacent pixels inside a mosaic cell match, while cells retain
        # different broad colors and none of the source's fine pattern.
        assert np.max(np.abs(pixels[25, 15].astype(int) -
                             pixels[25, 18].astype(int))) < 12
        assert np.max(np.abs(pixels[25, 16].astype(int) -
                             pixels[25, 51].astype(int))) > 25
        assert min(result.getpixel((30, 30))) > 10
        assert min(result.getpixel((80, 60))) > 240
        assert len(result.getexif()) == 0


def test_image_polygon_does_not_pixelate_its_bounding_box_corners(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    source, output = tmp_path / "source.png", tmp_path / "output.png"
    image = Image.new("RGB", (100, 100), "white")
    for x in range(20, 80):
        for y in range(15, 85):
            image.putpixel((x, y), (
                (x * 5 + y) % 255,
                (y * 7 + x) % 255,
                (x * 3 + y * 2) % 255,
            ))
    image.save(source)
    polygon = face_polygon(0.5, 0.5, 0.3, 0.35)
    item = region(source="face_detector")
    item.kind = "face"
    item.start_ms = item.end_ms = 0
    item.keyframes = [RegionKeyframe(
        time_ms=0,
        box=Box(x=0.2, y=0.15, width=0.6, height=0.7),
        polygon=polygon)]
    _render_image(source, output, [item], "image/png")
    with Image.open(source) as original, Image.open(output) as result:
        assert result.getpixel((50, 50)) != original.getpixel((50, 50))
        assert result.getpixel((21, 16)) == original.getpixel((21, 16))
        assert result.getpixel((79, 16)) == original.getpixel((79, 16))


def test_video_frame_polygon_keeps_pixels_outside_its_contour():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    rows, columns = np.indices((100, 100))
    frame = np.stack((
        (columns * 5 + rows) % 255,
        (rows * 7 + columns) % 255,
        (columns * 3 + rows * 2) % 255,
    ), axis=-1).astype(np.uint8)
    original = frame.copy()
    polygon = face_polygon(0.5, 0.5, 0.3, 0.35)
    item = region(source="face_detector")
    item.kind = "face"
    item.start_ms = item.end_ms = 0
    item.keyframes = [RegionKeyframe(
        time_ms=0,
        box=Box(x=0.2, y=0.15, width=0.6, height=0.7),
        polygon=polygon)]
    _pixelate_video_regions(frame, [item], 0, cv2, np)
    assert not np.array_equal(frame[50, 50], original[50, 50])
    assert np.array_equal(frame[16, 21], original[16, 21])
    assert np.array_equal(frame[16, 79], original[16, 79])


def _face_item(x=0.2, y=0.15, width=0.6, height=0.7):
    item = region(source="face_detector")
    item.kind = "face"
    item.start_ms = item.end_ms = 0
    item.keyframes = [RegionKeyframe(
        time_ms=0, box=Box(x=x, y=y, width=width, height=height))]
    return item


def _textured_frame(np, size=200):
    rows, columns = np.indices((size, size))
    return np.stack((
        (columns * 5 + rows * 2) % 255,
        (rows * 7 + columns) % 255,
        (columns * 3 + rows * 4) % 255,
    ), axis=-1).astype(np.uint8)


def _face_track(boxes, start=0, source="face_detector", reason="Rosto."):
    """A face region with one keyframe per (time_ms, (x, y, w, h))."""
    keys = [RegionKeyframe(time_ms=time, box=Box(
        x=x, y=y, width=w, height=h)) for time, (x, y, w, h) in boxes]
    item = region(source=source)
    item.kind = "face"
    item.category = "biometrico"
    item.reason = reason
    item.start_ms, item.end_ms = start, keys[-1].time_ms
    item.keyframes = keys
    return item


def test_a_smaller_face_box_inside_a_bigger_one_is_the_same_face():
    big = _face_track([(0, (0.30, 0.40, 0.40, 0.25)),
                       (1000, (0.35, 0.40, 0.40, 0.25))])
    small = _face_track([(0, (0.42, 0.45, 0.20, 0.11)),
                         (1000, (0.47, 0.45, 0.20, 0.11))],
                        source="gemini", reason="Rosto identificável.")
    merged = _merge_face_regions([big, small])
    assert len(merged) == 1
    face = merged[0]
    assert face.source == "gemini"
    assert face.reason == "Rosto identificável."
    first = face.keyframes[0].box
    assert (first.x, first.y, first.width, first.height) == pytest.approx(
        (0.30, 0.40, 0.40, 0.25))  # the union is the bigger box
    assert face.start_ms == 0 and face.end_ms == 1000


def test_pieces_of_a_split_face_track_become_one():
    first = _face_track([(0, (0.31, 0.42, 0.42, 0.23)),
                         (200, (0.33, 0.42, 0.42, 0.23))])
    second = _face_track([(200, (0.34, 0.43, 0.40, 0.22)),
                          (2000, (0.40, 0.43, 0.40, 0.22))], start=200)
    merged = _merge_face_regions([first, second])
    assert len(merged) == 1
    assert (merged[0].start_ms, merged[0].end_ms) == (0, 2000)


def test_a_piece_that_drifts_off_the_face_at_its_end_still_joins_it():
    # Seen on a real clip: the first 0.2 s of the face drifted to the right.
    drifting = _face_track([(0, (0.31, 0.42, 0.42, 0.23)),
                            (100, (0.56, 0.45, 0.24, 0.14)),
                            (200, (0.66, 0.45, 0.17, 0.10))])
    steady = _face_track([(200, (0.29, 0.39, 0.44, 0.25)),
                          (300, (0.30, 0.41, 0.45, 0.25)),
                          (500, (0.29, 0.44, 0.47, 0.27))], start=200)
    assert len(_merge_face_regions([drifting, steady])) == 1


def test_two_different_faces_stay_two():
    left = _face_track([(0, (0.05, 0.3, 0.2, 0.2)),
                        (1000, (0.05, 0.3, 0.2, 0.2))])
    right = _face_track([(0, (0.65, 0.3, 0.2, 0.2)),
                         (1000, (0.65, 0.3, 0.2, 0.2))])
    assert len(_merge_face_regions([left, right])) == 2


def test_the_same_spot_at_different_times_is_not_merged():
    early = _face_track([(0, (0.3, 0.3, 0.2, 0.2)),
                         (500, (0.3, 0.3, 0.2, 0.2))])
    late = _face_track([(3000, (0.3, 0.3, 0.2, 0.2)),
                        (4000, (0.3, 0.3, 0.2, 0.2))], start=3000)
    assert len(_merge_face_regions([early, late])) == 2


def test_only_faces_are_merged():
    document = region()
    document.keyframes = [RegionKeyframe(time_ms=0, box=Box(
        x=0.3, y=0.4, width=0.4, height=0.25)), RegionKeyframe(
        time_ms=1000, box=Box(x=0.3, y=0.4, width=0.4, height=0.25))]
    twin = document.model_copy(deep=True)
    face = _face_track([(0, (0.35, 0.45, 0.2, 0.1)),
                        (1000, (0.35, 0.45, 0.2, 0.1))])
    merged = _merge_face_regions([document, twin, face])
    assert [item.kind for item in merged].count("other") == 2
    assert [item.kind for item in merged].count("face") == 1


def test_the_merged_mask_never_loses_part_of_a_face():
    # Two overlapping detections of one face that disagree about its edges:
    # the result covers both at every instant.
    left = _face_track([(0, (0.30, 0.30, 0.30, 0.30)),
                        (1000, (0.30, 0.30, 0.30, 0.30))])
    right = _face_track([(0, (0.35, 0.33, 0.30, 0.30)),
                         (1000, (0.35, 0.33, 0.30, 0.30))])
    face = _merge_face_regions([left, right])[0]
    for instant in (0, 500, 1000):
        box = face.box_at(instant)
        assert box.x <= 0.30 and box.y <= 0.30
        assert box.x + box.width >= 0.65 - 1e-9
        assert box.y + box.height >= 0.63 - 1e-9


def test_duplicate_faces_in_a_photo_become_one():
    big = _face_track([(0, (0.30, 0.20, 0.40, 0.30))])
    nested = _face_track([(0, (0.40, 0.25, 0.20, 0.15))], source="gemini")
    other = region()
    other.kind = "plate"
    other.keyframes = other.keyframes[:1]
    merged = _merge_image_regions([big, nested, other])
    assert sorted(item.kind for item in merged) == ["face", "plate"]


def test_a_face_is_blurred_smoothly_not_as_a_grid_of_cells():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    frame = _textured_frame(np)
    _pixelate_video_regions(frame, [_face_item()], 0, cv2, np)
    core = frame[70:130, 70:130].astype(int)
    # Neighbouring pixels in the middle of the face differ little: there are
    # no hard cell borders (a nearest-neighbour mosaic jumps at every cell).
    assert np.max(np.abs(np.diff(core, axis=1))) < 12
    assert np.max(np.abs(np.diff(core, axis=0))) < 12


def test_a_face_blur_follows_the_face_not_the_whole_box():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    frame = _textured_frame(np)
    original = frame.copy()
    # The box covers 40..160 horizontally and 30..170 vertically.
    _pixelate_video_regions(frame, [_face_item()], 0, cv2, np)
    assert not np.array_equal(frame[100, 100], original[100, 100])
    assert not np.array_equal(frame[100, 45], original[100, 45])
    # The corners of the box are outside the face ellipse: untouched.
    for row, column in ((32, 42), (32, 158), (168, 42), (168, 158)):
        assert np.array_equal(frame[row, column], original[row, column])
    # And nothing far outside the box changes (the ellipse is a little larger
    # than the box, and its soft edge reaches a few pixels more).
    assert np.array_equal(frame[:8], original[:8])
    assert np.array_equal(frame[:, :18], original[:, :18])


def test_a_face_blur_removes_the_fine_detail():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    rows, columns = np.indices((200, 200))
    plain = np.full((200, 200, 3), 120, dtype=np.uint8)
    fine = plain.copy()
    # A one-pixel checkerboard: the finest detail a face could have.
    fine[(rows + columns) % 2 == 0] = 40
    fine[(rows + columns) % 2 == 1] = 200
    _pixelate_video_regions(plain, [_face_item()], 0, cv2, np)
    _pixelate_video_regions(fine, [_face_item()], 0, cv2, np)
    assert np.max(np.abs(
        plain[70:130, 70:130].astype(int) - fine[70:130, 70:130])) < 6


def test_a_very_small_face_falls_back_to_the_mosaic():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    frame = _textured_frame(np, 100)
    original = frame.copy()
    item = _face_item(x=0.4, y=0.4, width=0.05, height=0.05)
    _pixelate_video_regions(frame, [item], 0, cv2, np)
    assert not np.array_equal(frame[41:44, 41:44], original[41:44, 41:44])


def test_a_face_in_a_photo_is_blurred_the_same_way(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    np = pytest.importorskip("numpy")
    source, output = tmp_path / "source.png", tmp_path / "output.png"
    Image.fromarray(_textured_frame(np)).save(source)
    _render_image(source, output, [_face_item()], "image/png")
    with Image.open(source) as original, Image.open(output) as result:
        before = np.asarray(original.convert("RGB")).astype(int)
        after = np.asarray(result.convert("RGB")).astype(int)
    assert np.max(np.abs(np.diff(after[70:130, 70:130], axis=1))) < 12
    assert np.array_equal(after[32, 42], before[32, 42])


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg is required",
)
def test_video_render_keeps_audio_and_removes_metadata(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    source, output = tmp_path / "source.mp4", tmp_path / "output.mp4"
    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        "testsrc2=s=160x120:d=0.6:r=10", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=0.6", "-metadata", "title=Secret",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source),
    ]
    assert subprocess.run(
        command, capture_output=True, text=True).returncode == 0
    item = region()
    item.end_ms = 600
    item.keyframes = [RegionKeyframe(
        time_ms=0, box=Box(x=0.1, y=0.1, width=0.7, height=0.7))]
    _render_video(source, output, [item])
    original_capture = cv2.VideoCapture(str(source))
    output_capture = cv2.VideoCapture(str(output))
    source_ok, source_frame = original_capture.read()
    output_ok, output_frame = output_capture.read()
    original_capture.release()
    output_capture.release()
    assert source_ok and output_ok
    area = np.s_[12:96, 16:128]
    source_contrast = np.std(source_frame[area].astype(float))
    output_contrast = np.std(output_frame[area].astype(float))
    assert output_contrast < source_contrast
    original_gray = cv2.cvtColor(source_frame, cv2.COLOR_BGR2GRAY)[area]
    output_gray = cv2.cvtColor(output_frame, cv2.COLOR_BGR2GRAY)[area]
    original_detail = np.abs(np.diff(
        original_gray.astype(float), axis=1)).mean()
    output_detail = np.abs(np.diff(
        output_gray.astype(float), axis=1)).mean()
    assert output_detail < original_detail * 0.35
    assert np.mean(output_frame[area]) > 10
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(output),
    ], capture_output=True, text=True, check=True)
    data = json.loads(probe.stdout)
    assert {stream["codec_type"] for stream in data["streams"]} == {
        "video", "audio"}
    assert data["format"].get("tags", {}).get("title") is None


class FakeMediaProcessor:
    def verify_model(self):
        return MediaModel(
            "gemini-3.5-flash-lite",
            ("image", "video", "structured_output"), verified=True)

    def close(self):
        pass

    def analyze(self, path, content_type, progress, instructions):
        progress("analisar imagem", 1, 1)
        assert Path(path).read_bytes() == b"fake-image"
        model = MediaModel(
            "gemini-3.5-flash-lite",
            ("image", "video", "structured_output"), verified=True)
        item = region()
        item.start_ms = item.end_ms = 0
        item.keyframes = [RegionKeyframe(
            time_ms=0, box=Box(x=0.1, y=0.1, width=0.2, height=0.2))]
        return "image", {"width": 100, "height": 80}, [item], model

    def render(self, source, content_type, regions, output, progress):
        progress("exportar imagem", 1, 1)
        Path(output).write_bytes(b"redacted")


def wait_ready(api):
    for _ in range(100):
        data = api.get("/api/current").json()
        if data["status"] in {"ready", "failed"}:
            return data
        time.sleep(0.01)
    pytest.fail("background media job did not finish")


def test_media_review_api_is_fail_closed_and_exports(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import user_validation

    without_model = TestClient(user_validation.create_app())
    unavailable = without_model.post(
        "/api/document", content=b"fake-image",
        headers={"Content-Type": "image/jpeg"})
    assert unavailable.status_code == 503

    with TestClient(user_validation.create_app(
            media_processor=FakeMediaProcessor())) as api:
        ready = api.get("/api/ready").json()
        assert ready["media_ready"] is True
        assert ready["model"]["capabilities"] == [
            "image", "video", "structured_output"]
        response = api.post(
            "/api/document", content=b"fake-image",
            headers={
                "Content-Type": "image/jpeg",
                "X-File-Name": "Ana/../../foto.jpg",
            })
        assert response.status_code == 200
        assert response.json()["status"] in {"processing", "ready"}
        data = wait_ready(api)
        assert data["kind"] == "image"
        assert data["model"]["verified"] is True
        assert data["regions"][0]["reason"] == "Região de teste."
        assert api.get("/api/media/source").content == b"fake-image"

        manifest = {"attempt": 1, "regions": data["regions"]}
        assert api.put("/api/media/regions", json=manifest).status_code == 200
        assert api.post("/api/approve").status_code == 200
        approved = wait_ready(api)
        assert approved["approved"] is True
        assert api.get("/api/media/output").content == b"redacted"


def test_the_preview_route_returns_the_redacted_picture_of_the_draft():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import user_validation

    class Previewing(FakeMediaProcessor):
        def __init__(self):
            self.calls = []

        def preview(self, source, content_type, regions, time_ms):
            self.calls.append((content_type, len(regions), time_ms))
            return b"JPEG-preview"

    processor = Previewing()
    with TestClient(user_validation.create_app(
            media_processor=processor)) as api:
        api.post("/api/document", content=b"fake-image",
                 headers={"Content-Type": "image/jpeg"})
        data = wait_ready(api)
        draft = data["regions"] + data["regions"]  # an unsaved edit
        reply = api.post("/api/media/preview", json={
            "attempt": 1, "time_ms": 0, "regions": draft})
        assert reply.status_code == 200
        assert reply.headers["content-type"] == "image/jpeg"
        assert reply.headers["cache-control"] == "no-store"
        assert reply.content == b"JPEG-preview"
        assert processor.calls == [("image/jpeg", 2, 0)]
        stale = api.post("/api/media/preview", json={
            "attempt": 7, "time_ms": 0, "regions": []})
        assert stale.status_code == 409
        broken = api.post("/api/media/preview", json={
            "attempt": 1, "time_ms": 0,
            "regions": [{"id": "x", "category": "nope"}]})
        assert broken.status_code == 422


def test_the_preview_route_needs_a_finished_media_review():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import user_validation

    with TestClient(user_validation.create_app(
            media_processor=FakeMediaProcessor())) as api:
        reply = api.post("/api/media/preview", json={
            "attempt": 1, "time_ms": 0, "regions": []})
        assert reply.status_code == 409


def test_a_failing_preview_is_a_fixed_message_not_the_detail():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import user_validation
    from media import MediaError

    class Failing(FakeMediaProcessor):
        def preview(self, *args):
            raise MediaError("detalhe interno do OpenCV")

    with TestClient(user_validation.create_app(
            media_processor=Failing())) as api:
        api.post("/api/document", content=b"fake-image",
                 headers={"Content-Type": "image/jpeg"})
        wait_ready(api)
        reply = api.post("/api/media/preview", json={
            "attempt": 1, "time_ms": 0, "regions": []})
        assert reply.status_code == 502
        assert reply.json()["detail"] == user_validation.PREVIEW_FAILED
        assert "OpenCV" not in reply.text


def test_the_real_preview_shows_the_blur_of_a_photo(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    np = pytest.importorskip("numpy")
    import io
    source = tmp_path / "photo.png"
    Image.fromarray(_textured_frame(np)).save(source)
    processor = MediaProcessor(analyzer=None)

    def decode(data):
        with Image.open(io.BytesIO(data)) as picture:
            return np.asarray(picture.convert("RGB")).astype(int)

    plain = decode(processor.preview(source, "image/png", [], 0))
    blurred = decode(processor.preview(source, "image/png", [_face_item()], 0))
    # Smooth in the middle of the face, and the same as the plain preview at
    # the corners of the box (outside the ellipse).
    assert np.max(np.abs(np.diff(blurred[70:130, 70:130], axis=1))) < 14
    # (JPEG works in blocks, so "identical" means within its rounding.)
    assert np.abs(blurred[32, 42] - plain[32, 42]).max() <= 8
    assert np.abs(blurred[100, 100] - plain[100, 100]).max() > 20


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg is required",
)
def test_the_real_preview_shows_the_blur_of_a_video_frame(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    source = tmp_path / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=200x200:d=1:r=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
        check=True, capture_output=True)
    item = _face_item()
    item.end_ms = 1000
    processor = MediaProcessor(analyzer=None)
    data = processor.preview(source, "video/mp4", [item], 500)
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert frame.shape[:2] == (200, 200)
    assert np.max(np.abs(np.diff(
        frame[70:130, 70:130].astype(int), axis=1))) < 30


def test_media_initial_instructions_reach_the_analysis_and_the_reanalysis():
    pytest.importorskip("fastapi")
    from urllib.parse import quote
    from fastapi.testclient import TestClient
    import user_validation

    class Recording(FakeMediaProcessor):
        def __init__(self):
            self.received = []

        def analyze(self, path, content_type, progress, instructions):
            self.received.append(instructions)
            return super().analyze(path, content_type, progress, instructions)

    processor = Recording()
    with TestClient(user_validation.create_app(
            media_processor=processor)) as api:
        api.post("/api/document", content=b"fake-image", headers={
            "Content-Type": "image/jpeg",
            "X-User-Instructions": quote("Tapa também as matrículas."),
        })
        wait_ready(api)
        api.post("/api/reject", json={
            "attempt": 1, "text": "", "reason": "Falta uma cara."})
        wait_ready(api)
    assert processor.received[0] == "Tapa também as matrículas."
    assert "Tapa também as matrículas." in processor.received[1]
    assert "Falta uma cara." in processor.received[1]


def test_review_session_tracks_a_video_region_at_the_requested_time(tmp_path):
    from user_validation import RegionTrackRequest, ReviewSession

    class Tracker:
        def track(self, source, item, duration, seed_time):
            assert Path(source).name == "source.mp4"
            assert duration == 2000
            assert seed_time == 750
            item.keyframes.append(RegionKeyframe(
                time_ms=1000,
                box=Box(x=0.2, y=0.2, width=0.2, height=0.2)))
            return item

        def close(self):
            pass

    session = ReviewSession(media_processor=Tracker())
    source = Path(session.storage.name) / "source.mp4"
    source.write_bytes(b"video")
    session.kind = "video"
    session.status = "ready"
    session.source_path = source
    session.media = {"duration_ms": 2000}
    request = RegionTrackRequest(
        attempt=1, seed_time_ms=750, region=region(source="user"))
    tracked = session.track_region(request)
    assert len(tracked.keyframes) == 3
    session.close()

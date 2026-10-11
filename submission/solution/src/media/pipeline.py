"""Image/video inspection, tracking and irreversible rendering."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from .analyzer import GeminiMediaAnalyzer, MediaAnalysisError
from .capabilities import MediaConfigurationError, media_model_from_env
from .regions import (
    Box,
    MediaRegion,
    Point,
    RegionKeyframe,
    intersection_over_union,
    padded_box,
    polygon_box,
    transform_polygon,
)

IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}
MAX_IMAGE_PIXELS = 25_000_000
MAX_VIDEO_DURATION_MS = 60_000
MAX_VIDEO_WIDTH = 1920
MAX_VIDEO_HEIGHT = 1080
MAX_SAMPLES = 180
BATCH_SIZE = 8
VIDEO_SAMPLE_RATE = 3
TRACK_SAMPLE_RATE = 10
TRACK_MAX_GAP_MS = 1100
FACE_POLYGON_POINTS = 32
FACE_PARSER_SIZE = 512
FACE_LABELS = frozenset(range(1, 13)) | {15}


class MediaError(Exception):
    """Safe media-processing failure."""


class MediaValidationError(MediaError):
    pass


def supported_media_kind(content_type: str) -> str | None:
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime in IMAGE_TYPES:
        return "image"
    if mime in VIDEO_TYPES:
        return "video"
    return None


def suffix_for(content_type: str) -> str:
    mime = content_type.split(";", 1)[0].strip().lower()
    return IMAGE_TYPES.get(mime) or VIDEO_TYPES.get(mime) or ""


class MediaProcessor:
    def __init__(self, analyzer):
        self.analyzer = analyzer

    @classmethod
    def from_env(cls, environ=None):
        import os
        env = os.environ if environ is None else environ
        model = media_model_from_env(environ)
        try:
            timeout = float(env.get("GEMINI_GATEWAY_TIMEOUT", "90"))
            if timeout <= 0:
                raise ValueError
            analyzer = GeminiMediaAnalyzer(
                model,
                gateway_url=env["GEMINI_GATEWAY_URL"],
                origin=env["GEMINI_GATEWAY_ORIGIN"],
                timeout=timeout,
            )
        except (KeyError, ValueError, MediaAnalysisError):
            raise MediaConfigurationError(
                "Media model is not configured or does not support "
                "image/video.") from None
        return cls(analyzer)

    def close(self):
        close = getattr(self.analyzer, "close", None)
        if close:
            close()

    def verify_model(self):
        try:
            return self.analyzer.verify()
        except (MediaAnalysisError, MediaConfigurationError) as error:
            raise MediaError(str(error)) from None

    def _analyze_batch(self, frames, **options):
        try:
            return self.analyzer.analyze(frames, **options)
        except MediaAnalysisError as error:
            raise MediaError(str(error)) from None

    def analyze(self, path, content_type, progress=None, instructions=None):
        report = progress or (lambda *_args: None)
        model = self.verify_model()
        kind = supported_media_kind(content_type)
        if kind == "image":
            report("validar imagem", 0, 1)
            info, frame = _read_image(path)
            report("analisar imagem", 0, 2)
            detections = self._analyze_batch(
                [(0, frame)], instructions=instructions)
            detected_faces = _detect_image_faces(frame)
            regions = _refine_model_image_faces(
                [region for _, region in detections], detected_faces)
            _refine_region_polygons(frame, regions)
            regions = _merge_image_regions(regions)
            redacted = _redact_jpeg(frame, regions, 0)
            residual = self._analyze_batch(
                [(0, redacted)], residual=True, instructions=instructions)
            residual_regions = _refine_model_image_faces(
                [region for _, region in residual], detected_faces)
            _refine_region_polygons(frame, residual_regions)
            regions = _merge_image_regions(
                regions + residual_regions)
            report("análise concluída", 2, 2)
            return kind, info, regions, model

        report("validar vídeo", 0, 1)
        info = _probe_video(path)
        report("extrair fotogramas", 0, 1)
        samples, face_regions, scene_cuts = _sample_video(path, info, report)
        llm_regions = []
        total_batches = max(1, math.ceil(len(samples) / BATCH_SIZE) * 2)
        completed = 0
        for offset in range(0, len(samples), BATCH_SIZE):
            batch = samples[offset:offset + BATCH_SIZE]
            found = self._analyze_batch([
                (sample[0], sample[2]) for sample in batch
            ], instructions=instructions)
            _refine_found_polygons(found, batch)
            llm_regions.extend(_time_regions(found, samples, info))
            completed += 1
            report("detetar dados visuais", completed, total_batches)
        combined = _link_regions(
            _prefer_detected_faces(llm_regions, face_regions) + face_regions,
            info["duration_ms"], scene_cuts=scene_cuts)
        combined = _track_video_objects(path, combined, info, scene_cuts)
        for offset in range(0, len(samples), BATCH_SIZE):
            batch = samples[offset:offset + BATCH_SIZE]
            preview = [
                (frame_id, _redact_jpeg(data, combined, time_ms))
                for frame_id, time_ms, data in batch
            ]
            found = self._analyze_batch(
                preview, residual=True, instructions=instructions)
            _refine_found_polygons(found, batch)
            llm_regions.extend(_time_regions(found, samples, info))
            completed += 1
            report("verificar dados residuais", completed, total_batches)
        combined = _link_regions(
            _prefer_detected_faces(llm_regions, face_regions) + face_regions,
            info["duration_ms"], scene_cuts=scene_cuts)
        combined = self._recover_video_objects(
            path, combined, llm_regions, face_regions, samples, info,
            scene_cuts, instructions, report)
        combined = [_smooth_region(track) for track in combined]
        return kind, info, combined, model

    def _recover_video_objects(self, path, combined, observations, faces,
                               samples, info, scene_cuts, instructions,
                               report):
        uncertain_times = set()
        tracked = _track_video_objects(
            path, combined, info, scene_cuts, uncertain_times=uncertain_times)
        uncertain_times.difference_update(sample[1] for sample in samples)
        if not uncertain_times:
            return tracked
        # Bound additional model work using the same total frame budget. The
        # dense tracker still provides conservative coverage between anchors.
        times = sorted(uncertain_times)
        remaining = max(0, MAX_SAMPLES - len(samples))
        if not remaining:
            return tracked
        if len(times) > remaining:
            times = [times[round(index * (len(times) - 1) / (remaining - 1))]
                     for index in range(remaining)] if remaining > 1 else [
                         times[0]]
        extra = _read_video_recovery_frames(path, times, len(samples))
        batches = math.ceil(len(extra) / BATCH_SIZE)
        for offset in range(0, len(extra), BATCH_SIZE):
            batch = extra[offset:offset + BATCH_SIZE]
            report("verificar rastreio", offset // BATCH_SIZE, batches)
            found = self._analyze_batch(
                [(sample[0], sample[2]) for sample in batch],
                instructions=instructions)
            _refine_found_polygons(found, batch)
            observations.extend(_time_regions(found, extra, info))
        combined = _link_regions(
            _prefer_detected_faces(observations, faces) + faces,
            info["duration_ms"], scene_cuts=scene_cuts)
        report("verificar rastreio", batches, batches)
        return _track_video_objects(path, combined, info, scene_cuts)

    def track(self, source, region, duration_ms, seed_time_ms=None):
        """Track one reviewer-authored box in both directions."""

        if not region.keyframes:
            raise MediaValidationError("A região não tem uma caixa inicial.")
        try:
            return _track_manual_region(
                source, region, duration_ms, seed_time_ms)
        except MediaValidationError:
            raise
        except Exception:
            raise MediaError(
                "Não foi possível rastrear esta região.") from None

    def preview(self, source, content_type, regions, time_ms=0):
        """One redacted picture (JPEG bytes) with the same blur and mosaic as
        the export: the photo, or the video frame at ``time_ms``. Used to show
        the reviewer what the result will look like, before approving."""
        kind = supported_media_kind(content_type)
        if kind == "image":
            return _preview_image(source, regions)
        if kind == "video":
            return _preview_video_frame(source, regions, time_ms)
        raise MediaValidationError("Unsupported media type.")

    def render(self, source, content_type, regions, output, progress=None):
        report = progress or (lambda *_args: None)
        kind = supported_media_kind(content_type)
        if kind == "image":
            report("exportar imagem", 0, 1)
            _render_image(source, output, regions, content_type)
            report("exportação concluída", 1, 1)
        elif kind == "video":
            report("exportar vídeo", 0, 1)
            _render_video(source, output, regions)
            report("exportação concluída", 1, 1)
        else:
            raise MediaValidationError("Unsupported media type.")


PREVIEW_MAX_SIDE = 1280


def _preview_image(source, regions):
    """The photo with the same redaction as the export, as JPEG bytes."""
    import io
    from PIL import Image, ImageOps
    try:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
    except Exception:
        raise MediaError("Não foi possível abrir a imagem.") from None
    _pixelate_image_regions(image, regions, 0)
    image.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def _preview_video_frame(source, regions, time_ms):
    """One video frame, redacted like the export, as JPEG bytes."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise MediaError("O OpenCV não está instalado.") from None
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise MediaError("Não foi possível abrir o vídeo.")
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0, int(time_ms)))
        ok, frame = capture.read()
        if not ok:
            raise MediaError("Não foi possível ler esse instante do vídeo.")
    finally:
        capture.release()
    _pixelate_video_regions(frame, regions, time_ms, cv2, np)
    height, width = frame.shape[:2]
    scale = PREVIEW_MAX_SIDE / max(width, height)
    if scale < 1:
        frame = cv2.resize(
            frame, (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA)
    done, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not done:
        raise MediaError("Não foi possível gerar a pré-visualização.")
    return encoded.tobytes()


def _read_image(path):
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as source:
            source.verify()
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise MediaValidationError("A imagem excede 25 megapíxeis.")
            if not width or not height:
                raise MediaValidationError(
                    "A imagem não tem dimensões válidas.")
            image.thumbnail((1600, 1600))
            import io
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=88, optimize=True)
            return {"width": width, "height": height}, buffer.getvalue()
    except MediaValidationError:
        raise
    except Exception:
        raise MediaValidationError("Não foi possível ler a imagem.") from None


def _probe_video(path):
    if shutil.which("ffprobe") is None:
        raise MediaValidationError("O ffprobe não está instalado.")
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,avg_frame_rate:format=duration",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        duration_ms = round(float(data["format"]["duration"]) * 1000)
        rate = stream.get("avg_frame_rate") or stream["r_frame_rate"]
        numerator, denominator = rate.split("/")
        fps = float(numerator) / float(denominator)
    except (ValueError, KeyError, IndexError, ZeroDivisionError, TypeError):
        raise MediaValidationError("Não foi possível ler o vídeo.") from None
    if result.returncode or duration_ms <= 0 or fps <= 0:
        raise MediaValidationError("Não foi possível ler o vídeo.")
    if duration_ms > MAX_VIDEO_DURATION_MS:
        raise MediaValidationError("O vídeo não pode exceder 60 segundos.")
    if (max(width, height) > MAX_VIDEO_WIDTH or
            min(width, height) > MAX_VIDEO_HEIGHT):
        raise MediaValidationError("O vídeo não pode exceder 1920 × 1080.")
    # ffprobe reports the stored raster, whereas both OpenCV decoding and the
    # browser apply a phone video's rotation metadata. Region coordinates must
    # use the dimensions of those displayed frames, not the stored raster.
    try:
        import cv2
        capture = cv2.VideoCapture(str(path))
        opened, first_frame = capture.read()
        capture.release()
        if not opened:
            raise ValueError
        height, width = first_frame.shape[:2]
    except Exception:
        raise MediaValidationError("Não foi possível ler o vídeo.") from None
    return {
        "width": width, "height": height,
        "duration_ms": duration_ms, "fps": fps,
    }


def _capture_time_ms(capture, index, fps, previous=-1):
    """Return the decoder timestamp, with a CFR fallback.

    ``index / fps`` drifts on variable-frame-rate phone recordings. OpenCV
    exposes each decoded frame's presentation position through POS_MSEC on
    the supported backends; the arithmetic value is only a fallback for
    codecs that report zero or a non-monotonic position.
    """

    try:
        import cv2
        value = float(capture.get(cv2.CAP_PROP_POS_MSEC))
    except (ImportError, TypeError, ValueError):
        value = float("nan")
    fallback = round(index * 1000 / fps)
    if not math.isfinite(value) or value < 0:
        value = fallback
    candidate = round(value)
    if index and candidate <= previous:
        candidate = max(previous + 1, fallback)
    return candidate


def _create_face_detector(cv2):
    """Prefer a YuNet ONNX detector and retain an offline Haar fallback."""

    model_path = os.environ.get("OPENCV_FACE_DETECTOR_MODEL", "").strip()
    if model_path and Path(model_path).is_file() and hasattr(
            cv2, "FaceDetectorYN"):
        try:
            detector = cv2.FaceDetectorYN.create(
                model_path, "", (320, 320), 0.72, 0.3, 5000)
            return "yunet", detector
        except (cv2.error, OSError, ValueError):
            pass
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return "haar", cascade


def _create_face_parser(cv2):
    """Load the optional local face-parsing ONNX model."""

    model_path = os.environ.get("OPENCV_FACE_PARSER_MODEL", "").strip()
    if not model_path or not Path(model_path).is_file():
        return None
    try:
        return cv2.dnn.readNetFromONNX(model_path)
    except (cv2.error, OSError, ValueError):
        return None


def _detect_faces(frame, small_gray, gray_scale, detector):
    kind, implementation = detector
    height, width = frame.shape[:2]
    found = []
    if kind == "yunet":
        try:
            implementation.setInputSize((width, height))
            _, detections = implementation.detect(frame)
        except Exception:
            detections = None
        if detections is not None:
            found = [tuple(map(float, face[:4])) for face in detections]
    elif not implementation.empty():
        found = [
            (x / gray_scale, y / gray_scale,
             box_width / gray_scale, box_height / gray_scale)
            for x, y, box_width, box_height in implementation.detectMultiScale(
                small_gray, scaleFactor=1.08, minNeighbors=5,
                minSize=(24, 24))
        ]
    output = []
    for x, y, box_width, box_height in found:
        left = min(1.0, max(0.0, x / width))
        top = min(1.0, max(0.0, y / height))
        right = min(1.0, max(0.0, (x + box_width) / width))
        bottom = min(1.0, max(0.0, (y + box_height) / height))
        if right <= left or bottom <= top:
            continue
        normalized = Box(
            x=left, y=top, width=right - left, height=bottom - top,
        )
        # Small or fast-moving faces need a slightly larger safety edge.
        small_face = min(normalized.width, normalized.height) < 0.12
        margin = 0.08 if small_face else 0.05
        output.append(padded_box(normalized, margin))
    return output


def _parse_face_polygon(frame, box, parser, cv2):
    """Return a safe 32-point face contour or ``None`` for box fallback."""

    if parser is None:
        return None
    import numpy as np

    height, width = frame.shape[:2]
    crop_box = padded_box(box, 0.12)
    left = max(0, round(crop_box.x * width))
    top = max(0, round(crop_box.y * height))
    right = min(width, round((crop_box.x + crop_box.width) * width))
    bottom = min(height, round((crop_box.y + crop_box.height) * height))
    if right - left < 8 or bottom - top < 8:
        return None
    crop = frame[top:bottom, left:right]
    try:
        resized = cv2.resize(
            crop, (FACE_PARSER_SIZE, FACE_PARSER_SIZE),
            interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb /= 255.0
        rgb -= np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
        rgb /= np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
        blob = np.transpose(rgb, (2, 0, 1))[None]
        parser.setInput(blob)
        output = parser.forward()
    except Exception:
        return None
    if isinstance(output, (tuple, list)):
        if not output:
            return None
        output = output[0]
    scores = np.asarray(output)
    if scores.ndim == 4 and scores.shape[1] >= 16:
        classes = np.argmax(scores[0], axis=0).astype(np.uint8)
    elif scores.ndim == 4 and scores.shape[-1] >= 16:
        classes = np.argmax(scores[0], axis=-1).astype(np.uint8)
    elif scores.ndim == 3 and scores.shape[0] == 1:
        classes = scores[0].astype(np.uint8)
    else:
        return None
    classes = cv2.resize(
        classes, (right - left, bottom - top),
        interpolation=cv2.INTER_NEAREST)
    return _polygon_from_face_classes(
        classes, (left, top, right, bottom), box,
        width, height, cv2, np)


def _polygon_from_face_classes(
    classes,
    crop,
    detector_box,
    frame_width,
    frame_height,
    cv2,
    np,
):
    """Clean face-parser classes and reduce their boundary to 32 points."""

    mask = np.isin(classes, tuple(FACE_LABELS)).astype(np.uint8) * 255
    if not np.any(mask):
        return None
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    face_width_px = max(1, round(detector_box.width * frame_width))
    radius = max(4, round(face_width_px * 0.03))
    size = radius * 2 + 1
    mask = cv2.dilate(
        mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))

    count, components, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count <= 1:
        return None
    left, top, right, bottom = crop
    center_x = round(
        (detector_box.x + detector_box.width / 2) * frame_width) - left
    center_y = round(
        (detector_box.y + detector_box.height / 2) * frame_height) - top
    center_x = min(mask.shape[1] - 1, max(0, center_x))
    center_y = min(mask.shape[0] - 1, max(0, center_y))
    component = int(components[center_y, center_x])
    if component == 0:
        y0, y1 = max(0, center_y - 4), min(mask.shape[0], center_y + 5)
        x0, x1 = max(0, center_x - 4), min(mask.shape[1], center_x + 5)
        nearby = components[y0:y1, x0:x1]
        labels, frequencies = np.unique(nearby[nearby > 0], return_counts=True)
        if not len(labels):
            return None
        component = int(labels[np.argmax(frequencies)])
    component_area = int(stats[component, cv2.CC_STAT_AREA])
    total_area = int(np.count_nonzero(mask))
    detector_area = max(
        1,
        round(detector_box.width * frame_width) *
        round(detector_box.height * frame_height),
    )
    ratio = component_area / detector_area
    if component_area / max(1, total_area) < 0.75 or not 0.18 <= ratio <= 1.25:
        return None
    selected = np.where(components == component, 255, 0).astype(np.uint8)
    contours, _ = cv2.findContours(
        selected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    sampled = _resample_closed_contour(contour, FACE_POLYGON_POINTS, np)
    if sampled is None:
        return None
    points = [
        Point(
            x=min(1.0, max(0.0, (left + float(x)) / frame_width)),
            y=min(1.0, max(0.0, (top + float(y)) / frame_height)),
        )
        for x, y in sampled
    ]
    try:
        polygon_box(points)
    except ValueError:
        return None
    return points


def _resample_closed_contour(contour, count, np):
    """Sample a closed contour uniformly, clockwise, starting at its top."""

    if len(contour) < 3:
        return None
    points = contour.astype(np.float64)
    closed = np.vstack([points, points[0]])
    lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    perimeter = float(lengths.sum())
    if perimeter < 1:
        return None
    cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
    targets = np.arange(count, dtype=np.float64) * perimeter / count
    sampled = []
    for target in targets:
        segment = min(
            len(lengths) - 1,
            int(np.searchsorted(cumulative, target, side="right") - 1))
        span = lengths[segment]
        ratio = 0.0 if span == 0 else (
            target - cumulative[segment]) / span
        sampled.append(
            closed[segment] + (closed[segment + 1] - closed[segment]) * ratio)
    sampled = np.asarray(sampled)
    signed_area = np.sum(
        sampled[:, 0] * np.roll(sampled[:, 1], -1) -
        np.roll(sampled[:, 0], -1) * sampled[:, 1])
    if signed_area < 0:
        sampled = sampled[::-1]
    start = min(
        range(len(sampled)),
        key=lambda index: (sampled[index, 1], sampled[index, 0]))
    return np.roll(sampled, -start, axis=0)


def _refine_found_polygons(found, samples):
    """Refine every model box using its corresponding sampled frame."""

    frames = {frame_id: data for frame_id, _time_ms, data in samples}
    grouped = {}
    for frame_id, region in found:
        grouped.setdefault(frame_id, []).append(region)
    for frame_id, regions in grouped.items():
        data = frames.get(frame_id)
        if data is not None:
            _refine_region_polygons(data, regions)


def _refine_region_polygons(jpeg, regions):
    """Attempt a close-fit foreground polygon for any rectangular region."""

    try:
        import cv2
        import numpy as np
    except ImportError:
        return
    frame = cv2.imdecode(
        np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return
    for region in regions:
        # GrabCut can select a hand or only the colored half of a card. For
        # structured data, preserve the full model box so no text is exposed.
        if region.kind in {
                "identity_document", "text", "plate", "signature", "code"}:
            continue
        for keyframe in region.keyframes:
            if keyframe.polygon is not None:
                continue
            polygon = _segment_box_polygon(
                frame, keyframe.box, region.kind, cv2, np)
            if polygon is None:
                continue
            keyframe.polygon = polygon
            keyframe.box = polygon_box(polygon)


def _segment_box_polygon(frame, box, kind, cv2, np):
    """Use conservative GrabCut refinement with a full-box fallback."""

    height, width = frame.shape[:2]
    crop_box = padded_box(box, 0.18)
    left = max(0, round(crop_box.x * width))
    top = max(0, round(crop_box.y * height))
    right = min(width, round((crop_box.x + crop_box.width) * width))
    bottom = min(height, round((crop_box.y + crop_box.height) * height))
    crop = frame[top:bottom, left:right]
    if crop.shape[0] < 12 or crop.shape[1] < 12:
        return None
    seed_left = max(1, round(box.x * width) - left)
    seed_top = max(1, round(box.y * height) - top)
    seed_right = min(crop.shape[1] - 1,
                     round((box.x + box.width) * width) - left)
    seed_bottom = min(crop.shape[0] - 1,
                      round((box.y + box.height) * height) - top)
    if seed_right - seed_left < 3 or seed_bottom - seed_top < 3:
        return None
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    background = np.zeros((1, 65), dtype=np.float64)
    foreground = np.zeros((1, 65), dtype=np.float64)
    try:
        cv2.grabCut(
            crop, mask,
            (seed_left, seed_top,
             seed_right - seed_left, seed_bottom - seed_top),
            background, foreground, 4, cv2.GC_INIT_WITH_RECT)
    except (cv2.error, ValueError):
        return None
    selected = np.where(
        (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
        255, 0).astype(np.uint8)
    if not np.any(selected):
        return None
    short_edge = max(1, min(seed_right - seed_left,
                            seed_bottom - seed_top))
    if kind in {"text", "signature", "code"}:
        close_width = max(5, round((seed_right - seed_left) * 0.08))
        close_height = max(3, round((seed_bottom - seed_top) * 0.08))
        selected = cv2.morphologyEx(
            selected, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (close_width | 1, close_height | 1)))
    else:
        selected = cv2.morphologyEx(
            selected, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    radius = max(3, round(short_edge * 0.04))
    size = radius * 2 + 1
    selected = cv2.dilate(
        selected,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    contours, _ = cv2.findContours(
        selected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contours = [
        contour for contour in contours if cv2.contourArea(contour) > 4]
    if not contours:
        return None
    hull = cv2.convexHull(np.concatenate(contours, axis=0)).reshape(-1, 2)
    hull_left, hull_top = hull.min(axis=0)
    hull_right, hull_bottom = hull.max(axis=0)
    coverage_x = (hull_right - hull_left) / max(1, seed_right - seed_left)
    coverage_y = (hull_bottom - hull_top) / max(1, seed_bottom - seed_top)
    minimum_x = 0.65 if kind in {
        "text", "identity_document", "plate", "signature", "code"
    } else 0.45
    minimum_y = 0.50 if kind in {
        "text", "identity_document", "plate", "signature", "code"
    } else 0.45
    if coverage_x < minimum_x or coverage_y < minimum_y:
        return None
    sampled = _resample_closed_contour(hull, FACE_POLYGON_POINTS, np)
    if sampled is None:
        return None
    points = [Point(
        x=min(1.0, max(0.0, (left + float(x)) / width)),
        y=min(1.0, max(0.0, (top + float(y)) / height)),
    ) for x, y in sampled]
    refined_box = polygon_box(points)
    center_x = box.x + box.width / 2
    center_y = box.y + box.height / 2
    if not (
        refined_box.x <= center_x <= refined_box.x + refined_box.width and
        refined_box.y <= center_y <= refined_box.y + refined_box.height
    ):
        return None
    return points


def _encode_video_preview(frame, cv2):
    preview = frame
    if frame.shape[1] > 1280:
        ratio = 1280 / frame.shape[1]
        preview = cv2.resize(
            frame, None, fx=ratio, fy=ratio,
            interpolation=cv2.INTER_AREA)
    encoded, data = cv2.imencode(
        ".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 86])
    if not encoded:
        raise MediaValidationError("Falhou a extração do vídeo.")
    return data.tobytes()


def _sample_video(path, info, report):
    try:
        import cv2
    except ImportError:
        raise MediaValidationError("O OpenCV não está instalado.") from None
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise MediaValidationError("Não foi possível abrir o vídeo.")
    detector = _create_face_detector(cv2)
    parser = _create_face_parser(cv2)
    frame_count = max(1, round(info["duration_ms"] * info["fps"] / 1000))
    # Reserve part of the budget for cuts while keeping samples spread across
    # the complete clip. The previous online cap could exhaust all 180 slots
    # before the end of a busy video.
    base_budget = max(1, MAX_SAMPLES - 30)
    sample_interval = max(
        1,
        round(info["fps"] / VIDEO_SAMPLE_RATE),
        math.ceil(frame_count / base_budget),
    )
    face_interval = max(1, round(info["fps"] / TRACK_SAMPLE_RATE))
    base_samples, cut_samples, faces, scene_cuts = [], [], [], []
    previous_small = None
    previous_time_ms = -1
    last_frame = None
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        time_ms = _capture_time_ms(
            capture, index, info["fps"], previous_time_ms)
        previous_time_ms = time_ms
        last_frame = frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = min(1.0, 640 / frame.shape[1])
        small = cv2.resize(gray, None, fx=scale, fy=scale)
        if index % face_interval == 0:
            for box in _detect_faces(frame, small, scale, detector):
                polygon = _parse_face_polygon(frame, box, parser, cv2)
                if polygon is not None:
                    box = polygon_box(polygon)
                faces.append(MediaRegion(
                    category="biometrico", kind="face",
                    reason="Rosto potencialmente identificável.",
                    confidence="certo", source="face_detector",
                    start_ms=time_ms, end_ms=time_ms,
                    keyframes=[RegionKeyframe(
                        time_ms=time_ms, box=box, polygon=polygon)],
                ))
        scene_change = False
        difference = 0.0
        if previous_small is not None:
            difference = cv2.absdiff(small, previous_small).mean()
            scene_change = difference > 28
            if scene_change:
                scene_cuts.append(time_ms)
        previous_small = small
        if index % sample_interval == 0 or scene_change:
            try:
                data = _encode_video_preview(frame, cv2)
            except MediaValidationError:
                capture.release()
                raise
            sample = (0, time_ms, data)
            if index % sample_interval == 0:
                base_samples.append(sample)
            else:
                cut_samples.append((difference, sample))
        index += 1
        if index % max(1, round(info["fps"])) == 0:
            report("extrair fotogramas", min(index, frame_count), frame_count)
    capture.release()
    if not base_samples:
        raise MediaValidationError("O vídeo não contém fotogramas legíveis.")
    if (last_frame is not None and
            base_samples[-1][1] != previous_time_ms):
        base_samples.append((
            0, previous_time_ms,
            _encode_video_preview(last_frame, cv2)))
    remaining = max(0, MAX_SAMPLES - len(base_samples))
    chosen_cuts = [sample for _, sample in sorted(
        cut_samples, key=lambda item: item[0], reverse=True)[:remaining]]
    unique_samples = {
        sample[1]: sample for sample in base_samples + chosen_cuts}
    ordered_samples = sorted(
        unique_samples.values(), key=lambda sample: sample[1])
    samples = [
        (frame_id, sample[1], sample[2])
        for frame_id, sample in enumerate(ordered_samples)
    ]
    face_tracks = _link_regions(
        faces, info["duration_ms"], scene_cuts=scene_cuts)
    last_frame_ms = previous_time_ms
    _extend_face_tracks_to_edges(
        face_tracks, last_frame_ms, info["duration_ms"], info["fps"])
    return samples, face_tracks, scene_cuts


def _extend_face_tracks_to_edges(tracks, last_frame_ms, duration_ms, fps):
    edge_tolerance_ms = max(1, round(2 * 1000 / fps))
    for track in tracks:
        # Container duration includes the final frame's display interval. A
        # track seen near either edge must cover that entire interval too.
        if track.start_ms <= edge_tolerance_ms:
            track.start_ms = 0
        if last_frame_ms - track.end_ms <= edge_tolerance_ms:
            track.end_ms = duration_ms


def _detect_image_faces(jpeg):
    """Use measured face bounds to correct overly broad model boxes."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    scale = min(1.0, 640 / frame.shape[1])
    small = cv2.resize(gray, None, fx=scale, fy=scale)
    detector = _create_face_detector(cv2)
    parser = _create_face_parser(cv2)
    faces = []
    for box in _detect_faces(frame, small, scale, detector):
        polygon = _parse_face_polygon(frame, box, parser, cv2)
        if polygon is not None:
            box = polygon_box(polygon)
        faces.append(MediaRegion(
            category="biometrico", kind="face",
            reason="Rosto potencialmente identificável.",
            confidence="certo", source="face_detector",
            start_ms=0, end_ms=0,
            keyframes=[RegionKeyframe(
                time_ms=0, box=box, polygon=polygon)],
        ))
    return faces


def _refine_model_image_faces(regions, detected_faces):
    """Refine model-selected faces without adding local face candidates.

    Local detectors can mistake textures for faces. For still images, the
    visual model decides what exists; a local candidate only supplies geometry
    when it substantially overlaps a model-selected face. Keep the model's
    reason, confidence and provenance, including when no local match exists.
    """
    output = []
    for region in regions:
        if region.kind != "face" or region.source != "gemini":
            output.append(region)
            continue
        box = region.keyframes[0].box
        matches = [
            (intersection_over_union(box, candidate.keyframes[0].box),
             candidate)
            for candidate in detected_faces
            if candidate.kind == "face"
        ]
        score, candidate = max(matches, key=lambda match: match[0],
                               default=(0, None))
        if score >= 0.3:
            refined = region.model_copy(deep=True)
            refined.keyframes[0].box = candidate.keyframes[0].box.model_copy(
                deep=True)
            polygon = candidate.keyframes[0].polygon
            refined.keyframes[0].polygon = (
                [point.model_copy(deep=True) for point in polygon]
                if polygon is not None else None)
            output.append(refined)
        else:
            output.append(region)
    return output


def _prefer_detected_faces(regions, detected_faces):
    """Discard a model face box when a measured face sits inside it."""
    kept = []
    for region in regions:
        if region.kind != "face" or region.source != "gemini":
            kept.append(region)
            continue
        box = region.keyframes[0].box
        time_ms = region.keyframes[0].time_ms
        duplicate = any(
            detected.start_ms <= region.end_ms and
            detected.end_ms >= region.start_ms and
            _same_face_box(box, detected.box_at(time_ms))
            for detected in detected_faces
        )
        if not duplicate:
            kept.append(region)
    return kept


def _same_face_box(model_box, detected_box):
    """Match a model face to the measured box at the same video time."""

    if detected_box is None:
        return False
    model_center = (
        model_box.x + model_box.width / 2,
        model_box.y + model_box.height / 2,
    )
    detected_center = (
        detected_box.x + detected_box.width / 2,
        detected_box.y + detected_box.height / 2,
    )
    model_contains = (
        model_box.x <= detected_center[0] <= model_box.x + model_box.width and
        model_box.y <= detected_center[1] <= model_box.y + model_box.height
    )
    detector_contains = (
        detected_box.x <= model_center[0] <=
        detected_box.x + detected_box.width and
        detected_box.y <= model_center[1] <=
        detected_box.y + detected_box.height
    )
    return (
        model_contains or detector_contains or
        intersection_over_union(model_box, detected_box) >= 0.10
    )


def _time_regions(found, samples, info):
    by_id = {frame_id: time_ms for frame_id, time_ms, _ in samples}
    output = []
    for frame_id, region in found:
        time_ms = by_id.get(frame_id)
        if time_ms is None:
            continue
        region.start_ms = time_ms
        region.end_ms = time_ms
        region.keyframes[0].time_ms = time_ms
        output.append(region)
    return output


def _link_regions(regions, duration_ms, scene_cuts=()):
    """Associate observations one-to-one using time, motion and geometry."""

    observations = []
    for region in regions:
        keys = sorted((key for key in region.keyframes
                       if region.start_ms <= key.time_ms <= region.end_ms),
                      key=lambda key: key.time_ms)
        for index, keyframe in enumerate(keys):
            observation = region.model_copy(deep=True)
            observation.keyframes = [keyframe.model_copy(deep=True)]
            observation.start_ms = (
                region.start_ms if index == 0 else keyframe.time_ms)
            observation.end_ms = (
                region.end_ms if index == len(keys) - 1 else keyframe.time_ms)
            observations.append(observation)
    observations.sort(key=lambda item: item.keyframes[0].time_ms)
    grouped = {}
    for region in observations:
        grouped.setdefault(region.keyframes[0].time_ms, []).append(region)
    tracks = []
    for time_ms, current in grouped.items():
        current = _deduplicate_frame_regions(current)
        candidates = []
        for track_index, track in enumerate(tracks):
            last_time = track.keyframes[-1].time_ms
            elapsed = time_ms - last_time
            if (elapsed <= 0 or elapsed > TRACK_MAX_GAP_MS or
                    _crosses_scene_cut(last_time, time_ms, scene_cuts)):
                continue
            predicted = _predict_box(track.keyframes, time_ms)
            for region_index, region in enumerate(current):
                if (track.kind != region.kind or
                        track.source != region.source):
                    continue
                score = _association_score(
                    predicted, region.keyframes[0].box)
                # A noisy first observation can produce an extreme velocity.
                # Also compare the last measured bounds before splitting an
                # otherwise continuous object into overlapping tracks.
                measured_score = _association_score(
                    track.keyframes[-1].box, region.keyframes[0].box)
                if measured_score is not None:
                    score = max(score or 0, measured_score)
                if score is not None:
                    candidates.append(
                        (score, track_index, region_index))
        used_tracks, used_regions = set(), set()
        for _, track_index, region_index in sorted(
                candidates, reverse=True):
            if track_index in used_tracks or region_index in used_regions:
                continue
            track, region = tracks[track_index], current[region_index]
            keyframe = region.keyframes[0]
            if keyframe.time_ms - track.keyframes[-1].time_ms >= 80:
                track.keyframes.append(keyframe.model_copy(deep=True))
            track.start_ms = min(track.start_ms, region.start_ms)
            track.end_ms = max(track.end_ms, region.end_ms)
            if region.confidence == "certo":
                track.confidence = "certo"
            used_tracks.add(track_index)
            used_regions.add(region_index)
        for region_index, region in enumerate(current):
            if region_index not in used_regions:
                tracks.append(region.model_copy(deep=True))
    for track in tracks:
        track.keyframes.sort(key=lambda keyframe: keyframe.time_ms)
        track.start_ms = max(0, track.start_ms)
        track.end_ms = min(
            duration_ms, max(track.start_ms, track.end_ms))
    return tracks


def _deduplicate_frame_regions(regions):
    """Combine repeated detections at the same time, covering both boxes."""
    output = []
    for region in regions:
        box = region.keyframes[0].box
        duplicate = next((current for current in output
                          if current.kind == region.kind and
                          current.source == region.source and
                          intersection_over_union(
                              current.keyframes[0].box, box) >= 0.5), None)
        if duplicate is None:
            output.append(region.model_copy(deep=True))
            continue
        if region.kind == "face":
            continue
        previous = duplicate.keyframes[0].box
        left, top = min(previous.x, box.x), min(previous.y, box.y)
        right = max(previous.x + previous.width, box.x + box.width)
        bottom = max(previous.y + previous.height, box.y + box.height)
        duplicate.keyframes[0].box = Box(
            x=left, y=top, width=right - left, height=bottom - top)
        duplicate.keyframes[0].polygon = None
        duplicate.start_ms = min(duplicate.start_ms, region.start_ms)
        duplicate.end_ms = max(duplicate.end_ms, region.end_ms)
    return output


def _crosses_scene_cut(start_ms, end_ms, scene_cuts):
    return any(start_ms < cut <= end_ms for cut in scene_cuts)


def _box_values(box):
    return (
        box.x + box.width / 2,
        box.y + box.height / 2,
        box.width,
        box.height,
    )


def _box_from_values(center_x, center_y, width, height):
    width = min(1.0, max(0.002, width))
    height = min(1.0, max(0.002, height))
    x = min(1.0 - width, max(0.0, center_x - width / 2))
    y = min(1.0 - height, max(0.0, center_y - height / 2))
    return Box(x=x, y=y, width=width, height=height)


def _predict_box(keyframes, time_ms):
    last = keyframes[-1]
    if len(keyframes) < 2:
        return last.box
    previous = keyframes[-2]
    span = last.time_ms - previous.time_ms
    if span <= 0:
        return last.box
    ratio = min(2.0, max(0.0, (time_ms - last.time_ms) / span))
    before = _box_values(previous.box)
    after = _box_values(last.box)
    values = [
        after[index] + (after[index] - before[index]) * ratio
        for index in range(4)
    ]
    return _box_from_values(*values)


def _association_score(predicted, observed):
    first = _box_values(predicted)
    second = _box_values(observed)
    distance = math.hypot(first[0] - second[0], first[1] - second[1])
    radius = max(
        0.06,
        1.8 * math.hypot(predicted.width, predicted.height) / 2,
    )
    overlap = intersection_over_union(predicted, observed)
    if overlap < 0.035 and distance > radius:
        return None
    first_area = predicted.width * predicted.height
    second_area = observed.width * observed.height
    size_similarity = min(first_area, second_area) / max(
        first_area, second_area, 1e-9)
    return overlap * 2.0 + max(0.0, 1.0 - distance / radius) + (
        0.35 * size_similarity)


def _smooth_region(region):
    """Remove single-frame jitter and add a motion-aware safety edge."""

    result = region.model_copy(deep=True)
    # Moving document bounds are measured/flow-tracked. Averaging with future
    # positions shifts the mask away from the text it must cover.
    if result.kind != "face":
        return result
    keys = result.keyframes
    if len(keys) < 2:
        return result
    original = [_box_values(key.box) for key in keys]
    smoothed = []
    for index, values in enumerate(original):
        left = original[max(0, index - 1)]
        right = original[min(len(original) - 1, index + 1)]
        mixed = [
            left[field] * 0.2 + values[field] * 0.6 + right[field] * 0.2
            for field in range(4)
        ]
        elapsed = max(
            1,
            keys[min(len(keys) - 1, index + 1)].time_ms -
            keys[max(0, index - 1)].time_ms,
        )
        motion = math.hypot(right[0] - left[0], right[1] - left[1])
        speed = motion * 1000 / elapsed
        polygon = keys[index].polygon
        if polygon is None:
            margin = min(0.10, 0.025 + speed * 0.12)
            box = _box_from_values(*mixed)
            smoothed.append((padded_box(box, margin), None))
            continue
        left_polygon = keys[max(0, index - 1)].polygon or polygon
        right_polygon = keys[min(len(keys) - 1, index + 1)].polygon or polygon
        points = []
        for left_point, point, right_point in zip(
                left_polygon, polygon, right_polygon):
            points.append(Point(
                x=left_point.x * 0.2 + point.x * 0.6 +
                right_point.x * 0.2,
                y=left_point.y * 0.2 + point.y * 0.6 +
                right_point.y * 0.2,
            ))
        # Parsing already contributes a 3% fixed edge. Add only the extra
        # motion-dependent edge here so a stationary face remains close-fit.
        margin = min(0.08, speed * 0.08)
        center_x = sum(point.x for point in points) / len(points)
        center_y = sum(point.y for point in points) / len(points)
        scale = 1.0 + margin * 2
        points = [Point(
            x=min(1.0, max(0.0, center_x +
                  (point.x - center_x) * scale)),
            y=min(1.0, max(0.0, center_y +
                  (point.y - center_y) * scale)),
        ) for point in points]
        smoothed.append((polygon_box(points), points))
    for keyframe, (box, polygon) in zip(keys, smoothed):
        keyframe.box = box
        keyframe.polygon = polygon
    return result


def _read_video_recovery_frames(path, times, first_id=0):
    import cv2

    capture = cv2.VideoCapture(str(path))
    samples = []
    for time_ms in times:
        capture.set(cv2.CAP_PROP_POS_MSEC, time_ms)
        ok, frame = capture.read()
        if not ok:
            capture.release()
            raise MediaValidationError("Não foi possível ler um fotograma.")
        samples.append((first_id + len(samples), time_ms,
                        _encode_video_preview(frame, cv2)))
    capture.release()
    return samples


def _track_video_objects(path, regions, info, scene_cuts=(),
                         uncertain_times=None):
    """Follow model-selected objects between anchors, never before appearance.

    Model observations remain authoritative at their exact timestamps. Local
    optical flow adds measured positions at 10 Hz and continues only while
    visual features remain trackable. A failed flow between confirmed anchors
    uses their enclosing box until the next anchor; after the final anchor a
    failed flow ends the mask instead of holding a stale position indefinitely.
    """
    import cv2
    import numpy as np

    objects = [region for region in regions
               if region.source == "gemini" and region.kind != "face"]
    if not objects:
        return regions
    anchor_times = {key.time_ms for region in objects
                    for key in region.keyframes}
    interval = max(1, round(info["fps"] / TRACK_SAMPLE_RATE))
    capture = cv2.VideoCapture(str(path))
    frames = []
    index, previous_time = 0, -1
    last = None
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        time_ms = _capture_time_ms(capture, index, info["fps"], previous_time)
        previous_time = time_ms
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ratio = min(1.0, 640 / max(gray.shape[:2]))
        if ratio < 1:
            gray = cv2.resize(gray, None, fx=ratio, fy=ratio,
                              interpolation=cv2.INTER_AREA)
        last = (time_ms, gray)
        if index % interval == 0 or time_ms in anchor_times:
            frames.append(last)
        index += 1
    capture.release()
    if not frames:
        raise MediaValidationError("O vídeo não contém fotogramas legíveis.")
    if last[0] != frames[-1][0]:
        frames.append(last)
    frame_display_ms = max(1, round(1000 / info["fps"]))
    output = [region for region in regions if region not in objects]
    for region in objects:
        anchors = sorted(region.keyframes, key=lambda key: key.time_ms)
        by_time = {key.time_ms: key for key in anchors}
        tracked = []
        previous_gray = None
        current_key = None
        lost = False
        for time_ms, gray in frames:
            if time_ms < anchors[0].time_ms:
                continue
            if current_key is not None and _crosses_scene_cut(
                    current_key.time_ms, time_ms, scene_cuts):
                break
            anchor = by_time.get(time_ms)
            if anchor is not None:
                current_key = anchor.model_copy(deep=True)
                lost = False
            elif current_key is not None:
                moved = None if lost else _flow_object_keyframe(
                    previous_gray, gray, current_key, time_ms, cv2, np)
                if moved is None:
                    if uncertain_times is not None:
                        uncertain_times.add(time_ms)
                    future = next((key for key in anchors
                                   if key.time_ms > time_ms), None)
                    if future is None:
                        if uncertain_times is not None:
                            uncertain_times.update(
                                position for position, _ in frames
                                if time_ms <= position <=
                                anchors[-1].time_ms + TRACK_MAX_GAP_MS and
                                not _crosses_scene_cut(
                                    time_ms, position, scene_cuts))
                        break
                    past = max((key for key in anchors
                                if key.time_ms < time_ms),
                               key=lambda key: key.time_ms)
                    first, second = past.box, future.box
                    left, top = min(first.x, second.x), min(first.y, second.y)
                    right = max(first.x + first.width,
                                second.x + second.width)
                    bottom = max(first.y + first.height,
                                 second.y + second.height)
                    current_key = RegionKeyframe(time_ms=time_ms, box=Box(
                        x=left, y=top, width=right - left,
                        height=bottom - top))
                    lost = True
                else:
                    current_key = moved
            else:
                continue
            tracked.append(current_key)
            previous_gray = gray
        if tracked:
            result = region.model_copy(deep=True)
            result.keyframes = tracked
            result.start_ms = tracked[0].time_ms
            result.end_ms = min(info["duration_ms"],
                                tracked[-1].time_ms + frame_display_ms)
            output.append(result)
    return output


def _flow_object_keyframe(previous, current, keyframe, time_ms, cv2, np):
    """Estimate translation and tilt from consistent feature matches."""
    height, width = previous.shape[:2]
    box = keyframe.box
    mask = np.zeros_like(previous)
    left = max(0, round((box.x + box.width * 0.04) * width))
    top = max(0, round((box.y + box.height * 0.04) * height))
    right = min(width, round((box.x + box.width * 0.96) * width))
    bottom = min(height, round((box.y + box.height * 0.96) * height))
    mask[top:bottom, left:right] = 255
    points = cv2.goodFeaturesToTrack(
        previous, mask=mask, maxCorners=120, qualityLevel=0.01,
        minDistance=3, blockSize=5)
    if points is None or len(points) < 6:
        return None
    options = dict(winSize=(31, 31), maxLevel=3)
    moved, status, _ = cv2.calcOpticalFlowPyrLK(
        previous, current, points, None, **options)
    if moved is None:
        return None
    back, back_status, _ = cv2.calcOpticalFlowPyrLK(
        current, previous, moved, None, **options)
    if back is None:
        return None
    valid = ((status.reshape(-1) == 1) & (back_status.reshape(-1) == 1) &
             (np.linalg.norm((back - points).reshape(-1, 2), axis=1) < 1.5))
    before = points.reshape(-1, 2)[valid]
    after = moved.reshape(-1, 2)[valid]
    if len(before) < 6:
        return None
    matrix, inliers = cv2.estimateAffine2D(
        before, after, method=cv2.RANSAC, ransacReprojThreshold=2.5)
    if matrix is None or inliers is None or inliers.sum() < max(
            6, len(before) * 0.5):
        return None
    scales = np.linalg.svd(matrix[:, :2], compute_uv=False)
    if scales.min() < 0.65 or scales.max() > 1.5:
        return None
    corners = np.asarray([
        [box.x * width, box.y * height],
        [(box.x + box.width) * width, box.y * height],
        [(box.x + box.width) * width, (box.y + box.height) * height],
        [box.x * width, (box.y + box.height) * height],
    ], dtype=np.float32)
    transformed = cv2.transform(corners[None], matrix)[0]
    minimum, maximum = transformed.min(axis=0), transformed.max(axis=0)
    left, top = max(0, minimum[0] / width), max(0, minimum[1] / height)
    right, bottom = min(1, maximum[0] / width), min(1, maximum[1] / height)
    if right - left < 0.005 or bottom - top < 0.005:
        return None
    moved_box = Box(x=float(left), y=float(top),
                    width=float(right - left), height=float(bottom - top))
    return RegionKeyframe(time_ms=time_ms, box=moved_box,
                          polygon=transform_polygon(
                              keyframe.polygon, box, moved_box))


def _track_manual_region(path, region, duration_ms, seed_time_ms=None):
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise MediaValidationError("O OpenCV não está instalado.") from None
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise MediaValidationError("Não foi possível abrir o vídeo.")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or not math.isfinite(fps):
        capture.release()
        raise MediaValidationError("O vídeo não tem uma cadência válida.")
    interval = max(1, round(fps / TRACK_SAMPLE_RATE))
    frames = []
    index, previous_time = 0, -1
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        time_ms = _capture_time_ms(capture, index, fps, previous_time)
        previous_time = time_ms
        if index % interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            ratio = min(1.0, 360 / max(gray.shape[:2]))
            if ratio < 1.0:
                gray = cv2.resize(
                    gray, None, fx=ratio, fy=ratio,
                    interpolation=cv2.INTER_AREA)
            frames.append((time_ms, gray))
        index += 1
    capture.release()
    if not frames:
        raise MediaValidationError("O vídeo não contém fotogramas legíveis.")
    requested_time = (
        region.keyframes[-1].time_ms
        if seed_time_ms is None else seed_time_ms)
    requested_time = min(duration_ms, max(0, requested_time))
    initial = region.box_at(requested_time)
    if initial is None:
        initial = min(
            region.keyframes,
            key=lambda key: abs(key.time_ms - requested_time)).box
    initial_polygon = region.polygon_at(requested_time)
    seed_index = min(
        range(len(frames)),
        key=lambda item: abs(frames[item][0] - requested_time))

    def propagate(step):
        output = []
        current_box = initial
        current_polygon = initial_polygon
        misses = 0
        cursor = seed_index + step
        previous_gray = frames[seed_index][1]
        while 0 <= cursor < len(frames):
            time_ms, gray = frames[cursor]
            if cv2.absdiff(previous_gray, gray).mean() > 32:
                break
            moved = _flow_box(
                previous_gray, gray, current_box, cv2, np)
            if moved is None:
                misses += 1
                if misses >= 3:
                    break
            else:
                misses = 0
                current_polygon = transform_polygon(
                    current_polygon, current_box, moved)
                current_box = moved
            output.append(RegionKeyframe(
                time_ms=time_ms, box=current_box,
                polygon=current_polygon))
            previous_gray = gray
            cursor += step
        return output

    seed_time = frames[seed_index][0]
    tracked = list(reversed(propagate(-1)))
    tracked.append(RegionKeyframe(
        time_ms=seed_time, box=initial, polygon=initial_polygon))
    tracked.extend(propagate(1))
    result = region.model_copy(deep=True)
    result.keyframes = tracked
    edge_tolerance = max(250, round(2 * 1000 / TRACK_SAMPLE_RATE))
    result.start_ms = (
        0 if tracked[0].time_ms <= edge_tolerance
        else tracked[0].time_ms)
    result.end_ms = (
        duration_ms
        if duration_ms - tracked[-1].time_ms <= edge_tolerance
        else tracked[-1].time_ms)
    return _smooth_region(result)


def _flow_box(previous, current, box, cv2, np):
    height, width = previous.shape[:2]
    left = max(0, min(width - 1, round(box.x * width)))
    top = max(0, min(height - 1, round(box.y * height)))
    right = max(left + 1, min(width, round((box.x + box.width) * width)))
    bottom = max(top + 1, min(
        height, round((box.y + box.height) * height)))
    mask = np.zeros_like(previous)
    mask[top:bottom, left:right] = 255
    points = cv2.goodFeaturesToTrack(
        previous, mask=mask, maxCorners=80, qualityLevel=0.01,
        minDistance=3, blockSize=5)
    if points is None or len(points) < 4:
        return None
    moved, status, _ = cv2.calcOpticalFlowPyrLK(
        previous, current, points, None,
        winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                  30, 0.01))
    if moved is None or status is None:
        return None
    valid = status.reshape(-1) == 1
    before = points.reshape(-1, 2)[valid]
    after = moved.reshape(-1, 2)[valid]
    if len(before) < 4:
        return None
    displacement = np.median(after - before, axis=0)
    center_before = np.median(before, axis=0)
    center_after = np.median(after, axis=0)
    before_radius = np.linalg.norm(before - center_before, axis=1)
    after_radius = np.linalg.norm(after - center_after, axis=1)
    usable = before_radius > 1.0
    scale = 1.0
    if usable.sum() >= 4:
        scale = float(np.median(after_radius[usable] / before_radius[usable]))
        scale = min(1.12, max(0.89, scale))
    center_x, center_y, box_width, box_height = _box_values(box)
    return _box_from_values(
        center_x + float(displacement[0]) / width,
        center_y + float(displacement[1]) / height,
        box_width * scale,
        box_height * scale,
    )


def _merge_image_regions(regions):
    output = []
    for region in regions:
        duplicate = next((current for current in output
                          if current.kind == region.kind and
                          intersection_over_union(
                              current.keyframes[0].box,
                              region.keyframes[0].box) >= 0.55), None)
        if duplicate is None:
            output.append(region)
    return output


# Faces are not covered with a block mosaic: the crop is reduced to a handful
# of colour cells (which is what makes it irreversible), enlarged smoothly and
# lightly blurred, and shown through an ellipse that hugs the face, with a
# soft edge.
FACE_BLUR_CELLS = 6        # cells across the shorter side of the face
FACE_ELLIPSE_MARGIN = 1.08  # the ellipse is a little larger than the box
FACE_EDGE_SOFTNESS = 0.03   # edge feather, as a fraction of the shorter side
FACE_MIN_SIDE = 8           # smaller boxes fall back to the plain mosaic


def _blur_face(image, box, cv2, np):
    """Blur one face in place. ``image`` is a BGR or RGB array and ``box`` is
    ``(left, top, right, bottom)`` in pixels. Returns False if the box is too
    small, so the caller can use the mosaic instead."""
    height, width = image.shape[:2]
    left, top, right, bottom = box
    box_w, box_h = right - left, bottom - top
    if min(box_w, box_h) < FACE_MIN_SIDE:
        return False
    # Work on a crop a bit larger than the box: the ellipse is larger too.
    pad_x = int(round(box_w * (FACE_ELLIPSE_MARGIN - 1) / 2)) + 2
    pad_y = int(round(box_h * (FACE_ELLIPSE_MARGIN - 1) / 2)) + 2
    x0, y0 = max(0, left - pad_x), max(0, top - pad_y)
    x1, y1 = min(width, right + pad_x), min(height, bottom + pad_y)
    area = image[y0:y1, x0:x1]
    area_h, area_w = area.shape[:2]
    short = min(box_w, box_h)
    cell = max(4.0, short / FACE_BLUR_CELLS)
    columns = max(1, int(math.ceil(area_w / cell)))
    rows = max(1, int(math.ceil(area_h / cell)))
    coarse = cv2.resize(area, (columns, rows), interpolation=cv2.INTER_AREA)
    blurred = cv2.resize(
        coarse, (area_w, area_h), interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(blurred, (0, 0), cell * 0.5)
    sigma = max(1.5, short * FACE_EDGE_SOFTNESS)
    mask = np.zeros((area_h, area_w), dtype=np.float32)
    center = (int(round((left + right) / 2 - x0)),
              int(round((top + bottom) / 2 - y0)))
    axes = (int(round(box_w / 2 * FACE_ELLIPSE_MARGIN + 2 * sigma)),
            int(round(box_h / 2 * FACE_ELLIPSE_MARGIN + 2 * sigma)))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
    mask = np.clip(cv2.GaussianBlur(mask, (0, 0), sigma), 0.0, 1.0)[..., None]
    mixed = area.astype(np.float32) * (1.0 - mask) + (
        blurred.astype(np.float32) * mask)
    area[:] = np.clip(mixed + 0.5, 0, 255).astype(area.dtype)
    return True


def _redact_jpeg(data, regions, time_ms):
    import io
    from PIL import Image
    image = Image.open(io.BytesIO(data)).convert("RGB")
    _pixelate_image_regions(image, regions, time_ms)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=88)
    return buffer.getvalue()


def _pixelate_image_regions(image, regions, time_ms):
    width, height = image.size
    faces = []
    for region in regions:
        box = region.box_at(time_ms)
        if box is None:
            continue
        left = max(0, round(box.x * width))
        top = max(0, round(box.y * height))
        right = min(width, round((box.x + box.width) * width))
        bottom = min(height, round((box.y + box.height) * height))
        if right <= left or bottom <= top:
            continue
        if region.kind == "face":
            faces.append((region, (left, top, right, bottom)))
            continue
        _mosaic_image_region(
            image, region, time_ms, (left, top, right, bottom))
    if faces:
        _blur_image_faces(image, faces, time_ms)


def _blur_image_faces(image, faces, time_ms):
    import numpy as np
    from PIL import Image
    try:
        import cv2
    except ImportError:
        raise MediaError("O OpenCV não está instalado.") from None
    array = np.array(image)
    for region, box in faces:
        if not _blur_face(array, box, cv2, np):
            _mosaic_image_region(image, region, time_ms, box)
            array = np.array(image)
    image.paste(Image.fromarray(array))


def _mosaic_image_region(image, region, time_ms, box):
    """Cover a region with a coarse, tinted mosaic (text, plates, cards)."""
    from PIL import Image, ImageDraw
    width, height = image.size
    left, top, right, bottom = box
    area = image.crop((left, top, right, bottom))
    area_width, area_height = area.size
    # Average each large cell before enlarging it; nearest-neighbour keeps
    # the result visibly pixelated without retaining fine detail.
    cell_size = max(24, -(-min(area_width, area_height) // 5))
    columns = max(1, -(-area_width // cell_size))
    rows = max(1, -(-area_height // cell_size))
    coarse = area.resize(
        (columns, rows),
        resample=Image.Resampling.BOX,
    )
    mosaic = coarse.resize(area.size, resample=Image.Resampling.NEAREST)
    tint = Image.new("RGB", area.size, (43, 69, 90))
    redacted = Image.blend(mosaic, tint, 0.22)
    polygon = region.polygon_at(time_ms)
    if polygon is None:
        image.paste(redacted, (left, top))
        return
    mask = Image.new("L", area.size, 0)
    ImageDraw.Draw(mask).polygon([
        (round(point.x * width) - left,
         round(point.y * height) - top)
        for point in polygon
    ], fill=255)
    image.paste(redacted, (left, top), mask)


def _render_image(source, output, regions, content_type):
    from PIL import Image, ImageOps
    try:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            _pixelate_image_regions(image, regions, 0)
            mime = content_type.split(";", 1)[0].lower()
            image_format = {
                "image/png": "PNG", "image/webp": "WEBP",
            }.get(mime, "JPEG")
            image.save(output, image_format, quality=94)
    except Exception:
        raise MediaError("Não foi possível exportar a imagem.") from None


def _pixelate_video_regions(frame, regions, time_ms, cv2, np):
    """Apply rectangle or polygon masks to one decoded BGR frame."""

    height, width = frame.shape[:2]
    for region in regions:
        box = region.box_at(time_ms)
        if box is None:
            continue
        left, top = round(box.x * width), round(box.y * height)
        right = round((box.x + box.width) * width)
        bottom = round((box.y + box.height) * height)
        left, top = max(0, left), max(0, top)
        right, bottom = min(width, right), min(height, bottom)
        if right <= left or bottom <= top:
            continue
        if region.kind == "face" and _blur_face(
                frame, (left, top, right, bottom), cv2, np):
            continue
        area = frame[top:bottom, left:right]
        area_width, area_height = right - left, bottom - top
        cell_size = max(24, -(-min(area_width, area_height) // 5))
        columns = max(1, -(-area_width // cell_size))
        rows = max(1, -(-area_height // cell_size))
        coarse = cv2.resize(
            area, (columns, rows), interpolation=cv2.INTER_AREA)
        mosaic = cv2.resize(
            coarse, (area_width, area_height),
            interpolation=cv2.INTER_NEAREST)
        # OpenCV uses BGR, so this is the same slate tint as the preview.
        redacted = cv2.addWeighted(
            mosaic, 0.78, np.full_like(mosaic, (90, 69, 43)), 0.22, 0)
        polygon = region.polygon_at(time_ms)
        if polygon is None:
            frame[top:bottom, left:right] = redacted
            continue
        mask = np.zeros((area_height, area_width), dtype=np.uint8)
        points = np.asarray([[
            round(point.x * width) - left,
            round(point.y * height) - top,
        ] for point in polygon], dtype=np.int32)
        cv2.fillPoly(mask, [points], 255)
        np.copyto(area, redacted, where=mask[..., None].astype(bool))


def _render_video(source, output, regions):
    if shutil.which("ffmpeg") is None:
        raise MediaError("O ffmpeg não está instalado.")
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise MediaError("O OpenCV não está instalado.") from None
    capture = cv2.VideoCapture(str(source))
    fps = capture.get(cv2.CAP_PROP_FPS)
    width = round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    silent = Path(output).with_name("redacted-silent.mp4")
    writer = cv2.VideoWriter(
        str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not capture.isOpened() or not writer.isOpened():
        capture.release()
        writer.release()
        raise MediaError("Não foi possível preparar a exportação do vídeo.")
    index = 0
    previous_time_ms = -1
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        time_ms = _capture_time_ms(
            capture, index, fps, previous_time_ms)
        previous_time_ms = time_ms
        _pixelate_video_regions(frame, regions, time_ms, cv2, np)
        writer.write(frame)
        index += 1
    capture.release()
    writer.release()
    command = [
        "ffmpeg", "-y", "-i", str(silent), "-i", str(source),
        "-map", "0:v:0", "-map", "1:a?", "-c:v", "libx264",
        "-preset", "fast", "-crf", "18", "-c:a", "aac",
        "-map_metadata", "-1", "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    silent.unlink(missing_ok=True)
    if result.returncode:
        Path(output).unlink(missing_ok=True)
        raise MediaError("Não foi possível exportar o vídeo.")

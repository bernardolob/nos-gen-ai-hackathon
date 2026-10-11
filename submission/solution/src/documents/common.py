"""Source mapping, image deduplication and static-image redaction."""

import hashlib
import io
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageOps

from media.pipeline import MAX_IMAGE_PIXELS, _pixelate_image_regions

MAX_TOTAL_IMAGE_PIXELS = 100_000_000


class DocumentError(Exception):
    """A document error safe to show without exposing its contents."""


def mapped_lines(raw, references):
    """NFC lines and maps from each normalized character to raw references."""
    lines, maps = [], []
    start = 0
    for row in raw.splitlines(keepends=True):
        text = row.rstrip("\r\n").rstrip()
        if text.strip():
            chars, refs = [], []
            index = 0
            while index < len(text):
                end = index + 1
                while end < len(text) and unicodedata.combining(text[end]):
                    end += 1
                normalized = unicodedata.normalize("NFC", text[index:end])
                group = references[start + index:start + end]
                chars.append(normalized)
                refs.extend([group] * len(normalized))
                index = end
            lines.append("".join(chars))
            maps.append(refs)
        start += len(row)
    return lines, maps


@dataclass
class DocumentImage:
    id: str
    path: Path
    width: int
    height: int
    placements: list = field(default_factory=list)
    regions: list = field(default_factory=list)

    def snapshot(self):
        return {
            "id": self.id, "width": self.width, "height": self.height,
            "source_url": "/api/document/images/" + self.id,
            "placements": [p["label"] for p in self.placements],
            "regions": [r.model_dump() for r in self.regions],
        }


class DocumentAdapter:
    def __init__(self, path, folder):
        self.path = Path(path)
        self.folder = Path(folder)
        self.lines, self.maps = [], []
        self.images = []
        self.id = uuid4().hex
        self._pixels = 0

    def add_image(self, data, placement):
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP", "BMP",
                                         "TIFF", "GIF"}:
                    raise DocumentError("Formato de imagem não suportado.")
                if (source.width * source.height > MAX_IMAGE_PIXELS or
                        getattr(source, "n_frames", 1) != 1):
                    raise DocumentError(
                        "Imagem demasiado grande ou com vários fotogramas.")
                image = ImageOps.exif_transpose(source).convert("RGBA")
                digest = self.id + "-" + hashlib.sha256(
                    str(image.size).encode() + image.tobytes()).hexdigest()
                item = next((i for i in self.images if i.id == digest), None)
                if item is None:
                    self._pixels += image.width * image.height
                    if self._pixels > MAX_TOTAL_IMAGE_PIXELS:
                        raise DocumentError(
                            "O documento contém demasiados píxeis de imagem.")
                    target = self.folder / (digest + ".png")
                    image.save(target, "PNG")
                    item = DocumentImage(
                        digest, target, image.width, image.height)
                    self.images.append(item)
                item.placements.append(placement)
        except DocumentError:
            raise
        except Exception:
            raise DocumentError(
                "Não foi possível ler uma imagem do documento.") from None

    def snapshot(self, filename, output_url=None):
        return {
            "id": self.id,
            "format": self.format, "filename": filename,
            "images": [image.snapshot() for image in self.images],
            "output_url": output_url,
        }

    def redacted_images(self, regions):
        return {image.id: redact_image(image.path, regions[image.id])
                for image in self.images}


def redact_image(path, regions):
    """Keep transparency outside masks; masked pixels are opaque."""
    with Image.open(path) as original:
        rgba = original.convert("RGBA")
        rgb = rgba.convert("RGB")
        _pixelate_image_regions(rgb, regions, 0)
        alpha = rgba.getchannel("A")
        width, height = rgba.size
        for region in regions:
            box = region.box_at(0)
            if box is None:
                continue
            left, top = round(box.x * width), round(box.y * height)
            right = min(width, round((box.x + box.width) * width))
            bottom = min(height, round((box.y + box.height) * height))
            if right <= left or bottom <= top:
                continue
            polygon = region.polygon_at(0)
            if polygon:
                mask = Image.new("L", (right - left, bottom - top), 0)
                ImageDraw.Draw(mask).polygon([
                    (round(p.x * width) - left, round(p.y * height) - top)
                    for p in polygon], fill=255)
                alpha.paste(255, (left, top, right, bottom), mask)
            else:
                alpha.paste(255, (left, top, right, bottom))
        rgb.putalpha(alpha)
        output = io.BytesIO()
        rgb.save(output, "PNG")
        return output.getvalue()

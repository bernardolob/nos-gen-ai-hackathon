"""Validated, value-free redaction region contracts."""

from __future__ import annotations

from bisect import bisect_left
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from categories import CATEGORY_NAMES, CONFIDENCE_LEVELS

REGION_KINDS = {
    "face", "text", "identity_document", "plate", "signature",
    "biometric", "code", "other",
}
REGION_SOURCES = {"gemini", "face_detector", "user"}


class StrictMutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Box(StrictMutableModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @field_validator("width")
    @classmethod
    def width_fits(cls, value, info):
        x = info.data.get("x", 0)
        if x + value > 1.000001:
            raise ValueError("box exceeds image width")
        return value

    @field_validator("height")
    @classmethod
    def height_fits(cls, value, info):
        y = info.data.get("y", 0)
        if y + value > 1.000001:
            raise ValueError("box exceeds image height")
        return value


class Point(StrictMutableModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class RegionKeyframe(StrictMutableModel):
    time_ms: int = Field(ge=0)
    box: Box
    polygon: list[Point] | None = None

    @field_validator("polygon")
    @classmethod
    def valid_polygon(cls, value):
        if value is not None and len(value) != 32:
            raise ValueError("face polygons must contain exactly 32 points")
        return value

    @model_validator(mode="after")
    def polygon_fits_box(self):
        if self.polygon is None:
            return self
        tolerance = 0.000001
        right = self.box.x + self.box.width
        bottom = self.box.y + self.box.height
        if any(
            point.x < self.box.x - tolerance or point.x > right + tolerance or
            point.y < self.box.y - tolerance or point.y > bottom + tolerance
            for point in self.polygon
        ):
            raise ValueError("polygon must fit inside its fallback box")
        return self


class MediaRegion(StrictMutableModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    category: str
    kind: str
    reason: str = Field(min_length=1, max_length=240)
    confidence: str
    source: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    keyframes: list[RegionKeyframe] = Field(min_length=1)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value):
        if value not in CATEGORY_NAMES:
            raise ValueError("unknown sensitive-data category")
        return value

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value):
        if value not in REGION_KINDS:
            raise ValueError("unknown media region kind")
        return value

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value):
        if value not in CONFIDENCE_LEVELS:
            raise ValueError("unknown confidence")
        return value

    @field_validator("source")
    @classmethod
    def valid_source(cls, value):
        if value not in REGION_SOURCES:
            raise ValueError("unknown media region source")
        return value

    def box_at(self, time_ms: int) -> Box | None:
        if time_ms < self.start_ms or time_ms > self.end_ms:
            return None
        ordered = sorted(self.keyframes, key=lambda key: key.time_ms)
        times = [key.time_ms for key in ordered]
        index = bisect_left(times, time_ms)
        if index == 0:
            return ordered[0].box
        if index >= len(ordered):
            return ordered[-1].box
        left, right = ordered[index - 1], ordered[index]
        span = right.time_ms - left.time_ms
        ratio = 0 if span == 0 else (time_ms - left.time_ms) / span
        return Box(
            x=left.box.x + (right.box.x - left.box.x) * ratio,
            y=left.box.y + (right.box.y - left.box.y) * ratio,
            width=left.box.width + (right.box.width - left.box.width) * ratio,
            height=left.box.height + (
                right.box.height - left.box.height) * ratio,
        )

    def polygon_at(self, time_ms: int) -> list[Point] | None:
        """Interpolate matching polygon vertices, or use the safe box path."""

        if time_ms < self.start_ms or time_ms > self.end_ms:
            return None
        ordered = sorted(self.keyframes, key=lambda key: key.time_ms)
        times = [key.time_ms for key in ordered]
        index = bisect_left(times, time_ms)
        if index < len(ordered) and ordered[index].time_ms == time_ms:
            return _copy_polygon(ordered[index].polygon)
        if index == 0:
            polygon = ordered[0].polygon
            return _copy_polygon(polygon)
        if index >= len(ordered):
            polygon = ordered[-1].polygon
            return _copy_polygon(polygon)
        left, right = ordered[index - 1], ordered[index]
        if left.polygon is None or right.polygon is None:
            return None
        span = right.time_ms - left.time_ms
        ratio = 0 if span == 0 else (time_ms - left.time_ms) / span
        return [
            Point(
                x=first.x + (second.x - first.x) * ratio,
                y=first.y + (second.y - first.y) * ratio,
            )
            for first, second in zip(left.polygon, right.polygon)
        ]


class RegionManifest(StrictMutableModel):
    attempt: int = Field(ge=1)
    regions: list[MediaRegion]


def padded_box(box: Box, padding: float = 0.12) -> Box:
    """Expand a box on every side while keeping normalized bounds."""

    dx, dy = box.width * padding, box.height * padding
    x, y = max(0.0, box.x - dx), max(0.0, box.y - dy)
    right = min(1.0, box.x + box.width + dx)
    bottom = min(1.0, box.y + box.height + dy)
    return Box(x=x, y=y, width=right - x, height=bottom - y)


def polygon_box(polygon: list[Point]) -> Box:
    """Return the tight normalized box around a validated polygon."""

    left = min(point.x for point in polygon)
    top = min(point.y for point in polygon)
    right = max(point.x for point in polygon)
    bottom = max(point.y for point in polygon)
    return Box(
        x=left,
        y=top,
        width=max(0.000001, right - left),
        height=max(0.000001, bottom - top),
    )


def transform_polygon(
    polygon: list[Point] | None,
    source: Box,
    target: Box,
) -> list[Point] | None:
    """Apply the box move/resize transform to every polygon vertex."""

    if polygon is None:
        return None
    return [
        Point(
            x=min(1.0, max(0.0, target.x +
                  (point.x - source.x) / source.width * target.width)),
            y=min(1.0, max(0.0, target.y +
                  (point.y - source.y) / source.height * target.height)),
        )
        for point in polygon
    ]


def _copy_polygon(polygon):
    if polygon is None:
        return None
    return [Point(x=point.x, y=point.y) for point in polygon]


def intersection_over_union(first: Box, second: Box) -> float:
    left, top = max(first.x, second.x), max(first.y, second.y)
    right = min(first.x + first.width, second.x + second.width)
    bottom = min(first.y + first.height, second.y + second.height)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = first.width * first.height + second.width * second.height
    union -= intersection
    return intersection / union if union else 0.0

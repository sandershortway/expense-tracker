"""Local CPU-only OCR adapter built on pytesseract and Tesseract.

The adapter is deliberately small: it owns everything that touches the
Tesseract binary or PIL images, so the screenshot parser can be tested
with a fake engine. No image or OCR text ever leaves the machine.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytesseract
from PIL import Image, ImageOps

TESSERACT_ENV = "INVESTMENT_LEDGER_TESSERACT"
TESSDATA_ENV = "INVESTMENT_LEDGER_TESSDATA"
DEFAULT_LANGUAGE = "nld"
DEFAULT_TESSDATA = Path(".data") / "tessdata"
PREPROCESS_SCALE = 3
INK_THRESHOLD = 120
TOP_BAND_END = 0.55
BOTTOM_BAND_START = 0.72
RIGHT_PAD = 140
CENTS_BAND_END = 0.62
CENTS_RIGHT_PAD = 10
REGION_PAD = 8

_WINDOWS_TESSERACT = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


class OcrError(Exception):
    """An image could not be read or recognised."""


class OcrUnavailable(OcrError):
    """The Tesseract binary or language data is not installed."""


@dataclass(frozen=True)
class OcrWord:
    """One recognised word with its position on the prepared image."""

    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    block: int
    paragraph: int
    line: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def line_key(self) -> tuple[int, int, int]:
        return (self.block, self.paragraph, self.line)


@dataclass(frozen=True)
class OcrReading:
    """Text recognised in a region; confidence is -1 when empty."""

    text: str
    confidence: float


def find_tesseract_cmd() -> str:
    override = os.environ.get(TESSERACT_ENV)
    if override:
        if Path(override).is_file():
            return override
        raise OcrUnavailable(
            f"{TESSERACT_ENV} points to a missing file: {override}"
        )
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    for candidate in _WINDOWS_TESSERACT:
        if candidate.is_file():
            return str(candidate)
    raise OcrUnavailable(
        "Tesseract OCR is not installed. Install it (for example "
        "'winget install UB-Mannheim.TesseractOCR') or set "
        f"{TESSERACT_ENV} to the tesseract executable."
    )


def find_tessdata_dir(language: str = DEFAULT_LANGUAGE) -> str:
    override = os.environ.get(TESSDATA_ENV)
    if override:
        if (Path(override) / f"{language}.traineddata").is_file():
            return override
        raise OcrUnavailable(
            f"{TESSDATA_ENV} does not contain {language}.traineddata"
        )
    if (DEFAULT_TESSDATA / f"{language}.traineddata").is_file():
        return str(DEFAULT_TESSDATA)
    raise OcrUnavailable(
        f"Language data '{language}.traineddata' not found in "
        f"{DEFAULT_TESSDATA}. Download it from the tessdata_fast "
        "repository and set it up as described in the README, or "
        f"set {TESSDATA_ENV}."
    )


def _tsv_rows(data: dict[str, Any]) -> list[tuple[str, float, int]]:
    rows = []
    for i, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if text:
            rows.append((text, float(data["conf"][i]), i))
    return rows


class TesseractEngine:
    """Local OCR engine; one instance per command invocation."""

    def __init__(
        self,
        *,
        cmd: str | None = None,
        tessdata_dir: str | None = None,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self._language = language
        self._cmd = cmd or find_tesseract_cmd()
        self._tessdata = tessdata_dir or find_tessdata_dir(language)
        pytesseract.pytesseract.tesseract_cmd = self._cmd
        self._config = f"--tessdata-dir {self._tessdata}"

    @property
    def tessdata_dir(self) -> str:
        return self._tessdata

    def load(self, path: str | Path) -> Image.Image:
        try:
            return Image.open(path).convert("RGB")
        except (OSError, ValueError) as exc:
            raise OcrError(f"cannot open image {path}: {exc}") from exc

    def preprocess(self, image: Image.Image) -> Image.Image:
        """Invert the dark UI and upscale for small text."""
        inverted = ImageOps.invert(image.convert("RGB"))
        size = (
            inverted.width * PREPROCESS_SCALE,
            inverted.height * PREPROCESS_SCALE,
        )
        return inverted.resize(size, Image.LANCZOS)

    def mask(self, image: Image.Image, size: tuple[int, int]) -> Image.Image:
        """Blue channel used to locate the blue headline digits."""
        return image.convert("RGB").getchannel("B").resize(size, Image.LANCZOS)

    def words(self, image: Image.Image) -> list[OcrWord]:
        """Recognise words, confidence, and positions on an image."""
        data = pytesseract.image_to_data(
            image,
            lang=self._language,
            config=self._config,
            output_type=pytesseract.Output.DICT,
        )
        found = []
        for text, confidence, i in _tsv_rows(data):
            found.append(
                OcrWord(
                    text=text,
                    confidence=confidence,
                    left=int(data["left"][i]),
                    top=int(data["top"][i]),
                    width=int(data["width"][i]),
                    height=int(data["height"][i]),
                    block=int(data["block_num"][i]),
                    paragraph=int(data["par_num"][i]),
                    line=int(data["line_num"][i]),
                )
            )
        return found

    def read(
        self,
        image: Image.Image,
        *,
        whitelist: str | None = None,
        psm: int = 7,
    ) -> OcrReading:
        """Recognise a small region, optionally with a character whitelist."""
        config = f"{self._config} --psm {psm}"
        if whitelist is not None:
            config += f" -c tessedit_char_whitelist={whitelist}"
        data = pytesseract.image_to_data(
            image,
            lang=self._language,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
        rows = _tsv_rows(data)
        if not rows:
            return OcrReading(text="", confidence=-1.0)
        return OcrReading(
            text=" ".join(text for text, _, _ in rows),
            confidence=max(confidence for _, confidence, _ in rows),
        )

    def read_value(
        self,
        image: Image.Image,
        box: tuple[int, int, int, int],
        *,
        whitelist: str,
        psm: int = 7,
        pad: int = REGION_PAD,
    ) -> OcrReading:
        """Recognise a value inside a bounding box with some padding."""
        left, top, right, bottom = box
        crop = image.crop(
            (
                max(0, left - pad),
                max(0, top - pad),
                min(image.width, right + pad),
                min(image.height, bottom + pad),
            )
        )
        return self.read(crop, whitelist=whitelist, psm=psm)


def top_ink_region(
    mask: Image.Image,
    box: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    """Locate the superscript cents inside a headline amount box.

    The app renders cents as small superscript digits at the top right of
    the amount. On the blue-channel mask they are the rightmost ink that
    reaches the top band but not the bottom band, sitting after the
    baseline-only comma.
    """
    left, top, right, bottom = box
    region = mask.crop((left, top, min(mask.width, right + RIGHT_PAD), bottom))
    width, height = region.size
    if width <= 0 or height <= 0:
        return None
    pixels = region.load()
    top_end = int(height * TOP_BAND_END)
    bottom_start = int(height * BOTTOM_BAND_START)

    kinds = []
    for x in range(width):
        has_top = any(pixels[x, y] > INK_THRESHOLD for y in range(top_end))
        has_bottom = any(
            pixels[x, y] > INK_THRESHOLD for y in range(bottom_start, height)
        )
        if has_top and has_bottom:
            kinds.append("F")
        elif has_top:
            kinds.append("T")
        elif has_bottom:
            kinds.append("B")
        else:
            kinds.append(".")

    last_baseline = -1
    x = width - 1
    while x >= 0:
        if kinds[x] == "B":
            last_baseline = x
            break
        if kinds[x] == "F" and last_baseline == -1:
            last_baseline = -2
            break
        x -= 1
    if last_baseline < 0:
        return None

    runs: list[tuple[int, int]] = []
    run_start = -1
    for x in range(last_baseline + 1, width):
        if kinds[x] == "T":
            if run_start < 0:
                run_start = x
        elif run_start >= 0:
            runs.append((run_start, x - 1))
            run_start = -1
    if run_start >= 0:
        runs.append((run_start, width - 1))
    if not runs:
        return None

    cents_left = left + runs[0][0]
    cents_right = left + runs[-1][1] + CENTS_RIGHT_PAD
    return (cents_left, top, cents_right, top + int(height * CENTS_BAND_END))

import pytest
from PIL import Image, ImageDraw, ImageFont

from investment_ledger.ocr import (
    OcrError,
    OcrUnavailable,
    TesseractEngine,
    find_tessdata_dir,
    find_tesseract_cmd,
    top_ink_region,
)


def _fake_mask() -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Mask imitating '100,<sup>00' with a baseline-only comma."""
    mask = Image.new("L", (400, 100), 0)
    draw = ImageDraw.Draw(mask)
    for x in (20, 70, 120):
        draw.rectangle((x, 10, x + 30, 95), fill=255)
    draw.rectangle((170, 80, 180, 95), fill=255)
    for x in (200, 240):
        draw.rectangle((x, 5, x + 25, 40), fill=255)
    return mask, (0, 0, 200, 100)


def test_top_ink_region_finds_superscript_digits() -> None:
    mask, box = _fake_mask()
    region = top_ink_region(mask, box)
    assert region is not None
    left, top, right, bottom = region
    assert left >= 195
    assert right <= 285
    assert bottom - top <= 65


def test_top_ink_region_without_superscript() -> None:
    mask = Image.new("L", (300, 100), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((20, 10, 50, 95), fill=255)
    draw.rectangle((70, 10, 100, 95), fill=255)
    assert top_ink_region(mask, (0, 0, 120, 100)) is None


def test_top_ink_region_empty_box() -> None:
    mask = Image.new("L", (300, 100), 0)
    assert top_ink_region(mask, (10, 10, 10, 10)) is None


def test_find_tesseract_cmd_env_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "INVESTMENT_LEDGER_TESSERACT", str(tmp_path / "missing.exe")
    )
    with pytest.raises(OcrUnavailable):
        find_tesseract_cmd()


def test_find_tesseract_cmd_env_valid(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "tesseract.exe"
    binary.write_bytes(b"fake")
    monkeypatch.setenv("INVESTMENT_LEDGER_TESSERACT", str(binary))
    assert find_tesseract_cmd() == str(binary)


def test_find_tessdata_dir_env_missing_language(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INVESTMENT_LEDGER_TESSDATA", str(tmp_path))
    with pytest.raises(OcrUnavailable):
        find_tessdata_dir()


def test_find_tessdata_dir_env_valid(tmp_path, monkeypatch) -> None:
    (tmp_path / "nld.traineddata").write_bytes(b"fake")
    monkeypatch.setenv("INVESTMENT_LEDGER_TESSDATA", str(tmp_path))
    assert find_tessdata_dir() == str(tmp_path)


def _engine() -> TesseractEngine:
    try:
        return TesseractEngine()
    except OcrUnavailable:
        pytest.skip("tesseract binary or nld traineddata unavailable")


def test_load_missing_image(tmp_path) -> None:
    engine = _engine()
    with pytest.raises(OcrError):
        engine.load(tmp_path / "missing.png")


def _font(size: int = 40) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def test_engine_reads_generated_text(tmp_path) -> None:
    pytest.importorskip("pytesseract")
    engine = _engine()
    image = Image.new("RGB", (500, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 20), "Test 1234", fill="black", font=_font())
    reading = engine.read(image)
    assert "1234" in reading.text


def test_words_returns_confidence(tmp_path) -> None:
    engine = _engine()
    image = Image.new("RGB", (500, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 20), "Aankoop", fill="black", font=_font())
    found = engine.words(image)
    assert found
    assert any("aankoop" in word.text.lower() for word in found)
    assert all(isinstance(word.confidence, float) for word in found)

from collections import deque
from datetime import date
from decimal import Decimal

import pytest
from PIL import Image, ImageDraw

from investment_ledger.ocr import OcrReading, OcrWord
from investment_ledger.screenshot import (
    InstrumentMapping,
    parse_eur,
    parse_screenshot,
    parse_shares,
)


def _word(
    text: str,
    left: int,
    top: int,
    width: int = 80,
    height: int = 30,
    line: int = 1,
    confidence: float = 95.0,
) -> OcrWord:
    return OcrWord(
        text=text,
        confidence=confidence,
        left=left,
        top=top,
        width=width,
        height=height,
        block=1,
        paragraph=1,
        line=line,
    )


class FakeEngine:
    """Deterministic stand-in for TesseractEngine."""

    def __init__(
        self,
        words: list[OcrWord],
        mask: Image.Image,
        reads: dict[str, OcrReading] | None = None,
        value_reads: list[OcrReading] | None = None,
    ) -> None:
        self._words = words
        self._mask = mask
        self._reads = reads or {}
        self._value_reads = deque(value_reads or [])

    def preprocess(self, image: Image.Image) -> Image.Image:
        return image

    def mask(self, image: Image.Image, size) -> Image.Image:
        return self._mask.resize(size)

    def words(self, image: Image.Image) -> list[OcrWord]:
        return self._words

    def read(
        self, image: Image.Image, *, whitelist=None, psm: int = 7
    ) -> OcrReading:
        return self._reads.get(whitelist, OcrReading("", -1))

    def read_value(
        self, image, box, *, whitelist, psm: int = 7, pad: int = 8
    ) -> OcrReading:
        return self._value_reads.popleft()


def _mask_with_cents(
    box: tuple[int, int, int, int], size=(800, 900)
) -> Image.Image:
    """Mask where the headline has a comma plus superscript cents."""
    left, top, right, bottom = box
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((left + 10, top, left + 60, bottom), fill=255)
    draw.rectangle((right - 30, bottom - 20, right - 20, bottom), fill=255)
    draw.rectangle(
        (right + 10, top, right + 30, top + (bottom - top) // 2), fill=255
    )
    draw.rectangle(
        (right + 35, top, right + 55, top + (bottom - top) // 2), fill=255
    )
    return mask


def _purchase_words() -> list[OcrWord]:
    return [
        _word("&", 10, 20, line=1),
        _word("Terug", 40, 20, line=1),
        _word("Aankoop", 400, 20, line=1),
        _word("aandeel", 480, 20, line=1),
        _word("Nvidia", 350, 120, line=2),
        _word("11", 300, 170, width=30, line=3),
        _word("maart", 340, 170, line=3),
        _word("2025", 410, 170, width=50, line=3),
        _word("08:33", 470, 170, width=60, line=3),
        _word("€", 100, 300, width=40, height=80, line=4),
        _word("100,°°", 160, 295, width=180, height=90, line=4),
        _word("Aandelen", 50, 450, width=110, line=5),
        _word("1.03", 700, 450, width=60, line=5),
        _word("Koopprijs", 50, 500, width=110, line=6),
        _word("per", 170, 500, width=40, line=6),
        _word("aandeel", 220, 500, width=70, line=6),
        _word("€", 690, 500, width=20, line=6),
        _word("96,82", 715, 500, width=60, line=6),
        _word("Kosten", 50, 550, width=90, line=7),
        _word("€", 690, 550, width=20, line=7),
        _word("0,00", 715, 550, width=60, line=7),
    ]


def _dividend_words() -> list[OcrWord]:
    return [
        _word("&", 10, 20, line=1),
        _word("Terug", 40, 20, line=1),
        _word("Ontvangen", 380, 20, line=1),
        _word("dividend", 470, 20, line=1),
        _word("Nvidia", 350, 120, line=2),
        _word("2", 300, 170, width=20, line=3),
        _word("oktober", 330, 170, line=3),
        _word("2026", 410, 170, width=50, line=3),
        _word("15:35", 470, 170, width=60, line=3),
        _word("€", 100, 300, width=40, height=80, line=4),
        _word("2,07", 160, 295, width=100, height=90, line=4),
    ]


def _engine_for(
    words: list[OcrWord],
    reads: dict[str, OcrReading] | None = None,
    value_reads: list[OcrReading] | None = None,
) -> FakeEngine:
    headline = [w for w in words if w.line == 4]
    if headline:
        box = (
            min(w.left for w in headline),
            min(w.top for w in headline),
            max(w.right for w in headline),
            max(w.bottom for w in headline),
        )
    else:
        box = (0, 0, 10, 10)
    mask = _mask_with_cents(box)
    default_reads = {
        "0123456789": OcrReading("00", 60.0),
        "€.,0123456789 ": OcrReading("€ 100,", 90.0),
    }
    default_reads.update(reads or {})
    return FakeEngine(words, mask, default_reads, value_reads)


def test_parse_purchase_succeeds() -> None:
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(
        _purchase_words(),
        value_reads=[
            OcrReading("1.03", 95.0),
            OcrReading("96,82", 95.0),
            OcrReading("0,00", 95.0),
        ],
    )
    result = parse_screenshot(image, engine)
    assert result.event == "purchase"
    assert result.product_name == "Nvidia"
    assert result.trade_date == date(2025, 3, 11)
    assert result.trade_time == "08:33"
    assert result.gross_amount_eur == Decimal("100.00")
    assert result.displayed_quantity == Decimal("1.03")
    assert result.unit_price_eur == Decimal("96.82")
    assert result.fee_eur == Decimal("0.00")
    assert result.derived_quantity == Decimal("1.03284445")
    assert result.problems == []
    assert result.ready


def test_import_row_validates_with_domain() -> None:
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(
        _purchase_words(),
        value_reads=[
            OcrReading("1.03", 95.0),
            OcrReading("96,82", 95.0),
            OcrReading("0,00", 95.0),
        ],
    )
    result = parse_screenshot(image, engine)
    row = result.import_row(InstrumentMapping("stock", "NVDA", "XETRA"))
    assert row["side"] == "buy"
    assert row["ticker"] == "NVDA"
    assert row["exchange"] == "XETRA"
    assert row["trade_date"] == "2025-03-11"
    assert row["quantity"] == "1.03284445"
    assert row["gross_amount_eur"] == "100.00"
    assert row["name"] == "Nvidia"


def test_parse_dividend_without_card() -> None:
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(_dividend_words())
    result = parse_screenshot(image, engine)
    assert result.event == "dividend"
    assert result.product_name == "Nvidia"
    assert result.trade_date == date(2026, 10, 2)
    assert result.gross_amount_eur == Decimal("100.00")
    assert result.derived_quantity is None


def test_unknown_layout_is_rejected() -> None:
    image = Image.new("RGB", (800, 900))
    words = [_word("Hallo", 100, 100, line=1)]
    engine = _engine_for(words)
    result = parse_screenshot(image, engine)
    assert result.event is None
    assert result.problems


def test_missing_date_is_rejected() -> None:
    words = [w for w in _purchase_words() if w.line != 3]
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(words)
    result = parse_screenshot(image, engine)
    assert result.event == "purchase"
    assert any("date" in p for p in result.problems)


def test_missing_quantity_row_is_rejected() -> None:
    words = [w for w in _purchase_words() if w.line != 5]
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(
        words,
        value_reads=[OcrReading("96,82", 95.0), OcrReading("0,00", 95.0)],
    )
    result = parse_screenshot(image, engine)
    assert any("quantity" in p for p in result.problems)


def test_quantity_mismatch_is_rejected() -> None:
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(
        _purchase_words(),
        value_reads=[
            OcrReading("9.99", 95.0),
            OcrReading("96,82", 95.0),
            OcrReading("0,00", 95.0),
        ],
    )
    result = parse_screenshot(image, engine)
    assert any("quantity" in p for p in result.problems)
    assert not result.ready


def test_low_confidence_is_rejected() -> None:
    words = [
        OcrWord(**{**w.__dict__, "confidence": 10.0})
        if w.text == "Nvidia"
        else w
        for w in _purchase_words()
    ]
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(
        words,
        value_reads=[
            OcrReading("1.03", 95.0),
            OcrReading("96,82", 95.0),
            OcrReading("0,00", 95.0),
        ],
    )
    result = parse_screenshot(image, engine)
    assert any("confidence" in p for p in result.problems)


def test_bad_cents_read_is_rejected() -> None:
    image = Image.new("RGB", (800, 900))
    engine = _engine_for(
        _purchase_words(),
        reads={"0123456789": OcrReading("9", 40.0)},
        value_reads=[
            OcrReading("1.03", 95.0),
            OcrReading("96,82", 95.0),
            OcrReading("0,00", 95.0),
        ],
    )
    result = parse_screenshot(image, engine)
    assert any("cents" in p or "amount" in p for p in result.problems)


def test_parse_eur() -> None:
    assert parse_eur("€ 2.000,00") == Decimal("2000.00")
    assert parse_eur("96,82") == Decimal("96.82")
    assert parse_eur("4,75") == Decimal("4.75")
    with pytest.raises(ValueError):
        parse_eur("475")
    with pytest.raises(ValueError):
        parse_eur("1.000")


def test_parse_shares() -> None:
    assert parse_shares("1.03") == Decimal("1.03")
    assert parse_shares("52.51") == Decimal("52.51")
    with pytest.raises(ValueError):
        parse_shares("1,03")
    with pytest.raises(ValueError):
        parse_shares("103")

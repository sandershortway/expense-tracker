"""Parse the supported Dutch transaction screenshot layout.

The parser works against the :class:`OcrEngine` protocol so tests can
feed canned words and region readings. It fails closed: anything that
cannot be extracted confidently is recorded as a problem and the caller
must not produce an import row for that screenshot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Protocol

from investment_ledger.domain import TransactionData, ValidationError
from investment_ledger.ocr import OcrReading, OcrWord, top_ink_region

if TYPE_CHECKING:
    from PIL import Image

MIN_WORD_CONFIDENCE = 45.0
CENTS_PATTERN = re.compile(r"\d{2}\Z")
HEADLINE_INTEGER_PATTERN = re.compile(r"€?\s*\d{1,3}(?:\.\d{3})*\s*,?\Z")
EUR_PATTERN = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}\Z")
SHARES_PATTERN = re.compile(r"\d+\.\d{1,2}\Z")
DATE_PATTERN = re.compile(r"(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{1,2}):(\d{2})")

EUR_WHITELIST = "€.,0123456789 "
DIGITS_WHITELIST = "0123456789"
SHARES_WHITELIST = ".,0123456789"

DUTCH_MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}

_QUANTITY_QUANTUM = Decimal("0.00000001")
_DISPLAYED_QUANTUM = Decimal("0.01")
_CENT = Decimal("0.01")


class OcrEngine(Protocol):
    """Subset of TesseractEngine used by the parser."""

    def preprocess(self, image: Image.Image) -> Image.Image: ...
    def mask(
        self, image: Image.Image, size: tuple[int, int]
    ) -> Image.Image: ...
    def words(self, image: Image.Image) -> list[OcrWord]: ...
    def read(
        self, image: Image.Image, *, whitelist: str | None, psm: int = 7
    ) -> OcrReading: ...
    def read_value(
        self,
        image: Image.Image,
        box: tuple[int, int, int, int],
        *,
        whitelist: str,
        psm: int = 7,
        pad: int = 8,
    ) -> OcrReading: ...


@dataclass(frozen=True)
class InstrumentMapping:
    instrument_type: str
    ticker: str
    exchange: str


@dataclass
class ParsedScreenshot:
    """Everything the parser could establish about one screenshot."""

    event: str | None = None  # "purchase" | "dividend" | None
    product_name: str | None = None
    trade_date: date | None = None
    trade_time: str | None = None
    gross_amount_eur: Decimal | None = None
    displayed_quantity: Decimal | None = None
    unit_price_eur: Decimal | None = None
    fee_eur: Decimal | None = None
    derived_quantity: Decimal | None = None
    min_confidence: float = 100.0
    warnings: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.event == "purchase" and not self.problems

    def import_row(self, mapping: InstrumentMapping) -> dict[str, str | None]:
        """Build and validate a PRD-002 import row."""
        if not self.ready:
            raise ValidationError(
                "screenshot cannot produce an import row: "
                + "; ".join(self.problems or ["not a purchase"])
            )
        data = TransactionData.from_mapping(
            {
                "side": "buy",
                "instrument_type": mapping.instrument_type,
                "ticker": mapping.ticker,
                "exchange": mapping.exchange,
                "trade_date": self.trade_date.isoformat(),
                "quantity": str(self.derived_quantity),
                "unit_price_eur": str(self.unit_price_eur),
                "gross_amount_eur": str(self.gross_amount_eur),
                "fee_eur": None if self.fee_eur is None else str(self.fee_eur),
                "name": self.product_name,
            }
        )
        return data.to_mapping()


def parse_eur(text: str) -> Decimal:
    """Parse '€ 2.000,00'-style amounts; commas are mandatory."""
    cleaned = text.replace("€", "").strip().replace(" ", "")
    if not EUR_PATTERN.fullmatch(cleaned):
        raise ValueError(f"not a Dutch EUR amount: {text!r}")
    return Decimal(cleaned.replace(".", "").replace(",", "."))


def _parse_headline_integer(text: str) -> Decimal:
    cleaned = text.strip()
    if not HEADLINE_INTEGER_PATTERN.fullmatch(cleaned):
        raise ValueError(f"not a headline integer: {text!r}")
    return Decimal(
        cleaned.replace("€", "").replace(" ", "").replace(".", "").rstrip(",")
    )


def parse_shares(text: str) -> Decimal:
    """Parse the displayed share count ('1.03' uses a decimal point)."""
    cleaned = text.strip()
    if not SHARES_PATTERN.fullmatch(cleaned):
        raise ValueError(f"not a displayed share count: {text!r}")
    return Decimal(cleaned)


def _group_lines(words: list[OcrWord]) -> list[list[OcrWord]]:
    lines: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        lines.setdefault(word.line_key, []).append(word)
    grouped = sorted(lines.values(), key=lambda ws: min(w.top for w in ws))
    for group in grouped:
        group.sort(key=lambda w: w.left)
    return grouped


def _parse_dutch_datetime(
    text: str,
) -> tuple[date, str] | None:
    match = DATE_PATTERN.search(text.lower())
    if not match:
        return None
    day, month_name, year, hour, minute = match.groups()
    month = DUTCH_MONTHS.get(month_name)
    if month is None:
        return None
    try:
        parsed = date(int(year), month, int(day))
    except ValueError:
        return None
    return parsed, f"{int(hour):02d}:{int(minute):02d}"


def _first_line_containing(
    lines: list[list[OcrWord]], start: int, needle: str
) -> int | None:
    for index in range(start, len(lines)):
        if needle in " ".join(w.text for w in lines[index]):
            return index
    return None


def _value_box(
    line: list[OcrWord], label_right: int, image_width: int
) -> tuple[int, int, int, int] | None:
    threshold = label_right + int(image_width * 0.4)
    values = [w for w in line if w.left > max(label_right, threshold)]
    if not values:
        return None
    return (
        min(w.left for w in values),
        min(w.top for w in values),
        max(w.right for w in values),
        max(w.bottom for w in values),
    )


def _checked_confidence(
    result: ParsedScreenshot, confidences: list[float]
) -> None:
    used = [c for c in confidences if c >= 0]
    if used:
        result.min_confidence = min(result.min_confidence, min(used))


def _read_card_value(
    engine: OcrEngine,
    prepared: Image.Image,
    line: list[OcrWord],
    label: str,
    whitelist: str,
    result: ParsedScreenshot,
    field: str,
) -> str | None:
    label_word = next((w for w in line if w.text.lower() == label), None)
    if label_word is None:
        return None
    box = _value_box(line, label_word.right, prepared.width)
    if box is None:
        result.problems.append(f"{field}: no value found on '{label}' row")
        return None
    plain_words = [w for w in line if w.left >= box[0] and w.right <= box[2]]
    plain = " ".join(w.text for w in plain_words)
    reading = engine.read_value(prepared, box, whitelist=whitelist)
    # Whitelist-constrained reads cannot be scored, so only the
    # general-OCR words feed the confidence gate.
    _checked_confidence(
        result,
        [label_word.confidence] + [w.confidence for w in plain_words],
    )
    text = reading.text.replace(" ", "")
    if plain and text and plain.replace(" ", "") != text:
        try:
            plain_norm = plain.replace(" ", "").replace("€", "")
            if parse_eur(plain_norm) != parse_eur(text.replace("€", "")):
                result.warnings.append(
                    f"{field}: digit pass {text!r} differs from general "
                    f"OCR {plain!r}; digit pass used"
                )
        except InvalidOperation, ValueError:
            result.warnings.append(
                f"{field}: general OCR {plain!r} unreadable; "
                f"digit pass {text!r} used"
            )
    return text


def _read_headline(
    engine: OcrEngine,
    prepared: Image.Image,
    mask: Image.Image,
    line: list[OcrWord],
    result: ParsedScreenshot,
) -> None:
    box = (
        min(w.left for w in line),
        min(w.top for w in line),
        max(w.right for w in line),
        max(w.bottom for w in line),
    )
    cents_box = top_ink_region(mask, box)
    if cents_box is None:
        result.problems.append(
            "amount: could not locate the superscript cents"
        )
        return
    cents = engine.read(prepared.crop(cents_box), whitelist=DIGITS_WHITELIST)
    if not CENTS_PATTERN.fullmatch(cents.text.strip()):
        result.problems.append(
            f"amount: expected two cents digits, got {cents.text!r}"
        )
        return
    main_box = (box[0], box[1], max(box[0], cents_box[0] - 5), box[3])
    main = engine.read(prepared.crop(main_box), whitelist=EUR_WHITELIST)
    try:
        integer = _parse_headline_integer(main.text)
    except ValueError:
        result.problems.append(f"amount: could not parse {main.text!r}")
        return
    result.gross_amount_eur = (
        integer + Decimal(cents.text.strip()) / 100
    ).quantize(_CENT)


def _derive_quantity(result: ParsedScreenshot) -> None:
    gross = result.gross_amount_eur
    price = result.unit_price_eur
    if gross is None or price is None or price <= 0:
        return
    derived = (gross / price).quantize(
        _QUANTITY_QUANTUM, rounding=ROUND_HALF_UP
    )
    result.derived_quantity = derived
    displayed = result.displayed_quantity
    if displayed is not None:
        rounded = derived.quantize(_DISPLAYED_QUANTUM, rounding=ROUND_HALF_UP)
        if rounded != displayed:
            result.problems.append(
                f"quantity: derived {derived} rounds to {rounded}, "
                f"not the displayed {displayed}"
            )
    expected = (derived * price).quantize(_CENT, rounding=ROUND_HALF_UP)
    if expected != gross:
        result.problems.append(
            f"quantity: derived {derived} x {price} gives {expected}, "
            f"not the gross amount {gross}"
        )


def parse_screenshot(
    image: Image.Image, engine: OcrEngine
) -> ParsedScreenshot:
    """Parse one screenshot into a fail-closed extraction result."""
    prepared = engine.preprocess(image)
    mask = engine.mask(image, prepared.size)
    words = engine.words(prepared)
    result = ParsedScreenshot()
    lines = _group_lines(words)
    joined = " ".join(w.text for line in lines for w in line).lower()

    if re.search(r"\baankoop\b", joined):
        result.event = "purchase"
    elif re.search(r"\bdividend\b", joined):
        result.event = "dividend"
    else:
        result.problems.append(
            "layout: neither 'Aankoop aandeel' nor "
            "'Ontvangen dividend' recognised"
        )
        return result

    date_line_index = next(
        (
            i
            for i, line in enumerate(lines)
            if _parse_dutch_datetime(" ".join(w.text for w in line))
            is not None
        ),
        None,
    )
    if date_line_index is None:
        result.problems.append("date: no Dutch date/time line found")
        return result

    date_line = lines[date_line_index]
    parsed_dt = _parse_dutch_datetime(" ".join(w.text for w in date_line))
    assert parsed_dt is not None
    result.trade_date, result.trade_time = parsed_dt
    _checked_confidence(result, [w.confidence for w in date_line])

    if date_line_index > 0:
        name_line = lines[date_line_index - 1]
        name = " ".join(w.text for w in name_line).strip()
        if name:
            result.product_name = name
            _checked_confidence(result, [w.confidence for w in name_line])
    if result.product_name is None:
        result.problems.append("name: no product name above the date")

    headline_index = _first_line_containing(lines, date_line_index + 1, "€")
    if headline_index is None:
        result.problems.append("amount: no headline EUR amount found")
        return result
    _read_headline(engine, prepared, mask, lines[headline_index], result)

    if result.event == "dividend":
        return result

    card_labels = {
        "aandelen": ("displayed quantity", SHARES_WHITELIST),
        "koopprijs": ("unit price", EUR_WHITELIST),
        "kosten": ("fee", EUR_WHITELIST),
    }
    for line in lines[headline_index + 1 :]:
        first = line[0].text.lower() if line else ""
        if first not in card_labels:
            continue
        field_name, whitelist = card_labels[first]
        raw = _read_card_value(
            engine,
            prepared,
            line,
            first,
            whitelist,
            result,
            field_name,
        )
        if raw is None:
            continue
        try:
            if field_name == "displayed quantity":
                result.displayed_quantity = parse_shares(raw)
            elif field_name == "unit price":
                result.unit_price_eur = parse_eur(raw)
            else:
                result.fee_eur = parse_eur(raw)
        except ValueError:
            result.problems.append(f"{field_name}: could not parse {raw!r}")

    if result.displayed_quantity is None:
        result.problems.append("quantity: 'Aandelen' row missing")
    if result.unit_price_eur is None:
        result.problems.append(
            "unit price: 'Koopprijs per aandeel' row missing"
        )
    _derive_quantity(result)
    if result.min_confidence < MIN_WORD_CONFIDENCE:
        result.problems.append(
            f"confidence: lowest word confidence "
            f"{result.min_confidence:.0f} is below {MIN_WORD_CONFIDENCE:.0f}"
        )
    return result

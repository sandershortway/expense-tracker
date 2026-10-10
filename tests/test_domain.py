from datetime import date, timedelta
from decimal import Decimal

import pytest

from investment_ledger.domain import TransactionData, ValidationError


def transaction(**overrides):
    values = {
        "side": "buy",
        "instrument_type": "stock",
        "ticker": " acme ",
        "exchange": "xnas",
        "trade_date": "2024-01-02",
        "quantity": "1.25000000",
        "unit_price_eur": "12.340000",
        "gross_amount_eur": "15.43",
        "fee_eur": "0.00",
        "name": "Acme Corp",
    }
    values.update(overrides)
    return TransactionData.from_mapping(values)


def test_normalizes_instrument_and_preserves_decimal_scale():
    result = transaction()

    assert result.ticker == "ACME"
    assert result.exchange == "XNAS"
    assert result.quantity == Decimal("1.25000000")
    assert result.unit_price_eur == Decimal("12.340000")
    assert result.to_mapping()["quantity"] == "1.25000000"
    assert result.to_mapping()["unit_price_eur"] == "12.340000"


def test_rounds_gross_half_up_to_cents():
    result = transaction(
        quantity="0.5",
        unit_price_eur="0.01",
        gross_amount_eur="0.01",
        fee_eur=None,
    )

    assert result.gross_amount_eur == Decimal("0.01")
    assert result.fee_eur is None


def test_exact_product_is_not_limited_by_default_decimal_context():
    quantity = "9999999999999999"
    unit_price = "9999999999999999"
    gross = "99999999999999980000000000000001.00"

    result = transaction(
        quantity=quantity,
        unit_price_eur=unit_price,
        gross_amount_eur=gross,
    )

    assert result.gross_amount_eur == Decimal(gross)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("side", "hold", "side must"),
        ("instrument_type", "bond", "instrument_type must"),
        ("ticker", "  ", "ticker is required"),
        ("exchange", "", "exchange is required"),
        ("trade_date", "2024-1-2", "YYYY-MM-DD"),
        (
            "trade_date",
            (date.today() + timedelta(days=1)).isoformat(),
            "future",
        ),
        ("quantity", "0", "positive"),
        ("quantity", "1.000000001", "8 decimal places"),
        ("unit_price_eur", "1.0000001", "6 decimal places"),
        ("gross_amount_eur", "15.44", "rounded half-up"),
        ("fee_eur", "-0.01", "non-negative decimal"),
        ("currency", "USD", "currency must be EUR"),
    ],
)
def test_rejects_invalid_transaction_fields(field, value, message):
    with pytest.raises(ValidationError, match=message):
        transaction(**{field: value})


@pytest.mark.parametrize("value", [12, 12.0, True])
def test_decimal_fields_must_be_strings(value):
    with pytest.raises(ValidationError, match="decimal string"):
        transaction(quantity=value)


def test_rejects_unrecognized_fields():
    with pytest.raises(ValidationError, match="unknown field"):
        transaction(unexpected="value")


def test_optional_fee_none_and_zero_have_different_duplicate_keys():
    without_fee = transaction(fee_eur=None)
    zero_fee = transaction(fee_eur="0.00")

    assert without_fee.duplicate_key() != zero_fee.duplicate_key()


def test_duplicate_key_ignores_name_and_decimal_scale():
    first = transaction(
        name="First",
        quantity="1.0",
        unit_price_eur="12.34",
        gross_amount_eur="12.34",
    )
    second = transaction(
        name="Second",
        quantity="1.00000000",
        unit_price_eur="12.340000",
        gross_amount_eur="12.34",
    )

    assert first.duplicate_key() == second.duplicate_key()

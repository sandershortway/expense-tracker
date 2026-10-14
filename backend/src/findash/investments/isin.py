import re

_ISIN_PATTERN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


def is_valid_isin(value: str) -> bool:
    """Check the ISIN format and its check digit (ISO 6166)."""
    if not _ISIN_PATTERN.fullmatch(value):
        return False
    # Letters become two-digit numbers (A=10 ... Z=35); then apply Luhn.
    digits = "".join(str(int(char, 36)) for char in value)
    total = 0
    for position, char in enumerate(reversed(digits)):
        number = int(char)
        if position % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0

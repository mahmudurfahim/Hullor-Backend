import re

from django.core.exceptions import ValidationError

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
PHONE_RE = re.compile(r"^01[3-9]\d{8}$")


def normalize_phone(raw):
    """'+88 01863-709122' / '০১৮৬৩৭০৯১২২' -> '01863709122'. ভুল হলে ValidationError।"""
    value = str(raw or "").translate(_BN_DIGITS)
    value = re.sub(r"[\s\-()]", "", value)
    if value.startswith("+88"):
        value = value[3:]
    elif value.startswith("88") and len(value) == 13:
        value = value[2:]
    if not PHONE_RE.match(value):
        raise ValidationError("সঠিক মোবাইল নম্বর দিন (যেমন: 01XXXXXXXXX)।")
    return value

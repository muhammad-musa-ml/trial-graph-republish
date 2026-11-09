"""Baseline normalization applied before any interpretation rule."""
import re
import unicodedata

# Acute accents, grave accents and curly quotes that stand in for an apostrophe in source labels.
# They are translated before NFKC, which would otherwise turn an acute accent into a space.
_APOSTROPHES = {ord(c): "'" for c in "´‘’ʼ`"}


def norm_label(text):
    text = unicodedata.normalize("NFKC", text.translate(_APOSTROPHES))
    return re.sub(r"\s+", " ", text.strip()).casefold()


def sponsor_name(text):
    """'AbbVie (prior sponsor, Abbott)' and 'AbbVie' are the same sponsor."""
    return re.sub(r"\s*\(.*\)\s*$", "", text).strip()

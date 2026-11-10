"""Deterministic correctness evaluators for single-value answers.

Two scores are reported so verbose answers cannot masquerade as correct:

* ``exact_match``     – the whole response, after normalization, equals the
  ground truth. This is the headline metric.
* ``contains_answer`` – the ground truth appears as a standalone token in the
  response (e.g. "The length is 14,511 ft." contains 14511). Useful for
  diagnosing formatting failures versus reasoning failures.

Normalization lowercases, strips markdown/punctuation and units, removes
thousands separators, and compares numbers numerically (14511 == 14511.0).
"""

import re
from typing import Any, Dict

_UNIT_WORDS = r"(?:feet|foot|ft|degrees|degree|deg|nm|nautical miles|°)"
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


def normalize(text: str) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"[`*_\"']", "", text)
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = re.sub(rf"(?<=\d)\s*{_UNIT_WORDS}(?![a-z])", "", text)
    text = re.sub(r"[.\s]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _same_value(a: str, b: str) -> bool:
    if _NUMBER.match(a) and _NUMBER.match(b):
        return float(a) == float(b)
    return a == b


def _tokens(text: str) -> list[str]:
    return re.findall(r"-?[a-z0-9/]+(?:\.\d+)?", text)


def _texts(output: Dict[str, Any], expected: Dict[str, Any]) -> tuple[str, str]:
    response = normalize(output.get("responses", "") if isinstance(output, dict) else output)
    truth = normalize(expected.get("expected") or expected.get("answer", "") if isinstance(expected, dict) else expected)
    return response, truth


def exact_match(output: Dict[str, Any], expected: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """1 if the normalized response is exactly the expected value."""
    response, truth = _texts(output, expected)
    ok = bool(truth) and _same_value(response, truth)
    return {"score": int(ok), "label": "correct" if ok else "incorrect"}


def contains_answer(output: Dict[str, Any], expected: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """1 if the expected value appears as a whole token in the response."""
    response, truth = _texts(output, expected)
    if not truth:
        return {"score": 0, "label": "incorrect"}
    if " " in truth:
        ok = re.search(rf"(?<![a-z0-9/]){re.escape(truth)}(?![a-z0-9/])", response) is not None
    else:
        ok = any(_same_value(tok, truth) for tok in _tokens(response))
    return {"score": int(ok), "label": "contains" if ok else "missing"}

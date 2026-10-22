"""The actual daily form must expose every reason accepted by saved records."""

from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from waste_log import REASONS


class ReasonOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_reason = False
        self.options = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.in_reason = attrs.get("id") == "reason"
        elif tag == "option" and self.in_reason:
            self.current = {"value": attrs.get("value"), "label": ""}
            self.options.append(self.current)

    def handle_data(self, data):
        if self.current is not None:
            self.current["label"] += data

    def handle_endtag(self, tag):
        if tag == "option":
            self.current = None
        elif tag == "select":
            self.current = None
            self.in_reason = False


def test_daily_form_offers_every_supported_waste_reason_once():
    parser = ReasonOptions()
    parser.feed((ROOT / "log.html").read_text(encoding="utf-8"))
    values = [option["value"] for option in parser.options]
    assert set(values) == REASONS | {""}
    assert len(values) == len(REASONS) + 1
    assert {option["value"]: option["label"].strip() for option in parser.options}[
        "overproduction"
    ] == "Overproduction"

import re

from conftest import ROOT
from delica_mut.channels import channels_markdown


def test_channels_doc_tables_match_the_code():
    doc = (ROOT / "docs" / "CHANNELS.md").read_text(encoding="utf-8")
    for ecu in ("gearbox", "engine"):
        block = re.search(rf"<!-- BEGIN {ecu.upper()} TABLE -->\n(.*?)\n<!-- END {ecu.upper()} TABLE -->", doc, re.S)
        assert block and block.group(1) == channels_markdown(ecu), f"docs/CHANNELS.md {ecu} table is out of date"


def test_docs_have_no_em_dashes_or_personal_paths():
    files = [p for p in ROOT.glob("*.md") if p.name != "SCOPE-OF-WORK.md"] + list((ROOT / "docs").glob("*.md")) + list((ROOT / "examples").glob("*"))
    files += list((ROOT / "delica_mut").glob("*.py")) + list((ROOT / "delica_mut" / "web").glob("*"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "\u2014" not in text, f"em dash in {path.name}"
        for needle in ("/home/", "C:\\Users", "gdrive"):
            assert needle.lower() not in text.lower(), f"{needle} in {path.name}"


def test_required_docs_exist():
    for name in ("README.md", "CONTRIBUTING.md", "LICENSE", "third_party/README.md",
                 "third_party/mitsu-kkl/LICENSE", "docs/HARDWARE.md", "docs/PROTOCOL.md", "docs/CHANNELS.md",
                 "docs/SAFETY.md", "docs/AI-ANALYSIS.md", "docs/FINDINGS-EXAMPLE.md"):
        assert (ROOT / name).is_file(), name

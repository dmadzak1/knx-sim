"""Generate byte-exact cEMI frame fixtures using xknx as an independent reference.

Throwaway generator script for M2 Step 4.3/4.4 (see docs/GUIDE.md Part 4).
Writes tests/fixtures/cemi/known_frames.json. Run manually with:

    python scripts/generate_cemi_fixtures.py

Requires `pip install xknx` in the venv (dev-only tool, not a project
dependency in pyproject.toml).
"""

from __future__ import annotations

import json
from pathlib import Path

from xknx.cemi.cemi_frame import CEMIFrame, CEMILData
from xknx.cemi.const import CEMIMessageCode
from xknx.dpt.payload import DPTArray, DPTBinary
from xknx.telegram import GroupAddress as XGroupAddress
from xknx.telegram import IndividualAddress as XIndividualAddress
from xknx.telegram import Telegram as XTelegram
from xknx.telegram.apci import GroupValueRead, GroupValueResponse, GroupValueWrite

FIXTURES_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "cemi" / "known_frames.json"


def main() -> None:
    cases = [
        (
            "write_inline_on",
            CEMIMessageCode.L_DATA_IND,
            XTelegram(
                destination_address=XGroupAddress("1/2/10"),
                payload=GroupValueWrite(DPTBinary(1)),
                source_address=XIndividualAddress("1.1.23"),
            ),
            "GroupValueWrite ON, 1.1.23 -> 1/2/10 (matches docs/notes/cemi.md worked example)",
        ),
        (
            "write_appended_2byte",
            CEMIMessageCode.L_DATA_REQ,
            XTelegram(
                destination_address=XGroupAddress("0/0/1"),
                payload=GroupValueWrite(DPTArray((0x0C, 0x33))),
                source_address=XIndividualAddress("1.1.1"),
            ),
            "GroupValueWrite with a 2-byte appended payload (0x0C 0x33, e.g. DPT 9.001 21.5C)",
        ),
        (
            "read_no_payload",
            CEMIMessageCode.L_DATA_IND,
            XTelegram(
                destination_address=XGroupAddress("3/1/5"),
                payload=GroupValueRead(),
                source_address=XIndividualAddress("2.3.4"),
            ),
            "GroupValueRead, no payload at all",
        ),
        (
            "response_appended_1byte",
            CEMIMessageCode.L_DATA_CON,
            XTelegram(
                destination_address=XGroupAddress("2/2/2"),
                payload=GroupValueResponse(DPTArray(128)),
                source_address=XIndividualAddress("1.1.5"),
            ),
            "GroupValueResponse with a 1-byte appended payload (128, e.g. DPT 5.001 50%)",
        ),
    ]

    fixtures = {}
    for name, code, telegram, description in cases:
        cemi_data = CEMILData.init_from_telegram(telegram)
        frame = CEMIFrame(code=code, data=cemi_data)
        fixtures[name] = {
            "hex": frame.to_knx().hex(),
            "msg_code": code.name,
            "description": description,
        }

    FIXTURES_PATH.write_text(json.dumps(fixtures, indent=2) + "\n")
    print(f"Wrote {len(fixtures)} fixtures to {FIXTURES_PATH}")


if __name__ == "__main__":
    main()

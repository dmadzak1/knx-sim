"""Compare knx_sim DPT codecs against xknx's implementation.

Throwaway verification script for M1 Step 3.5 (see docs/GUIDE.md Part 3).
Not part of the test suite — run manually with:

    python scripts/compare_with_xknx.py

Requires `pip install xknx` in the venv (dev-only tool, not a project
dependency in pyproject.toml).
"""

from __future__ import annotations

from xknx.dpt.dpt_1 import DPTSwitch, Step, Switch
from xknx.dpt.dpt_3 import ControlDimming, DPTControlDimming
from xknx.dpt.dpt_5 import DPTPercentU8, DPTScaling
from xknx.dpt.dpt_9 import DPTTemperature
from xknx.dpt.payload import DPTArray, DPTBinary

from knx_sim.dpt.dpt1 import DPT1001
from knx_sim.dpt.dpt3 import DPT3007, DimmingControl
from knx_sim.dpt.dpt5 import DPT5001, DPT5004
from knx_sim.dpt.dpt9 import DPT9001


def xknx_bytes(payload: DPTArray | DPTBinary) -> bytes:
    """Reduce an xknx payload object to the same byte shape our codecs use:
    a single low-bits byte for DPTBinary, the raw bytes for DPTArray."""
    if isinstance(payload, DPTBinary):
        return bytes([payload.value])
    return bytes(payload.value)


def compare(dpt_id: str, label: str, ours: bytes, theirs: bytes) -> bool:
    ok = ours == theirs
    status = "OK  " if ok else "DIFF"
    print(f"[{status}] {dpt_id:8} {label:20} ours={ours.hex()}  xknx={theirs.hex()}")
    return ok


def main() -> None:
    all_ok = True

    for switch_value in (False, True):
        switch = Switch.ON if switch_value else Switch.OFF
        ours = DPT1001.encode(switch_value)
        theirs = xknx_bytes(DPTSwitch.to_knx(switch))
        all_ok &= compare("1.001", str(switch_value), ours, theirs)

    for direction in (False, True):
        for step_code in range(8):
            ours = DPT3007.encode(DimmingControl(direction=direction, step_code=step_code))
            step = Step.INCREASE if direction else Step.DECREASE
            theirs = xknx_bytes(
                DPTControlDimming.to_knx(ControlDimming(control=step, step_code=step_code))
            )
            all_ok &= compare("3.007", f"dir={direction} step={step_code}", ours, theirs)

    for percent_value in (0.0, 0.5, 1.0, 33.3, 50.0, 66.6, 99.5, 100.0):
        ours = DPT5001.encode(percent_value)
        theirs = xknx_bytes(DPTScaling.to_knx(percent_value))
        all_ok &= compare("5.001", str(percent_value), ours, theirs)

    for raw_value in (0, 1, 42, 128, 200, 255):
        ours = DPT5004.encode(raw_value)
        theirs = xknx_bytes(DPTPercentU8.to_knx(raw_value))
        all_ok &= compare("5.004", str(raw_value), ours, theirs)

    for temp_value in (
        0.0,
        21.5,
        -10.0,
        100.0,
        -50.0,
        300.5,
        0.005,
        -0.005,
        0.0051,
        -0.0051,
        0.01,
        -0.01,
    ):
        ours = DPT9001.encode(temp_value)
        theirs = xknx_bytes(DPTTemperature.to_knx(temp_value))
        all_ok &= compare("9.001", str(temp_value), ours, theirs)

    print()
    print("All match." if all_ok else "DIFFERENCES FOUND -- fix knx_sim before committing M1.")


if __name__ == "__main__":
    main()

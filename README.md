# knx-sim

A software simulator of a complete KNX home-automation installation: a virtual
bus routing KNX telegrams between simulated devices, exposed via a
standards-compliant KNXnet/IP server so that real, unmodified KNX tools
(xknx above all) can connect and operate the virtual house.

See `docs/PROJECT_CONTEXT.md` and `docs/SPEC.md` for the full picture.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

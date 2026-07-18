"""Compare knx_sim's KNXnet/IP wire format against xknx's implementation.

Throwaway verification script for M4 (see docs/GUIDE.md-style workflow used
throughout this project). Run manually with:

    python scripts/compare_knxip_with_xknx.py

Requires `pip install xknx` in the venv (dev-only tool, not a project
dependency in pyproject.toml).
"""

from __future__ import annotations

from xknx.knxip import HPAI as XHPAI
from xknx.knxip import (
    DescriptionRequest as XDescriptionRequest,
)
from xknx.knxip import (
    DescriptionResponse as XDescriptionResponse,
)
from xknx.knxip import (
    KNXIPFrame as XKNXIPFrame,
)
from xknx.knxip import (
    RoutingIndication as XRoutingIndication,
)
from xknx.knxip import (
    SearchRequest as XSearchRequest,
)
from xknx.knxip import (
    SearchResponse as XSearchResponse,
)
from xknx.knxip.dib import DIBDeviceInformation as XDIBDeviceInformation
from xknx.knxip.dib import DIBSuppSVCFamilies as XDIBSuppSVCFamilies
from xknx.knxip.knxip_enum import DIBServiceFamily as XDIBServiceFamily
from xknx.knxip.knxip_enum import KNXMedium as XKNXMedium
from xknx.telegram.address import IndividualAddress as XIndividualAddress

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import MessageCode, Service, Telegram, build_cemi
from knx_sim.knxip.dib import (
    DeviceInformationDIB,
    ServiceFamily,
    SupportedServiceFamiliesDIB,
    SupportedServiceFamily,
)
from knx_sim.knxip.frame import (
    DescriptionRequest,
    DescriptionResponse,
    RoutingIndication,
    SearchRequest,
    SearchResponse,
)
from knx_sim.knxip.hpai import HPAI


def compare(label: str, ours: bytes, theirs: bytes) -> bool:
    ok = ours == theirs
    status = "OK  " if ok else "DIFF"
    print(f"[{status}] {label:24} ours={ours.hex()}")
    if not ok:
        print(f"              theirs={theirs.hex()}")
    return ok


def x_device_info() -> XDIBDeviceInformation:
    dib = XDIBDeviceInformation()
    dib.knx_medium = XKNXMedium.TP1
    dib.programming_mode = False
    dib.individual_address = XIndividualAddress("15.15.0")
    dib.project_number = 0
    dib.installation_number = 0
    dib.serial_number = "00:00:00:00:00:00"
    dib.multicast_address = "224.0.23.12"
    dib.mac_address = "00:00:00:00:00:00"
    dib.name = "knx-sim"
    return dib


def x_supp_svc() -> XDIBSuppSVCFamilies:
    dib = XDIBSuppSVCFamilies()
    dib.families = [
        XDIBSuppSVCFamilies.Family(XDIBServiceFamily.CORE, 1),
        XDIBSuppSVCFamilies.Family(XDIBServiceFamily.ROUTING, 1),
    ]
    return dib


def ours_device_info() -> DeviceInformationDIB:
    return DeviceInformationDIB(individual_address=IndividualAddress(15, 15, 0), name="knx-sim")


def ours_supp_svc() -> SupportedServiceFamiliesDIB:
    return SupportedServiceFamiliesDIB(
        families=(
            SupportedServiceFamily(ServiceFamily.CORE, 1),
            SupportedServiceFamily(ServiceFamily.ROUTING, 1),
        )
    )


def main() -> None:
    all_ok = True

    ours = SearchRequest(discovery_endpoint=HPAI("192.168.1.5", 54321)).to_knx()
    theirs = XKNXIPFrame.init_from_body(
        XSearchRequest(discovery_endpoint=XHPAI("192.168.1.5", 54321))
    ).to_knx()
    all_ok &= compare("SearchRequest", ours, theirs)

    ours = SearchResponse(
        control_endpoint=HPAI("192.168.1.5", 3671),
        device_info=ours_device_info(),
        supported_services=ours_supp_svc(),
    ).to_knx()
    x_search_response = XSearchResponse(control_endpoint=XHPAI("192.168.1.5", 3671))
    x_search_response.dibs = [x_device_info(), x_supp_svc()]
    theirs = XKNXIPFrame.init_from_body(x_search_response).to_knx()
    all_ok &= compare("SearchResponse", ours, theirs)

    ours = DescriptionRequest(control_endpoint=HPAI("192.168.1.5", 54321)).to_knx()
    theirs = XKNXIPFrame.init_from_body(
        XDescriptionRequest(control_endpoint=XHPAI("192.168.1.5", 54321))
    ).to_knx()
    all_ok &= compare("DescriptionRequest", ours, theirs)

    ours = DescriptionResponse(
        device_info=ours_device_info(), supported_services=ours_supp_svc()
    ).to_knx()
    x_description_response = XDescriptionResponse()
    x_description_response.dibs = [x_device_info(), x_supp_svc()]
    theirs = XKNXIPFrame.init_from_body(x_description_response).to_knx()
    all_ok &= compare("DescriptionResponse", ours, theirs)

    cemi = build_cemi(
        Telegram(
            source=IndividualAddress(1, 1, 1),
            destination=GroupAddress(1, 2, 3),
            service=Service.GROUP_WRITE,
            payload=1,
        ),
        MessageCode.L_DATA_IND,
    )
    ours = RoutingIndication(raw_cemi=cemi).to_knx()
    theirs = XKNXIPFrame.init_from_body(XRoutingIndication(raw_cemi=cemi)).to_knx()
    all_ok &= compare("RoutingIndication", ours, theirs)

    print()
    print("All match." if all_ok else "DIFFERENCES FOUND -- fix knx_sim before committing.")


if __name__ == "__main__":
    main()

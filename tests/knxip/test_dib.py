from __future__ import annotations

import pytest

from knx_sim.cemi.address import IndividualAddress
from knx_sim.knxip.dib import (
    DeviceInformationDIB,
    KNXMedium,
    ServiceFamily,
    SupportedServiceFamiliesDIB,
    SupportedServiceFamily,
)
from knx_sim.knxip.errors import ParseError


class TestDeviceInformationDIB:
    def test_round_trip(self) -> None:
        dib = DeviceInformationDIB(
            individual_address=IndividualAddress(15, 15, 0),
            name="knx-sim",
            serial_number=bytes([1, 2, 3, 4, 5, 6]),
            mac_address=bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]),
        )
        assert DeviceInformationDIB.from_knx(dib.to_knx()) == dib

    def test_to_knx_is_54_bytes(self) -> None:
        dib = DeviceInformationDIB(individual_address=IndividualAddress(15, 15, 0), name="x")
        assert len(dib.to_knx()) == 54

    def test_name_padded_and_truncated_on_wire(self) -> None:
        dib = DeviceInformationDIB(individual_address=IndividualAddress(0, 0, 0), name="ab")
        raw = dib.to_knx()
        assert raw[24:54] == b"ab" + b"\x00" * 28

    def test_rejects_name_too_long(self) -> None:
        with pytest.raises(ValueError, match="must fit in 30 latin-1 bytes"):
            DeviceInformationDIB(
                individual_address=IndividualAddress(0, 0, 0), name="x" * 31
            )

    def test_rejects_wrong_serial_length(self) -> None:
        with pytest.raises(ValueError, match="serial_number must be 6 bytes"):
            DeviceInformationDIB(
                individual_address=IndividualAddress(0, 0, 0), name="x", serial_number=b"\x00"
            )

    def test_from_knx_rejects_wrong_type_code(self) -> None:
        # Correct length byte (54), but the SUPP_SVC_FAMILIES type code (0x02)
        # instead of DEVICE_INFO's (0x01).
        raw = bytes([54, 0x02]) + bytes(52)
        with pytest.raises(ParseError, match="Expected DEVICE_INFO DIB"):
            DeviceInformationDIB.from_knx(raw)

    def test_knx_medium_round_trips(self) -> None:
        dib = DeviceInformationDIB(
            individual_address=IndividualAddress(0, 0, 0), name="x", knx_medium=KNXMedium.KNX_IP
        )
        assert DeviceInformationDIB.from_knx(dib.to_knx()).knx_medium is KNXMedium.KNX_IP


class TestSupportedServiceFamiliesDIB:
    def test_round_trip(self) -> None:
        dib = SupportedServiceFamiliesDIB(
            families=(
                SupportedServiceFamily(ServiceFamily.CORE, 1),
                SupportedServiceFamily(ServiceFamily.ROUTING, 1),
            )
        )
        assert SupportedServiceFamiliesDIB.from_knx(dib.to_knx()) == dib

    def test_calculated_length(self) -> None:
        dib = SupportedServiceFamiliesDIB(
            families=(SupportedServiceFamily(ServiceFamily.CORE, 1),)
        )
        assert dib.calculated_length() == 4  # 2 header bytes + 1 family * 2 bytes
        assert len(dib.to_knx()) == 4

    def test_empty_families(self) -> None:
        dib = SupportedServiceFamiliesDIB(families=())
        assert SupportedServiceFamiliesDIB.from_knx(dib.to_knx()) == dib

    def test_rejects_unsupported_family_code(self) -> None:
        raw = bytes([4, 0x02, 0xFF, 0x01])  # unknown family code 0xFF
        with pytest.raises(ParseError, match="Unsupported service family code"):
            SupportedServiceFamiliesDIB.from_knx(raw)

    def test_supported_service_family_rejects_version_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="version must be 0..255"):
            SupportedServiceFamily(ServiceFamily.CORE, 256)

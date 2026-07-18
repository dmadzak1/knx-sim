from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import (
    MessageCode,
    ParseError,
    Priority,
    Service,
    Telegram,
    build_cemi,
    parse_cemi,
)

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "cemi" / "known_frames.json"
FIXTURES = json.loads(FIXTURES_PATH.read_text())

# Telegram equivalents of tests/fixtures/cemi/known_frames.json, generated
# independently via xknx by scripts/generate_cemi_fixtures.py.
KNOWN_FRAMES: dict[str, tuple[MessageCode, Telegram]] = {
    "write_inline_on": (
        MessageCode.L_DATA_IND,
        Telegram(
            source=IndividualAddress(1, 1, 23),
            destination=GroupAddress(1, 2, 10),
            service=Service.GROUP_WRITE,
            payload=1,
        ),
    ),
    "write_appended_2byte": (
        MessageCode.L_DATA_REQ,
        Telegram(
            source=IndividualAddress(1, 1, 1),
            destination=GroupAddress(0, 0, 1),
            service=Service.GROUP_WRITE,
            payload=bytes([0x0C, 0x33]),
        ),
    ),
    "read_no_payload": (
        MessageCode.L_DATA_IND,
        Telegram(
            source=IndividualAddress(2, 3, 4),
            destination=GroupAddress(3, 1, 5),
            service=Service.GROUP_READ,
            payload=None,
        ),
    ),
    "response_appended_1byte": (
        MessageCode.L_DATA_CON,
        Telegram(
            source=IndividualAddress(1, 1, 5),
            destination=GroupAddress(2, 2, 2),
            service=Service.GROUP_RESPONSE,
            payload=bytes([128]),
        ),
    ),
}


class TestKnownFrames:
    @pytest.mark.parametrize("name", KNOWN_FRAMES.keys())
    def test_build_matches_xknx_fixture(self, name: str) -> None:
        msg_code, telegram = KNOWN_FRAMES[name]
        expected = bytes.fromhex(FIXTURES[name]["hex"])
        assert build_cemi(telegram, msg_code) == expected

    @pytest.mark.parametrize("name", KNOWN_FRAMES.keys())
    def test_parse_matches_expected_telegram(self, name: str) -> None:
        expected_msg_code, expected_telegram = KNOWN_FRAMES[name]
        raw = bytes.fromhex(FIXTURES[name]["hex"])
        msg_code, telegram = parse_cemi(raw)
        assert msg_code == expected_msg_code
        assert telegram == expected_telegram


class TestTelegramValidation:
    def test_group_read_rejects_payload(self) -> None:
        with pytest.raises(ValueError, match="must not carry a payload"):
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=GroupAddress(0, 0, 1),
                service=Service.GROUP_READ,
                payload=1,
            )

    def test_write_requires_payload(self) -> None:
        with pytest.raises(ValueError, match="requires a payload"):
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=GroupAddress(0, 0, 1),
                service=Service.GROUP_WRITE,
                payload=None,
            )

    def test_inline_payload_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="inline payload must be 0..63"):
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=GroupAddress(0, 0, 1),
                service=Service.GROUP_WRITE,
                payload=64,
            )

    def test_appended_payload_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=GroupAddress(0, 0, 1),
                service=Service.GROUP_WRITE,
                payload=b"",
            )

    @pytest.mark.parametrize("hop_count", [-1, 8])
    def test_hop_count_out_of_range(self, hop_count: int) -> None:
        with pytest.raises(ValueError, match="hop_count must be 0..7"):
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=GroupAddress(0, 0, 1),
                service=Service.GROUP_READ,
                payload=None,
                hop_count=hop_count,
            )


class TestParseErrors:
    def test_too_short(self) -> None:
        with pytest.raises(ParseError, match="too short"):
            parse_cemi(bytes(8))

    def test_unsupported_message_code(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[0] = 0xFF
        with pytest.raises(ParseError, match="Unsupported cEMI message code"):
            parse_cemi(bytes(raw))

    def test_additional_info_not_supported(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[1] = 0x01
        with pytest.raises(ParseError, match="Additional info blocks are not supported"):
            parse_cemi(bytes(raw))

    def test_individual_address_destination_not_supported(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[3] &= 0x7F  # clear the group-address-destination bit
        with pytest.raises(ParseError, match="Individual-address destinations"):
            parse_cemi(bytes(raw))

    def test_npdu_length_mismatch(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[8] = 0x05
        with pytest.raises(ParseError, match="NPDU length mismatch"):
            parse_cemi(bytes(raw))

    def test_tpdu_too_short(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[8] = 0x00
        del raw[10]
        with pytest.raises(ParseError, match="TPDU too short"):
            parse_cemi(bytes(raw))

    def test_numbered_tpci_not_supported(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[9] |= 0x40  # set the "numbered" TPCI bit
        with pytest.raises(ParseError, match="Unsupported TPCI type"):
            parse_cemi(bytes(raw))

    def test_control_tpci_not_supported(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[9] |= 0x80  # set the "control" TPCI bit
        with pytest.raises(ParseError, match="Unsupported TPCI type"):
            parse_cemi(bytes(raw))

    def test_unexpected_sequence_number(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[9] |= 0b0000_0100  # sequence number bits on an unnumbered TPCI
        with pytest.raises(ParseError, match="Unexpected sequence number"):
            parse_cemi(bytes(raw))

    def test_extended_apci_not_supported(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_inline_on"]["hex"]))
        raw[9] |= 0b0000_0011  # set APCI bits 9-8
        with pytest.raises(ParseError, match="APCI bits 9-8"):
            parse_cemi(bytes(raw))

    def test_group_read_with_stray_payload(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["read_no_payload"]["hex"]))
        raw[10] |= 0x01  # set a stray inline bit on an otherwise-empty GroupValueRead
        with pytest.raises(ParseError, match="must not carry a payload"):
            parse_cemi(bytes(raw))

    def test_malformed_apci_both_inline_and_appended(self) -> None:
        raw = bytearray(bytes.fromhex(FIXTURES["write_appended_2byte"]["hex"]))
        raw[10] |= 0x01  # set an inline bit alongside the already-appended bytes
        with pytest.raises(ParseError, match="Malformed APCI byte"):
            parse_cemi(bytes(raw))


def _telegram_strategy() -> st.SearchStrategy[tuple[MessageCode, Telegram]]:
    addresses = st.builds(
        IndividualAddress,
        area=st.integers(0, 15),
        line=st.integers(0, 15),
        device=st.integers(0, 255),
    )
    group_addresses = st.builds(
        GroupAddress,
        main=st.integers(0, 31),
        middle=st.integers(0, 7),
        sub=st.integers(0, 255),
    )
    common = {
        "source": addresses,
        "destination": group_addresses,
        "priority": st.sampled_from(Priority),
        "hop_count": st.integers(0, 7),
    }

    read = st.builds(Telegram, service=st.just(Service.GROUP_READ), payload=st.none(), **common)
    inline_write = st.builds(
        Telegram,
        service=st.sampled_from([Service.GROUP_WRITE, Service.GROUP_RESPONSE]),
        payload=st.integers(0, 63),
        **common,
    )
    appended_write = st.builds(
        Telegram,
        service=st.sampled_from([Service.GROUP_WRITE, Service.GROUP_RESPONSE]),
        payload=st.binary(min_size=1, max_size=14),
        **common,
    )
    return st.tuples(
        st.sampled_from(MessageCode), st.one_of(read, inline_write, appended_write)
    )


@given(_telegram_strategy())
def test_round_trip(msg_code_and_telegram: tuple[MessageCode, Telegram]) -> None:
    msg_code, telegram = msg_code_and_telegram
    raw = build_cemi(telegram, msg_code)
    parsed_msg_code, parsed_telegram = parse_cemi(raw)
    assert parsed_msg_code == msg_code
    assert parsed_telegram == telegram

"""Shared exception for the knxip module."""

from __future__ import annotations


class ParseError(Exception):
    """Raised when a byte sequence is not a valid/supported KNXnet/IP frame.

    Distinct from knx_sim.cemi.frame.ParseError -- different protocol layer,
    different failure modes.
    """

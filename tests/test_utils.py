"""Unit tests for the pure value helpers."""

from nautobot_ssot_msdhcp.utils.dhcp import (
    canonical_dt,
    join_option_value,
    lease_state_from_ms,
    ms_type_to_datatype,
    normalize_mac,
    prefix_from_scope,
)


def test_prefix_from_scope():
    assert prefix_from_scope("10.0.10.0", "255.255.255.0") == "10.0.10.0/24"
    assert prefix_from_scope("172.16.0.0", "255.255.0.0") == "172.16.0.0/16"


def test_normalize_mac():
    assert normalize_mac("00-11-22-33-44-55") == "00:11:22:33:44:55"
    assert normalize_mac("AABBCCDDEEFF") == "aa:bb:cc:dd:ee:ff"
    # Non-MAC client-id is returned lowercased, untouched otherwise.
    assert normalize_mac("some-client-id-7") == "some-client-id-7"


def test_lease_state_from_ms():
    assert lease_state_from_ms("Active") == "active"
    assert lease_state_from_ms("ActiveReservation") == "active"
    assert lease_state_from_ms("Declined") == "declined"
    assert lease_state_from_ms("Expired") == "expired"
    assert lease_state_from_ms("") == "active"


def test_ms_type_to_datatype():
    assert ms_type_to_datatype("IPv4Address") == "ipv4-address"
    assert ms_type_to_datatype("String") == "string"
    assert ms_type_to_datatype("DWord") == "uint32"
    assert ms_type_to_datatype("weird") == "string"


def test_join_option_value():
    assert join_option_value(["10.0.0.1", "10.0.0.2"]) == "10.0.0.1,10.0.0.2"
    assert join_option_value("corp.example.com") == "corp.example.com"
    assert join_option_value(None) == ""


def test_canonical_dt_normalizes_z_and_offset():
    a = canonical_dt("2026-06-29T08:00:00Z")
    b = canonical_dt("2026-06-29T08:00:00+00:00")
    assert a == b == "2026-06-29T08:00:00+00:00"
    assert canonical_dt("") == ""

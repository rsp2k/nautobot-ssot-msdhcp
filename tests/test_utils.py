"""Unit tests for the pure value helpers."""

from nautobot_ssot_msdhcp.utils.dhcp import (
    canonical_dt,
    join_option_value,
    lease_state_from_ms,
    ms_type_to_datatype,
    normalize_mac,
    parse_export,
    prefix_from_scope,
    split_identifier,
)


def test_split_identifier_routes_mac_vs_extended():
    """A real MAC -> mac_address; an extended client-id -> the wider field (no overflow)."""
    # Dash-form MAC normalizes and lands in the mac slot.
    assert split_identifier("00-11-22-33-44-55") == ("00:11:22:33:44:55", "")
    # RFC 4361 / DUID-style id (18 bytes) is too long for mac_address(17). A non-MAC
    # value is preserved lowercased (dashes kept), routed to the wider field.
    duid = "58-FA-1F-46-00-02-00-00-AB-11-38-34-59-10-5F-03-E5-2C"
    mac, other = split_identifier(duid)
    assert mac == "" and len(other) > 17 and other == duid.lower()
    # Cisco ASCII client-id (hex of "cisco-...-Vl1").
    cisco = "63-69-73-63-6f-2d-36-38-39-65"
    assert split_identifier(cisco)[0] == ""
    # Empty input.
    assert split_identifier("") == ("", "")


def test_parse_export_strips_utf8_bom():
    """Windows PowerShell 5.1 'Out-File -Encoding utf8' prepends a UTF-8 BOM;
    parse_export must tolerate it (plain json.loads raises on the BOM)."""
    body = b'{"server": {"name": "dhcp01"}}'
    assert parse_export(b"\xef\xbb\xbf" + body) == {"server": {"name": "dhcp01"}}
    # And it is a no-op on a BOM-less export.
    assert parse_export(body) == {"server": {"name": "dhcp01"}}


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

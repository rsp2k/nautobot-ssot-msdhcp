"""Microsoft-specific value helpers for the MS DHCP source adapter.

Vendor-neutral helpers (canonical_dt, normalize_mac, join_option_value) are
re-exported from the shared ``nautobot_dhcp_models.ssot.helpers`` so the source
adapter has one import surface.
"""

from __future__ import annotations

import ipaddress
import json
import re

from nautobot_dhcp_models.ssot.helpers import (  # noqa: F401 -- re-exported for the adapter
    canonical_dt,
    join_option_value,
    normalize_mac,
)

# A normalized MAC is exactly six colon-separated hex octets.
_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def split_identifier(client_id: str) -> tuple[str, str]:
    """Split an MS ClientId into ``(mac_address, other_identifier)``.

    MS stores a hardware address and an extended client-identifier in the same
    ``ClientId`` field. A real MAC normalizes to six hex octets and belongs in the
    17-char ``mac_address`` column; anything longer (an RFC 4361 / DUID-style id, or
    a Cisco ASCII client-id like ``cisco-689e.0b80.f900-Vl1``) would overflow it, so
    it is returned as the second element to go in the wider ``client_id``/``duid``
    field instead. Returns ``("", "")`` for an empty input.
    """
    norm = normalize_mac(client_id or "")
    if _MAC_RE.match(norm):
        return norm, ""
    return "", norm


def parse_export(raw: bytes) -> dict:
    """Parse the uploaded MS DHCP export bytes into a dict.

    Decode with ``utf-8-sig`` so a byte-order mark is stripped: Windows
    PowerShell 5.1 (the default on Windows Server) writes a UTF-8 BOM with
    ``Out-File -Encoding utf8``, and a leading BOM makes ``json.loads`` raise
    "Unexpected UTF-8 BOM". ``utf-8-sig`` is a no-op on BOM-less files, so this is
    safe for exports from any PowerShell version.
    """
    return json.loads(raw.decode("utf-8-sig"))


def prefix_from_scope(scope_id: str, subnet_mask: str) -> str:
    """Combine an MS scope network address + dotted mask into a CIDR string.

    >>> prefix_from_scope("10.0.10.0", "255.255.255.0")
    '10.0.10.0/24'
    """
    net = ipaddress.ip_network(f"{scope_id}/{subnet_mask}", strict=False)
    return str(net)


# Microsoft option Type -> DHCPOptionDataTypeChoices value.
MS_OPTION_TYPE_MAP = {
    "ipv4address": "ipv4-address",
    "ipaddress": "ipv4-address",
    "string": "string",
    "word": "uint16",
    "dword": "uint32",
    "byte": "uint8",
    "binarydata": "binary",
    "encapsulateddata": "binary",
}


def ms_type_to_datatype(ms_type: str) -> str:
    """Map a Windows DHCP option Type to a DHCPOptionDataTypeChoices value."""
    return MS_OPTION_TYPE_MAP.get((ms_type or "").lower(), "string")


# Microsoft scope State -> DHCPScopeStateChoices value.
SCOPE_STATE_MAP = {
    "active": "enabled",
    "inactive": "disabled",
}

# Microsoft reservation Type -> DHCPReservationTypeChoices value.
RESERVATION_TYPE_MAP = {
    "dhcp": "dhcp",
    "bootp": "bootp",
    "both": "both",
}


def lease_state_from_ms(address_state: str) -> str:
    """Map a Windows AddressState string to a DHCPLeaseStateChoices value."""
    s = (address_state or "").strip().lower()
    if s.startswith("active"):
        return "active"
    if s.startswith("declined"):
        return "declined"
    if s.startswith("expired"):
        return "expired"
    return "active"

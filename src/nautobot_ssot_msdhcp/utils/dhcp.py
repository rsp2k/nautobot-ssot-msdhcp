"""Microsoft-specific value helpers for the MS DHCP source adapter.

Vendor-neutral helpers (canonical_dt, normalize_mac, join_option_value) are
re-exported from the shared ``nautobot_dhcp_models.ssot.helpers`` so the source
adapter has one import surface.
"""

from __future__ import annotations

import ipaddress

from nautobot_dhcp_models.ssot.helpers import (  # noqa: F401 -- re-exported for the adapter
    canonical_dt,
    join_option_value,
    normalize_mac,
)


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

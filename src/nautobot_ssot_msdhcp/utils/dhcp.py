"""Pure helpers for translating Microsoft DHCP export values to model values.

No Django/Nautobot imports here so these are unit-testable on plain pytest.
"""

from __future__ import annotations

import datetime
import ipaddress


def prefix_from_scope(scope_id: str, subnet_mask: str) -> str:
    """Combine an MS scope network address + dotted mask into a CIDR string.

    >>> prefix_from_scope("10.0.10.0", "255.255.255.0")
    '10.0.10.0/24'
    """
    net = ipaddress.ip_network(f"{scope_id}/{subnet_mask}", strict=False)
    return str(net)


def normalize_mac(client_id: str) -> str:
    """Normalize a Windows DHCP ClientId to colon-separated lowercase MAC.

    Windows reports MACs as ``00-11-22-33-44-55``. Non-MAC client identifiers
    (length != 12 hex chars) are returned lowercased but otherwise untouched.

    >>> normalize_mac("00-11-22-33-44-55")
    '00:11:22:33:44:55'
    """
    hexstr = (client_id or "").replace("-", "").replace(":", "").replace(".", "").strip().lower()
    if len(hexstr) != 12 or any(c not in "0123456789abcdef" for c in hexstr):
        return (client_id or "").strip().lower()
    return ":".join(hexstr[i : i + 2] for i in range(0, 12, 2))


def canonical_dt(value) -> str:
    """Canonicalize a timestamp (ISO string or datetime) to UTC isoformat.

    Both adapters run values through this so the same instant compares equal
    regardless of source format (``...Z`` from the export vs ``...+00:00`` from
    the ORM). Microseconds are dropped for stability. Returns "" for empty input.
    """
    if not value:
        return ""
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(text)
        except ValueError:
            return ""
    else:
        dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()


def join_option_value(value) -> str:
    """Join an option value (list or scalar) into a comma-separated string."""
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return "" if value is None else str(value)


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


# Microsoft lease AddressState -> DHCPLeaseStateChoices value. MS has several
# *active* sub-states (ActiveReservation, etc.); anything starting "active" maps
# to active. Declined/Expired map directly.
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

"""Vendor-neutral DiffSync models shared by the MS DHCP and Nautobot adapters.

Identifiers are all strings so the same record loaded from the JSON export and
from the nautobot-dhcp-models ORM produce identical keys. FKs are represented by
their natural string form: a server by name, a scope by its CIDR prefix, a
reservation/lease by its IP.
"""

from __future__ import annotations

from diffsync import DiffSyncModel


class DhcpServer(DiffSyncModel):
    """A DHCP server instance."""

    _modelname = "dhcpserver"
    _identifiers = ("name",)
    _attributes = ("vendor", "version", "ad_authorized")

    name: str
    vendor: str = "microsoft"
    version: str = ""
    ad_authorized: bool | None = None


class DhcpScope(DiffSyncModel):
    """A scope/subnet, keyed by (server, prefix)."""

    _modelname = "dhcpscope"
    _identifiers = ("server_name", "prefix")
    _attributes = ("name", "state", "default_lease_time", "description")

    server_name: str
    prefix: str  # CIDR, e.g. "10.0.10.0/24"
    name: str = ""
    state: str = "enabled"
    default_lease_time: int = 86400
    description: str = ""


class DhcpPool(DiffSyncModel):
    """An address pool/range within a scope."""

    _modelname = "dhcppool"
    _identifiers = ("server_name", "prefix", "start_address", "end_address")
    _attributes = ("description",)

    server_name: str
    prefix: str
    start_address: str
    end_address: str
    description: str = ""


class DhcpExclusion(DiffSyncModel):
    """An excluded address range within a scope."""

    _modelname = "dhcpexclusion"
    _identifiers = ("server_name", "prefix", "start_address", "end_address")
    _attributes = ("description",)

    server_name: str
    prefix: str
    start_address: str
    end_address: str
    description: str = ""


class DhcpReservation(DiffSyncModel):
    """A static host reservation, keyed by (server, prefix, ip)."""

    _modelname = "dhcpreservation"
    _identifiers = ("server_name", "prefix", "ip_address")
    _attributes = ("mac_address", "hostname", "reservation_type", "description")

    server_name: str
    prefix: str
    ip_address: str
    mac_address: str = ""
    hostname: str = ""
    reservation_type: str = "dhcp"
    description: str = ""


class DhcpLease(DiffSyncModel):
    """An observed dynamic lease, keyed by (server, prefix, ip)."""

    _modelname = "dhcplease"
    _identifiers = ("server_name", "prefix", "ip_address")
    _attributes = ("mac_address", "hostname", "lease_state", "expires")

    server_name: str
    prefix: str
    ip_address: str
    mac_address: str = ""
    hostname: str = ""
    lease_state: str = "active"
    expires: str = ""  # ISO-8601, "" if unknown


class DhcpOption(DiffSyncModel):
    """An option value applied at the server, scope, or reservation level.

    The parent level is encoded in the identifiers: ``scope_prefix`` and
    ``reservation_ip`` are empty strings for levels that don't apply, so
    server-level = ("", ""), scope-level = (prefix, ""), reservation-level =
    (prefix, ip). Together with the server and option code that is a unique key.
    """

    _modelname = "dhcpoption"
    _identifiers = ("server_name", "scope_prefix", "reservation_ip", "code")
    _attributes = ("value", "option_name", "data_type")

    server_name: str
    scope_prefix: str
    reservation_ip: str
    code: int
    value: str = ""
    option_name: str = ""
    data_type: str = "string"

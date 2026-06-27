"""DiffSync model classes: vendor-neutral base + Nautobot-side CRUD subclasses."""

from nautobot_ssot_msdhcp.diffsync.models.base import (
    DhcpExclusion,
    DhcpLease,
    DhcpOption,
    DhcpPool,
    DhcpReservation,
    DhcpScope,
    DhcpServer,
)
from nautobot_ssot_msdhcp.diffsync.models.nautobot import (
    NautobotDhcpExclusion,
    NautobotDhcpLease,
    NautobotDhcpOption,
    NautobotDhcpPool,
    NautobotDhcpReservation,
    NautobotDhcpScope,
    NautobotDhcpServer,
)

__all__ = [
    "DhcpExclusion",
    "DhcpLease",
    "DhcpOption",
    "DhcpPool",
    "DhcpReservation",
    "DhcpScope",
    "DhcpServer",
    "NautobotDhcpExclusion",
    "NautobotDhcpLease",
    "NautobotDhcpOption",
    "NautobotDhcpPool",
    "NautobotDhcpReservation",
    "NautobotDhcpScope",
    "NautobotDhcpServer",
]

"""Source adapter: load a Microsoft DHCP JSON export into DiffSync.

This is the read side (PULL). It parses the export produced by
``Export-MSDHCP.ps1`` and normalizes every value to its dhcp-models-native form
(scope state, reservation type, lease state, MAC, option data type, CIDR prefix)
so the diff against the Nautobot side is apples-to-apples.
"""

from __future__ import annotations

from diffsync import Adapter
from nautobot_dhcp_models.ssot.base import (
    DhcpExclusion,
    DhcpLease,
    DhcpOption,
    DhcpPool,
    DhcpRedundancyGroup,
    DhcpRedundancyGroupMember,
    DhcpReservation,
    DhcpScope,
    DhcpServer,
)

from nautobot_ssot_msdhcp.utils.dhcp import (
    RESERVATION_TYPE_MAP,
    SCOPE_STATE_MAP,
    canonical_dt,
    join_option_value,
    lease_state_from_ms,
    ms_type_to_datatype,
    normalize_mac,
    prefix_from_scope,
)

# Microsoft failover mode -> vendor-neutral DHCPRedundancyMode (no passive-backup in MS).
_MS_FAILOVER_MODE = {"loadbalance": "load-balance", "hotstandby": "hot-standby"}


def _hostname(name: str) -> str:
    """Lowercase short hostname for tolerant FQDN-vs-short server-name matching."""
    return (name or "").strip().lower().split(".")[0]


class MSDHCPAdapter(Adapter):
    """Load a parsed MS DHCP export dict into the DiffSync store."""

    dhcpserver = DhcpServer
    dhcpredundancygroup = DhcpRedundancyGroup
    dhcpredundancygroupmember = DhcpRedundancyGroupMember
    dhcpscope = DhcpScope
    dhcppool = DhcpPool
    dhcpexclusion = DhcpExclusion
    dhcpreservation = DhcpReservation
    dhcpoption = DhcpOption
    dhcplease = DhcpLease

    top_level = (
        "dhcpserver",
        "dhcpredundancygroup",
        "dhcpredundancygroupmember",
        "dhcpscope",
        "dhcppool",
        "dhcpexclusion",
        "dhcpreservation",
        "dhcpoption",
        "dhcplease",
    )

    def __init__(self, *args, export: dict, job=None, sync=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.export = export
        self.job = job
        self.sync = sync

    def load(self) -> None:
        """Walk the export: server, server options, then each scope and its children."""
        server = self.export.get("server", {})
        server_name = server.get("name")
        if not server_name:
            raise ValueError("MS DHCP export is missing server.name")

        self.add(
            self.dhcpserver(
                name=server_name,
                vendor="microsoft",
                ad_authorized=server.get("ad_authorized"),
            )
        )
        for opt in self.export.get("server_options", []):
            self._add_option(server_name, "", "", opt)

        # Failover relationships -> redundancy group + THIS server's own membership.
        for failover in self.export.get("failover", []):
            self._load_failover(server_name, failover)

        for scope in self.export.get("scopes", []):
            self._load_scope(server_name, scope)

    def _load_failover(self, server_name: str, failover: dict) -> None:
        """Project an MS failover relationship into a redundancy group + this server's member.

        Like the Kea HA projection, this emits only THIS server's membership; the
        partner contributes its own row when its export is synced. The relationship
        name is shared by both partners, so both syncs upsert the same group. Role is
        derived from whether this server is the relationship's primary or secondary.
        """
        name = failover.get("name")
        if not name:
            return
        self.add(
            self.dhcpredundancygroup(
                name=name,
                mode=_MS_FAILOVER_MODE.get((failover.get("mode") or "").lower(), "hot-standby"),
                mclt=failover.get("mclt"),
                load_balance_percent=failover.get("load_balance_percent"),
                state_switch_interval=failover.get("state_switch_interval"),
                # max_response_delay / max_unacked_clients / heartbeat_delay are Kea HA
                # concepts with no MS analog; they stay unset.
                enabled=True,
            )
        )
        this = _hostname(server_name)
        if this == _hostname(failover.get("primary_server")):
            role = "primary"
        elif this == _hostname(failover.get("secondary_server")):
            role = "secondary"
        else:
            # This server matches neither named partner -- skip the membership rather
            # than guess a role (the group still records the relationship).
            return
        self.add(
            self.dhcpredundancygroupmember(
                group_name=name,
                server_name=server_name,
                role=role,
            )
        )

    def _load_scope(self, server_name: str, scope: dict) -> None:
        prefix = prefix_from_scope(scope["scope_id"], scope["subnet_mask"])
        self.add(
            self.dhcpscope(
                server_name=server_name,
                prefix=prefix,
                name=scope.get("name", ""),
                state=SCOPE_STATE_MAP.get((scope.get("state") or "").lower(), "enabled"),
                default_lease_time=scope.get("lease_duration_seconds") or 86400,
                description=scope.get("description", ""),
            )
        )
        if scope.get("start_range") and scope.get("end_range"):
            self.add(
                self.dhcppool(
                    server_name=server_name,
                    prefix=prefix,
                    start_address=scope["start_range"],
                    end_address=scope["end_range"],
                )
            )
        for excl in scope.get("exclusions", []):
            self.add(
                self.dhcpexclusion(
                    server_name=server_name,
                    prefix=prefix,
                    start_address=excl["start_range"],
                    end_address=excl["end_range"],
                )
            )
        for opt in scope.get("options", []):
            self._add_option(server_name, prefix, "", opt)
        for res in scope.get("reservations", []):
            self._load_reservation(server_name, prefix, res)
        for lease in scope.get("leases", []):
            self._load_lease(server_name, prefix, lease)

    def _load_reservation(self, server_name: str, prefix: str, res: dict) -> None:
        ip = res["ip_address"]
        self.add(
            self.dhcpreservation(
                server_name=server_name,
                prefix=prefix,
                ip_address=ip,
                mac_address=normalize_mac(res.get("client_id", "")),
                hostname=res.get("name", ""),
                reservation_type=RESERVATION_TYPE_MAP.get((res.get("type") or "").lower(), "dhcp"),
                description=res.get("description", ""),
            )
        )
        for opt in res.get("options", []):
            self._add_option(server_name, prefix, ip, opt)

    def _load_lease(self, server_name: str, prefix: str, lease: dict) -> None:
        self.add(
            self.dhcplease(
                server_name=server_name,
                prefix=prefix,
                ip_address=lease["ip_address"],
                mac_address=normalize_mac(lease.get("client_id", "")),
                hostname=lease.get("hostname", ""),
                lease_state=lease_state_from_ms(lease.get("address_state", "")),
                expires=canonical_dt(lease.get("lease_expiry")),
            )
        )

    def _add_option(self, server_name: str, scope_prefix: str, reservation_ip: str, opt: dict) -> None:
        self.add(
            self.dhcpoption(
                server_name=server_name,
                scope_prefix=scope_prefix,
                reservation_ip=reservation_ip,
                code=int(opt["option_id"]),
                value=join_option_value(opt.get("value")),
                option_name=opt.get("name", ""),
                data_type=ms_type_to_datatype(opt.get("type", "")),
            )
        )

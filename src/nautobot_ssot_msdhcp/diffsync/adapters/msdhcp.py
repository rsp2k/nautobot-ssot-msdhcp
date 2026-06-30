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
    DhcpSharedNetwork,
)

from nautobot_ssot_msdhcp.utils.dhcp import (
    RESERVATION_TYPE_MAP,
    SCOPE_STATE_MAP,
    canonical_dt,
    join_option_value,
    lease_state_from_ms,
    ms_type_to_datatype,
    prefix_from_scope,
    split_identifier,
)

# Microsoft failover mode -> vendor-neutral DHCPRedundancyMode (no passive-backup in MS).
_MS_FAILOVER_MODE = {"loadbalance": "load-balance", "hotstandby": "hot-standby"}


def _hostname(name: str) -> str:
    """Lowercase short hostname for tolerant FQDN-vs-short server-name matching."""
    return (name or "").strip().lower().split(".")[0]


def _ddns_from_ms(dynamic_updates, update_older_clients) -> dict:
    """Map MS scope DNS settings to the vendor-neutral ddns_* fields.

    MS ``DynamicUpdates``: Always = server always updates (overrides client),
    OnClientRequest = updates only when the client asks, Never = no updates.
    ``UpdateDnsRRForOlderClients`` = update even for clients that don't request it,
    which is the same intent as Kea's ddns-override-no-update.
    """
    out: dict = {}
    du = (dynamic_updates or "").lower()
    if du == "always":
        out["ddns_send_updates"] = True
        out["ddns_override_client_update"] = True
    elif du == "onclientrequest":
        out["ddns_send_updates"] = True
        out["ddns_override_client_update"] = False
    elif du == "never":
        out["ddns_send_updates"] = False
    if update_older_clients is not None:
        out["ddns_override_no_update"] = bool(update_older_clients)
    return out


class MSDHCPAdapter(Adapter):
    """Load a parsed MS DHCP export dict into the DiffSync store."""

    dhcpserver = DhcpServer
    dhcpredundancygroup = DhcpRedundancyGroup
    dhcpredundancygroupmember = DhcpRedundancyGroupMember
    dhcpsharednetwork = DhcpSharedNetwork
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
        "dhcpsharednetwork",
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
        # MS failover is per-scope, so build a scope_id -> relationship-name map while
        # loading, then tag each protected scope with its redundancy group below.
        self._failover_of: dict[str, str] = {}
        for failover in self.export.get("failover", []):
            self._load_failover(server_name, failover)

        # Superscopes -> shared networks; build a scope_id -> superscope-name map so
        # each member scope can link to its shared network (MS superscopes carry no
        # operational fields, only the grouping).
        self._superscope_of: dict[str, str] = {}
        for ss in self.export.get("superscopes", []):
            ss_name = ss.get("name")
            if not ss_name:
                continue
            self.add(self.dhcpsharednetwork(server_name=server_name, name=ss_name))
            for sid in ss.get("scope_ids", []):
                self._superscope_of[sid] = ss_name

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
        for sid in failover.get("scope_ids", []):
            self._failover_of[sid] = name
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
                shared_network=self._superscope_of.get(scope["scope_id"], ""),
                redundancy_group=self._failover_of.get(scope["scope_id"], ""),
                name=scope.get("name", ""),
                state=SCOPE_STATE_MAP.get((scope.get("state") or "").lower(), "enabled"),
                default_lease_time=scope.get("lease_duration_seconds") or 86400,
                description=scope.get("description", ""),
                **_ddns_from_ms(scope.get("dynamic_updates"), scope.get("update_older_clients")),
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
        # A real MAC goes in mac_address; an extended client-identifier (RFC 4361 /
        # DUID-style, or a Cisco ASCII client-id) would overflow it, so it routes to
        # the wider client_id column with identifier_type=client-id.
        mac, other = split_identifier(res.get("client_id", ""))
        self.add(
            self.dhcpreservation(
                server_name=server_name,
                prefix=prefix,
                ip_address=ip,
                identifier_type="client-id" if other else "hw-address",
                mac_address=mac,
                client_id=other,
                hostname=res.get("name", ""),
                reservation_type=RESERVATION_TYPE_MAP.get((res.get("type") or "").lower(), "dhcp"),
                description=res.get("description", ""),
            )
        )
        for opt in res.get("options", []):
            self._add_option(server_name, prefix, ip, opt)

    def _load_lease(self, server_name: str, prefix: str, lease: dict) -> None:
        # As for reservations: real MAC -> mac_address, else the extended identifier
        # goes in duid (the lease's wide opaque-identifier slot) rather than overflow.
        mac, other = split_identifier(lease.get("client_id", ""))
        self.add(
            self.dhcplease(
                server_name=server_name,
                prefix=prefix,
                ip_address=lease["ip_address"],
                mac_address=mac,
                duid=other,
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

"""Target adapter: load existing nautobot-dhcp-models records for one server.

Reads the *current beliefs* (the default manager) scoped to a single DHCP server
by name, so the diff is against what Nautobot currently believes that MS server's
config + leases to be.
"""

from __future__ import annotations

from diffsync import Adapter

from nautobot_ssot_msdhcp.diffsync.models.nautobot import (
    NautobotDhcpExclusion,
    NautobotDhcpLease,
    NautobotDhcpOption,
    NautobotDhcpPool,
    NautobotDhcpReservation,
    NautobotDhcpScope,
    NautobotDhcpServer,
)
from nautobot_ssot_msdhcp.utils.dhcp import canonical_dt


class NautobotAdapter(Adapter):
    """Load nautobot-dhcp-models current beliefs for a single server."""

    dhcpserver = NautobotDhcpServer
    dhcpscope = NautobotDhcpScope
    dhcppool = NautobotDhcpPool
    dhcpexclusion = NautobotDhcpExclusion
    dhcpreservation = NautobotDhcpReservation
    dhcpoption = NautobotDhcpOption
    dhcplease = NautobotDhcpLease

    top_level = (
        "dhcpserver",
        "dhcpscope",
        "dhcppool",
        "dhcpexclusion",
        "dhcpreservation",
        "dhcpoption",
        "dhcplease",
    )

    def __init__(self, *args, server_name: str, job=None, sync=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_name = server_name
        self.job = job
        self.sync = sync

    def load(self) -> None:
        """Pull this server's current-belief records out of dhcp-models."""
        from nautobot_dhcp_models.models import (
            DHCPExclusion,
            DHCPLease,
            DHCPOption,
            DHCPPool,
            DHCPReservation,
            DHCPScope,
            DHCPServer,
        )

        for server in DHCPServer.objects.filter(name=self.server_name):
            self.add(
                self.dhcpserver(
                    name=server.name,
                    vendor=server.vendor,
                    ad_authorized=server.ad_authorized,
                )
            )

        for scope in DHCPScope.objects.filter(server__name=self.server_name).select_related("prefix", "server"):
            self.add(
                self.dhcpscope(
                    server_name=self.server_name,
                    prefix=str(scope.prefix.prefix),
                    name=scope.name,
                    state=scope.state,
                    default_lease_time=scope.default_lease_time,
                    description=scope.description,
                )
            )

        for pool in DHCPPool.objects.filter(scope__server__name=self.server_name).select_related("scope__prefix"):
            self.add(
                self.dhcppool(
                    server_name=self.server_name,
                    prefix=str(pool.scope.prefix.prefix),
                    start_address=str(pool.start_address),
                    end_address=str(pool.end_address),
                    description=pool.description,
                )
            )

        for excl in DHCPExclusion.objects.filter(scope__server__name=self.server_name).select_related("scope__prefix"):
            self.add(
                self.dhcpexclusion(
                    server_name=self.server_name,
                    prefix=str(excl.scope.prefix.prefix),
                    start_address=str(excl.start_address),
                    end_address=str(excl.end_address),
                    description=excl.description,
                )
            )

        for res in DHCPReservation.objects.filter(scope__server__name=self.server_name).select_related(
            "scope__prefix", "ip_address"
        ):
            self.add(
                self.dhcpreservation(
                    server_name=self.server_name,
                    prefix=str(res.scope.prefix.prefix),
                    ip_address=str(res.ip_address.host),
                    mac_address=res.mac_address,
                    hostname=res.hostname,
                    reservation_type=res.reservation_type,
                    description=res.description,
                )
            )

        self._load_options(DHCPOption)

        for lease in DHCPLease.objects.filter(scope__server__name=self.server_name).select_related("scope__prefix"):
            self.add(
                self.dhcplease(
                    server_name=self.server_name,
                    prefix=str(lease.scope.prefix.prefix),
                    ip_address=str(lease.ip_address),
                    mac_address=lease.mac_address,
                    hostname=lease.hostname,
                    lease_state=lease.lease_state,
                    expires=canonical_dt(lease.expires),
                )
            )

    def _load_options(self, DHCPOption) -> None:
        # Server-level.
        for opt in DHCPOption.objects.filter(server__name=self.server_name).select_related("option_definition"):
            self._add_option(opt, scope_prefix="", reservation_ip="")
        # Scope-level.
        for opt in DHCPOption.objects.filter(scope__server__name=self.server_name).select_related(
            "scope__prefix", "option_definition"
        ):
            self._add_option(opt, scope_prefix=str(opt.scope.prefix.prefix), reservation_ip="")
        # Reservation-level.
        for opt in DHCPOption.objects.filter(reservation__scope__server__name=self.server_name).select_related(
            "reservation__scope__prefix", "reservation__ip_address", "option_definition"
        ):
            self._add_option(
                opt,
                scope_prefix=str(opt.reservation.scope.prefix.prefix),
                reservation_ip=str(opt.reservation.ip_address.host),
            )

    def _add_option(self, opt, scope_prefix: str, reservation_ip: str) -> None:
        self.add(
            self.dhcpoption(
                server_name=self.server_name,
                scope_prefix=scope_prefix,
                reservation_ip=reservation_ip,
                code=opt.option_definition.code,
                value=opt.value,
                option_name=opt.option_definition.name,
                data_type=opt.option_definition.data_type,
            )
        )

"""SSoT Job: Microsoft DHCP export -> nautobot-dhcp-models (one-way)."""

from __future__ import annotations

import json

from diffsync.enum import DiffSyncFlags
from nautobot.apps.jobs import BooleanVar, FileVar, register_jobs
from nautobot_ssot.jobs.base import DataSource

from nautobot_ssot_msdhcp.diffsync.adapters.msdhcp import MSDHCPAdapter
from nautobot_ssot_msdhcp.diffsync.adapters.nautobot import NautobotAdapter

name = "Microsoft DHCP SSoT"  # noqa: F841 -- grouping label in the Jobs UI


class MSDHCPDataSource(DataSource):
    """Sync a Microsoft DHCP JSON export into nautobot-dhcp-models."""

    export_file = FileVar(
        label="MS DHCP export (JSON)",
        description="JSON produced by Export-MSDHCP.ps1 on the Windows DHCP server.",
    )
    delete_records_missing_from_source = BooleanVar(
        default=False,
        label="Delete records missing from the export",
        description=(
            "If True, delete Nautobot DHCP records absent from this export. "
            "If False (default), additive-only: create/update only, never delete."
        ),
    )

    class Meta:
        """Job metadata shown in the SSoT dashboard."""

        name = "Microsoft DHCP -> Nautobot"
        data_source = "Microsoft DHCP"
        data_target = "Nautobot"
        description = "Pull MS DHCP scopes, pools, exclusions, reservations, options, and leases into dhcp-models."

    @classmethod
    def data_mappings(cls):
        """Describe the source->target mapping shown on the job detail page."""
        from nautobot_ssot.contrib.types import DataMapping  # noqa: PLC0415

        return (
            DataMapping("Scope", None, "DHCP Scope", None),
            DataMapping("Reservation", None, "DHCP Reservation", None),
            DataMapping("Lease", None, "DHCP Lease", None),
            DataMapping("Option", None, "DHCP Option", None),
        )

    def run(self, *args, **kwargs):  # type: ignore[override]
        """Parse the upload up-front, then run the standard SSoT sync."""
        self.export_file = kwargs["export_file"]
        self.delete_records_missing_from_source = kwargs["delete_records_missing_from_source"]
        self.export = json.loads(self.export_file.read().decode("utf-8"))
        self.server_name = self.export.get("server", {}).get("name")
        if not self.server_name:
            raise ValueError("Export is missing server.name; check the PowerShell export output.")
        self.logger.info(f"Loaded export for DHCP server {self.server_name!r}.")
        super().run(*args, **kwargs)

    def load_source_adapter(self) -> None:
        """Build the MS DHCP adapter from the parsed export."""
        self.source_adapter = MSDHCPAdapter(export=self.export, job=self, sync=self.sync)
        self.source_adapter.load()
        self.logger.info(
            f"Loaded from export: {len(self.source_adapter.get_all('dhcpscope'))} scope(s), "
            f"{len(self.source_adapter.get_all('dhcpreservation'))} reservation(s), "
            f"{len(self.source_adapter.get_all('dhcplease'))} lease(s)."
        )

    def load_target_adapter(self) -> None:
        """Build the Nautobot adapter scoped to this server's existing records."""
        self.target_adapter = NautobotAdapter(server_name=self.server_name, job=self, sync=self.sync)
        self.target_adapter.load()

    def execute_sync(self) -> None:
        """Run the sync, honoring the additive-only default."""
        if not self.delete_records_missing_from_source:
            self.diffsync_flags |= DiffSyncFlags.SKIP_UNMATCHED_DST
            self.logger.info("Additive-only: Nautobot records absent from the export were NOT deleted.")
        super().execute_sync()


jobs = [MSDHCPDataSource]
register_jobs(*jobs)

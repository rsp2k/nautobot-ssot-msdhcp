"""Nautobot SSoT data source for Microsoft AD DHCP.

Reads a Microsoft DHCP configuration+lease export (produced by the bundled
PowerShell script) and syncs it one-way into ``nautobot-dhcp-models``.
"""

from importlib.metadata import PackageNotFoundError, version

from nautobot.apps import NautobotAppConfig

try:
    __version__ = version("nautobot-ssot-msdhcp")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+unknown"


class NautobotSSoTMSDHCPConfig(NautobotAppConfig):
    """App configuration for the Microsoft DHCP SSoT integration."""

    name = "nautobot_ssot_msdhcp"
    verbose_name = "Nautobot SSoT Microsoft DHCP"
    description = "Sync Microsoft AD DHCP scopes, reservations, leases, and options into nautobot-dhcp-models."
    version = __version__
    author = "Ryan Malloy"
    author_email = "ryan@supported.systems"
    base_url = "ssot-msdhcp"
    required_settings: list[str] = []
    default_settings: dict = {}
    caching_config: dict = {}


config = NautobotSSoTMSDHCPConfig

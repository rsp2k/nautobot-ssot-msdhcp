"""Add an 'Import Microsoft DHCP' item to the shared DHCP nav tab.

Matching the tab name/weight that nautobot-dhcp-models declares merges this group
into the same DHCP menu, so the import page sits alongside servers/scopes.
"""

from nautobot.apps.ui import (
    NavigationWeightChoices,
    NavMenuGroup,
    NavMenuItem,
    NavMenuTab,
)

menu_items = (
    NavMenuTab(
        name="DHCP",
        icon="bus-globe",
        weight=NavigationWeightChoices.IPAM + 10,
        groups=(
            NavMenuGroup(
                name="Import",
                weight=800,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_ssot_msdhcp:import",
                        name="Import Microsoft DHCP",
                        weight=100,
                        permissions=["extras.run_job"],
                    ),
                ),
            ),
        ),
    ),
)

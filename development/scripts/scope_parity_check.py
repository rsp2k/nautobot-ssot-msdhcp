"""Verify MS scope-parity (superscope -> shared-network, DDNS) syncs end-to-end.

Confirms the MS source's superscope -> shared-network projection + per-scope DDNS
mapping create cleanly through the shared target (shared-network before member
scope per top_level), with no perpetual diff. Run via `nautobot-server shell` in
the msdhcp stack.
"""

from nautobot_dhcp_models.models import DHCPScope, DHCPServer, DHCPSharedNetwork
from nautobot_dhcp_models.ssot.adapter import NautobotAdapter
from nautobot_ssot_msdhcp.diffsync.adapters.msdhcp import MSDHCPAdapter

EXPORT = {
    "server": {"name": "sp-ms01.corp.example.com", "ad_authorized": True},
    "superscopes": [{"name": "sp-campus", "scope_ids": ["10.50.10.0", "10.50.20.0"]}],
    "scopes": [
        {
            "scope_id": "10.50.10.0", "subnet_mask": "255.255.255.0", "name": "sp-a",
            "description": "", "start_range": "10.50.10.10", "end_range": "10.50.10.250",
            "state": "Active", "lease_duration_seconds": 86400,
            "dynamic_updates": "Always", "update_older_clients": True,
            "options": [], "exclusions": [], "reservations": [], "leases": [],
        },
        {
            "scope_id": "10.50.20.0", "subnet_mask": "255.255.255.0", "name": "sp-b",
            "description": "", "start_range": "10.50.20.10", "end_range": "10.50.20.250",
            "state": "Active", "lease_duration_seconds": 86400,
            "dynamic_updates": "Never",
            "options": [], "exclusions": [], "reservations": [], "leases": [],
        },
    ],
}


def run():
    name = "sp-ms01.corp.example.com"
    src = MSDHCPAdapter(export=EXPORT)
    src.load()
    tgt = NautobotAdapter(server_name=name)
    tgt.load()
    tgt.sync_from(src)
    again = NautobotAdapter(server_name=name)
    again.load()
    s = again.diff_from(src).summary()
    print(f"[{name}] re-sync diff summary: {s}")
    assert s.get("create", 0) == 0 and s.get("update", 0) == 0 and s.get("delete", 0) == 0, s

    srv = DHCPServer.objects.get(name=name)
    sn = DHCPSharedNetwork.objects.get(server=srv, name="sp-campus")
    members = sorted(str(sc.prefix.prefix) for sc in DHCPScope.objects.filter(shared_network=sn))
    print("shared-network sp-campus members:", members)
    assert members == ["10.50.10.0/24", "10.50.20.0/24"], members

    a = DHCPScope.objects.get(server=srv, prefix__network="10.50.10.0")
    b = DHCPScope.objects.get(server=srv, prefix__network="10.50.20.0")
    print("scope a ddns:", a.ddns_send_updates, a.ddns_override_client_update, a.ddns_override_no_update)
    print("scope b ddns_send_updates:", b.ddns_send_updates)
    assert a.ddns_send_updates is True and a.ddns_override_client_update is True and a.ddns_override_no_update is True
    assert b.ddns_send_updates is False
    print("MS SCOPE-PARITY OK")


run()

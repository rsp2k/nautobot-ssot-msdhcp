"""Verify MS failover -> redundancy syncs end-to-end through the shared target.

Confirms the MS source's redundancy projection creates the group + this server's
member via the Nautobot target CRUD, with no perpetual diff. The cross-server
invariant itself is proven by the Kea redundancy check; this proves the MS source
path. Run via `nautobot-server shell` in the msdhcp stack.
"""

from nautobot_dhcp_models.models import DHCPRedundancyGroup, DHCPServer
from nautobot_dhcp_models.ssot.adapter import NautobotAdapter
from nautobot_ssot_msdhcp.diffsync.adapters.msdhcp import MSDHCPAdapter

EXPORT = {
    "server": {"name": "fo-ms01.corp.example.com", "ad_authorized": True},
    "failover": [{
        "name": "fo-relationship",
        "mode": "LoadBalance",
        "primary_server": "fo-ms01.corp.example.com",
        "secondary_server": "fo-ms02.corp.example.com",
        "mclt": 3600,
        "load_balance_percent": 50,
        "state_switch_interval": None,
        "scope_ids": ["10.40.0.0"],
    }],
    "scopes": [{
        "scope_id": "10.40.0.0", "subnet_mask": "255.255.255.0", "name": "fo-scope",
        "description": "", "start_range": "10.40.0.10", "end_range": "10.40.0.250",
        "state": "Active", "lease_duration_seconds": 86400,
        "options": [], "exclusions": [], "reservations": [], "leases": [],
    }],
}


def run():
    name = "fo-ms01.corp.example.com"
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

    g = DHCPRedundancyGroup.objects.get(name="fo-relationship")
    members = {m.server.name: m.role for m in g.members.all()}
    print("group:", g.name, "mode:", g.mode, "mclt:", g.mclt, "lb%:", g.load_balance_percent)
    print("members:", members)
    assert g.mode == "load-balance" and g.mclt == 3600 and g.load_balance_percent == 50
    assert members == {name: "primary"}
    print("MS FAILOVER -> REDUNDANCY OK")


run()

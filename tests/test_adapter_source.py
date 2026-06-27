"""MS DHCP source adapter — load() against the fixture export.

Pure pytest: no Django, no Nautobot ORM, no live DHCP server.
"""

import json
from pathlib import Path

import pytest

from nautobot_ssot_msdhcp.diffsync.adapters.msdhcp import MSDHCPAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "ms_dhcp_export.json"


@pytest.fixture
def adapter() -> MSDHCPAdapter:
    export = json.loads(FIXTURE.read_text())
    a = MSDHCPAdapter(export=export)
    a.load()
    return a


def test_server_loaded(adapter):
    server = adapter.get("dhcpserver", "ms-dhcp01.corp.example.com")
    assert server.vendor == "microsoft"
    assert server.ad_authorized is True


def test_scopes_loaded_with_cidr_and_state(adapter):
    scopes = {s.prefix: s for s in adapter.get_all("dhcpscope")}
    assert set(scopes) == {"10.0.10.0/24", "10.0.20.0/24"}
    assert scopes["10.0.10.0/24"].state == "enabled"
    assert scopes["10.0.10.0/24"].default_lease_time == 691200
    assert scopes["10.0.10.0/24"].name == "VLAN10-Workstations"


def test_pool_and_exclusion(adapter):
    pools = adapter.get_all("dhcppool")
    assert len(pools) == 2  # one per scope with a range
    p10 = [p for p in pools if p.prefix == "10.0.10.0/24"][0]
    assert p10.start_address == "10.0.10.10"
    assert p10.end_address == "10.0.10.250"

    exclusions = adapter.get_all("dhcpexclusion")
    assert len(exclusions) == 1
    assert exclusions[0].start_address == "10.0.10.10"
    assert exclusions[0].end_address == "10.0.10.19"


def test_reservation_normalizes_mac(adapter):
    res = adapter.get(
        "dhcpreservation",
        {"server_name": "ms-dhcp01.corp.example.com", "prefix": "10.0.10.0/24", "ip_address": "10.0.10.5"},
    )
    assert res.mac_address == "00:11:22:33:44:55"
    assert res.hostname == "printer-f1"
    assert res.reservation_type == "both"


def test_leases_loaded(adapter):
    leases = adapter.get_all("dhcplease")
    assert len(leases) == 2
    lease = adapter.get(
        "dhcplease",
        {"server_name": "ms-dhcp01.corp.example.com", "prefix": "10.0.10.0/24", "ip_address": "10.0.10.50"},
    )
    assert lease.mac_address == "aa:bb:cc:dd:ee:01"
    assert lease.lease_state == "active"
    assert lease.expires == "2026-06-29T08:00:00+00:00"


def test_options_at_three_levels(adapter):
    options = adapter.get_all("dhcpoption")
    # Server-level (2), scope-level (one per scope = 2), reservation-level (1) = 5
    server_opts = [o for o in options if not o.scope_prefix and not o.reservation_ip]
    scope_opts = [o for o in options if o.scope_prefix and not o.reservation_ip]
    res_opts = [o for o in options if o.reservation_ip]
    assert len(server_opts) == 2
    assert len(scope_opts) == 2
    assert len(res_opts) == 1

    dns = [o for o in server_opts if o.code == 6][0]
    assert dns.value == "10.0.0.10,10.0.0.11"
    assert dns.data_type == "ipv4-address"

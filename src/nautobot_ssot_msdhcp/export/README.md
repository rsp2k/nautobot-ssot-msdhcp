# Microsoft DHCP export format (v1)

`Export-MSDHCP.ps1` produces the JSON document this SSoT data source ingests. Run it on (or
against) a Windows DHCP server, then upload the file to the **Microsoft DHCP → Nautobot** job.

```powershell
.\Export-MSDHCP.ps1 -ComputerName dhcp01 -OutFile C:\temp\dhcp01.json
```

## Shape

```jsonc
{
  "export_version": "3",
  "exported_at": "2026-06-27T12:00:00Z",
  "server": {
    "name": "ms-dhcp01.corp.example.com",   // -> DHCPServer.name (natural key)
    "version": "10.0",
    "ad_authorized": true                     // -> DHCPServer.ad_authorized
  },
  "server_options": [                          // options applied at the server level
    { "option_id": 6, "name": "DNS Servers", "type": "IPv4Address", "value": ["10.0.0.10", "10.0.0.11"] }
  ],
  "failover": [                                // Get-DhcpServerv4Failover -> DHCPRedundancyGroup + member
    {
      "name": "ms-dhcp01-failover",            // -> DHCPRedundancyGroup.name (natural key)
      "mode": "LoadBalance",                   // LoadBalance|HotStandby -> load-balance|hot-standby
      "primary_server": "ms-dhcp01.corp.example.com",    // this server's role is derived from these
      "secondary_server": "ms-dhcp02.corp.example.com",
      "mclt": 3600,                            // -> mclt (seconds)
      "load_balance_percent": 50,              // -> load_balance_percent
      "state_switch_interval": null,           // -> state_switch_interval (hot-standby, seconds)
      "scope_ids": ["10.0.10.0"]               // scopes protected by this relationship
    }
  ],
  "superscopes": [                             // Get-DhcpServerv4Superscope -> DHCPSharedNetwork
    {
      "name": "campus-a",                      // -> DHCPSharedNetwork.name; member scopes link to it
      "scope_ids": ["10.0.10.0", "10.0.20.0"]
    }
  ],
  "scopes": [
    {
      "scope_id": "10.0.10.0",                 // network address
      "subnet_mask": "255.255.255.0",          // scope_id + mask -> ipam.Prefix 10.0.10.0/24
      "name": "VLAN10",
      "description": "...",
      "start_range": "10.0.10.10",             // -> DHCPPool.start_address
      "end_range": "10.0.10.250",              // -> DHCPPool.end_address
      "state": "Active",                       // Active|Inactive -> DHCPScope.state
      "lease_duration_seconds": 691200,        // -> DHCPScope.default_lease_time
      "dynamic_updates": "Always",             // Always|OnClientRequest|Never -> ddns_send_updates (+override_client_update)
      "update_older_clients": true,            // -> ddns_override_no_update
      "options": [ /* option objects, scope level */ ],
      "exclusions": [
        { "start_range": "10.0.10.10", "end_range": "10.0.10.19" }   // -> DHCPExclusion
      ],
      "reservations": [
        {
          "ip_address": "10.0.10.5",           // -> DHCPReservation.ip_address (ipam.IPAddress)
          "client_id": "00-11-22-33-44-55",    // MAC, dash form -> normalized to colons
          "name": "printer-f1",                // -> hostname
          "description": "...",
          "type": "Both",                      // Dhcp|Bootp|Both -> reservation_type
          "options": [ /* option objects, reservation level */ ]
        }
      ],
      "leases": [
        {
          "ip_address": "10.0.10.50",          // -> DHCPLease.ip_address (raw)
          "client_id": "aa-bb-cc-dd-ee-01",    // MAC -> normalized to colons
          "hostname": "laptop-42.corp.example.com",
          "address_state": "Active",           // -> DHCPLease.lease_state
          "lease_expiry": "2026-06-29T08:00:00Z"  // -> DHCPLease.expires / valid_during.upper
        }
      ]
    }
  ]
}
```

## Option object

```jsonc
{ "option_id": 3, "name": "Router", "type": "IPv4Address", "value": ["10.0.10.1"] }
```

`option_id` + `name` + `type` populate / match a `DHCPOptionDefinition` (space `dhcp4`); `value`
is joined with commas into `DHCPOption.value`. An option's parent is the level it appears under
(server / scope / reservation).

## Notes

- MAC `client_id`s use Windows dash notation (`00-11-22-33-44-55`); the adapter normalizes them
  to colon notation for the model's `mac_address` field.
- `lease_duration_seconds` is the scope lease time; the per-lease `lease_expiry` feeds the
  lease's wire-time window (`valid_during.upper`).
- Leases can be large; pass `-IncludeLeases $false` to skip them.

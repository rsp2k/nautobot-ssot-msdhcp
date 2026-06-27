# Nautobot SSoT — Microsoft DHCP

A [Nautobot](https://nautobot.com/) [SSoT](https://docs.nautobot.com/projects/ssot/en/latest/)
data source that syncs **Microsoft AD DHCP** (IPv4) into
[`nautobot-dhcp-models`](https://github.com/rsp2k/nautobot-app-dhcp-models). One-way:
Microsoft DHCP is the source of truth being migrated *from*; dhcp-models is the SSoT target.

It's the first per-vendor adapter for the vendor-neutral dhcp-models store — pair it later
with an ISC Kea adapter to diff the two and drive an MS→Kea migration.

## How it works

1. An operator runs the bundled PowerShell script on the Windows DHCP server:
   ```powershell
   .\Export-MSDHCP.ps1 -ComputerName dhcp01 -OutFile dhcp01.json
   ```
   (See [the export format](src/nautobot_ssot_msdhcp/export/README.md).)
2. They run the **Microsoft DHCP → Nautobot** SSoT job in Nautobot and upload `dhcp01.json`.
3. DiffSync compares the export against what Nautobot currently believes for that server and
   creates/updates **scopes, pools, exclusions, reservations, options, and leases**.

The job is **additive-only by default** — it never deletes Nautobot records unless you opt in.

## Honoring the bitemporal contracts

The target writes through the dhcp-models contracts:

- New objects are created as the first belief; **drift is applied via `.amend()`**, so the
  belief log rotates instead of overwriting — every re-sync stays queryable as history.
- **Leases follow the churn-control rule**: a re-observed lease whose client (MAC) changed is
  an `amend()` (a new occupancy belief); a renewal of the same binding is an in-place `save()`
  that just widens the wire-time window. Re-observations that change nothing are no-ops.
- IPAM is materialized first: scope prefixes and reservation IPs are `get_or_create`-d before
  the DHCP record links to them.

## Status

v1 covers core config + leases. Client classes (MS policies), superscopes, and failover are
future work. Requires PostgreSQL for the bitemporal belief log (see dhcp-models).

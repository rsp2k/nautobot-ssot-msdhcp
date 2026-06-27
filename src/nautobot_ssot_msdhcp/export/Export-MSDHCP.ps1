<#
.SYNOPSIS
    Export Microsoft DHCP (IPv4) config + leases to the JSON format consumed by
    the nautobot-ssot-msdhcp data source.

.DESCRIPTION
    Run on (or against) a Windows DHCP server with the DhcpServer PowerShell
    module available. Produces a single JSON document: server info, server-level
    options, and every scope with its options, exclusions, reservations, and
    active leases. Upload the resulting file to the Nautobot SSoT job.

.PARAMETER ComputerName
    DHCP server to query. Defaults to the local machine.

.PARAMETER OutFile
    Path to write the JSON export to. Defaults to .\ms-dhcp-export.json

.PARAMETER IncludeLeases
    Include dynamic leases (can be large). Defaults to $true.

.EXAMPLE
    .\Export-MSDHCP.ps1 -ComputerName dhcp01 -OutFile C:\temp\dhcp01.json
#>
[CmdletBinding()]
param(
    [string]$ComputerName = $env:COMPUTERNAME,
    [string]$OutFile = ".\ms-dhcp-export.json",
    [bool]$IncludeLeases = $true
)

Import-Module DhcpServer -ErrorAction Stop

function Convert-OptionValue {
    param($opt)
    [PSCustomObject]@{
        option_id = [int]$opt.OptionId
        name      = [string]$opt.Name
        type      = [string]$opt.Type
        value     = @($opt.Value | ForEach-Object { [string]$_ })
    }
}

$serverName = $ComputerName
try { $ver = (Get-DhcpServerVersion -ComputerName $ComputerName) } catch { $ver = $null }
$authorized = $false
try { $authorized = @(Get-DhcpServerInDC | Where-Object { $_.DnsName -like "*$ComputerName*" }).Count -gt 0 } catch {}

$serverOptions = @()
try {
    $serverOptions = @(Get-DhcpServerv4OptionValue -ComputerName $ComputerName -All -ErrorAction Stop |
        ForEach-Object { Convert-OptionValue $_ })
} catch {}

$scopes = @()
foreach ($scope in (Get-DhcpServerv4Scope -ComputerName $ComputerName)) {
    $sid = $scope.ScopeId.IPAddressToString

    $exclusions = @(Get-DhcpServerv4ExclusionRange -ComputerName $ComputerName -ScopeId $sid -ErrorAction SilentlyContinue |
        ForEach-Object { [PSCustomObject]@{ start_range = $_.StartRange.IPAddressToString; end_range = $_.EndRange.IPAddressToString } })

    $scopeOptions = @(Get-DhcpServerv4OptionValue -ComputerName $ComputerName -ScopeId $sid -ErrorAction SilentlyContinue |
        ForEach-Object { Convert-OptionValue $_ })

    $reservations = @()
    foreach ($r in (Get-DhcpServerv4Reservation -ComputerName $ComputerName -ScopeId $sid -ErrorAction SilentlyContinue)) {
        $resOptions = @(Get-DhcpServerv4OptionValue -ComputerName $ComputerName -ScopeId $sid -ReservedIP $r.IPAddress.IPAddressToString -ErrorAction SilentlyContinue |
            ForEach-Object { Convert-OptionValue $_ })
        $reservations += [PSCustomObject]@{
            ip_address  = $r.IPAddress.IPAddressToString
            client_id   = [string]$r.ClientId
            name        = [string]$r.Name
            description = [string]$r.Description
            type        = [string]$r.Type
            options     = $resOptions
        }
    }

    $leases = @()
    if ($IncludeLeases) {
        foreach ($l in (Get-DhcpServerv4Lease -ComputerName $ComputerName -ScopeId $sid -ErrorAction SilentlyContinue)) {
            $expiry = $null
            if ($l.LeaseExpiryTime) { $expiry = $l.LeaseExpiryTime.ToUniversalTime().ToString("o") }
            $leases += [PSCustomObject]@{
                ip_address    = $l.IPAddress.IPAddressToString
                client_id     = [string]$l.ClientId
                hostname      = [string]$l.HostName
                address_state = [string]$l.AddressState
                lease_expiry  = $expiry
            }
        }
    }

    $duration = $null
    if ($scope.LeaseDuration) { $duration = [int]$scope.LeaseDuration.TotalSeconds }

    $scopes += [PSCustomObject]@{
        scope_id               = $sid
        name                   = [string]$scope.Name
        description            = [string]$scope.Description
        subnet_mask            = $scope.SubnetMask.IPAddressToString
        start_range            = $scope.StartRange.IPAddressToString
        end_range              = $scope.EndRange.IPAddressToString
        state                  = [string]$scope.State
        lease_duration_seconds = $duration
        options                = $scopeOptions
        exclusions             = $exclusions
        reservations           = $reservations
        leases                 = $leases
    }
}

$export = [PSCustomObject]@{
    export_version = "1"
    exported_at    = (Get-Date).ToUniversalTime().ToString("o")
    server         = [PSCustomObject]@{
        name          = $serverName
        version       = if ($ver) { "$($ver.MajorVersion).$($ver.MinorVersion)" } else { $null }
        ad_authorized = $authorized
    }
    server_options = $serverOptions
    scopes         = $scopes
}

$export | ConvertTo-Json -Depth 8 | Out-File -FilePath $OutFile -Encoding utf8
Write-Host "Exported $($scopes.Count) scope(s) to $OutFile"

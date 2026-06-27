"""Nautobot-side DiffSync models: CRUD against nautobot-dhcp-models.

These honor the dhcp-models contracts:

- **create** writes the first belief via ``objects.create`` (IPAM Prefix/IPAddress
  are ``get_or_create``-d first, since dhcp-models requires the FK to exist).
- **update** routes drift through ``obj.amend(**changed)`` so the belief log
  rotates instead of overwriting in place -- except leases (see below).
- **DHCPLease.update** implements the churn-control rule: a *new holder*
  (different MAC) is an ``amend()``; a *renewal/state change* on the same binding
  is an in-place ``save()`` that just widens the wire-time window.
- **delete** hard-deletes; the SSoT job defaults to additive-only so deletes only
  happen when the operator opts in.

ORM imports are lazy (inside methods) so this module imports without a Django env.
"""

from __future__ import annotations

import datetime
from typing import Any

from nautobot_ssot_msdhcp.diffsync.models.base import (
    DhcpExclusion,
    DhcpLease,
    DhcpOption,
    DhcpPool,
    DhcpReservation,
    DhcpScope,
    DhcpServer,
)

# --------------------------------------------------------------------------- helpers


def _active_status():
    from nautobot.extras.models import Status

    return Status.objects.get(name="Active")


def _global_namespace():
    from nautobot.ipam.models import Namespace

    return Namespace.objects.get(name="Global")


def _get_or_create_prefix(cidr: str):
    from nautobot.ipam.models import Prefix

    prefix, _ = Prefix.objects.get_or_create(
        prefix=cidr,
        namespace=_global_namespace(),
        defaults={"status": _active_status(), "type": "network"},
    )
    return prefix


def _get_or_create_ipaddress(ip: str):
    from nautobot.ipam.models import IPAddress

    host = ip.split("/")[0]
    address = ip if "/" in ip else f"{ip}/32"
    # `namespace` isn't a queryable field on IPAddress (it lives on parent), so we
    # can't use get_or_create(namespace=...). Look up by host within the Global
    # namespace; create with the namespace kwarg (which the create path resolves
    # to a parent prefix).
    existing = IPAddress.objects.filter(host=host, parent__namespace=_global_namespace()).first()
    if existing:
        return existing
    return IPAddress.objects.create(address=address, namespace=_global_namespace(), status=_active_status())


def _resolve_server(name: str):
    from nautobot_dhcp_models.models import DHCPServer

    return DHCPServer.objects.get(name=name)


def _resolve_scope(server_name: str, cidr: str):
    from nautobot.ipam.models import Prefix
    from nautobot_dhcp_models.models import DHCPScope

    # `prefix` on Prefix is a derived property, not a join-traversable field, so we
    # resolve the Prefix object by its direct `prefix=` lookup, then filter by FK.
    prefix = Prefix.objects.get(prefix=cidr, namespace=_global_namespace())
    return DHCPScope.objects.get(server__name=server_name, prefix=prefix)


def _parse_dt(value: str):
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _lease_window(expires_iso: str):
    """Build the lease wire-time window: [observed-now, expires) (open if expired/unknown)."""
    from django.utils import timezone
    from psycopg2.extras import DateTimeTZRange

    now = timezone.now()
    expires = _parse_dt(expires_iso)
    upper = expires if (expires and expires > now) else None
    return DateTimeTZRange(lower=now, upper=upper, bounds="[)")


def _option_definition(code: int, name: str, data_type: str):
    from nautobot_dhcp_models.models import DHCPOptionDefinition

    optdef, _ = DHCPOptionDefinition.objects.get_or_create(
        space="dhcp4",
        code=code,
        defaults={"name": name or f"option-{code}", "data_type": data_type or "string"},
    )
    return optdef


# --------------------------------------------------------------------------- models


class NautobotDhcpServer(DhcpServer):
    @classmethod
    def create(cls, adapter, ids: dict[str, Any], attrs: dict[str, Any]):
        from django.contrib.contenttypes.models import ContentType
        from nautobot_dhcp_models.models import DHCPServer

        status = _active_status()
        status.content_types.add(ContentType.objects.get_for_model(DHCPServer))
        DHCPServer.objects.update_or_create(
            name=ids["name"],
            defaults={
                "vendor": attrs.get("vendor", "microsoft"),
                "ad_authorized": attrs.get("ad_authorized"),
                "status": status,
            },
        )
        return super().create(adapter, ids, attrs)

    def update(self, attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPServer

        DHCPServer.objects.filter(name=self.name).update(
            **{k: v for k, v in attrs.items() if k in ("vendor", "ad_authorized")}
        )
        return super().update(attrs)

    def delete(self):
        from nautobot_dhcp_models.models import DHCPServer

        DHCPServer.objects.filter(name=self.name).delete()
        super().delete()
        return self


class NautobotDhcpScope(DhcpScope):
    @classmethod
    def create(cls, adapter, ids: dict[str, Any], attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPScope

        DHCPScope.objects.create(
            server=_resolve_server(ids["server_name"]),
            prefix=_get_or_create_prefix(ids["prefix"]),
            name=attrs.get("name", ""),
            state=attrs.get("state", "enabled"),
            default_lease_time=attrs.get("default_lease_time", 86400),
            description=attrs.get("description", ""),
        )
        return super().create(adapter, ids, attrs)

    def update(self, attrs: dict[str, Any]):
        scope = _resolve_scope(self.server_name, self.prefix)
        drift = {k: v for k, v in attrs.items() if k in ("name", "state", "default_lease_time", "description")}
        if drift:
            scope.amend(**drift)
        return super().update(attrs)

    def delete(self):
        _resolve_scope(self.server_name, self.prefix).delete()
        super().delete()
        return self


class NautobotDhcpPool(DhcpPool):
    @classmethod
    def create(cls, adapter, ids: dict[str, Any], attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPPool

        DHCPPool.objects.create(
            scope=_resolve_scope(ids["server_name"], ids["prefix"]),
            start_address=ids["start_address"],
            end_address=ids["end_address"],
            description=attrs.get("description", ""),
        )
        return super().create(adapter, ids, attrs)

    def update(self, attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPPool

        pool = DHCPPool.objects.get(
            scope=_resolve_scope(self.server_name, self.prefix),
            start_address=self.start_address,
            end_address=self.end_address,
        )
        if "description" in attrs:
            pool.amend(description=attrs["description"])
        return super().update(attrs)

    def delete(self):
        from nautobot_dhcp_models.models import DHCPPool

        DHCPPool.objects.filter(
            scope=_resolve_scope(self.server_name, self.prefix),
            start_address=self.start_address,
            end_address=self.end_address,
        ).delete()
        super().delete()
        return self


class NautobotDhcpExclusion(DhcpExclusion):
    @classmethod
    def create(cls, adapter, ids: dict[str, Any], attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPExclusion

        DHCPExclusion.objects.create(
            scope=_resolve_scope(ids["server_name"], ids["prefix"]),
            start_address=ids["start_address"],
            end_address=ids["end_address"],
            description=attrs.get("description", ""),
        )
        return super().create(adapter, ids, attrs)

    def update(self, attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPExclusion

        excl = DHCPExclusion.objects.get(
            scope=_resolve_scope(self.server_name, self.prefix),
            start_address=self.start_address,
            end_address=self.end_address,
        )
        if "description" in attrs:
            excl.amend(description=attrs["description"])
        return super().update(attrs)

    def delete(self):
        from nautobot_dhcp_models.models import DHCPExclusion

        DHCPExclusion.objects.filter(
            scope=_resolve_scope(self.server_name, self.prefix),
            start_address=self.start_address,
            end_address=self.end_address,
        ).delete()
        super().delete()
        return self


class NautobotDhcpReservation(DhcpReservation):
    @classmethod
    def create(cls, adapter, ids: dict[str, Any], attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPReservation

        DHCPReservation.objects.create(
            scope=_resolve_scope(ids["server_name"], ids["prefix"]),
            ip_address=_get_or_create_ipaddress(ids["ip_address"]),
            mac_address=attrs.get("mac_address", ""),
            hostname=attrs.get("hostname", ""),
            reservation_type=attrs.get("reservation_type", "dhcp"),
            description=attrs.get("description", ""),
            identifier_type="hw-address",
        )
        return super().create(adapter, ids, attrs)

    def _resolve(self):
        from nautobot_dhcp_models.models import DHCPReservation

        return DHCPReservation.objects.get(
            scope=_resolve_scope(self.server_name, self.prefix),
            ip_address__host=self.ip_address,
        )

    def update(self, attrs: dict[str, Any]):
        drift = {k: v for k, v in attrs.items() if k in ("mac_address", "hostname", "reservation_type", "description")}
        if drift:
            self._resolve().amend(**drift)
        return super().update(attrs)

    def delete(self):
        self._resolve().delete()
        super().delete()
        return self


class NautobotDhcpLease(DhcpLease):
    @classmethod
    def create(cls, adapter, ids: dict[str, Any], attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPLease

        DHCPLease.objects.create(
            scope=_resolve_scope(ids["server_name"], ids["prefix"]),
            ip_address=ids["ip_address"],
            mac_address=attrs.get("mac_address", ""),
            hostname=attrs.get("hostname", ""),
            lease_state=attrs.get("lease_state", "active"),
            expires=_parse_dt(attrs.get("expires", "")),
            valid_during=_lease_window(attrs.get("expires", "")),
        )
        return super().create(adapter, ids, attrs)

    def update(self, attrs: dict[str, Any]):
        """Churn-control: new holder (MAC change) -> amend(); same binding -> save()."""
        from nautobot_dhcp_models.models import DHCPLease

        lease = DHCPLease.objects.get(scope=_resolve_scope(self.server_name, self.prefix), ip_address=self.ip_address)
        new_mac = attrs.get("mac_address", self.mac_address)
        expires_iso = attrs.get("expires", self.expires)

        if "mac_address" in attrs and new_mac != lease.mac_address:
            # A different client now holds this address -> a new occupancy belief.
            lease.amend(
                mac_address=new_mac,
                hostname=attrs.get("hostname", self.hostname),
                lease_state=attrs.get("lease_state", self.lease_state),
                expires=_parse_dt(expires_iso),
                valid_during=_lease_window(expires_iso),
            )
        else:
            # Renewal / state change on the same binding -> in-place; widen the window.
            for field in ("hostname", "lease_state"):
                if field in attrs:
                    setattr(lease, field, attrs[field])
            if "expires" in attrs:
                lease.expires = _parse_dt(expires_iso)
                lease.valid_during = _lease_window(expires_iso)
            lease.save()
        return super().update(attrs)

    def delete(self):
        from nautobot_dhcp_models.models import DHCPLease

        DHCPLease.objects.filter(
            scope=_resolve_scope(self.server_name, self.prefix), ip_address=self.ip_address
        ).delete()
        super().delete()
        return self


class NautobotDhcpOption(DhcpOption):
    @classmethod
    def _parent_kwargs(cls, server_name, scope_prefix, reservation_ip):
        """Return the single parent FK kwarg for a DHCPOption at this level."""
        if reservation_ip:
            from nautobot_dhcp_models.models import DHCPReservation

            scope = _resolve_scope(server_name, scope_prefix)
            reservation = DHCPReservation.objects.get(scope=scope, ip_address__host=reservation_ip)
            return {"reservation": reservation}
        if scope_prefix:
            return {"scope": _resolve_scope(server_name, scope_prefix)}
        return {"server": _resolve_server(server_name)}

    @classmethod
    def create(cls, adapter, ids: dict[str, Any], attrs: dict[str, Any]):
        from nautobot_dhcp_models.models import DHCPOption

        parent = cls._parent_kwargs(ids["server_name"], ids["scope_prefix"], ids["reservation_ip"])
        optdef = _option_definition(ids["code"], attrs.get("option_name", ""), attrs.get("data_type", "string"))
        DHCPOption.objects.create(
            option_definition=optdef,
            value=attrs.get("value", ""),
            **parent,
        )
        return super().create(adapter, ids, attrs)

    def _resolve(self):
        from nautobot_dhcp_models.models import DHCPOption

        parent = self._parent_kwargs(self.server_name, self.scope_prefix, self.reservation_ip)
        return DHCPOption.objects.get(option_definition__space="dhcp4", option_definition__code=self.code, **parent)

    def update(self, attrs: dict[str, Any]):
        if "value" in attrs:
            self._resolve().amend(value=attrs["value"])
        return super().update(attrs)

    def delete(self):
        self._resolve().delete()
        super().delete()
        return self

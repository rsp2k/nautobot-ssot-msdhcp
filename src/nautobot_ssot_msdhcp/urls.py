"""URLs for the nautobot-ssot-msdhcp import page."""

from django.urls import path

from nautobot_ssot_msdhcp.views import MSDHCPImportView

app_name = "nautobot_ssot_msdhcp"

urlpatterns = [
    path("import/", MSDHCPImportView.as_view(), name="import"),
]

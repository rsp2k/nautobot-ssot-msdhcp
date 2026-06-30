"""Admin-facing 'Import Microsoft DHCP' page.

One place to (1) download ``Export-MSDHCP.ps1`` with run instructions and
(2) upload its JSON output. The upload reuses the existing
``MSDHCPDataSource`` SSoT job verbatim -- it just creates a FileProxy from the
upload and enqueues the job -- so the import gets the job framework's logging,
async execution, and result tracking for free.
"""

from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

SCRIPT_PATH = Path(__file__).parent / "export" / "Export-MSDHCP.ps1"
SCRIPT_NAME = "Export-MSDHCP.ps1"
JOB_NAME = "Microsoft DHCP -> Nautobot"


class MSDHCPImportView(View):
    """GET: download the script / render the page. POST: enqueue the import job."""

    def _can_run(self, request) -> bool:
        """Gate on the run-job permission, since importing runs the SSoT job."""
        user = request.user
        return user.is_authenticated and (user.is_superuser or user.has_perm("extras.run_job"))

    def get(self, request):
        """Serve the script (``?download=script``) or render the import page."""
        if request.GET.get("download") == "script":
            return FileResponse(
                open(SCRIPT_PATH, "rb"),
                as_attachment=True,
                filename=SCRIPT_NAME,
                content_type="text/plain; charset=utf-8",
            )
        context = {
            "script_name": SCRIPT_NAME,
            "download_url": f"{reverse('plugins:nautobot_ssot_msdhcp:import')}?download=script",
            "can_run": self._can_run(request),
        }
        return render(request, "nautobot_ssot_msdhcp/ms_dhcp_import.html", context)

    def post(self, request):
        """Create a FileProxy from the upload and enqueue MSDHCPDataSource."""
        from nautobot.extras.models import FileProxy, JobResult
        from nautobot.extras.models import Job as JobModel

        if not self._can_run(request):
            return HttpResponseForbidden("You do not have permission to run import jobs.")

        upload = request.FILES.get("export_file")
        if not upload:
            messages.error(request, "Choose the JSON file produced by Export-MSDHCP.ps1 first.")
            return redirect("plugins:nautobot_ssot_msdhcp:import")

        dryrun = bool(request.POST.get("dryrun"))
        delete = bool(request.POST.get("delete_records_missing_from_source"))

        try:
            job_model = JobModel.objects.get(name=JOB_NAME)
        except JobModel.DoesNotExist:
            messages.error(request, f"The '{JOB_NAME}' job is not installed.")
            return redirect("plugins:nautobot_ssot_msdhcp:import")

        # Nautobot disables jobs by default; an authorized import implies running it.
        if not job_model.enabled:
            job_model.enabled = True
            job_model.save()

        file_proxy = FileProxy.objects.create(name=upload.name, file=upload)
        job_result = JobResult.enqueue_job(
            job_model,
            request.user,
            export_file=str(file_proxy.pk),
            dryrun=dryrun,
            delete_records_missing_from_source=delete,
        )
        mode = "Dry run" if dryrun else "Import"
        messages.success(request, f"{mode} started for {upload.name}. Follow its progress below.")
        return redirect(job_result.get_absolute_url())

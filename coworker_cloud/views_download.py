"""Public download of the Windows One9 worker (OpenWorker desktop, One9 Cloud)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET


def _filename() -> str:
    return getattr(settings, "OPENWORKER_WINDOWS_FILENAME", "One9Worker-Setup.exe")


def _local_installer() -> Path | None:
    folder = Path(getattr(settings, "OPENWORKER_LOCAL_DOWNLOAD_DIR"))
    path = folder / _filename()
    return path if path.is_file() else None


def _direct_url() -> str:
    configured = getattr(settings, "OPENWORKER_WINDOWS_DOWNLOAD_URL", "") or ""
    if configured:
        return configured
    return (
        "https://github.com/one9founders-org/backend/releases/download/"
        "windows-worker-v0.1.7/One9Worker-Setup.exe"
    )


def _api_download_url(request) -> str:
    public = (getattr(settings, "COWORKER_CLOUD_PUBLIC_URL", "") or "").rstrip("/")
    if public.startswith("http"):
        return f"{public}/v1/openworker/download/windows"
    return request.build_absolute_uri("/v1/openworker/download/windows")


def _release_payload(request) -> dict:
    configured = bool(getattr(settings, "OPENWORKER_WINDOWS_DOWNLOAD_URL", "") or "")
    local = _local_installer()
    return {
        "name": "One9 Worker",
        "cloud": "One9Founders Cloud",
        "windows": {
            "available": bool(local)
            or configured
            or not getattr(settings, "DEBUG", False),
            "os": "Windows 10/11 (x64)",
            "filename": _filename(),
            "version": getattr(settings, "OPENWORKER_WINDOWS_VERSION", "0.1.7"),
            "url": _api_download_url(request),
            "direct_url": _direct_url(),
            "local": bool(local),
        },
    }


@require_GET
def openworker_landing(request):
    """Human download page — Windows EXE of the One9 worker."""
    payload = _release_payload(request)
    # A local file or an explicit S3 URL means the button should work.
    payload["windows"]["available"] = True
    return render(request, "coworker_cloud/download.html", payload)


@require_GET
def openworker_releases(request):
    """JSON the One9 website uses for the Download Windows button."""
    return JsonResponse(_release_payload(request))


@require_GET
def download_windows(request):
    """Serve the Windows installer EXE, or redirect to the hosted S3 object."""
    local = _local_installer()
    if local:
        return FileResponse(
            local.open("rb"),
            as_attachment=True,
            filename=_filename(),
            content_type="application/octet-stream",
        )
    configured = getattr(settings, "OPENWORKER_WINDOWS_DOWNLOAD_URL", "") or ""
    if configured or not getattr(settings, "DEBUG", False):
        return redirect(_direct_url())
    return HttpResponseNotFound(
        "Windows installer is not published yet. "
        "Build with openworker/packaging/build_windows.ps1, then run "
        "python manage.py publish_openworker_windows <path-to-setup.exe>."
    )

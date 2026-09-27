"""
Azure Scanner Module
--------------------
Wraps Azure CLI calls via subprocess and parses the JSON output
into structured dictionaries suitable for cost analysis.

Windows note: az ships as a .CMD batch wrapper, which Python's
subprocess cannot launch directly (CreateProcess does not perform
PATHEXT resolution). We route through cmd.exe /c on Windows to
work around this.
"""

import json
import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional


class AzureCLIError(Exception):
    """Raised when an Azure CLI command fails."""

    def __init__(self, message: str, kind: str = "unknown"):
        super().__init__(message)
        self.kind = kind  # "not_installed", "not_logged_in", "not_found", "unknown"


def _resolve_az() -> str:
    """
    Return the full path to the az executable.

    Prefers the AZ_CLI_PATH environment variable (set in .env), then
    falls back to shutil.which. Returning an absolute path avoids
    Windows's .CMD resolution quirks inside subprocess.
    """
    explicit = os.getenv("AZ_CLI_PATH")
    if explicit and os.path.exists(explicit):
        return explicit

    found = shutil.which("az")
    if not found:
        raise AzureCLIError(
            "Azure CLI is not installed or not on PATH. "
            "Set AZ_CLI_PATH in .env or install from "
            "https://learn.microsoft.com/cli/azure/install-azure-cli",
            kind="not_installed",
        )
    return found


def _run_az(args: List[str]) -> Any:
    """Run an `az` command and return parsed JSON output."""
    az = _resolve_az()

    # On Windows, az is a .CMD file. subprocess.run() cannot launch .CMD
    # directly because CreateProcess doesn't do PATHEXT resolution. Route
    # through cmd.exe /c so the shell resolves and interprets the batch file.
    if platform.system() == "Windows":
        cmd = ["cmd.exe", "/c", az, *args]
    else:
        cmd = [az, *args]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AzureCLIError(
            f"Azure CLI executable not found at {az!r}.", kind="not_installed"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AzureCLIError(
            f"Azure CLI command timed out: az {' '.join(args)}"
        ) from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        lower = stderr.lower()
        if "az login" in lower or "not logged in" in lower:
            raise AzureCLIError(
                "You are not logged in to Azure. Run `az login` first.",
                kind="not_logged_in",
            )
        if "could not be found" in lower or "resourcegroupnotfound" in lower:
            raise AzureCLIError(stderr or "Resource group not found.", kind="not_found")
        if "subscription" in lower and "not found" in lower:
            raise AzureCLIError(
                stderr or "Azure subscription not found. Run `az login`.",
                kind="not_logged_in",
            )
        raise AzureCLIError(stderr or "Azure CLI command failed.", kind="unknown")

    try:
        return json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError as exc:
        raise AzureCLIError(
            f"Failed to parse Azure CLI JSON output: {exc}"
        ) from exc


def list_resource_groups() -> List[Dict[str, Any]]:
    """Return all Azure resource groups in the active subscription."""
    groups = _run_az(["group", "list", "-o", "json"])
    return [
        {
            "name": g.get("name"),
            "location": g.get("location"),
            "id": g.get("id"),
            "tags": g.get("tags") or {},
            "provisioning_state": g.get("properties", {}).get("provisioningState"),
        }
        for g in groups
    ]


def _extract_sku(resource: Dict[str, Any]) -> Optional[str]:
    """Pull a human-readable SKU string from various Azure shapes."""
    sku = resource.get("sku")
    if isinstance(sku, dict):
        name = sku.get("name")
        tier = sku.get("tier")
        if name and tier:
            return f"{name} ({tier})"
        return name or tier
    if isinstance(sku, str):
        return sku

    props = resource.get("properties") or {}
    hardware = props.get("hardwareProfile") or {}
    if isinstance(hardware, dict) and hardware.get("vmSize"):
        return hardware["vmSize"]

    return None


def _normalize_resource(resource: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten an Azure resource dict into our structured format."""
    return {
        "id": resource.get("id"),
        "name": resource.get("name"),
        "type": resource.get("type"),
        "location": resource.get("location"),
        "sku": _extract_sku(resource),
        "kind": resource.get("kind"),
        "tags": resource.get("tags") or {},
        "resource_group": resource.get("resourceGroup"),
    }


def list_resources(resource_group: str) -> List[Dict[str, Any]]:
    """Return all resources in a given resource group, normalized."""
    if not resource_group or not resource_group.strip():
        raise AzureCLIError("resource_group must be a non-empty string.", kind="unknown")

    raw = _run_az(
        ["resource", "list", "--resource-group", resource_group, "-o", "json"]
    )
    if not isinstance(raw, list):
        raise AzureCLIError("Unexpected response from Azure CLI.")

    return [_normalize_resource(r) for r in raw]
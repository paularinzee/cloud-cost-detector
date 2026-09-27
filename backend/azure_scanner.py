"""
Azure Scanner Module
--------------------
Wraps Azure CLI calls via subprocess and parses the JSON output
into structured dictionaries suitable for cost analysis.
"""

import json
import shutil
import subprocess
from typing import Any, Dict, List, Optional


class AzureCLIError(Exception):
    """Raised when an Azure CLI command fails."""

    def __init__(self, message: str, kind: str = "unknown"):
        super().__init__(message)
        self.kind = kind  # "not_installed", "not_logged_in", "not_found", "unknown"


def _ensure_az_installed() -> None:
    if shutil.which("az") is None:
        raise AzureCLIError(
            "Azure CLI is not installed or not on PATH. "
            "Install it from https://learn.microsoft.com/cli/azure/install-azure-cli",
            kind="not_installed",
        )


def _run_az(args: List[str]) -> Any:
    _ensure_az_installed()
    try:
        result = subprocess.run(
            ["az", *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AzureCLIError("Azure CLI executable not found.", kind="not_installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise AzureCLIError(f"Azure CLI command timed out: az {' '.join(args)}") from exc

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
        raise AzureCLIError(f"Failed to parse Azure CLI JSON output: {exc}") from exc


def list_resource_groups() -> List[Dict[str, Any]]:
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
    if not resource_group or not resource_group.strip():
        raise AzureCLIError("resource_group must be a non-empty string.", kind="unknown")
    raw = _run_az(["resource", "list", "--resource-group", resource_group, "-o", "json"])
    if not isinstance(raw, list):
        raise AzureCLIError("Unexpected response from Azure CLI.")
    return [_normalize_resource(r) for r in raw]
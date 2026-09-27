"""
AI Cost Analyzer
----------------
Takes the normalized Azure resource list (from azure_scanner) and asks
OpenAI's chat completions API (gpt-4o) to produce a structured cost
optimization report.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv()


class AIAnalyzerError(Exception):
    def __init__(self, message: str, kind: str = "unknown"):
        super().__init__(message)
        self.kind = kind  # "missing_key", "api_error", "parse_error"


SYSTEM_PROMPT = """You are an expert Azure cloud cost optimization engineer.

You will receive a JSON array of Azure resources. For EACH resource, analyze:
1. Over-provisioning — SKUs/sizes larger than a typical workload needs.
2. Unused / idle resources — orphaned disks, unattached public IPs, stopped VMs
   still billing, empty App Service Plans, idle load balancers, unused NAT gateways.
3. Misconfigurations — missing tags, wrong region, no autoscale, expensive
   redundancy settings, public exposure where not needed.
4. Wrong pricing tiers — Premium SSD where Standard would do, Premium App
   Service Plan for a low-traffic app, over-specced SQL DTUs.
5. Cost optimization opportunities — right-sizing, reserved instances,
   savings plans, spot VMs, storage lifecycle policies, shutting down off-hours.

You MUST respond with a single JSON object using exactly this schema:

{
  "summary": "<2-4 sentence overview of the resource group's cost posture>",
  "estimated_monthly_savings_usd": <number>,
  "issues": [
    {
      "resource_name": "<name>",
      "resource_type": "<azure type, e.g. Microsoft.Compute/virtualMachines>",
      "severity": "high" | "medium" | "low",
      "category": "over_provisioned" | "unused" | "misconfigured" | "wrong_tier" | "optimization",
      "title": "<short issue title>",
      "description": "<why this is a problem, 1-3 sentences>",
      "estimated_monthly_savings_usd": <number>,
      "fix_command": "<a single, runnable Azure CLI command or empty string if manual>"
    }
  ],
  "quick_wins": ["<short actionable tip>", "..."]
}

Rules:
- Every `fix_command` MUST be a valid, single-line `az ...` command where possible.
- `severity` MUST be exactly one of: "high", "medium", "low".
- `category` MUST be exactly one of the 5 values above.
- Use USD estimates; be conservative and label uncertainty in the description.
- If a resource looks fine, do not invent an issue for it.
- Output ONLY the JSON object. No markdown, no prose outside JSON.
"""


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-your-key"):
        raise AIAnalyzerError(
            "OPENAI_API_KEY is missing or not set. Add it to backend/.env.",
            kind="missing_key",
        )
    return OpenAI(api_key=api_key)


def _build_user_prompt(resource_group: str, resources: List[Dict[str, Any]]) -> str:
    trimmed = [
        {
            "name": r.get("name"),
            "type": r.get("type"),
            "location": r.get("location"),
            "sku": r.get("sku"),
            "kind": r.get("kind"),
            "tags": r.get("tags") or {},
        }
        for r in resources
    ]
    return (
        f"Resource group: {resource_group}\n"
        f"Resource count: {len(trimmed)}\n\n"
        f"Resources (JSON):\n{json.dumps(trimmed, indent=2)}\n\n"
        "Produce the cost optimization report as specified."
    )


def _empty_report(reason: str) -> Dict[str, Any]:
    return {
        "summary": reason,
        "estimated_monthly_savings_usd": 0,
        "issues": [],
        "quick_wins": [],
    }


def analyze_costs(
    resource_group: str,
    resources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not resources:
        return _empty_report(
            f"No resources found in '{resource_group}'. Nothing to analyze."
        )

    client = _get_client()
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))

    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=timeout,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(resource_group, resources)},
            ],
        )
    except OpenAIError as exc:
        raise AIAnalyzerError(f"OpenAI API call failed: {exc}", kind="api_error") from exc

    content = response.choices[0].message.content or ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIAnalyzerError(f"AI returned non-JSON content: {exc}", kind="parse_error") from exc

    return _normalize_report(parsed)


def _normalize_report(raw: Dict[str, Any]) -> Dict[str, Any]:
    valid_severity = {"high", "medium", "low"}
    valid_category = {
        "over_provisioned", "unused", "misconfigured", "wrong_tier", "optimization",
    }

    issues = []
    for item in raw.get("issues", []) or []:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "low")).lower()
        category = str(item.get("category", "optimization")).lower()
        issues.append(
            {
                "resource_name": item.get("resource_name", ""),
                "resource_type": item.get("resource_type", ""),
                "severity": severity if severity in valid_severity else "low",
                "category": category if category in valid_category else "optimization",
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "estimated_monthly_savings_usd": float(
                    item.get("estimated_monthly_savings_usd") or 0
                ),
                "fix_command": item.get("fix_command", "") or "",
            }
        )

    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: order.get(i["severity"], 3))

    total_savings = raw.get("estimated_monthly_savings_usd")
    if total_savings is None:
        total_savings = sum(i["estimated_monthly_savings_usd"] for i in issues)

    quick_wins = [
        str(w) for w in (raw.get("quick_wins") or [])
        if isinstance(w, (str, int, float))
    ]

    return {
        "summary": str(raw.get("summary") or "No summary provided."),
        "estimated_monthly_savings_usd": float(total_savings or 0),
        "issues": issues,
        "quick_wins": quick_wins,
    }
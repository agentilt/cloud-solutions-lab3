"""Parsed, validated representation of an architecture spec."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceSpec:
    """A single AWS service the generated project should provision."""

    type: str
    logical_id: str
    config: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ArchitectureSpec:
    """The full, validated input to the generator."""

    project_name: str
    pattern: str
    services: list[ServiceSpec] = field(default_factory=list)
    deployment_boundary: str = "change-set-only"
    budget_monthly_usd: float | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "ArchitectureSpec":
        """Build a spec from an already-schema-validated dict."""
        services = [
            ServiceSpec(
                type=service["type"],
                logical_id=service["logical_id"],
                config=dict(service.get("config") or {}),
            )
            for service in raw["services"]
        ]
        return cls(
            project_name=raw["project_name"],
            pattern=raw["pattern"],
            services=services,
            deployment_boundary=raw.get("deployment_boundary", "change-set-only"),
            budget_monthly_usd=raw.get("budget_monthly_usd"),
        )

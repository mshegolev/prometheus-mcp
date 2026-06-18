"""MCP tools for Alertmanager (read-only).

4 tools covering the Alertmanager API v2 surface useful for incident investigation:

- ``alertmanager_list_silences``    — list active/pending/expired silences
- ``alertmanager_list_alerts``      — list alerts with suppression state
- ``alertmanager_get_status``       — cluster status, version, config
- ``alertmanager_list_alert_groups`` — alert groups by receiver/routing
"""

from __future__ import annotations

from typing import Any

from prometheus_mcp import output
from prometheus_mcp._mcp import get_alertmanager_client, mcp
from prometheus_mcp.federation import fan_out_prometheus
from prometheus_mcp.models import (
    AMAlertGroupItem,
    AMAlertItem,
    AMAlertStatus,
    AMStatusOutput,
    ListAMAlertGroupsOutput,
    ListAMAlertsOutput,
    ListSilencesOutput,
    SilenceItem,
    SilenceMatcher,
)

_MD_ITEM_LIMIT = 20


# ── List Silences ─────────────────────────────────────────────────────────────


@mcp.tool(
    name="alertmanager_list_silences",
    annotations={
        "title": "List Silences",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def alertmanager_list_silences(
    *,
    instance: str | None = None,
    instances: list[str] | None = None,
) -> ListSilencesOutput:
    """List all silences from Alertmanager.

    Wraps ``GET /api/v2/silences``. Returns silences with matchers, status
    (active/pending/expired), creator, comment, and time bounds.

    Use this to understand which alerts are currently silenced and why.
    During incident handoffs, knowing what's silenced is critical — a
    silenced alert is invisible in Prometheus ``/alerts``.

    Examples:
        - Use when: "Is the HighCPU alert silenced?"
          → search silences for matching matchers.
        - Use when: "Who silenced alerts for the payment service?"
          → check ``createdBy`` and ``comment``.
        - Don't use when: You want active firing alerts
          (call ``alertmanager_list_alerts``).

    Returns:
        dict with ``total_count`` / ``active_count`` / ``pending_count`` /
        ``expired_count`` / ``silences`` (list with matchers, status, etc.).
    """
    try:
        from prometheus_mcp._mcp import _registry

        # Handle fan-out cases
        if instance == "all" or instances is not None:
            # Get registry from global
            registry = _registry
            if registry is None:
                return output.fail(Exception("Registry not available"), "listing Alertmanager silences")

            # Get Alertmanager clients
            if instance == "all":
                clients = registry.all_alertmanager_clients()
                # Get instance names for labeling
                instance_names = registry.list_instances()
                # Filter to only Alertmanager instances
                am_instance_names = []
                for name in instance_names:
                    try:
                        registry.get_alertmanager_client(name)
                        am_instance_names.append(name)
                    except:
                        pass
                client_names = am_instance_names
            else:
                # Subset targeting
                clients = []
                client_names = []
                if instances:
                    for inst_name in instances:
                        try:
                            client = registry.get_alertmanager_client(inst_name)
                            clients.append(client)
                            client_names.append(inst_name)
                        except Exception as e:
                            # Skip invalid instances for now - federation should handle this
                            pass

            if not clients:
                return output.fail(Exception("No Alertmanager instances available"), "listing Alertmanager silences")

            # Define query function for fan-out
            def query_func(client):
                return client.get("/silences") or []

            # Execute fan-out
            fan_out_result = fan_out_prometheus(query_func, clients, instance_names=client_names)

            # For now, return results from first successful instance
            # TODO: Implement proper merging of silences from multiple instances
            successful_instances = fan_out_result["successful_instances"]
            if successful_instances:
                # Use results from first successful instance
                raw_data = fan_out_result["data"]
                if raw_data and len(raw_data) > 0:
                    raw = raw_data[0] if isinstance(raw_data, list) else raw_data
                else:
                    raw = []
            else:
                # All instances failed
                failed_instances = fan_out_result["failed_instances"]
                if failed_instances:
                    first_error = failed_instances[0]
                    return output.fail(
                        Exception(
                            f"Alertmanager instance {first_error['instance_name']} failed: {first_error['message']}"
                        ),
                        "listing Alertmanager silences",
                    )
                else:
                    raw = []
        else:
            # Single instance case
            client = get_alertmanager_client(instance)
            raw = client.get("/silences") or []

        silences: list[SilenceItem] = []
        active = 0
        pending = 0
        expired = 0
        for s in raw:
            status_obj = s.get("status") or {}
            state = str(status_obj.get("state", ""))
            if state == "active":
                active += 1
            elif state == "pending":
                pending += 1
            elif state == "expired":
                expired += 1

            matchers: list[SilenceMatcher] = []
            for m in s.get("matchers") or []:
                matchers.append(
                    {
                        "name": str(m.get("name", "")),
                        "value": str(m.get("value", "")),
                        "isRegex": bool(m.get("isRegex", False)),
                        "isEqual": bool(m.get("isEqual", True)),
                    }
                )

            silences.append(
                {
                    "id": str(s.get("id", "")),
                    "status": state,
                    "matchers": matchers,
                    "createdBy": str(s.get("createdBy", "")),
                    "comment": str(s.get("comment", "")),
                    "startsAt": str(s.get("startsAt", "")),
                    "endsAt": str(s.get("endsAt", "")),
                    "updatedAt": str(s.get("updatedAt", "")),
                }
            )

        result: ListSilencesOutput = {
            "total_count": len(silences),
            "active_count": active,
            "pending_count": pending,
            "expired_count": expired,
            "silences": silences,
        }

        md = f"## Alertmanager Silences ({len(silences)} total)\n\n"
        md += f"- **Active:** {active}\n- **Pending:** {pending}\n- **Expired:** {expired}\n\n"

        if not silences:
            md += "_No silences found._\n"
        else:
            for s in silences[:_MD_ITEM_LIMIT]:
                matcher_str = ", ".join(f'{m["name"]}="{m["value"]}"' for m in s["matchers"])
                md += f"- **{s['status']}** `{matcher_str}` — by {s['createdBy']}: {s['comment'][:60]}\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "listing Alertmanager silences")


# ── List Alerts ───────────────────────────────────────────────────────────────


@mcp.tool(
    name="alertmanager_list_alerts",
    annotations={
        "title": "List AM Alerts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def alertmanager_list_alerts(
    *,
    instance: str | None = None,
) -> ListAMAlertsOutput:
    """List alerts from Alertmanager with suppression state.

    Wraps ``GET /api/v2/alerts``. Returns alerts with their status
    (active/suppressed/unprocessed), silence IDs, and inhibition IDs.

    Unlike ``prometheus_list_alerts``, this shows WHY an alert is or
    isn't firing — suppressed alerts include ``silencedBy`` and
    ``inhibitedBy`` arrays.

    Examples:
        - Use when: "Why isn't the HighCPU alert firing?"
          → check if it's suppressed (silencedBy or inhibitedBy).
        - Use when: "Show all suppressed alerts"
          → filter by ``status.state == 'suppressed'``.
        - Don't use when: You want Prometheus-side alert state
          (call ``prometheus_list_alerts``).

    Returns:
        dict with ``total_count`` / ``active_count`` / ``suppressed_count`` /
        ``unprocessed_count`` / ``alerts`` (list with status, silencedBy, etc.).
    """
    try:
        client = get_alertmanager_client(instance)
        raw: list[dict[str, Any]] = client.get("/alerts") or []

        alerts: list[AMAlertItem] = []
        active_count = 0
        suppressed_count = 0
        unprocessed_count = 0

        for a in raw:
            status_obj = a.get("status") or {}
            state = str(status_obj.get("state", ""))
            if state == "active":
                active_count += 1
            elif state == "suppressed":
                suppressed_count += 1
            elif state == "unprocessed":
                unprocessed_count += 1

            alert_status: AMAlertStatus = {
                "state": state,
                "silencedBy": [str(s) for s in (status_obj.get("silencedBy") or [])],
                "inhibitedBy": [str(s) for s in (status_obj.get("inhibitedBy") or [])],
            }

            alerts.append(
                {
                    "labels": {k: str(v) for k, v in (a.get("labels") or {}).items()},
                    "annotations": {k: str(v) for k, v in (a.get("annotations") or {}).items()},
                    "status": alert_status,
                    "startsAt": str(a.get("startsAt", "")),
                    "endsAt": str(a.get("endsAt", "")),
                    "generatorURL": str(a.get("generatorURL", "")),
                    "fingerprint": str(a.get("fingerprint", "")),
                }
            )

        result: ListAMAlertsOutput = {
            "total_count": len(alerts),
            "active_count": active_count,
            "suppressed_count": suppressed_count,
            "unprocessed_count": unprocessed_count,
            "alerts": alerts,
        }

        md = f"## Alertmanager Alerts ({len(alerts)} total)\n\n"
        md += f"- **Active:** {active_count}\n- **Suppressed:** {suppressed_count}\n"
        md += f"- **Unprocessed:** {unprocessed_count}\n\n"

        for a in alerts[:_MD_ITEM_LIMIT]:
            name = a["labels"].get("alertname", "(unknown)")
            state = a["status"]["state"]
            silenced = f" silenced={a['status']['silencedBy']}" if a["status"]["silencedBy"] else ""
            inhibited = f" inhibited={a['status']['inhibitedBy']}" if a["status"]["inhibitedBy"] else ""
            md += f"- **{name}** [{state}]{silenced}{inhibited}\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "listing Alertmanager alerts")


# ── Get Status ────────────────────────────────────────────────────────────────


@mcp.tool(
    name="alertmanager_get_status",
    annotations={
        "title": "AM Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def alertmanager_get_status(
    *,
    instance: str | None = None,
) -> AMStatusOutput:
    """Get Alertmanager cluster status, version, and config.

    Wraps ``GET /api/v2/status``. Returns cluster state (ready/settling),
    version info, uptime, and the raw configuration YAML.

    Examples:
        - Use when: "Is Alertmanager healthy?"
          → check ``cluster_status``.
        - Use when: "What version of Alertmanager is running?"
          → check ``version_info``.
        - Don't use when: You want to see active alerts
          (call ``alertmanager_list_alerts``).

    Returns:
        dict with ``cluster_status`` / ``version_info`` / ``uptime`` /
        ``config_yaml``.
    """
    try:
        client = get_alertmanager_client(instance)
        raw: dict[str, Any] = client.get("/status") or {}

        cluster = raw.get("cluster") or {}
        cluster_status = str(cluster.get("status", "unknown"))

        version_info: dict[str, str] = {}
        vi = raw.get("versionInfo") or {}
        for key in ("version", "revision", "branch", "buildUser", "buildDate", "goVersion"):
            version_info[key] = str(vi.get(key, ""))

        uptime = str(raw.get("uptime", ""))

        config = raw.get("config") or {}
        config_yaml = str(config.get("original", ""))

        result: AMStatusOutput = {
            "cluster_status": cluster_status,
            "version_info": version_info,
            "uptime": uptime,
            "config_yaml": config_yaml,
        }

        md = "## Alertmanager Status\n\n"
        md += f"- **Cluster:** {cluster_status}\n"
        md += f"- **Uptime:** {uptime}\n"
        if version_info.get("version"):
            md += f"- **Version:** {version_info['version']}\n"
        if config_yaml:
            md += f"\n### Config\n\n```yaml\n{config_yaml[:500]}\n```\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "fetching Alertmanager status")


# ── List Alert Groups ─────────────────────────────────────────────────────────


@mcp.tool(
    name="alertmanager_list_alert_groups",
    annotations={
        "title": "AM Alert Groups",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
    structured_output=True,
)
def alertmanager_list_alert_groups(
    *,
    instance: str | None = None,
) -> ListAMAlertGroupsOutput:
    """List alert groups from Alertmanager showing routing topology.

    Wraps ``GET /api/v2/alerts/groups``. Returns groups with their labels,
    receiver, and alert count — shows how alerts are grouped for notification.

    Examples:
        - Use when: "Why did I get one notification instead of many?"
          → check which alerts are in the same group.
        - Use when: "What receiver handles payment alerts?"
          → find the group and check its receiver.
        - Don't use when: You want individual alert details
          (call ``alertmanager_list_alerts``).

    Returns:
        dict with ``total_groups`` / ``total_alerts`` / ``groups``
        (list with ``labels``, ``receiver``, ``alert_count``).
    """
    try:
        client = get_alertmanager_client(instance)
        raw: list[dict[str, Any]] = client.get("/alerts/groups") or []

        groups: list[AMAlertGroupItem] = []
        total_alerts = 0

        for g in raw:
            alerts_list = g.get("alerts") or []
            alert_count = len(alerts_list)
            total_alerts += alert_count
            receiver = g.get("receiver") or {}
            receiver_name = str(receiver.get("name", "")) if isinstance(receiver, dict) else str(receiver)
            groups.append(
                {
                    "labels": {k: str(v) for k, v in (g.get("labels") or {}).items()},
                    "receiver": receiver_name,
                    "alert_count": alert_count,
                }
            )

        result: ListAMAlertGroupsOutput = {
            "total_groups": len(groups),
            "total_alerts": total_alerts,
            "groups": groups,
        }

        md = f"## Alert Groups ({len(groups)} groups, {total_alerts} alerts)\n\n"
        for g in groups[:_MD_ITEM_LIMIT]:
            label_str = ", ".join(f'{k}="{v}"' for k, v in g["labels"].items()) if g["labels"] else "(no labels)"
            md += f"- **{g['receiver']}** `{label_str}` — {g['alert_count']} alerts\n"

        if not groups:
            md += "_No alert groups found._\n"

        return output.ok(result, md)  # type: ignore[return-value]
    except Exception as exc:
        output.fail(exc, "listing Alertmanager alert groups")

"""Core correlation engine for cross-instance alert analysis.

Provides functionality for:
- Cross-instance alert matching using temporal windows and label similarity
- Alert grouping by service identifiers across all instances
- Cascading alert detection with directional dependency inference
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING

from prometheus_mcp.models import (
    AMAlertItem,
    AlertGroupResult,
    CascadeDetectionResult,
    CascadeRelationship,
    CorrelatedAlert,
    CorrelationGroup,
    CorrelationResult,
)

if TYPE_CHECKING:
    from prometheus_mcp.registry import InstanceRegistry

logger = logging.getLogger(__name__)


class AlertMatcher:
    """Handles temporal and similarity-based alert matching."""

    def calculate_temporal_similarity(self, alert1: AMAlertItem, alert2: AMAlertItem, window_seconds: int) -> bool:
        """Check if two alerts occurred within the temporal window.

        Args:
            alert1: First alert to compare
            alert2: Second alert to compare
            window_seconds: Time window in seconds

        Returns:
            True if alerts are within the temporal window, False otherwise
        """
        try:
            # Parse timestamps
            ts1 = datetime.fromisoformat(alert1["startsAt"].replace("Z", "+00:00"))
            ts2 = datetime.fromisoformat(alert2["startsAt"].replace("Z", "+00:00"))

            # Calculate time difference
            time_diff = abs((ts1 - ts2).total_seconds())

            return time_diff <= window_seconds
        except Exception as e:
            logger.warning(f"Error calculating temporal similarity: {e}")
            return False

    def calculate_label_similarity(self, labels1: dict[str, str], labels2: dict[str, str]) -> float:
        """Calculate similarity score between alert label sets using Jaccard index.

        Args:
            labels1: First set of labels
            labels2: Second set of labels

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not labels1 and not labels2:
            return 1.0
        if not labels1 or not labels2:
            return 0.0

        # Convert to sets of key-value pairs for comparison
        set1 = set(labels1.items())
        set2 = set(labels2.items())

        # Calculate Jaccard similarity
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        if union == 0:
            return 0.0

        return intersection / union


class AlertGrouper:
    """Groups alerts by service identifiers and relationship patterns."""

    def identify_service_identifier(self, labels: dict[str, str]) -> str:
        """Extract service identifier from alert labels.

        Args:
            labels: Alert labels dictionary

        Returns:
            Service identifier string
        """
        # Priority order for service identification
        service_keys = ["job", "service", "app", "namespace", "component"]

        for key in service_keys:
            if key in labels:
                return labels[key]

        # Fallback to instance if available
        if "instance" in labels:
            return labels["instance"]

        # Generic identifier
        return "unknown_service"

    def group_related_alerts(self, alerts: list[AMAlertItem]) -> dict[str, list[AMAlertItem]]:
        """Group alerts by service identifiers across instances.

        Args:
            alerts: List of alerts to group

        Returns:
            Dictionary mapping service identifiers to alert lists
        """
        groups = defaultdict(list)

        for alert in alerts:
            service_id = self.identify_service_identifier(alert["labels"])
            groups[service_id].append(alert)

        return dict(groups)


class CascadeDetector:
    """Detects cascading alert patterns and infers dependencies."""

    def infer_dependency_direction(self, parent_alert: AMAlertItem, child_alert: AMAlertItem) -> tuple[bool, float]:
        """Infer if parent alert caused child alert and calculate strength.

        Args:
            parent_alert: Potential parent alert
            child_alert: Potential child alert

        Returns:
            Tuple of (is_causal, strength) where is_causal indicates if
            parent likely caused child, and strength is confidence level
        """
        try:
            # Parse timestamps
            parent_ts = datetime.fromisoformat(parent_alert["startsAt"].replace("Z", "+00:00"))
            child_ts = datetime.fromisoformat(child_alert["startsAt"].replace("Z", "+00:00"))

            # Check temporal ordering (parent must come before child)
            if parent_ts >= child_ts:
                return False, 0.0

            # Calculate temporal delay
            delay = (child_ts - parent_ts).total_seconds()

            # If child fires within reasonable time window after parent, likely causal
            # Assume max reasonable delay of 10 minutes for cascade detection
            if delay <= 600 and delay > 0:
                # Strength based on proximity (closer = stronger)
                strength = max(0.1, 1.0 - (delay / 600))
                return True, strength

            return False, 0.0
        except Exception as e:
            logger.warning(f"Error inferring dependency direction: {e}")
            return False, 0.0

    def calculate_correlation_strength(self, alert1: AMAlertItem, alert2: AMAlertItem) -> float:
        """Calculate correlation strength between two alerts.

        Args:
            alert1: First alert
            alert2: Second alert

        Returns:
            Correlation strength between 0.0 and 1.0
        """
        matcher = AlertMatcher()

        # Temporal similarity (weight: 0.4)
        temporal_sim = matcher.calculate_temporal_similarity(alert1, alert2, 300)  # 5 minutes
        temporal_weight = 0.4 if temporal_sim else 0.0

        # Label similarity (weight: 0.6)
        label_sim = matcher.calculate_label_similarity(alert1["labels"], alert2["labels"])
        label_weight = label_sim * 0.6

        return temporal_weight + label_weight


class CorrelationEngine:
    """Main class for cross-instance alert correlation operations."""

    def __init__(self, registry: InstanceRegistry) -> None:
        """Initialize correlation engine with instance registry.

        Args:
            registry: Instance registry for accessing configured instances
        """
        self.registry = registry
        self.matcher = AlertMatcher()
        self.grouper = AlertGrouper()
        self.cascade_detector = CascadeDetector()

    def correlate_alerts_across_instances(
        self, temporal_window: int = 300, similarity_threshold: float = 0.7
    ) -> CorrelationResult:
        """Match alerts across instances using temporal windows and label similarity.

        Args:
            temporal_window: Time window in seconds for correlation (default: 300s)
            similarity_threshold: Minimum similarity score for correlation (default: 0.7)

        Returns:
            CorrelationResult with matched alerts and groups
        """
        # Get all Alertmanager clients
        clients = self.registry.all_alertmanager_clients()
        instance_names = self.registry.list_instances()

        # Filter to only Alertmanager instances
        am_instance_names = []
        for name in instance_names:
            try:
                self.registry.get_alertmanager_client(name)
                am_instance_names.append(name)
            except:
                pass

        # Collect alerts from all instances
        all_alerts_with_instances = []
        instance_attribution = defaultdict(int)

        for i, client in enumerate(clients):
            if i < len(am_instance_names):
                instance_name = am_instance_names[i]
                try:
                    # Get alerts from this instance
                    raw_alerts = client.get("/alerts") or []
                    alerts = []
                    for a in raw_alerts:
                        alert_item: AMAlertItem = {
                            "labels": {k: str(v) for k, v in (a.get("labels") or {}).items()},
                            "annotations": {k: str(v) for k, v in (a.get("annotations") or {}).items()},
                            "status": {
                                "state": str(a.get("status", {}).get("state", "")),
                                "silencedBy": [str(s) for s in (a.get("status", {}).get("silencedBy") or [])],
                                "inhibitedBy": [str(s) for s in (a.get("status", {}).get("inhibitedBy") or [])],
                            },
                            "startsAt": str(a.get("startsAt", "")),
                            "endsAt": str(a.get("endsAt", "")),
                            "generatorURL": str(a.get("generatorURL", "")),
                            "fingerprint": str(a.get("fingerprint", "")),
                        }
                        alerts.append(alert_item)

                    # Add instance attribution
                    for alert in alerts:
                        all_alerts_with_instances.append((alert, instance_name))
                        instance_attribution[instance_name] += 1

                except Exception as e:
                    logger.warning(f"Failed to fetch alerts from instance {instance_name}: {e}")
                    continue

        # Extract alerts for correlation
        alerts = [alert for alert, _ in all_alerts_with_instances]

        # Perform correlation
        correlated_alerts = []
        correlation_groups = []

        # Compare all pairs of alerts
        for i, (alert1, instance1) in enumerate(all_alerts_with_instances):
            for j, (alert2, instance2) in enumerate(all_alerts_with_instances):
                if i >= j:  # Avoid duplicate comparisons and self-comparison
                    continue

                # Check temporal similarity
                if not self.matcher.calculate_temporal_similarity(alert1, alert2, temporal_window):
                    continue

                # Calculate label similarity
                similarity = self.matcher.calculate_label_similarity(alert1["labels"], alert2["labels"])

                # If similarity meets threshold, consider correlated
                if similarity >= similarity_threshold:
                    # Add both alerts as correlated
                    correlated_alerts.extend(
                        [
                            {"alert": alert1, "instance": instance1, "correlation_score": similarity},
                            {"alert": alert2, "instance": instance2, "correlation_score": similarity},
                        ]
                    )

                    # Create correlation group
                    service_id1 = self.grouper.identify_service_identifier(alert1["labels"])
                    service_id2 = self.grouper.identify_service_identifier(alert2["labels"])

                    # Group by common service identifier or create combined group
                    group_service_id = service_id1 if service_id1 == service_id2 else f"{service_id1}_{service_id2}"

                    correlation_groups.append(
                        {
                            "group_id": f"group_{len(correlation_groups)}",
                            "alerts": [
                                {"alert": alert1, "instance": instance1, "correlation_score": similarity},
                                {"alert": alert2, "instance": instance2, "correlation_score": similarity},
                            ],
                            "service_identifier": group_service_id,
                            "correlation_strength": similarity,
                        }
                    )

        # Detect cascades
        cascades = []
        for i, (alert1, instance1) in enumerate(all_alerts_with_instances):
            for j, (alert2, instance2) in enumerate(all_alerts_with_instances):
                if i == j:  # Skip self-comparison
                    continue

                is_causal, strength = self.cascade_detector.infer_dependency_direction(alert1, alert2)
                if is_causal and strength > 0.3:  # Minimum strength threshold
                    try:
                        ts1 = datetime.fromisoformat(alert1["startsAt"].replace("Z", "+00:00"))
                        ts2 = datetime.fromisoformat(alert2["startsAt"].replace("Z", "+00:00"))
                        delay = (ts2 - ts1).total_seconds()

                        cascades.append(
                            {
                                "parent": {"alert": alert1, "instance": instance1, "correlation_score": strength},
                                "child": {"alert": alert2, "instance": instance2, "correlation_score": strength},
                                "dependency_strength": strength,
                                "temporal_delay": delay,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Error creating cascade relationship: {e}")
                        continue

        return {
            "total_correlations": len(correlated_alerts) // 2,  # Each pair counted twice
            "correlated_alerts": correlated_alerts,
            "groups": correlation_groups,
            "cascades": cascades,
            "instance_attribution": dict(instance_attribution),
            "rca_enhancement": None,  # Placeholder for RCA enhancement
        }

    def group_alerts_by_service(self, alerts: list[AMAlertItem]) -> AlertGroupResult:
        """Cluster related alerts by service identifiers across all instances.

        Args:
            alerts: List of alerts to group by service

        Returns:
            AlertGroupResult with grouped alerts
        """
        groups = self.grouper.group_related_alerts(alerts)

        # Count ungrouped alerts (those with "unknown_service")
        ungrouped_count = len(groups.get("unknown_service", []))
        if "unknown_service" in groups and not groups["unknown_service"]:
            del groups["unknown_service"]

        return {
            "total_groups": len(groups),
            "groups": groups,
            "ungrouped_count": ungrouped_count,
            "rca_enhancement": None,
        }

    def detect_cascading_alerts(self, alerts: list[AMAlertItem], temporal_window: int = 300) -> CascadeDetectionResult:
        """Detect cascading alert patterns with directional dependency inference.

        Args:
            alerts: List of alerts to analyze for cascading patterns
            temporal_window: Time window in seconds for cascade detection (default: 300s)

        Returns:
            CascadeDetectionResult with detected cascades and root causes
        """
        cascades = []
        root_causes = []

        # Check all pairs for cascade relationships
        for i, alert1 in enumerate(alerts):
            for j, alert2 in enumerate(alerts):
                if i == j:  # Skip self-comparison
                    continue

                is_causal, strength = self.cascade_detector.infer_dependency_direction(alert1, alert2)
                if is_causal and strength > 0.3:  # Minimum strength threshold
                    try:
                        ts1 = datetime.fromisoformat(alert1["startsAt"].replace("Z", "+00:00"))
                        ts2 = datetime.fromisoformat(alert2["startsAt"].replace("Z", "+00:00"))
                        delay = (ts2 - ts1).total_seconds()

                        cascade = {
                            "parent": {
                                "alert": alert1,
                                "instance": alert1["labels"].get("__prometheus_instance__", "unknown"),
                                "correlation_score": strength,
                            },
                            "child": {
                                "alert": alert2,
                                "instance": alert2["labels"].get("__prometheus_instance__", "unknown"),
                                "correlation_score": strength,
                            },
                            "dependency_strength": strength,
                            "temporal_delay": delay,
                        }

                        cascades.append(cascade)

                        # Add parent as potential root cause if not already in cascades as child
                        is_child = False
                        for existing_cascade in cascades:
                            if existing_cascade["parent"]["alert"] == alert1:
                                is_child = True
                                break

                        if not is_child:
                            root_causes.append(
                                {
                                    "alert": alert1,
                                    "instance": alert1["labels"].get("__prometheus_instance__", "unknown"),
                                    "correlation_score": strength,
                                }
                            )

                    except Exception as e:
                        logger.warning(f"Error creating cascade relationship: {e}")
                        continue

        return {
            "total_cascades": len(cascades),
            "cascades": cascades,
            "root_causes": root_causes,
            "rca_enhancement": None,
        }

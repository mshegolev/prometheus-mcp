# Evaluation suite

This repository ships a 10-question evaluation (`evaluation.xml`) built per the
mcp-builder Phase 4 specification. The suite measures whether an LLM can
productively use prometheus-mcp to answer realistic, read-only questions about
metrics, alerts, and scrape targets.

## Design principles

Every question is **read-only, independent, stable, verifiable, complex, and
instance-agnostic** — same principles as sonarqube-mcp's template. Since
prometheus-mcp wraps a customer-owned Prometheus instance, no pre-solved answer
shared fixture exists. The suite ships with `__VERIFY_ON_INSTANCE__` placeholders.

## Filling in answers

1. Pick a target Prometheus (self-hosted, or the public demo at https://demo.promlabs.com).
2. Export env vars:
   ```bash
   export PROMETHEUS_URL=https://prometheus.example.com
   # optional: export PROMETHEUS_TOKEN=... / PROMETHEUS_USERNAME / PROMETHEUS_PASSWORD
   ```
3. Solve each question manually — fastest path is to run Claude Code with this
   MCP configured and ask the question verbatim.
4. Replace the placeholder with the verified value.
5. Narrow each question to target one specific entity for stability (e.g.
   replace "first metric" with a specific metric name on your instance).

## Running the harness

```bash
python scripts/evaluation.py \
  -t stdio \
  -c uvx \
  -a prometheus-mcp \
  -e PROMETHEUS_URL=$PROMETHEUS_URL \
  -e PROMETHEUS_TOKEN=$PROMETHEUS_TOKEN \
  -o evaluation_report.md \
  evaluation.xml
```

Low-accuracy questions usually signal one of:

- Tool description is ambiguous → tighten in `tools.py`.
- Output schema is under/over-specified → adjust TypedDict in `models.py`.
- Question itself is ambiguous on your instance → rephrase.

## Design deviations

Same honest compromise as sonarqube-mcp and jaeger-mcp: question *structure*
is fixed (validates the MCP design), *values* come from whichever Prometheus
you verify against. A shared fixture would require standing up a demo Prometheus
with pinned metrics — out of scope for v0.1.0.

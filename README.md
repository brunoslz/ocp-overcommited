# OpenShift Cluster Resource Monitor

🤖 **AI-powered monitoring tool for detecting resource overcommitment in OpenShift/Kubernetes clusters**

## Overview

This tool helps cluster operators quickly identify nodes that are overcommitted (where pod resource requests exceed allocatable capacity). It uses Claude AI to provide intelligent analysis and actionable recommendations.

### Key Features

- 📊 **Real-time cluster analysis** - Scans all nodes and pods in seconds
- 🎯 **Overcommit detection** - Identifies nodes exceeding capacity thresholds
- 🤖 **AI-powered insights** - Claude analyzes metrics and suggests actions
- 🎨 **Beautiful terminal output** - Color-coded status with visual indicators
- 📈 **Risk scoring** - Quantifies cluster health (0-100 scale)
- 🔧 **Flexible thresholds** - Customizable warning/critical levels
- 📤 **Multiple outputs** - Terminal display or JSON for automation

## Quick Start

### Prerequisites

- Python 3.9 or higher
- OpenShift CLI (`oc`) or Kubernetes CLI (`kubectl`)
- Access to an OpenShift/Kubernetes cluster
- Anthropic API key (for AI analysis)

### Installation

1. **Clone or download the files:**
   ```bash
   cd /home/brunoslz/GIT-REPOS/ocp-overcommited
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your Anthropic API key:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API key
   export ANTHROPIC_API_KEY="your_api_key_here"
   ```

4. **Make the script executable:**
   ```bash
   chmod +x oc_monitor.py
   ```

### Basic Usage

```bash
# Run with current cluster context
python oc_monitor.py

# Use specific context
python oc_monitor.py --context production-cluster

# Skip AI analysis
python oc_monitor.py --no-ai

# Output JSON for scripting
python oc_monitor.py -o json

# Verbose mode for debugging
python oc_monitor.py -vv
```

## Usage Examples

### Example 1: Quick Health Check

```bash
python oc_monitor.py
```

**Output:**
```
======================================================================
       OpenShift Cluster Resource Monitor (AI-Powered)
======================================================================

📊 CLUSTER SUMMARY
──────────────────────────────────────────────────────────────────
Total Nodes:           12
Overcommitted:         2  🔴
Warning State:         3  🟡
Healthy:              7  🟢
Overall Risk Score:   67/100

📋 NODE DETAILS
──────────────────────────────────────────────────────────────────
Node Name              CPU Usage       Memory Usage      Status           Pods
worker-1               ████████  95.0% ████████  92.0%  🔴 OVERCOMMITTED   87
worker-2               ███████░  88.0% ██████░░  78.0%  🟡 WARNING         72
master-1               ███░░░░░  45.0% ████░░░░  52.0%  🟢 HEALTHY         34
...

🤖 AI ANALYSIS (Claude Sonnet 4.5)
──────────────────────────────────────────────────────────────────

CRITICAL ISSUES:
• worker-1 and worker-5 are overcommitted (>100% CPU requests)
• High memory pressure on worker nodes
• Risk of pod evictions during traffic spikes

RISK ASSESSMENT:
• IMMEDIATE: worker-1 could reject new pods
• SHORT-TERM: Zone imbalance may cause cascading failures
• LONG-TERM: Insufficient headroom for cluster upgrades

RECOMMENDATIONS (PRIORITIZED):
1. [HIGH] Add 2 worker nodes or migrate workloads from worker-1
2. [HIGH] Review large deployments: app-backend (12 pods, 24 cores)
3. [MED] Implement pod disruption budgets for critical apps
4. [LOW] Balance workloads across availability zones

PATTERNS DETECTED:
• Namespace "production" accounts for 65% of cluster requests
• Most pods lack memory limits (risk of OOM kills)

──────────────────────────────────────────────────────────────────
✅ Analysis complete.
```

### Example 2: Custom Thresholds

```bash
# Lower warning threshold to 80% instead of 85%
python oc_monitor.py --threshold-warning 0.80 --threshold-critical 0.95
```

### Example 3: JSON Output for Automation

```bash
python oc_monitor.py -o json | jq '.cluster_summary'
```

**Output:**
```json
{
  "total_nodes": 12,
  "overcommitted_count": 2,
  "warning_count": 3,
  "healthy_count": 7,
  "cluster_risk_score": 67.2
}
```

### Example 4: Different CLI Tool

```bash
# Use kubectl instead of oc
python oc_monitor.py --cli-tool kubectl
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--context TEXT` | Kubernetes context to use | Current context |
| `-o, --output [terminal\|json]` | Output format | `terminal` |
| `--threshold-warning FLOAT` | Warning threshold (0-1) | `0.85` |
| `--threshold-critical FLOAT` | Critical threshold (0-1) | `1.0` |
| `--ai / --no-ai` | Enable/disable AI analysis | `--ai` |
| `--api-key TEXT` | Anthropic API key | `$ANTHROPIC_API_KEY` |
| `-v, --verbose` | Verbose output (use -vv for debug) | Off |
| `--cli-tool [oc\|kubectl]` | CLI tool to use | `oc` |
| `--help` | Show help message | - |

## Understanding the Output

### Status Indicators

- 🟢 **HEALTHY** - Resource requests ≤ 85% of allocatable capacity
- 🟡 **WARNING** - Resource requests > 85% but ≤ 100%
- 🔴 **OVERCOMMITTED** - Resource requests > 100% of allocatable capacity

### Risk Score

- **0-40**: Low risk - Cluster has ample headroom
- **41-70**: Medium risk - Monitor and plan capacity
- **71-100**: High risk - Immediate action recommended

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All nodes healthy |
| `1` | Some nodes in WARNING state |
| `2` | Some nodes OVERCOMMITTED |
| `3` | CLI tool not found |
| `4` | Cluster connection error |
| `5` | Insufficient permissions |
| `6` | General monitor error |

## How It Works

1. **Data Collection**
   - Executes `oc get nodes -o json` to fetch node capacity
   - Executes `oc get pods -A -o json` to fetch all pod resources
   - Aggregates pod requests/limits by node

2. **Analysis**
   - Calculates request/allocatable ratios for CPU and memory
   - Classifies nodes as HEALTHY, WARNING, or OVERCOMMITTED
   - Computes cluster-wide risk score

3. **AI Enhancement**
   - Sends structured metrics to Claude AI
   - Receives contextualized analysis and recommendations
   - Identifies patterns and prioritizes actions

4. **Presentation**
   - Renders color-coded terminal output
   - Or exports JSON for downstream processing

## Configuration

### Environment Variables

Create a `.env` file in the same directory:

```bash
# Required for AI analysis
ANTHROPIC_API_KEY=sk-ant-api03-...

# Optional: Default CLI tool
CLI_TOOL=oc
```

Load with:
```bash
source .env
python oc_monitor.py
```

### Customizing Thresholds

Adjust thresholds based on your cluster's workload patterns:

```bash
# Conservative (flag issues earlier)
python oc_monitor.py --threshold-warning 0.70 --threshold-critical 0.90

# Aggressive (tolerate higher utilization)
python oc_monitor.py --threshold-warning 0.90 --threshold-critical 1.10
```

## Testing

Run the unit tests to verify functionality:

```bash
# Install pytest
pip install pytest

# Run tests
python -m pytest test_monitor.py -v
```

**Expected output:**
```
test_monitor.py::test_cpu_parsing_millicores PASSED
test_monitor.py::test_memory_parsing_binary PASSED
test_monitor.py::test_node_status_healthy PASSED
test_monitor.py::test_detect_overcommitment PASSED
...
========================= 15 passed =========================
```

## Troubleshooting

### "CLI tool not found"

**Problem:** `oc` or `kubectl` is not installed or not in PATH.

**Solution:**
```bash
# Install OpenShift CLI
# https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html

# Or use kubectl instead
python oc_monitor.py --cli-tool kubectl
```

### "Cannot connect to cluster"

**Problem:** Not authenticated to cluster.

**Solution:**
```bash
# For OpenShift
oc login https://api.your-cluster.com

# For Kubernetes
kubectl config use-context your-context

# Verify connection
oc whoami
```

### "AI analysis skipped"

**Problem:** `ANTHROPIC_API_KEY` not set.

**Solution:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

Or run without AI:
```bash
python oc_monitor.py --no-ai
```

### "Insufficient permissions"

**Problem:** User lacks RBAC permissions to list nodes/pods.

**Solution:**
```bash
# You need at least these permissions:
# - nodes: get, list
# - pods: get, list (cluster-wide)

# Check current permissions
oc auth can-i list nodes
oc auth can-i list pods --all-namespaces
```

## Advanced Usage

### Scheduled Monitoring

Run as a cron job to monitor clusters periodically:

```bash
# Add to crontab
0 */6 * * * cd /path/to/oc-monitor && python oc_monitor.py -o json >> /var/log/cluster-monitor.log 2>&1
```

### Integration with Alerting

Combine with alerting tools:

```bash
#!/bin/bash
# alert-on-overcommit.sh

python oc_monitor.py -o json > /tmp/cluster-status.json
EXIT_CODE=$?

if [ $EXIT_CODE -eq 2 ]; then
    # Overcommitment detected - send alert
    cat /tmp/cluster-status.json | mail -s "Cluster Overcommit Alert" ops@example.com
fi
```

### Multi-Cluster Monitoring

Monitor multiple clusters:

```bash
#!/bin/bash
# monitor-all-clusters.sh

for context in prod-us-east prod-eu-west staging; do
    echo "=== Checking $context ==="
    python oc_monitor.py --context $context --no-ai
    echo
done
```

## Architecture

**Single-file design** for simplicity:

```
oc_monitor.py (~ 700 lines)
├── Custom Exceptions
├── Data Classes (NodeMetrics, ResourceMetrics)
├── Helper Functions (parsing, formatting)
├── CLI Execution (run_oc_command)
├── Data Collection (collect_cluster_data)
├── Overcommit Detection (detect_overcommitment)
├── AI Analysis (analyze_with_claude)
├── Terminal Rendering (render_*)
└── CLI Interface (Click framework)
```

## Dependencies

- **anthropic** - Claude AI SDK
- **click** - CLI framework
- **colorama** - Cross-platform colored output
- **pyyaml** - YAML parsing (for oc output)
- **tabulate** - Table formatting

## Security Considerations

- **API keys**: Never commit `.env` files. Use environment variables.
- **Permissions**: Tool requires read-only cluster access (nodes, pods).
- **Data privacy**: Metrics sent to Claude do not include secret data.
- **Audit**: All oc/kubectl commands are logged in verbose mode (`-vv`).

## Performance

- **Small clusters** (< 20 nodes): < 10 seconds
- **Medium clusters** (20-100 nodes): 10-20 seconds
- **Large clusters** (100+ nodes): 20-30 seconds

AI analysis adds 5-15 seconds depending on Claude API response time.

## Contributing

Found a bug or have a feature request? Please:

1. Check existing issues
2. Test with verbose mode (`-vv`)
3. Include cluster size and output format
4. Share sanitized JSON output if possible

## License

This tool is provided as-is for monitoring OpenShift/Kubernetes clusters.

## Support

For questions or issues:
- Run with `-vv` for detailed debug output
- Check OpenShift/Kubernetes connection: `oc whoami`
- Verify API key: `echo $ANTHROPIC_API_KEY`
- Review test suite: `pytest test_monitor.py -v`

---

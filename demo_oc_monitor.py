#!/usr/bin/env python3
"""
Demo script for oc_monitor.py
Simulates a cluster with sample data to demonstrate the monitor's capabilities
"""

import json
import sys
from oc_monitor import (
    NodeMetrics,
    ResourceMetrics,
    detect_overcommitment,
    render_header,
    render_summary,
    render_node_table,
    render_footer,
    colorama_init
)

def create_sample_cluster():
    """Create sample cluster data for demonstration"""

    # Create nodes with different status levels
    nodes = [
        # OVERCOMMITTED nodes (critical)
        NodeMetrics(
            name="worker-node-1",
            cpu=ResourceMetrics(allocatable=8.0, requests=9.5, limits=16.0),
            memory=ResourceMetrics(allocatable=32.0, requests=30.0, limits=48.0),
            pod_count=87
        ),
        NodeMetrics(
            name="worker-node-5",
            cpu=ResourceMetrics(allocatable=16.0, requests=18.2, limits=32.0),
            memory=ResourceMetrics(allocatable=64.0, requests=58.0, limits=80.0),
            pod_count=110
        ),

        # WARNING nodes
        NodeMetrics(
            name="worker-node-2",
            cpu=ResourceMetrics(allocatable=8.0, requests=7.2, limits=12.0),
            memory=ResourceMetrics(allocatable=32.0, requests=25.0, limits=40.0),
            pod_count=72
        ),
        NodeMetrics(
            name="worker-node-3",
            cpu=ResourceMetrics(allocatable=8.0, requests=7.0, limits=14.0),
            memory=ResourceMetrics(allocatable=32.0, requests=28.0, limits=32.0),
            pod_count=68
        ),
        NodeMetrics(
            name="worker-node-6",
            cpu=ResourceMetrics(allocatable=16.0, requests=14.5, limits=24.0),
            memory=ResourceMetrics(allocatable=64.0, requests=52.0, limits=72.0),
            pod_count=95
        ),

        # HEALTHY nodes
        NodeMetrics(
            name="master-node-1",
            cpu=ResourceMetrics(allocatable=4.0, requests=1.8, limits=4.0),
            memory=ResourceMetrics(allocatable=16.0, requests=8.5, limits=16.0),
            pod_count=34
        ),
        NodeMetrics(
            name="master-node-2",
            cpu=ResourceMetrics(allocatable=4.0, requests=2.1, limits=4.0),
            memory=ResourceMetrics(allocatable=16.0, requests=9.2, limits=16.0),
            pod_count=38
        ),
        NodeMetrics(
            name="master-node-3",
            cpu=ResourceMetrics(allocatable=4.0, requests=1.9, limits=4.0),
            memory=ResourceMetrics(allocatable=16.0, requests=8.8, limits=16.0),
            pod_count=36
        ),
        NodeMetrics(
            name="worker-node-4",
            cpu=ResourceMetrics(allocatable=8.0, requests=4.5, limits=10.0),
            memory=ResourceMetrics(allocatable=32.0, requests=18.0, limits=28.0),
            pod_count=52
        ),
        NodeMetrics(
            name="worker-node-7",
            cpu=ResourceMetrics(allocatable=16.0, requests=9.0, limits=20.0),
            memory=ResourceMetrics(allocatable=64.0, requests=35.0, limits=55.0),
            pod_count=65
        ),
        NodeMetrics(
            name="worker-node-8",
            cpu=ResourceMetrics(allocatable=16.0, requests=8.5, limits=18.0),
            memory=ResourceMetrics(allocatable=64.0, requests=32.0, limits=50.0),
            pod_count=58
        ),
        NodeMetrics(
            name="infra-node-1",
            cpu=ResourceMetrics(allocatable=8.0, requests=3.2, limits=8.0),
            memory=ResourceMetrics(allocatable=32.0, requests=16.0, limits=28.0),
            pod_count=42
        ),
    ]

    return nodes


def generate_ai_analysis_sample():
    """Generate sample AI analysis for demo"""

    return """
CRITICAL ISSUES:
• worker-node-1 and worker-node-5 are severely overcommitted (>100% CPU and memory requests)
• worker-node-1 has 118% CPU allocation - immediate risk of pod scheduling failures
• worker-node-5 at 113% CPU - hitting pod limits (110 pods vs typical 110 max)
• Combined overcommit represents 23% of total worker capacity

RISK ASSESSMENT:
• IMMEDIATE: New pod deployments will fail on overcommitted nodes
  - worker-node-1 cannot accept additional workloads
  - worker-node-5 at pod count limit

• SHORT-TERM (24-48h):
  - High risk of pod evictions during memory pressure events
  - CPU throttling likely affecting application performance
  - No headroom for traffic spikes or autoscaling events

• MEDIUM-TERM (1-2 weeks):
  - Cluster upgrade path blocked (need 20% headroom minimum)
  - Risk of cascading failures if any node goes down
  - Worker nodes in WARNING state approaching critical thresholds

RECOMMENDATIONS (PRIORITIZED):

[CRITICAL - Next 4 hours]
1. Add 2 new worker nodes (16 core, 64GB each) to absorb overcommit
2. Drain and evacuate worker-node-1 for rebalancing
   - Use: oc adm drain worker-node-1 --ignore-daemonsets
3. Implement pod disruption budgets for critical workloads before rebalancing

[HIGH - Next 24 hours]
4. Review top resource consumers and right-size requests:
   - Identify pods with >2 core requests per container
   - Check for over-provisioned databases and caching layers
5. Enable vertical pod autoscaler (VPA) for recommendation mode
6. Set resource quotas on high-usage namespaces to prevent future overcommit

[MEDIUM - Next week]
7. Implement horizontal pod autoscaler (HPA) with proper min/max replicas
8. Balance pod distribution across availability zones
9. Review and adjust QoS classes (Guaranteed vs Burstable)
10. Set up monitoring alerts for >80% node utilization

[LOW - Next month]
11. Consider cluster expansion strategy (current 12 nodes → 16 nodes)
12. Evaluate workload consolidation on infra nodes
13. Implement resource consumption dashboards for teams

PATTERNS DETECTED:

• Node Sizing Imbalance:
  - Worker nodes have mixed capacity (8 core vs 16 core)
  - Consider standardizing on 16 core workers for predictability

• Master Nodes Healthy:
  - All 3 masters well within limits (45-52% utilization)
  - Good separation of control plane from workload nodes

• Large Pod Deployments:
  - worker-node-5 running 110 pods (at max capacity)
  - worker-node-1 with 87 pods + overcommit = resource contention

• Resource Request Patterns:
  - Average CPU request: 0.75 cores per pod
  - Average memory request: 2.5 GB per pod
  - High variation suggests inconsistent sizing practices

• Missing Resource Limits:
  - Limit-to-request ratio varies significantly
  - Some nodes show limits at 2x requests (risky for memory)
  - Recommend enforcing limit ranges at namespace level

IMMEDIATE ACTION SCRIPT:

```bash
# 1. Add capacity immediately
oc scale machineset worker-machine-set --replicas=14

# 2. Cordon overcommitted nodes
oc adm cordon worker-node-1 worker-node-5

# 3. Wait for new nodes (5-10 minutes)
watch oc get nodes

# 4. Gracefully drain when new capacity available
oc adm drain worker-node-1 --ignore-daemonsets --delete-emptydir-data

# 5. Monitor pod rescheduling
oc get pods -A --field-selector spec.nodeName=worker-node-1
```

MONITORING THRESHOLDS:
Consider adjusting your monitoring to alert on:
- CPU requests > 85% (WARNING)
- CPU requests > 95% (CRITICAL)
- Memory requests > 90% (WARNING)
- Memory requests > 98% (CRITICAL)
- Pod count > 90% of max (WARNING)
"""


def main():
    """Run the demo"""

    # Initialize colorama
    colorama_init(autoreset=True)

    print("\n" + "="*70)
    print("DEMO MODE - Simulated OpenShift Cluster")
    print("="*70 + "\n")

    # Create sample cluster
    nodes = create_sample_cluster()

    # Analyze
    analysis_data = detect_overcommitment(nodes)

    # Render terminal output
    render_header()
    render_summary(analysis_data)
    render_node_table(nodes)

    # Show AI analysis sample
    from colorama import Fore, Style
    print(f"{Fore.WHITE}🤖 AI ANALYSIS (Claude Sonnet 4.5) - DEMO{Style.RESET_ALL}")
    print("─" * 70)
    print(generate_ai_analysis_sample().strip())
    print()

    render_footer(success=len(analysis_data['overcommitted']) == 0)

    # Also show JSON output
    print("\n" + "="*70)
    print("JSON OUTPUT (for automation)")
    print("="*70 + "\n")

    json_output = {
        'cluster_summary': {
            'total_nodes': analysis_data['total_nodes'],
            'overcommitted_count': len(analysis_data['overcommitted']),
            'warning_count': len(analysis_data['warning']),
            'healthy_count': len(analysis_data['healthy']),
            'cluster_risk_score': analysis_data['cluster_risk']
        },
        'nodes': [
            {
                'name': n.name,
                'status': n.status.value,
                'cpu_request_ratio': round(n.cpu.request_ratio, 3),
                'memory_request_ratio': round(n.memory.request_ratio, 3),
                'pod_count': n.pod_count,
                'risk_score': round(n.risk_score, 1)
            }
            for n in sorted(nodes, key=lambda x: x.risk_score, reverse=True)
        ]
    }

    print(json.dumps(json_output, indent=2))

    # Exit code based on status
    if analysis_data['overcommitted']:
        sys.exit(2)
    elif analysis_data['warning']:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()

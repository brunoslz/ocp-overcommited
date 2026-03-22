#!/usr/bin/env python3
"""
OpenShift/Kubernetes Cluster Resource Monitor
AI-powered overcommit detection and analysis tool
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional, Tuple

import click
from colorama import Fore, Style, init as colorama_init
from tabulate import tabulate
import anthropic


# ============================================================================
# Custom Exceptions
# ============================================================================

class MonitorError(Exception):
    """Base exception for monitor errors"""
    pass


class CLIToolNotFoundError(MonitorError):
    """oc/kubectl not in PATH"""
    pass


class ClusterConnectionError(MonitorError):
    """Cannot connect to cluster"""
    pass


class APIKeyMissingError(MonitorError):
    """Anthropic API key not provided"""
    pass


class InsufficientPermissionsError(MonitorError):
    """User lacks required RBAC permissions"""
    pass


# ============================================================================
# Data Classes and Enums
# ============================================================================

class NodeStatus(Enum):
    """Node resource status classification"""
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    OVERCOMMITTED = "OVERCOMMITTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ResourceMetrics:
    """Resource metrics for CPU or Memory"""
    allocatable: float
    requests: float
    limits: float

    @property
    def request_ratio(self) -> float:
        """Calculate request/allocatable ratio"""
        return (self.requests / self.allocatable) if self.allocatable > 0 else 0

    @property
    def limit_ratio(self) -> float:
        """Calculate limit/allocatable ratio"""
        return (self.limits / self.allocatable) if self.allocatable > 0 else 0

    @property
    def request_percentage(self) -> float:
        """Get request ratio as percentage"""
        return self.request_ratio * 100


@dataclass
class NodeMetrics:
    """Complete metrics for a single node"""
    name: str
    cpu: ResourceMetrics
    memory: ResourceMetrics
    pod_count: int

    @property
    def status(self) -> NodeStatus:
        """Determine node status based on resource utilization"""
        max_request_ratio = max(
            self.cpu.request_ratio,
            self.memory.request_ratio
        )

        if max_request_ratio > 1.0:
            return NodeStatus.OVERCOMMITTED
        elif max_request_ratio > 0.85:
            return NodeStatus.WARNING
        else:
            return NodeStatus.HEALTHY

    @property
    def risk_score(self) -> float:
        """Calculate risk score (0-100)"""
        cpu_score = self.cpu.request_ratio * 50
        memory_score = self.memory.request_ratio * 50
        return min(cpu_score + memory_score, 100)


# ============================================================================
# Helper Functions
# ============================================================================

def parse_resource_quantity(quantity: str) -> float:
    """
    Convert Kubernetes resource quantities to standard units.

    CPU: "2000m" -> 2.0 cores, "500m" -> 0.5 cores
    Memory: "2Gi" -> 2147483648 bytes, "512Mi" -> 536870912 bytes
    """
    if not quantity:
        return 0.0

    quantity = str(quantity).strip()

    # Handle CPU millicores
    if quantity.endswith('m'):
        return float(quantity[:-1]) / 1000

    # Memory units (binary: Ki, Mi, Gi, Ti; decimal: K, M, G, T)
    units = {
        'Ki': 1024,
        'Mi': 1024**2,
        'Gi': 1024**3,
        'Ti': 1024**4,
        'K': 1000,
        'M': 1000**2,
        'G': 1000**3,
        'T': 1000**4,
    }

    for suffix, multiplier in units.items():
        if quantity.endswith(suffix):
            return float(quantity[:-len(suffix)]) * multiplier

    # Plain number (cores for CPU, bytes for memory)
    try:
        return float(quantity)
    except ValueError:
        return 0.0


def format_bytes(bytes_value: float) -> str:
    """Format bytes to human-readable format (GiB)"""
    gib = bytes_value / (1024**3)
    return f"{gib:.1f}Gi"


def format_cores(cores: float) -> str:
    """Format CPU cores to readable format"""
    return f"{cores:.1f}"


def create_progress_bar(ratio: float, width: int = 8) -> str:
    """Create a text-based progress bar"""
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return bar


def get_status_color(status: NodeStatus) -> str:
    """Get colorama color for node status"""
    colors = {
        NodeStatus.HEALTHY: Fore.GREEN,
        NodeStatus.WARNING: Fore.YELLOW,
        NodeStatus.OVERCOMMITTED: Fore.RED,
        NodeStatus.UNKNOWN: Fore.WHITE,
    }
    return colors.get(status, Fore.WHITE)


def get_status_emoji(status: NodeStatus) -> str:
    """Get emoji for node status"""
    emojis = {
        NodeStatus.HEALTHY: "🟢",
        NodeStatus.WARNING: "🟡",
        NodeStatus.OVERCOMMITTED: "🔴",
        NodeStatus.UNKNOWN: "⚪",
    }
    return emojis.get(status, "⚪")


# ============================================================================
# CLI Command Execution
# ============================================================================

def run_oc_command(command: str, verbose: int = 0) -> str:
    """
    Execute oc/kubectl command and return output.

    Args:
        command: Full command to execute
        verbose: Verbosity level (0=quiet, 1=info, 2=debug)

    Returns:
        Command output as string

    Raises:
        CLIToolNotFoundError: Command not found
        ClusterConnectionError: Failed to connect to cluster
    """
    if verbose >= 2:
        click.echo(f"[DEBUG] Executing: {command}", err=True)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip()

            # Check for specific error conditions
            if "command not found" in error_msg.lower():
                raise CLIToolNotFoundError(f"CLI tool not found. Please install OpenShift or Kubernetes CLI.")
            elif "unable to connect" in error_msg.lower() or "connection refused" in error_msg.lower():
                raise ClusterConnectionError(f"Cannot connect to cluster: {error_msg}")
            elif "forbidden" in error_msg.lower() or "unauthorized" in error_msg.lower():
                raise InsufficientPermissionsError(f"Insufficient permissions: {error_msg}")
            else:
                raise MonitorError(f"Command failed: {error_msg}")

        return result.stdout

    except subprocess.TimeoutExpired:
        raise MonitorError("Command timed out after 30 seconds")
    except FileNotFoundError:
        raise CLIToolNotFoundError("CLI tool not found in PATH")


# ============================================================================
# Data Collection
# ============================================================================

def collect_cluster_data(cli_tool: str = 'oc', context: Optional[str] = None,
                        verbose: int = 0) -> List[NodeMetrics]:
    """
    Collect node and pod metrics from cluster.

    Args:
        cli_tool: CLI tool to use ('oc' or 'kubectl')
        context: Kubernetes context to use
        verbose: Verbosity level

    Returns:
        List of NodeMetrics objects
    """
    context_flag = f"--context={context}" if context else ""

    if verbose >= 1:
        click.echo("📊 Collecting cluster metrics...")

    # Get all nodes
    nodes_cmd = f"{cli_tool} {context_flag} get nodes -o json"
    nodes_output = run_oc_command(nodes_cmd, verbose)
    nodes_data = json.loads(nodes_output)

    # Get all pods
    pods_cmd = f"{cli_tool} {context_flag} get pods -A -o json"
    pods_output = run_oc_command(pods_cmd, verbose)
    pods_data = json.loads(pods_output)

    if verbose >= 1:
        click.echo(f"   Found {len(nodes_data['items'])} nodes and {len(pods_data['items'])} pods")

    # Process nodes
    node_metrics = {}
    for node in nodes_data['items']:
        node_name = node['metadata']['name']
        allocatable = node['status']['allocatable']

        cpu_allocatable = parse_resource_quantity(allocatable.get('cpu', '0'))
        memory_allocatable = parse_resource_quantity(allocatable.get('memory', '0'))

        node_metrics[node_name] = NodeMetrics(
            name=node_name,
            cpu=ResourceMetrics(allocatable=cpu_allocatable, requests=0, limits=0),
            memory=ResourceMetrics(allocatable=memory_allocatable, requests=0, limits=0),
            pod_count=0
        )

    # Aggregate pod resources by node
    for pod in pods_data['items']:
        # Skip pods not scheduled or in terminal states
        phase = pod['status'].get('phase', '')
        if phase not in ['Running', 'Pending']:
            continue

        node_name = pod['spec'].get('nodeName')
        if not node_name or node_name not in node_metrics:
            continue

        # Count pod
        node_metrics[node_name].pod_count += 1

        # Sum container resources
        for container in pod['spec'].get('containers', []):
            resources = container.get('resources', {})
            requests = resources.get('requests', {})
            limits = resources.get('limits', {})

            cpu_request = parse_resource_quantity(requests.get('cpu', '0'))
            memory_request = parse_resource_quantity(requests.get('memory', '0'))
            cpu_limit = parse_resource_quantity(limits.get('cpu', '0'))
            memory_limit = parse_resource_quantity(limits.get('memory', '0'))

            node_metrics[node_name].cpu.requests += cpu_request
            node_metrics[node_name].cpu.limits += cpu_limit
            node_metrics[node_name].memory.requests += memory_request
            node_metrics[node_name].memory.limits += memory_limit

    return list(node_metrics.values())


# ============================================================================
# Overcommit Detection
# ============================================================================

def detect_overcommitment(nodes: List[NodeMetrics],
                         threshold_warning: float = 0.85,
                         threshold_critical: float = 1.0) -> Dict:
    """
    Analyze cluster and categorize nodes by status.

    Args:
        nodes: List of NodeMetrics
        threshold_warning: Warning threshold ratio
        threshold_critical: Critical threshold ratio

    Returns:
        Dict with categorized nodes and cluster risk score
    """
    categorized = {
        'overcommitted': [],
        'warning': [],
        'healthy': [],
    }

    for node in nodes:
        max_ratio = max(node.cpu.request_ratio, node.memory.request_ratio)

        if max_ratio > threshold_critical:
            categorized['overcommitted'].append(node)
        elif max_ratio > threshold_warning:
            categorized['warning'].append(node)
        else:
            categorized['healthy'].append(node)

    # Calculate overall cluster risk
    cluster_risk = sum(n.risk_score for n in nodes) / len(nodes) if nodes else 0

    return {
        **categorized,
        'cluster_risk': cluster_risk,
        'total_nodes': len(nodes)
    }


# ============================================================================
# AI Analysis with Claude
# ============================================================================

def analyze_with_claude(nodes: List[NodeMetrics], analysis_data: Dict,
                       api_key: str, verbose: int = 0) -> str:
    """
    Use Claude AI to analyze cluster metrics and provide recommendations.

    Args:
        nodes: List of NodeMetrics
        analysis_data: Detection results from detect_overcommitment
        api_key: Anthropic API key
        verbose: Verbosity level

    Returns:
        AI analysis as formatted text
    """
    if verbose >= 1:
        click.echo("🤖 Analyzing with Claude AI...")

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Prepare data for Claude
        node_details = []
        for node in nodes:
            node_details.append({
                'name': node.name,
                'status': node.status.value,
                'cpu': {
                    'allocatable': format_cores(node.cpu.allocatable),
                    'requests': format_cores(node.cpu.requests),
                    'ratio': f"{node.cpu.request_percentage:.1f}%"
                },
                'memory': {
                    'allocatable': format_bytes(node.memory.allocatable),
                    'requests': format_bytes(node.memory.requests),
                    'ratio': f"{node.memory.request_percentage:.1f}%"
                },
                'pods': node.pod_count,
                'risk_score': f"{node.risk_score:.0f}/100"
            })

        system_prompt = """You are an expert OpenShift/Kubernetes cluster reliability engineer.
Analyze cluster resource metrics and provide actionable recommendations.

Your analysis should:
1. Identify critical issues (overcommitment, imbalance)
2. Assess risk levels (immediate, short-term, long-term)
3. Provide specific, actionable recommendations
4. Detect patterns (specific apps, namespaces, node groups)
5. Prioritize actions by impact

Be concise but thorough. Focus on what operators should do next."""

        user_prompt = f"""Analyze this OpenShift cluster resource utilization:

CLUSTER SUMMARY:
- Total Nodes: {analysis_data['total_nodes']}
- Overcommitted: {len(analysis_data['overcommitted'])} nodes
- Warning State: {len(analysis_data['warning'])} nodes
- Healthy: {len(analysis_data['healthy'])} nodes
- Overall Risk Score: {analysis_data['cluster_risk']:.0f}/100

NODE DETAILS:
{json.dumps(node_details, indent=2)}

Please provide:
1. CRITICAL ISSUES: What needs immediate attention?
2. RISK ASSESSMENT: What could go wrong under load?
3. RECOMMENDATIONS: Specific actions to take (prioritized)
4. PATTERNS: Any concerning trends or configurations?

Format your response in clear sections."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            system=system_prompt
        )

        return message.content[0].text

    except anthropic.APIError as e:
        raise MonitorError(f"Claude API error: {str(e)}")


# ============================================================================
# Terminal Rendering
# ============================================================================

def render_header():
    """Render application header"""
    print()
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'OpenShift Cluster Resource Monitor (AI-Powered)':^70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
    print()


def render_summary(analysis_data: Dict):
    """Render cluster summary section"""
    print(f"{Fore.WHITE}📊 CLUSTER SUMMARY{Style.RESET_ALL}")
    print("─" * 70)

    total = analysis_data['total_nodes']
    over_count = len(analysis_data['overcommitted'])
    warn_count = len(analysis_data['warning'])
    healthy_count = len(analysis_data['healthy'])
    risk = analysis_data['cluster_risk']

    print(f"Total Nodes:           {total}")
    print(f"Overcommitted:         {Fore.RED}{over_count}  🔴{Style.RESET_ALL}")
    print(f"Warning State:         {Fore.YELLOW}{warn_count}  🟡{Style.RESET_ALL}")
    print(f"Healthy:              {Fore.GREEN}{healthy_count}  🟢{Style.RESET_ALL}")
    print(f"Overall Risk Score:   {risk:.0f}/100")
    print()


def render_node_table(nodes: List[NodeMetrics]):
    """Render node details table"""
    print(f"{Fore.WHITE}📋 NODE DETAILS{Style.RESET_ALL}")
    print("─" * 70)

    # Sort by risk score (highest first)
    sorted_nodes = sorted(nodes, key=lambda n: n.risk_score, reverse=True)

    table_data = []
    for node in sorted_nodes:
        status = node.status
        color = get_status_color(status)
        emoji = get_status_emoji(status)

        cpu_bar = create_progress_bar(node.cpu.request_ratio)
        mem_bar = create_progress_bar(node.memory.request_ratio)

        table_data.append([
            node.name[:30],  # Truncate long names
            f"{color}{cpu_bar} {node.cpu.request_percentage:5.1f}%{Style.RESET_ALL}",
            f"{color}{mem_bar} {node.memory.request_percentage:5.1f}%{Style.RESET_ALL}",
            f"{color}{emoji} {status.value:13}{Style.RESET_ALL}",
            f"{node.pod_count:>3}"
        ])

    headers = ["Node Name", "CPU Usage", "Memory Usage", "Status", "Pods"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))
    print()


def render_ai_analysis(analysis: str):
    """Render Claude AI analysis"""
    print(f"{Fore.WHITE}🤖 AI ANALYSIS (Claude Sonnet 4.5){Style.RESET_ALL}")
    print("─" * 70)
    print(analysis)
    print()


def render_footer(success: bool = True):
    """Render footer"""
    print("─" * 70)
    if success:
        print(f"{Fore.GREEN}✅ Analysis complete.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}❌ Analysis completed with warnings.{Style.RESET_ALL}")
    print()


# ============================================================================
# Main CLI
# ============================================================================

@click.command()
@click.option(
    '--context',
    help='Kubernetes context to use (default: current context)'
)
@click.option(
    '--output', '-o',
    type=click.Choice(['terminal', 'json']),
    default='terminal',
    help='Output format'
)
@click.option(
    '--threshold-warning',
    type=float,
    default=0.85,
    help='Warning threshold (default: 0.85)'
)
@click.option(
    '--threshold-critical',
    type=float,
    default=1.0,
    help='Critical threshold (default: 1.0)'
)
@click.option(
    '--ai/--no-ai',
    default=True,
    help='Enable/disable AI analysis (default: enabled)'
)
@click.option(
    '--api-key',
    envvar='ANTHROPIC_API_KEY',
    help='Anthropic API key (or set ANTHROPIC_API_KEY env var)'
)
@click.option(
    '--verbose', '-v',
    count=True,
    help='Verbose output (-v for info, -vv for debug)'
)
@click.option(
    '--cli-tool',
    type=click.Choice(['oc', 'kubectl']),
    default='oc',
    help='CLI tool to use (default: oc)'
)
def monitor(context, output, threshold_warning, threshold_critical,
            ai, api_key, verbose, cli_tool):
    """Monitor OpenShift/Kubernetes cluster for resource overcommitment"""

    # Initialize colorama
    colorama_init(autoreset=True)

    try:
        # Collect cluster data
        nodes = collect_cluster_data(cli_tool, context, verbose)

        if not nodes:
            click.echo(f"{Fore.YELLOW}⚠️  No nodes found in cluster{Style.RESET_ALL}", err=True)
            sys.exit(1)

        # Detect overcommitment
        analysis_data = detect_overcommitment(nodes, threshold_warning, threshold_critical)

        # Output based on format
        if output == 'json':
            # JSON output
            result = {
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
                        'cpu_request_ratio': n.cpu.request_ratio,
                        'memory_request_ratio': n.memory.request_ratio,
                        'pod_count': n.pod_count,
                        'risk_score': n.risk_score
                    }
                    for n in nodes
                ]
            }

            # Add AI analysis if enabled
            if ai and api_key:
                ai_analysis = analyze_with_claude(nodes, analysis_data, api_key, verbose)
                result['ai_analysis'] = ai_analysis

            print(json.dumps(result, indent=2))

        else:
            # Terminal output
            render_header()
            render_summary(analysis_data)
            render_node_table(nodes)

            # AI analysis if enabled
            if ai:
                if not api_key:
                    click.echo(f"{Fore.YELLOW}⚠️  AI analysis skipped: ANTHROPIC_API_KEY not set{Style.RESET_ALL}")
                else:
                    try:
                        ai_analysis = analyze_with_claude(nodes, analysis_data, api_key, verbose)
                        render_ai_analysis(ai_analysis)
                    except MonitorError as e:
                        click.echo(f"{Fore.YELLOW}⚠️  AI analysis failed: {e}{Style.RESET_ALL}", err=True)

            render_footer(success=len(analysis_data['overcommitted']) == 0)

        # Exit with appropriate code
        if analysis_data['overcommitted']:
            sys.exit(2)  # Overcommitment detected
        elif analysis_data['warning']:
            sys.exit(1)  # Warning state
        else:
            sys.exit(0)  # All healthy

    except CLIToolNotFoundError as e:
        click.echo(f"{Fore.RED}❌ Error: {e}{Style.RESET_ALL}", err=True)
        click.echo(f"{Fore.YELLOW}Please install OpenShift CLI (oc) or Kubernetes CLI (kubectl){Style.RESET_ALL}", err=True)
        sys.exit(3)
    except ClusterConnectionError as e:
        click.echo(f"{Fore.RED}❌ Error: {e}{Style.RESET_ALL}", err=True)
        click.echo(f"{Fore.YELLOW}Please check your cluster connection and credentials{Style.RESET_ALL}", err=True)
        sys.exit(4)
    except InsufficientPermissionsError as e:
        click.echo(f"{Fore.RED}❌ Error: {e}{Style.RESET_ALL}", err=True)
        click.echo(f"{Fore.YELLOW}Please ensure you have sufficient RBAC permissions{Style.RESET_ALL}", err=True)
        sys.exit(5)
    except MonitorError as e:
        click.echo(f"{Fore.RED}❌ Error: {e}{Style.RESET_ALL}", err=True)
        sys.exit(6)
    except Exception as e:
        if verbose >= 2:
            import traceback
            traceback.print_exc()
        click.echo(f"{Fore.RED}❌ Unexpected error: {e}{Style.RESET_ALL}", err=True)
        sys.exit(99)


if __name__ == '__main__':
    monitor()

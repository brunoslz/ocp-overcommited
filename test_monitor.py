"""
Unit tests for oc-monitor.py
"""

import pytest
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import functions from oc-monitor
from oc_monitor import (
    parse_resource_quantity,
    NodeMetrics,
    ResourceMetrics,
    NodeStatus,
    detect_overcommitment,
    format_bytes,
    format_cores,
)


# ============================================================================
# Test Resource Quantity Parsing
# ============================================================================

def test_cpu_parsing_millicores():
    """Test parsing CPU millicores"""
    assert parse_resource_quantity("2000m") == 2.0
    assert parse_resource_quantity("500m") == 0.5
    assert parse_resource_quantity("1500m") == 1.5
    assert parse_resource_quantity("100m") == 0.1


def test_cpu_parsing_cores():
    """Test parsing CPU cores"""
    assert parse_resource_quantity("4") == 4.0
    assert parse_resource_quantity("2") == 2.0
    assert parse_resource_quantity("1") == 1.0
    assert parse_resource_quantity("0.5") == 0.5


def test_memory_parsing_binary():
    """Test parsing memory in binary units (Ki, Mi, Gi)"""
    assert parse_resource_quantity("2Gi") == 2 * 1024**3
    assert parse_resource_quantity("512Mi") == 512 * 1024**2
    assert parse_resource_quantity("1024Ki") == 1024 * 1024
    assert parse_resource_quantity("1Ti") == 1024**4


def test_memory_parsing_decimal():
    """Test parsing memory in decimal units (K, M, G)"""
    assert parse_resource_quantity("2G") == 2 * 1000**3
    assert parse_resource_quantity("512M") == 512 * 1000**2
    assert parse_resource_quantity("1024K") == 1024 * 1000


def test_empty_and_invalid_parsing():
    """Test parsing empty and invalid values"""
    assert parse_resource_quantity("") == 0.0
    assert parse_resource_quantity(None) == 0.0
    assert parse_resource_quantity("invalid") == 0.0


# ============================================================================
# Test ResourceMetrics
# ============================================================================

def test_resource_metrics_ratio():
    """Test ResourceMetrics ratio calculations"""
    cpu = ResourceMetrics(allocatable=8.0, requests=6.0, limits=12.0)

    assert cpu.request_ratio == 0.75  # 6/8
    assert cpu.limit_ratio == 1.5  # 12/8
    assert cpu.request_percentage == 75.0


def test_resource_metrics_zero_allocatable():
    """Test ResourceMetrics with zero allocatable"""
    cpu = ResourceMetrics(allocatable=0, requests=0, limits=0)
    assert cpu.request_ratio == 0
    assert cpu.limit_ratio == 0


# ============================================================================
# Test NodeMetrics and Status Classification
# ============================================================================

def test_node_status_healthy():
    """Test node classified as HEALTHY"""
    cpu = ResourceMetrics(allocatable=8.0, requests=4.0, limits=8.0)
    memory = ResourceMetrics(allocatable=32.0, requests=16.0, limits=32.0)
    node = NodeMetrics(name="test-node", cpu=cpu, memory=memory, pod_count=50)

    assert node.status == NodeStatus.HEALTHY
    assert node.risk_score < 85


def test_node_status_warning():
    """Test node classified as WARNING"""
    cpu = ResourceMetrics(allocatable=8.0, requests=7.0, limits=8.0)
    memory = ResourceMetrics(allocatable=32.0, requests=16.0, limits=32.0)
    node = NodeMetrics(name="test-node", cpu=cpu, memory=memory, pod_count=70)

    assert node.status == NodeStatus.WARNING
    # Risk score = 87.5% CPU * 50 + 50% memory * 50 = 43.75 + 25 = 68.75
    assert node.risk_score == 68.75


def test_node_status_overcommitted_cpu():
    """Test node overcommitted on CPU"""
    cpu = ResourceMetrics(allocatable=8.0, requests=9.0, limits=16.0)
    memory = ResourceMetrics(allocatable=32.0, requests=16.0, limits=32.0)
    node = NodeMetrics(name="test-node", cpu=cpu, memory=memory, pod_count=90)

    assert node.status == NodeStatus.OVERCOMMITTED


def test_node_status_overcommitted_memory():
    """Test node overcommitted on memory"""
    cpu = ResourceMetrics(allocatable=8.0, requests=4.0, limits=8.0)
    memory = ResourceMetrics(allocatable=32.0, requests=35.0, limits=40.0)
    node = NodeMetrics(name="test-node", cpu=cpu, memory=memory, pod_count=90)

    assert node.status == NodeStatus.OVERCOMMITTED


def test_node_risk_score():
    """Test node risk score calculation"""
    # 50% CPU + 50% memory = 50 risk score
    cpu = ResourceMetrics(allocatable=8.0, requests=4.0, limits=8.0)
    memory = ResourceMetrics(allocatable=32.0, requests=16.0, limits=32.0)
    node = NodeMetrics(name="test-node", cpu=cpu, memory=memory, pod_count=50)

    assert node.risk_score == 50.0

    # 100% CPU + 100% memory = 100 risk score (capped)
    cpu2 = ResourceMetrics(allocatable=8.0, requests=8.0, limits=16.0)
    memory2 = ResourceMetrics(allocatable=32.0, requests=32.0, limits=64.0)
    node2 = NodeMetrics(name="test-node-2", cpu=cpu2, memory=memory2, pod_count=100)

    assert node2.risk_score == 100.0


# ============================================================================
# Test Overcommitment Detection
# ============================================================================

def test_detect_overcommitment():
    """Test overcommitment detection across multiple nodes"""
    nodes = [
        # Healthy node
        NodeMetrics(
            name="node-1",
            cpu=ResourceMetrics(allocatable=8.0, requests=4.0, limits=8.0),
            memory=ResourceMetrics(allocatable=32.0, requests=16.0, limits=32.0),
            pod_count=40
        ),
        # Warning node
        NodeMetrics(
            name="node-2",
            cpu=ResourceMetrics(allocatable=8.0, requests=7.0, limits=12.0),
            memory=ResourceMetrics(allocatable=32.0, requests=20.0, limits=32.0),
            pod_count=70
        ),
        # Overcommitted node
        NodeMetrics(
            name="node-3",
            cpu=ResourceMetrics(allocatable=8.0, requests=10.0, limits=16.0),
            memory=ResourceMetrics(allocatable=32.0, requests=28.0, limits=40.0),
            pod_count=90
        ),
    ]

    result = detect_overcommitment(nodes)

    assert result['total_nodes'] == 3
    assert len(result['healthy']) == 1
    assert len(result['warning']) == 1
    assert len(result['overcommitted']) == 1
    assert result['healthy'][0].name == "node-1"
    assert result['warning'][0].name == "node-2"
    assert result['overcommitted'][0].name == "node-3"
    assert 0 <= result['cluster_risk'] <= 100


def test_detect_overcommitment_custom_thresholds():
    """Test overcommitment detection with custom thresholds"""
    nodes = [
        NodeMetrics(
            name="node-1",
            cpu=ResourceMetrics(allocatable=8.0, requests=7.2, limits=12.0),
            memory=ResourceMetrics(allocatable=32.0, requests=20.0, limits=32.0),
            pod_count=70
        ),
    ]

    # With default thresholds (0.85, 1.0), this should be WARNING (90% > 85%)
    result_default = detect_overcommitment(nodes)
    assert len(result_default['warning']) == 1

    # With custom thresholds (0.80, 0.95), this should still be WARNING (90% > 80% but < 95%)
    result_custom = detect_overcommitment(nodes, threshold_warning=0.80, threshold_critical=0.95)
    assert len(result_custom['warning']) == 1


def test_detect_overcommitment_empty():
    """Test overcommitment detection with no nodes"""
    result = detect_overcommitment([])
    assert result['total_nodes'] == 0
    assert len(result['healthy']) == 0
    assert len(result['warning']) == 0
    assert len(result['overcommitted']) == 0
    assert result['cluster_risk'] == 0


# ============================================================================
# Test Formatting Functions
# ============================================================================

def test_format_bytes():
    """Test byte formatting to GiB"""
    assert format_bytes(1024**3) == "1.0Gi"
    assert format_bytes(2 * 1024**3) == "2.0Gi"
    assert format_bytes(512 * 1024**2) == "0.5Gi"


def test_format_cores():
    """Test CPU core formatting"""
    assert format_cores(2.0) == "2.0"
    assert format_cores(0.5) == "0.5"
    assert format_cores(8.5) == "8.5"


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class NormalizedPoint:
    baseline_mode: str
    design_name: str
    tech: str
    mm: int
    microarch_name: str
    nn: int
    workload_name: str
    workload_exec_name: str
    xx: int
    yy: int
    ss: int
    bb: int
    rr: int
    ff: int
    objective_name: str
    workload_motif: str | None
    workload_ref: str | None
    workload_status: str | None
    workload_trace_ref: str | None
    workload_trace_summary: Dict[str, Any] | None
    workload_trace_scalars: Dict[str, float] | None
    xcut: int
    ycut: int
    package_type: str
    IO_type: str
    ddr_type: str
    ddr_bw: int
    noc: int
    nop_bw: int
    mac: int
    ul3: int
    tops_target_tops: int
    tops: int
    proposal_budget: int | None
    seed: int
    time_cap_minutes: float | None

    @property
    def chiplet_count(self) -> int:
        return self.xcut * self.ycut

    @property
    def total_core_count(self) -> int:
        return self.xx * self.yy

    @property
    def cores_per_chiplet(self) -> int:
        return max(self.total_core_count // max(self.chiplet_count, 1), 1)

    @property
    def ul3_bytes_per_chiplet(self) -> int:
        return max(self.ul3, 1) * 1024

    @property
    def ul3_bytes_per_core(self) -> int:
        return max(self.ul3_bytes_per_chiplet // self.cores_per_chiplet, 1024)

    @property
    def memory_bandwidth_gbps(self) -> float:
        return self.ddr_bw / 1024.0


@dataclass(frozen=True)
class SearchState:
    mapping_tiling: int
    pipeline_depth: int
    segment_span: int
    interleave: bool
    spm_level: int
    memory_prefetch: int
    route_slack: float
    memory_balance: float
    noc_balance: float
    placement_skew: float
    batch_cluster: bool


@dataclass(frozen=True)
class SearchTraceEntry:
    round: int
    seed: int
    move_family: str
    accepted: bool
    legal: bool
    illegal_reason: str
    best_score: float
    temperature: float
    elapsed_time: float


@dataclass(frozen=True)
class EvaluationResult:
    objective_score: float
    cycle: int
    energy: float
    edp: float
    cost_overall: float
    legal: bool
    legality_flags: Dict[str, str]
    illegal_reasons: List[str]
    energy_breakdown: Dict[str, float]
    cost_breakdown: Dict[str, float]
    die_area_breakdown: Dict[str, float]
    derived_terms: Dict[str, float]


@dataclass(frozen=True)
class LegalityAssessment:
    legal: bool
    legality_flags: Dict[str, str]
    illegal_reasons: List[str]
    derived_terms: Dict[str, float]


@dataclass(frozen=True)
class AreaModelResult:
    compute_array_area: float
    buffer_area: float
    control_area: float
    total_compute_area: float
    per_compute_die_area: float
    phy_area: float
    memory_phy_area: float
    io_die_area: float
    total_die_area: float


@dataclass(frozen=True)
class MappingModelResult:
    estimated_layer_count: int
    segment_count: int
    boundary_count: int
    pipeline_wave_count: int
    locality_score: float
    placement_dispersion: float
    cross_chip_share: float
    multicast_degree: float
    multicast_efficiency: float
    spm_residency: float
    spm_overflow_ratio: float
    weight_reuse_factor: float
    activation_reuse_factor: float
    batch_reuse_factor: float
    memory_stream_count: int
    working_set_scale: float
    collective_pressure: float
    latency_sensitivity: float


@dataclass(frozen=True)
class TrafficModelResult:
    traffic_matrix: List[List[float]]
    peak_noc_link_gbps: float
    peak_nop_link_gbps: float
    peak_route_link_gbps: float
    peak_dram_channel_gbps: float
    average_noc_hops: float
    average_nop_hops: float
    total_noc_hop_volume: float
    total_nop_hop_volume: float
    total_dram_access_volume: float
    total_interchip_bw: float
    edge_demand: float
    edge_capacity: float
    route_demand: float
    route_budget: float
    memory_required_bw: float
    available_memory_bw: float
    channel_count_available: int
    channel_count_required: int
    phy_count: int
    locality: float
    serialization_ratio: float
    dram_channel_imbalance: float
    noc_pressure: float
    nop_pressure: float
    dram_pressure: float


@dataclass(frozen=True)
class LatencyModelResult:
    compute_cycles: int
    noc_service_cycles: int
    nop_service_cycles: int
    dram_service_cycles: int
    endpoint_latency_cycles: int
    segment_sync_cycles: int
    overlap_discount: float
    total_cycles: int


@dataclass(frozen=True)
class CostModelResult:
    cost_chip: float
    cost_package: float
    cost_system_package: float
    cost_soc: float
    raw_die_cost: float
    defect_die_cost: float
    raw_package_cost: float
    package_defect_cost: float
    assembly_waste_cost: float
    chip_nre: float
    module_nre: float
    package_nre: float
    amortized_nre_cost: float
    package_area: float
    interposer_area: float
    distinct_chip_type_count: int


@dataclass
class SearchExecution:
    raw_tokens: List[str]
    trace_entries: List[SearchTraceEntry]
    stdout: str
    stderr: str
    summary: Dict[str, Any] = field(default_factory=dict)

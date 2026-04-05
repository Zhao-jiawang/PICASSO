from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

from .models import AreaModelResult, CostModelResult, NormalizedPoint


NODES = ["3", "5", "7", "12", "14", "20", "28", "40", "55"]
NRE_SCALE_FACTOR_MODULE = 0.5
NRE_SCALE_FACTOR_CHIP = 0.3
NRE_AMORTIZATION_UNITS = 300.0
WAFER_DIAMETER = 300.0
SCRIBE_LANE = 0.2
EDGE_LOSS = 5.0
CRITICAL_LEVEL = 10.0
OS_AREA_SCALE_FACTOR = 4.0
OS_NRE_COST_FACTOR = 3e3
OS_NRE_COST_FIXED = 3e5
COST_FACTOR_OS = 0.005
BONDING_YIELD_OS = 0.99
C4_BUMP_COST_FACTOR = 0.005
COST_WAFER_RDL = 1200.0
DEFECT_DENSITY_RDL = 0.05
RDL_AREA_SCALE_FACTOR = 1.2
CRITICAL_LEVEL_RDL = 3.0
BONDING_YIELD_RDL = 0.98
FO_NRE_COST_FACTOR = 7.5e6
FO_NRE_COST_FIXED = 7.5e6
DEFECT_DENSITY_SI = 0.06
SI_AREA_SCALE_FACTOR = 1.1
CRITICAL_LEVEL_SI = 6.0
BONDING_YIELD_SI = 0.95
U_BUMP_COST_FACTOR = 0.01

DEFECT_DENSITY_DIE = {
    "3": 0.2,
    "5": 0.11,
    "7": 0.09,
    "12": 0.08,
    "14": 0.08,
    "20": 0.07,
    "28": 0.07,
    "40": 0.07,
    "55": 0.07,
}
WAFER_COST_DIE = {
    "3": 30000.0,
    "5": 16988.0,
    "7": 9346.0,
    "12": 5992.0,
    "14": 3984.0,
    "20": 3677.0,
    "28": 2891.0,
    "40": 2274.0,
    "55": 1937.0,
}
COST_NRE = {
    "3": 100e7,
    "5": 54.2e7,
    "7": 29.8e7,
    "12": 17.4e7,
    "14": 10.6e7,
    "20": 7e7,
    "28": 5.1e7,
    "40": 3.8e7,
    "55": 2.8e7,
}
CHIP_NRE_COST_FACTOR = {node: NRE_SCALE_FACTOR_CHIP * COST_NRE[node] / 300.0 for node in NODES}
CHIP_NRE_COST_FIXED = {node: (1.0 - NRE_SCALE_FACTOR_MODULE - NRE_SCALE_FACTOR_CHIP) * COST_NRE[node] for node in NODES}
MODULE_NRE_COST_FACTOR = {node: NRE_SCALE_FACTOR_MODULE * COST_NRE[node] / NRE_AMORTIZATION_UNITS for node in NODES}
SI_NRE_COST_FACTOR = CHIP_NRE_COST_FACTOR["55"] * 1.2
SI_NRE_COST_FIXED = CHIP_NRE_COST_FIXED["55"] * 1.2
COST_WAFER_SI = WAFER_COST_DIE["55"]


@dataclass(frozen=True)
class ChipDescriptor:
    name: str
    node: str
    area: float
    count: int


def _dies_per_wafer(area: float) -> float:
    area = max(area, 1e-3)
    area_with_scribe = area + 2.0 * SCRIBE_LANE * math.sqrt(area) + SCRIBE_LANE**2
    usable_radius = WAFER_DIAMETER / 2.0 - EDGE_LOSS
    dies = (
        math.pi * usable_radius**2 / area_with_scribe
        - math.pi * (WAFER_DIAMETER - 2.0 * EDGE_LOSS) / math.sqrt(2.0 * area_with_scribe)
    )
    return max(dies, 1e-3)


def _die_yield(node: str, area: float) -> float:
    density = DEFECT_DENSITY_DIE[node]
    value = math.pow(1.0 + (density / 100.0 * area / CRITICAL_LEVEL), -CRITICAL_LEVEL)
    return min(max(value, 1e-6), 1.0)


def _cost_raw_die(node: str, area: float) -> float:
    return WAFER_COST_DIE[node] / _dies_per_wafer(area)


def _cost_known_good_die(node: str, area: float) -> float:
    return WAFER_COST_DIE[node] / (_dies_per_wafer(area) * _die_yield(node, area))


def _cost_defect_die(node: str, area: float) -> float:
    return _cost_known_good_die(node, area) - _cost_raw_die(node, area)


def _package_area(package_type: str, chip_descriptors: List[ChipDescriptor]) -> float:
    total_chip_area = sum(chip.area * chip.count for chip in chip_descriptors)
    if package_type == "OS":
        return total_chip_area * OS_AREA_SCALE_FACTOR
    if package_type == "FO":
        return total_chip_area * RDL_AREA_SCALE_FACTOR * OS_AREA_SCALE_FACTOR
    return total_chip_area * SI_AREA_SCALE_FACTOR * OS_AREA_SCALE_FACTOR


def _interposer_area(package_type: str, chip_descriptors: List[ChipDescriptor]) -> float:
    total_chip_area = sum(chip.area * chip.count for chip in chip_descriptors)
    if package_type == "FO":
        return total_chip_area * RDL_AREA_SCALE_FACTOR
    if package_type == "SI":
        return total_chip_area * SI_AREA_SCALE_FACTOR
    return 0.0


def _package_nre(package_type: str, chip_descriptors: List[ChipDescriptor]) -> float:
    package_area = _package_area(package_type, chip_descriptors)
    interposer_area = _interposer_area(package_type, chip_descriptors)
    if package_type == "OS":
        chip_num = sum(chip.count for chip in chip_descriptors)
        if chip_num == 1:
            factor = 1.0
        elif package_area > 30 * 30:
            factor = 2.0
        elif package_area > 17 * 17:
            factor = 1.75
        else:
            factor = 1.5
        return package_area * OS_NRE_COST_FACTOR * factor + OS_NRE_COST_FIXED
    if package_type == "FO":
        return interposer_area * FO_NRE_COST_FACTOR + FO_NRE_COST_FIXED + package_area * COST_FACTOR_OS
    return interposer_area * SI_NRE_COST_FACTOR + SI_NRE_COST_FIXED + package_area * COST_FACTOR_OS


def _chip_nre(chip_descriptors: List[ChipDescriptor]) -> float:
    total = 0.0
    for chip in chip_descriptors:
        total += chip.area * CHIP_NRE_COST_FACTOR[chip.node] + CHIP_NRE_COST_FIXED[chip.node]
    return total


def _module_node(point: NormalizedPoint, chip_descriptors: List[ChipDescriptor]) -> str:
    candidate_nodes = [chip.node for chip in chip_descriptors if chip.name == "compute"]
    if not candidate_nodes:
        candidate_nodes = [point.tech]
    return min(candidate_nodes, key=lambda node: int(node))


def _module_nre(point: NormalizedPoint, chip_descriptors: List[ChipDescriptor]) -> float:
    module_node = _module_node(point, chip_descriptors)
    return _package_area(point.package_type, chip_descriptors) * MODULE_NRE_COST_FACTOR[module_node]


def _package_raw_cost(package_type: str, chip_descriptors: List[ChipDescriptor]) -> float:
    package_area = _package_area(package_type, chip_descriptors)
    chip_num = sum(chip.count for chip in chip_descriptors)
    if package_type == "OS":
        if chip_num == 1:
            factor = 1.0
        elif package_area > 30 * 30:
            factor = 2.0
        elif package_area > 17 * 17:
            factor = 1.75
        else:
            factor = 1.5
        return package_area * COST_FACTOR_OS * factor

    interposer_area = _interposer_area(package_type, chip_descriptors)
    defect_density = DEFECT_DENSITY_RDL if package_type == "FO" else DEFECT_DENSITY_SI
    critical_level = CRITICAL_LEVEL_RDL if package_type == "FO" else CRITICAL_LEVEL_SI
    wafer_cost = COST_WAFER_RDL if package_type == "FO" else COST_WAFER_SI
    interposer_area_with_scribe = interposer_area + 2.0 * SCRIBE_LANE * math.sqrt(interposer_area) + SCRIBE_LANE**2
    package_total = (
        math.pi * (WAFER_DIAMETER / 2.0 - EDGE_LOSS) ** 2 / interposer_area_with_scribe
        - math.pi * (WAFER_DIAMETER - 2.0 * EDGE_LOSS) / math.sqrt(2.0 * interposer_area_with_scribe)
    )
    package_total = max(package_total, 1e-3)
    package_yield = math.pow(1.0 + (defect_density / 100.0 * interposer_area / critical_level), -critical_level)
    package_yield = min(max(package_yield, 1e-6), 1.0)
    del package_yield
    bump_cost = C4_BUMP_COST_FACTOR if package_type == "FO" else U_BUMP_COST_FACTOR
    return wafer_cost / package_total + interposer_area * bump_cost + package_area * COST_FACTOR_OS


def _package_re_costs(package_type: str, chip_descriptors: List[ChipDescriptor]) -> tuple[float, float, float, float, float]:
    raw_chips = 0.0
    defect_chips = 0.0
    bump_cost = C4_BUMP_COST_FACTOR if package_type in {"OS", "FO"} else U_BUMP_COST_FACTOR
    chip_num = sum(chip.count for chip in chip_descriptors)
    for chip in chip_descriptors:
        raw_chips += (_cost_raw_die(chip.node, chip.area) + chip.area * bump_cost) * chip.count
        defect_chips += _cost_defect_die(chip.node, chip.area) * chip.count

    if package_type == "OS":
        pkg_raw = _package_raw_cost(package_type, chip_descriptors)
        pkg_defect = pkg_raw * (1.0 / math.pow(BONDING_YIELD_OS, chip_num) - 1.0)
        wasted = (raw_chips + defect_chips) * (1.0 / math.pow(BONDING_YIELD_OS, chip_num) - 1.0)
        return raw_chips, defect_chips, pkg_raw, pkg_defect, wasted

    interposer_area = _interposer_area(package_type, chip_descriptors)
    defect_density = DEFECT_DENSITY_RDL if package_type == "FO" else DEFECT_DENSITY_SI
    critical_level = CRITICAL_LEVEL_RDL if package_type == "FO" else CRITICAL_LEVEL_SI
    bonding_yield = BONDING_YIELD_RDL if package_type == "FO" else BONDING_YIELD_SI
    package_yield = math.pow(1.0 + (defect_density / 100.0 * interposer_area / critical_level), -critical_level)
    package_yield = min(max(package_yield, 1e-6), 1.0)
    pkg_raw = _package_raw_cost(package_type, chip_descriptors)
    pkg_defect = pkg_raw * (1.0 / (package_yield * math.pow(bonding_yield, chip_num) * BONDING_YIELD_OS) - 1.0)
    wasted = (raw_chips + defect_chips) * (1.0 / (math.pow(bonding_yield, chip_num) * BONDING_YIELD_OS) - 1.0)
    return raw_chips, defect_chips, pkg_raw, pkg_defect, wasted


def compute_cost_model(point: NormalizedPoint, area: AreaModelResult, memory_unit_cost: float) -> CostModelResult:
    chiplet_count = max(point.chiplet_count, 1)
    chip_descriptors: List[ChipDescriptor]
    if chiplet_count == 1:
        chip_descriptors = [ChipDescriptor(name="compute", node=point.tech, area=area.total_die_area, count=1)]
    else:
        chip_descriptors = [ChipDescriptor(name="compute", node=point.tech, area=area.per_compute_die_area, count=chiplet_count)]
        if area.io_die_area > 0.0:
            io_node = "12" if point.tech == "7" else point.tech
            chip_descriptors.append(ChipDescriptor(name="io", node=io_node, area=area.io_die_area, count=1))

    raw_die_cost, defect_die_cost, raw_package_cost, package_defect_cost, assembly_waste_cost = _package_re_costs(point.package_type, chip_descriptors)
    cost_chip = raw_die_cost + defect_die_cost
    cost_package = raw_package_cost + package_defect_cost + assembly_waste_cost
    chip_nre = _chip_nre(chip_descriptors)
    module_nre = _module_nre(point, chip_descriptors)
    package_nre = _package_nre(point.package_type, chip_descriptors)
    amortized_nre_cost = (chip_nre + module_nre + package_nre) / NRE_AMORTIZATION_UNITS
    cost_system_package = cost_package + (module_nre + package_nre) / NRE_AMORTIZATION_UNITS
    memory_cost = point.memory_bandwidth_gbps * memory_unit_cost / 8.0
    cost_soc = cost_chip + cost_system_package + memory_cost + chip_nre / NRE_AMORTIZATION_UNITS
    package_area = _package_area(point.package_type, chip_descriptors)
    interposer_area = _interposer_area(point.package_type, chip_descriptors)

    return CostModelResult(
        cost_chip=cost_chip,
        cost_package=cost_package,
        cost_system_package=cost_system_package,
        cost_soc=cost_soc,
        raw_die_cost=raw_die_cost,
        defect_die_cost=defect_die_cost,
        raw_package_cost=raw_package_cost,
        package_defect_cost=package_defect_cost,
        assembly_waste_cost=assembly_waste_cost,
        chip_nre=chip_nre,
        module_nre=module_nre,
        package_nre=package_nre,
        amortized_nre_cost=amortized_nre_cost,
        package_area=package_area,
        interposer_area=interposer_area,
        distinct_chip_type_count=len(chip_descriptors),
    )

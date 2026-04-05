from __future__ import annotations

from typing import List

from .models import EvaluationResult, NormalizedPoint


RESULT_FLOAT_FIELDS = {
    "cost_overall",
    "energy",
    "edp",
    "cost",
    "ubuf_energy",
    "buf_energy",
    "bus_energy",
    "mac_energy",
    "NoC_energy",
    "NoP_energy",
    "DRAM_energy",
    "compute_die_area",
    "IO_die_area",
    "total_die_area",
    "cost_chip",
    "cost_package",
    "cost_system_package",
    "cost_soc",
}


def format_result_value(key: str, value: float | int | str) -> str:
    if isinstance(value, str):
        return value
    if key in RESULT_FLOAT_FIELDS:
        return f"{float(value):.5f}"
    return str(int(value))


def result_tokens(point: NormalizedPoint, best_eval: EvaluationResult, best_round: int) -> List[str]:
    tokens = {
        "tech": point.tech,
        "mm": point.mm,
        "nn": point.nn,
        "xx": point.xx,
        "yy": point.yy,
        "ss": point.ss,
        "bb": point.bb,
        "rr": point.rr,
        "ff": point.ff,
        "xcut": point.xcut,
        "ycut": point.ycut,
        "package_type": point.package_type,
        "IO_type": point.IO_type,
        "nop_bw": point.nop_bw,
        "ddr_type": point.ddr_type,
        "ddr_bw": point.ddr_bw,
        "noc": point.noc,
        "mac": point.mac,
        "ul3": point.ul3,
        "tops": point.tops,
        "cost_overall": best_eval.cost_overall,
        "energy": best_eval.energy,
        "cycle": best_eval.cycle,
        "edp": best_eval.edp,
        "cost": best_eval.objective_score,
        "idx": best_round,
        "ubuf_energy": best_eval.energy_breakdown["ubuf"],
        "buf_energy": best_eval.energy_breakdown["buf"],
        "bus_energy": best_eval.energy_breakdown["bus"],
        "mac_energy": best_eval.energy_breakdown["mac"],
        "NoC_energy": best_eval.energy_breakdown["noc"],
        "NoP_energy": best_eval.energy_breakdown["nop"],
        "DRAM_energy": best_eval.energy_breakdown["dram"],
        "compute_die_area": best_eval.die_area_breakdown["compute_die_area"],
        "IO_die_area": best_eval.die_area_breakdown["io_die_area"],
        "total_die_area": best_eval.die_area_breakdown["total_die_area"],
        "cost_chip": best_eval.cost_breakdown["cost_chip"],
        "cost_package": best_eval.cost_breakdown["cost_package"],
        "cost_system_package": best_eval.cost_breakdown["cost_system_package"],
        "cost_soc": best_eval.cost_breakdown["cost_soc"],
    }
    ordered_keys = [
        "tech",
        "mm",
        "nn",
        "xx",
        "yy",
        "ss",
        "bb",
        "rr",
        "ff",
        "xcut",
        "ycut",
        "package_type",
        "IO_type",
        "nop_bw",
        "ddr_type",
        "ddr_bw",
        "noc",
        "mac",
        "ul3",
        "tops",
        "cost_overall",
        "energy",
        "cycle",
        "edp",
        "cost",
        "idx",
        "ubuf_energy",
        "buf_energy",
        "bus_energy",
        "mac_energy",
        "NoC_energy",
        "NoP_energy",
        "DRAM_energy",
        "compute_die_area",
        "IO_die_area",
        "total_die_area",
        "cost_chip",
        "cost_package",
        "cost_system_package",
        "cost_soc",
    ]
    return [format_result_value(key, tokens[key]) for key in ordered_keys]


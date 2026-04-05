#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def load_json(path: Path):
    return json.loads(path.read_text())


def load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def latest_dir(parent: Path, suffix: str) -> Optional[Path]:
    matches = sorted(entry for entry in parent.iterdir() if entry.is_dir() and entry.name.endswith(suffix))
    return matches[-1] if matches else None


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def design_record_legality(aggregated_dir: Path) -> Dict[str, object]:
    records = load_json(aggregated_dir / 'design_records.json')['records']
    total = len(records)
    legal = 0
    illegal_reasons: Dict[str, int] = {}
    for record in records:
        overall = record.get('legality_flags', {}).get('overall', '').lower()
        if overall == 'legal':
            legal += 1
        else:
            reasons = record.get('legality_details', {}).get('reasons', []) or ['unknown']
            for reason in reasons:
                illegal_reasons[reason] = illegal_reasons.get(reason, 0) + 1
    return {
        'total': total,
        'legal': legal,
        'illegal': total - legal,
        'illegal_reasons': illegal_reasons,
    }


def package_order_ok(path: Path) -> Tuple[bool, Dict[str, float]]:
    rows = load_csv_rows(path)
    costs = {row['package_class']: float(row['avg_package_cost']) for row in rows}
    ok = all(key in costs for key in ('OS', 'FO', 'SI')) and costs['OS'] < costs['FO'] < costs['SI']
    return ok, costs


def compute_grounding_ok(path: Path) -> Tuple[bool, List[Dict[str, str]]]:
    rows = load_csv_rows(path)
    interesting = []
    ok = True
    for row in rows:
        interesting.append(
            {
                'process_node': row['process_node'],
                'latency_advantage_vs_12nm': row['latency_advantage_vs_12nm'],
                'latency_advantage_basis': row['latency_advantage_basis'],
                'matched_anchor_count': row['matched_anchor_count'],
            }
        )
        try:
            advantage = float(row['latency_advantage_vs_12nm'])
        except ValueError:
            ok = False
            continue
        if not (0.5 <= advantage <= 10.0):
            ok = False
    return ok, interesting


def placeholder_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    rows = load_csv_rows(path)
    flagged = []
    for row in rows:
        blob = ' '.join(str(value) for value in row.values()).lower()
        if 'bootstrap_placeholder' in blob or 'placeholder' in blob:
            flagged.append(row)
    return flagged


def build_check(category: str, item: str, status: str, detail: str) -> Dict[str, str]:
    return {
        'category': category,
        'item': item,
        'status': status,
        'detail': detail,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    docs_root = repo_root / 'docs'
    results_root = repo_root / 'results'

    aggregated_root = results_root / 'aggregated'
    plot_ready_root = results_root / 'plot_ready'
    backend_aggregated_root = results_root / 'backend_aggregated'
    validation_root = repo_root / 'validation'

    latest = {
        'paper_smoke': latest_dir(aggregated_root, 'paper_smoke'),
        'paper_core': latest_dir(aggregated_root, 'paper_core_bootstrap'),
        'paper_full': latest_dir(aggregated_root, 'paper_full_bootstrap'),
        'plot_smoke': latest_dir(plot_ready_root, 'paper_smoke'),
        'plot_core': latest_dir(plot_ready_root, 'paper_core_bootstrap'),
        'plot_full': latest_dir(plot_ready_root, 'paper_full_bootstrap'),
        'backend_smoke': latest_dir(backend_aggregated_root, 'paper_smoke'),
        'backend_core': latest_dir(backend_aggregated_root, 'paper_core_bootstrap'),
        'backend_full': latest_dir(backend_aggregated_root, 'paper_full_bootstrap'),
    }

    checks: List[Dict[str, str]] = []

    required_dirs = [
        repo_root / 'configs',
        repo_root / 'workloads',
        repo_root / 'scripts',
        results_root / 'raw',
        results_root / 'aggregated',
        results_root / 'plot_ready',
        results_root / 'figures',
        results_root / 'backend' / 'floorplan',
        results_root / 'backend' / 'package',
        results_root / 'backend' / 'nop',
        results_root / 'backend' / 'memory',
        results_root / 'backend_aggregated',
        results_root / 'backend_figures',
        docs_root,
        repo_root / 'paper' / 'figures',
    ]
    for path in required_dirs:
        checks.append(
            build_check(
                'repo_structure',
                relative(path, repo_root),
                'pass' if path.exists() else 'open',
                'exists' if path.exists() else 'missing required directory',
            )
        )

    for path in [
        repo_root / 'README.md',
        docs_root / 'README.md',
        docs_root / 'REPRODUCE.md',
        docs_root / 'PAPER_MAPPING.md',
        docs_root / 'Checklist.md',
        docs_root / 'CALIBRATION_STATUS_ZH.md',
    ]:
        checks.append(
            build_check(
                'documentation',
                relative(path, repo_root),
                'pass' if path.exists() else 'open',
                'exists' if path.exists() else 'missing required documentation file',
            )
        )

    for path in [
        repo_root / 'scripts' / 'run_smoke.sh',
        repo_root / 'scripts' / 'run_paper_core.sh',
        repo_root / 'scripts' / 'run_paper_full.sh',
        repo_root / 'scripts' / 'run_paper_full_parallel.sh',
        repo_root / 'scripts' / 'run_backend_smoke.sh',
        repo_root / 'scripts' / 'run_backend_core.sh',
        repo_root / 'scripts' / 'run_backend_full.sh',
        repo_root / 'scripts' / 'run_figure4.sh',
        repo_root / 'scripts' / 'run_figure5.sh',
        repo_root / 'scripts' / 'run_figure6.sh',
        repo_root / 'scripts' / 'run_figure7.sh',
        repo_root / 'scripts' / 'run_figure8.sh',
    ]:
        checks.append(
            build_check(
                'entrypoints',
                relative(path, repo_root),
                'pass' if path.exists() else 'open',
                'exists' if path.exists() else 'missing script',
            )
        )

    legality_summary = {}
    all_legal = True
    for key in ('paper_smoke', 'paper_core', 'paper_full'):
        directory = latest[key]
        if not directory:
            checks.append(build_check('runs', key, 'open', 'missing latest aggregated run'))
            all_legal = False
            continue
        summary = design_record_legality(directory)
        legality_summary[key] = {
            'run': relative(directory, repo_root),
            **summary,
        }
        status = 'pass' if summary['legal'] == summary['total'] else 'open'
        detail = f"{summary['legal']}/{summary['total']} legal"
        if summary['illegal']:
            detail += f"; reasons={summary['illegal_reasons']}"
            all_legal = False
        checks.append(build_check('runs', relative(directory, repo_root), status, detail))

    figure_manifest = repo_root / 'results' / 'figures' / 'paper_figure_manifest.json'
    manifest_ok = False
    if figure_manifest.exists():
        manifest = load_json(figure_manifest)
        figures = manifest.get('figures', [])
        manifest_ok = bool(figures)
        checks.append(
            build_check(
                'figures',
                relative(figure_manifest, repo_root),
                'pass' if manifest_ok else 'open',
                f"{len(figures)} figure entries recorded" if manifest_ok else 'manifest missing figures section',
            )
        )
    else:
        checks.append(build_check('figures', relative(figure_manifest, repo_root), 'open', 'missing manifest'))

    for stem in ('fig3_validation', 'fig4_baselines', 'fig5_interface_memory', 'fig6_phase_map', 'fig7_pareto_energy', 'fig8_closure'):
        for ext in ('pdf', 'png'):
            path = repo_root / 'results' / 'figures' / f'{stem}.{ext}'
            checks.append(
                build_check(
                    'figures',
                    relative(path, repo_root),
                    'pass' if path.exists() else 'open',
                    'exists' if path.exists() else 'missing rendered figure',
                )
            )

    model_parameterization = repo_root / 'results' / 'aggregated' / 'model_parameterization.json'
    mp_status = 'open'
    mp_detail = 'missing model parameterization export'
    if model_parameterization.exists():
        mp = load_json(model_parameterization)
        required_terms = ['Be(i,p)', 'Gedge(p,k)', 'Rbudget(p)', 'I(d)', 'P(d)']
        missing_terms = [term for term in required_terms if term not in mp]
        mp_status = 'pass' if not missing_terms else 'open'
        mp_detail = 'all required parameterization terms exported' if not missing_terms else f'missing terms: {missing_terms}'
    checks.append(build_check('schema', relative(model_parameterization, repo_root), mp_status, mp_detail))

    validation_checks = [
        validation_root / 'compute_grounding.csv',
        validation_root / 'interface_envelope.csv',
        validation_root / 'package_yield_anchor.csv',
    ]
    for path in validation_checks:
        checks.append(
            build_check(
                'validation',
                relative(path, repo_root),
                'pass' if path.exists() else 'open',
                'exists' if path.exists() else 'missing validation export',
            )
        )

    compute_ok, compute_rows = compute_grounding_ok(validation_root / 'compute_grounding.csv')
    checks.append(
        build_check(
            'validation',
            'compute_grounding_sanity',
            'pass' if compute_ok else 'open',
            json.dumps(compute_rows, ensure_ascii=False),
        )
    )
    package_ok, package_costs = package_order_ok(validation_root / 'package_yield_anchor.csv')
    checks.append(
        build_check(
            'validation',
            'package_ordering',
            'pass' if package_ok else 'open',
            json.dumps(package_costs, ensure_ascii=False),
        )
    )

    plot_ready_required = [
        'winner_change_matrix.csv',
        'reevaluated_loss.csv',
        'interface_vs_package.csv',
        'memory_off_ablation.csv',
        'phase_boundary.csv',
        'split_margin.csv',
        'pareto_points.csv',
        'energy_breakdown.csv',
        'boundary_drift.csv',
        'sensitivity_tags.csv',
        'illegal_breakdown.csv',
        'weight_shift_summary.csv',
    ]
    plot_dir = latest['plot_full']
    if plot_dir:
        for name in plot_ready_required:
            path = plot_dir / name
            checks.append(
                build_check(
                    'plot_ready',
                    relative(path, repo_root),
                    'pass' if path.exists() else 'open',
                    'exists in latest paper_full plot-ready bundle' if path.exists() else 'missing in latest paper_full plot-ready bundle',
                )
            )
    else:
        checks.append(build_check('plot_ready', 'latest_paper_full_plot_ready', 'open', 'missing latest plot-ready bundle'))

    backend_required = [
        'winner_agreement.csv',
        'legality_confusion.csv',
        'boundary_drift_backend.csv',
        'claim_closure.csv',
        'closure_summary.csv',
        'closure_summary.json',
        'router_sensitivity.csv',
        'package_cost_ordering_check.csv',
        'deployment_regime_summary.csv',
    ]
    backend_dir = latest['backend_full']
    placeholder_findings: Dict[str, int] = {}
    if backend_dir:
        for name in backend_required:
            path = backend_dir / name
            status = 'pass' if path.exists() else 'open'
            detail = 'exists in latest paper_full backend bundle' if path.exists() else 'missing in latest paper_full backend bundle'
            if path.suffix == '.csv' and path.exists():
                flagged = placeholder_rows(path)
                if flagged:
                    status = 'open'
                    detail = f'placeholder rows still present ({len(flagged)})'
                    placeholder_findings[name] = len(flagged)
            checks.append(build_check('backend_closure', relative(path, repo_root), status, detail))
    else:
        checks.append(build_check('backend_closure', 'latest_paper_full_backend', 'open', 'missing latest backend aggregate bundle'))

    calibration_freeze = all_legal and package_ok and compute_ok
    checks.append(
        build_check(
            'calibration_decision',
            'freeze_default_calibration_thread',
            'pass' if calibration_freeze else 'open',
            'keep focus on artifact/project work unless new regression appears' if calibration_freeze else 'calibration still blocks artifact focus',
        )
    )

    open_items = [check for check in checks if check['status'] != 'pass']
    summary = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'contexts': {key: relative(value, repo_root) if value else None for key, value in latest.items()},
        'calibration_freeze_recommended': calibration_freeze,
        'legality_summary': legality_summary,
        'open_item_count': len(open_items),
        'pass_item_count': len(checks) - len(open_items),
        'placeholder_findings': placeholder_findings,
    }
    audit = {
        'summary': summary,
        'checks': checks,
    }

    results_acceptance = repo_root / 'results' / 'acceptance'
    results_acceptance.mkdir(parents=True, exist_ok=True)
    (results_acceptance / 'current_acceptance_audit.json').write_text(json.dumps(audit, indent=2, ensure_ascii=False) + '\n')

    lines = []
    lines.append('# PICASSO Acceptance Status')
    lines.append('')
    lines.append(f"Generated from `pyscripts/analysis/audit_acceptance.py` on `{summary['generated_at_utc']}`.")
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append(f"- Calibration freeze recommended: `{summary['calibration_freeze_recommended']}`")
    lines.append(f"- Passed checks: `{summary['pass_item_count']}`")
    lines.append(f"- Open checks: `{summary['open_item_count']}`")
    lines.append('')
    lines.append('## Current Contexts')
    lines.append('')
    for key, value in summary['contexts'].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append('')
    lines.append('## Run Legality')
    lines.append('')
    for key, info in legality_summary.items():
        lines.append(f"- `{key}`: `{info['legal']}/{info['total']}` legal from `{info['run']}`")
    lines.append('')
    lines.append('## Validation Anchors')
    lines.append('')
    lines.append(f"- Package ordering: `{package_costs}`")
    lines.append(f"- Compute grounding sanity: `{compute_rows}`")
    lines.append('')
    lines.append('## Open Items')
    lines.append('')
    if open_items:
        for check in open_items:
            lines.append(f"- `{check['category']}` / `{check['item']}`: {check['detail']}")
    else:
        lines.append('- None.')
    lines.append('')
    lines.append('## Recommended Focus')
    lines.append('')
    if calibration_freeze:
        lines.append('- Default work should stay on PICASSO artifact and paper-sync tasks rather than reopening evaluator calibration.')
    else:
        lines.append('- Keep calibration active until the open blocking items above are resolved.')
    if placeholder_findings:
        lines.append('- Backend closure still contains placeholder rows. The next useful work is reviewer-facing backend replay and closure hardening.')
    lines.append('- Use this audit together with `docs/Checklist.md` to distinguish completed scaffolding from still-open hardening tasks.')
    lines.append('')

    markdown = '\n'.join(lines)
    (results_acceptance / 'current_acceptance_audit.md').write_text(markdown + '\n')
    (docs_root / 'ACCEPTANCE_STATUS.md').write_text(markdown + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

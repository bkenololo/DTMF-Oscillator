#!/usr/bin/env python3
"""Run the existing DTMF studies from any working directory. No stage runs by default."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
V1 = Path('02_Wien_Bridge_Studies/wien_bridge_lookup')
V2 = Path('02_Wien_Bridge_Studies/wien_bridge_expanded_C')
SUM = Path('03_Summing_Amplifier/wien_dtmf_summing_corrected')
LT = SUM / 'circuits/LTspice_DTMF'
LAB = Path('05_Analisis_Hasil_Uji')
DESCRIPTIONS = {
    'v1': 'Historical fixed-10-nF sweep and plots.',
    'v2': 'Expanded preferred-capacitor sweep (11,150 physical cases).',
    'refinement': 'Fine series-resistor sweep (1,250 physical cases).',
    'verification': 'Finer-timestep finalists; needs completed v2 and refinement.',
    'combine': 'Combined V2 overview; needs completed v2, refinement, verification.',
    'resistor-tolerance': 'Corrected pinned resistor pairs, independent physical-part tolerances.',
    'summing-nominal': 'Quick nominal combined circuit only.',
    'summing': 'Full corrected summer tolerance grids and numerical/load checks.',
    'standalone': 'Standalone oscillator reference simulations and comparison.',
    'audio': 'Export simulated WAV files; needs summing or summing-nominal.',
    'report': 'Rebuild summer tables/figures/report; needs summing, standalone, audio.',
    'decoder': 'Check the simulated steady WAV with the local basic decoder.',
    'tests': 'Existing oscillator physics and summer/audio unit tests.',
    'ltspice': 'Rebuild ASC/ASY, compare electrical connectivity, extract CIR, render PNG.',
    'ltspice-sim': 'Same LTspice rebuild plus four native batch simulations.',
    'lab': 'Reanalyze copied lab data and replay archived website decoder code; needs Node/sharp.',
}
ALL = ('v1', 'v2', 'refinement', 'verification', 'combine', 'resistor-tolerance',
       'summing', 'standalone', 'audio', 'report', 'decoder', 'tests', 'ltspice')
CURRENT = ('resistor-tolerance', 'summing', 'standalone', 'audio', 'report',
           'decoder', 'tests', 'ltspice')


def commands(stage: str, workers: int):
    """Return (working-directory, argument-list) pairs; never invoke a shell."""
    jobs = {
        'v1': [(V1, ['run.py', '--workers', str(workers)])],
        'v2': [(V2, ['run.py', '--workers', str(workers)])],
        'refinement': [(V2, ['run_refinement.py', '--workers', str(workers)])],
        'verification': [(V2, ['scripts/verify_finalists.py'])],
        'combine': [(V2, ['scripts/combine_results.py'])],
        'resistor-tolerance': [(V2, ['resistor_tolerance_table_values/run_resistor_tolerance.py',
                                    '--workers', str(workers)])],
        'summing-nominal': [(SUM, ['run.py', '--nominal', '--workers', str(workers)])],
        'summing': [(SUM, ['run.py', '--workers', str(workers)])],
        'standalone': [(SUM, ['scripts/check_standalone.py'])],
        'audio': [(SUM, ['scripts/export_audio.py'])],
        'report': [(SUM, ['scripts/make_report.py'])],
        'decoder': [(SUM, ['scripts/decode_wav.py', 'audio/dtmf_4_steady_48k.wav'])],
        'tests': [(folder, ['-m', 'unittest', 'discover', '-s', 'tests', '-v'])
                  for folder in (V1, V2, SUM)],
        'ltspice': [(LT, ['scripts/reproduce.py'])],
        'ltspice-sim': [(LT, ['scripts/reproduce.py', '--simulate'])],
        'lab': [(LAB, ['04_Skrip/analyze.py'])],
    }
    return [(ROOT / cwd, [sys.executable, *args]) for cwd, args in jobs[stage]]


def source_hashes():
    """Hash reproducibility inputs, excluding raw data, caches and derived outputs."""
    paths = {ROOT / 'reproduce.py', ROOT / 'requirements.txt'}
    for folder in (V1, V2, SUM):
        project = ROOT / folder
        paths.update(project.glob('*.py'))
        paths.update(project.glob('config*.json'))
        for sub in ('src', 'scripts', 'models', 'tests'):
            paths.update(p for p in (project / sub).glob('*')
                         if p.suffix in ('.py', '.lib', '.301'))
    for sub in ('refinement', 'resistor_tolerance_table_values'):
        paths.update(p for p in (ROOT / V2 / sub).glob('*.py'))
        paths.update(ROOT / V2 / sub / name for name in ('config.json', 'selected_parameters.json'))
    paths.update((ROOT / LT / 'scripts').glob('*.py'))
    paths.update((ROOT / LT / 'reference').glob('*.cir'))
    paths.update(ROOT / LT / name for name in ('TL074_original.301', '1N4148.lib'))
    paths.add(ROOT / SUM / 'reference/user_selected_table.json')
    paths.update((ROOT / LAB / '04_Skrip').glob('*'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choose = parser.add_mutually_exclusive_group()
    choose.add_argument('--stage', action='append', choices=tuple(DESCRIPTIONS),
                        help='Repeat to run several stages in the order supplied.')
    choose.add_argument('--all', action='store_true', help='Run historical and current simulation stages; excludes lab and native LTspice.')
    choose.add_argument('--current', action='store_true', help='Rebuild current pinned-design results without historical lookup sweeps.')
    parser.add_argument('--list', action='store_true', help='List available stages.')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without running or writing files.')
    parser.add_argument('--workers', type=int, default=4, help='Workers for stages with a worker option (default: 4).')
    parser.add_argument('--ngspice', type=Path, help='Override ngspice; otherwise use NGSPICE, PATH or existing project tools.')
    parser.add_argument('--ltspice', type=Path, help='Override LTspice for ltspice-sim; otherwise autodiscover.')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be at least 1')
    stages = list(ALL if args.all else CURRENT if args.current else args.stage or ())
    if args.list or not stages:
        for name, description in DESCRIPTIONS.items():
            print(f'{name:20s} {description}')
        if not stages:
            print('\nNo stage executed. Example: python reproduce.py --stage summing-nominal')
            return
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env.setdefault('MPLBACKEND', 'Agg')
    for option, key in ((args.ngspice, 'NGSPICE'), (args.ltspice, 'LTSPICE')):
        if option:
            if not option.is_file():
                parser.error(f'{key} executable does not exist: {option}')
            env[key] = str(option.resolve())
    plan = [(stage, cwd, command) for stage in stages
            for cwd, command in commands(stage, args.workers)]
    for stage, cwd, command in plan:
        if not cwd.is_dir():
            parser.error(f'Missing project folder: {cwd}')
        if command[1] != '-m' and not (cwd / command[1]).is_file():
            parser.error(f'Missing script: {cwd / command[1]}')
        print(f'[{stage}] cwd={cwd}\n  {shlex.join(command)}', flush=True)
    if args.dry_run:
        return
    # Each run gets its own provenance/log directory. Child stages update their normal derived outputs.
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    logs = ROOT / 'reproduction_logs' / stamp
    logs.mkdir(parents=True)
    packages = {}
    for name in ('numpy', 'matplotlib', 'Pillow', 'openpyxl'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    report = dict(started_utc=stamp, python=sys.version, executable=sys.executable, packages=packages,
                  project_root=str(ROOT), stages=stages,
                  simulator_overrides={k: env[k] for k in ('NGSPICE', 'LTSPICE', 'NODE_BIN', 'SHARP_MODULE') if k in env},
                  source_sha256=source_hashes(), runs=[])
    report_file = logs / 'run.json'
    def save_report():
        report_file.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    save_report()
    for i, (stage, cwd, command) in enumerate(plan, 1):
        log = logs / f'{i:02d}_{stage}.log'
        entry = dict(stage=stage, cwd=str(cwd), command=command, log=log.name, status='running')
        report['runs'].append(entry)
        save_report()
        start = time.monotonic()
        print(f'\nRunning {stage}; log: {log}', flush=True)
        try:
            with log.open('w', encoding='utf-8') as stream:
                proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, errors='replace')
                try:
                    for line in proc.stdout:
                        print(line, end='', flush=True)
                        stream.write(line)
                        stream.flush()
                    returncode = proc.wait()
                except BaseException:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    raise
            entry.update(returncode=returncode, status='passed' if returncode == 0 else 'failed')
        except BaseException as exc:
            entry.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', error=str(exc))
            raise
        finally:
            entry['elapsed_s'] = time.monotonic() - start
            save_report()
        if returncode:
            raise RuntimeError(f'{stage} failed; see {log}. Later stages were not run.')
    print(f'\nCompleted {len(plan)} commands. Run record: {report_file}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nStopped by user.', file=sys.stderr)
        sys.exit(130)

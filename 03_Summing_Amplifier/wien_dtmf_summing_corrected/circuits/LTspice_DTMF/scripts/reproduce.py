#!/usr/bin/env python3
"""Rebuild the hierarchy, verify its graph, and optionally simulate extracted netlists."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
CASES=('DTMF4','Test_LowOscillator','Test_HighOscillator','Test_SummingAmplifier')
def simulator(explicit):
 candidates=[explicit,os.environ.get('LTSPICE'),shutil.which('ltspice'),shutil.which('LTspice'),'/Applications/LTspice.app/Contents/MacOS/LTspice']
 for env in ['LOCALAPPDATA','ProgramFiles']:
  if os.environ.get(env):
   for rel in ['Programs/ADI/LTspice/LTspice.exe','ADI/LTspice/LTspice.exe','LTC/LTspiceXVII/XVIIx64.exe']:candidates.append(str(Path(os.environ[env])/rel))
 for c in candidates:
  if c and Path(c).is_file():return str(Path(c).resolve())
 raise RuntimeError('LTspice executable not found. Supply --ltspice PATH or set LTSPICE. Build/check do not require LTspice.')
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--output-dir',type=Path,default=ROOT/'reproduced')
 ap.add_argument('--simulate',action='store_true',help='Run all four extracted CIR files using the real LTspice executable.')
 ap.add_argument('--ltspice',help='Path to LTspice executable; optional when discoverable.')
 ap.add_argument('--timeout',type=float,default=120,help='Maximum seconds per simulation.')
 ap.add_argument('--check-only',action='store_true',help='Check existing generated files without rebuilding.')
 a=ap.parse_args();out=a.output_dir.resolve()
 if a.timeout<=0:ap.error('--timeout must be positive')
 if not a.check_only:
  print('Building schematics:',out,flush=True)
  subprocess.run([sys.executable,str(ROOT/'scripts/build_project.py'),'--output-dir',str(out)],check=True)
 subprocess.run([sys.executable,str(ROOT/'scripts/check_project.py'),'--project-dir',str(out)],check=True)
 runs=[]
 if a.simulate:
  exe=simulator(a.ltspice)
  for name in CASES:
   cir=out/(name+'_extracted.cir');print('LTspice:',name,flush=True);start=time.monotonic()
   # Remove stale derived artifacts so an old successful run cannot mask failure.
   for suffix in ('.raw','.log'):
    cir.with_suffix(suffix).unlink(missing_ok=True)
   proc=subprocess.run([exe,'-b',str(cir)],cwd=out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=a.timeout)
   logfile=cir.with_suffix('.log');blob=logfile.read_bytes() if logfile.exists() else proc.stdout
   log=blob.decode('utf-16' if blob.startswith((b'\xff\xfe',b'\xfe\xff')) else ('utf-16-le' if b'\x00' in blob[:100] else 'utf-8'),errors='replace')
   (out/'verification'/('LTspice_'+name+'.log')).write_text(log,encoding='utf-8')
   ok=proc.returncode==0 and 'fatal error' not in log.lower() and cir.with_suffix('.raw').is_file()
   runs.append(dict(circuit=name,ok=ok,returncode=proc.returncode,elapsed_s=time.monotonic()-start,netlist_sha256=hashlib.sha256(cir.read_bytes()).hexdigest()))
   if not ok:
    (out/'verification/simulation_runs.json').write_text(json.dumps(runs,indent=2))
    raise RuntimeError(f'{name} failed. See {out / "verification" / ("LTspice_"+name+".log")}')
 report=dict(python=sys.version,source_root=str(ROOT),output_dir=str(out),simulator=exe if a.simulate else None,runs=runs,inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'TL074_original.301',ROOT/'1N4148.lib',ROOT/'reference/circuit.cir',ROOT/'scripts/build_project.py',ROOT/'scripts/check_project.py']})
 (out/'verification/reproduction.json').write_text(json.dumps(report,indent=2))
 print('Done. Open',out/'DTMF4.asc',flush=True)
 print('Previews are rendered from ASC/ASY geometry. Simulation uses extracted CIR files; GUI hierarchy traversal is not verified.')
if __name__=='__main__':
 try:main()
 except (RuntimeError,subprocess.SubprocessError,FileNotFoundError,ModuleNotFoundError) as exc:print(f'ERROR: {exc}',file=sys.stderr);sys.exit(1)

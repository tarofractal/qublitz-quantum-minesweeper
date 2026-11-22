from __future__ import annotations

import argparse
import json
from pathlib import Path

from .experiments import Error
from .states import INPUTS


def main():
    parser = argparse.ArgumentParser(description="QUBLITZ 2026 Quantum Minesweeper")
    commands = parser.add_subparsers(dest="command", required=True)
    sim = commands.add_parser("simulate", help="Run all 150 cases")
    sim.add_argument("--shots", type=int, default=512)
    sim.add_argument("--seed", type=int, default=2026)
    sim.add_argument("--out", type=Path, default=Path("results"))
    sim.add_argument("--levels", type=int, nargs="+", choices=(1, 2, 3, 4), default=[1, 2, 3, 4])
    demo = commands.add_parser("demo", help="Step through a simulated recovery")
    demo.add_argument("--level", type=int, choices=(1, 2, 3), default=1)
    demo.add_argument("--input", choices=INPUTS, default="+i")
    demo.add_argument("--error", choices=("I", "X", "Z", "Y"), default="X")
    demo.add_argument("--location", type=int, default=1)
    demo.add_argument("--shots", type=int, default=512)
    demo.add_argument("--seed", type=int, default=2026)
    demo.add_argument("--out", type=Path, default=Path("results"))
    iqm = commands.add_parser("iqm", help="Prepare, run, retrieve or analyze IQM experiments")
    iqm.add_argument("--mode", choices=("prepare", "fake", "run", "retrieve", "analyze"), default="prepare")
    iqm.add_argument("--level", type=int, choices=(1, 4), default=4)
    iqm.add_argument("--input", choices=INPUTS, default="+i")
    iqm.add_argument("--error", choices=("I", "X", "Y", "Z"), default="Y")
    iqm.add_argument("--location", type=int, default=1)
    iqm.add_argument("--shots", type=int, default=32)
    iqm.add_argument("--seed", type=int, default=2026)
    iqm.add_argument("--url", help="IQM Server URL, otherwise IQM_SERVER_URL")
    iqm.add_argument("--computer", help="QPU name, otherwise IQM_QUANTUM_COMPUTER")
    iqm.add_argument("--job-id", help="For --mode retrieve")
    iqm.add_argument("--result-file", type=Path, help="For --mode analyze/retrieve")
    iqm.add_argument("--out", type=Path, default=Path("results/iqm-prepared"))
    comp=commands.add_parser("compare",help="Fair original/improved Level-4 experiment")
    comp.add_argument("--mode",choices=("prepare","simulate","run","retrieve","analyze","import-export"),default="prepare")
    comp.add_argument("--calibration",type=Path,default=Path("data/calibration.json"))
    comp.add_argument("--suite",choices=("balanced","locations","full"),default="balanced")
    comp.add_argument("--shots",type=int,default=256)
    comp.add_argument("--max-layouts",type=int,default=24)
    comp.add_argument("--transpiler-seeds",type=int,nargs="+",default=[7,19,43])
    comp.add_argument("--noise",action="store_true",help="Approximate calibration noise; simulation only")
    comp.add_argument("--noise-seed",type=int,default=49157)
    comp.add_argument("--include-placement",action="store_true",help="Add the placement-only ablation")
    comp.add_argument("--url")
    comp.add_argument("--computer")
    comp.add_argument("--connection-from",type=Path,default=Path("results/iqm-pilot/job.json"),
                      help="Reuse server/QPU configuration from the original pilot receipt; never reads a token")
    comp.add_argument("--pin-calibration",action="store_true",help="Request the snapshot's calibration set on the live device")
    comp.add_argument("--prompt-token",action="store_true",help="Read a missing IQM_TOKEN privately from the terminal")
    comp.add_argument("--result-file",type=Path)
    comp.add_argument("--export-file",type=Path,help="IQM dashboard export JSON; import-export mode only")
    comp.add_argument("--protocol-file",type=Path,default=Path("results/comparison-prepared/manifest.json"),
                      help="Fixed circuit-order manifest or original matching job receipt")
    comp.add_argument("--export-bit-order",choices=("measurement-keys","qiskit"),
                      help="Explicit export character convention; never inferred by maximizing success")
    comp.add_argument("--job-id",help="Job UUID for an imported export or retrieval without a saved receipt")
    comp.add_argument("--out",type=Path,default=Path("results/comparison-prepared"))
    args = parser.parse_args()
    if hasattr(args, "shots") and args.shots <= 0:
        parser.error("--shots must be positive")
    if args.command == "simulate":
        from .simulation import run_suite
        result = run_suite(args.out, args.shots, args.seed, tuple(dict.fromkeys(args.levels)))
        print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))
    elif args.command == "demo":
        from .demo import run_demo
        error = Error() if args.error == "I" else Error(args.error, args.location)
        run_demo(args.level, args.input, error, args.shots, args.seed, args.out)
    elif args.command=="compare":
        from .comparison import run_comparison
        run_comparison(args)
    else:
        from .hardware import run_iqm
        run_iqm(args)


if __name__ == "__main__":
    main()

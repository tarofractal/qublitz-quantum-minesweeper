# QUBLITZ 2026 — Quantum Minesweeper, improved IQM comparison

The original Levels 1–4 implementation is preserved. This update adds a verified shorter Level-4 circuit, calibration-aware placement, exact native-state checks and a fair original/improved IQM experiment.

**Archived physical pilot:** 24/32 expected `11` outcomes = **75% classification success** (95% Wilson 57.89–86.75%). The likely +i/Y1 configuration is inferred from the documented command; the supplied ZIP contains no physical pilot receipt/native circuit/layout. This is not logical-state fidelity.

**Improved physical circuit:** not run on IQM hardware in this environment. The prepared paired experiment is ready to submit on your authorized physical QPU.

| Evidence | Original | Improved |
|---|---:|---:|
| Native CZ instructions, verified offline target | 24 | **11** |
| Gate-layer depth | 45 | **17** |
| Native R instructions | 52 | **33** |
| Exact Level-4 input/error cases | 78/78 pass | 78/78 pass |
| Shared calibration-noise simulation, balanced I/X1/Y1/Z1 | 89.65% | **93.77%** |
| Archived physical IQM pilot | 75% (24/32) | No new physical result |

The calibrated simulation gain is **4.13 percentage points**, not a measured hardware gain. The ranking score is a heuristic. The 11-CZ result is a verified improvement over the reconstructed local baseline, not a proof of global optimality.

## Read first

- `docs/IMPROVEMENT_REPORT.pdf` / `.md`: current evidence, layouts, metrics, raw counts, confusion matrices, uncertainty and protocol.
- `docs/IMPROVEMENT_JA.pdf` / `.md`: short beginner Japanese explanation and three accurate English demo sentences.
- `results/improvement/`: raw evidence, all candidate scores, 234 compiled-native checks and held-out noise seeds.
- `results/comparison-prepared/`: eight interleaved native circuits, their exact layouts, metadata and ideal checks.
- `data/calibration.json`, `data/pilot-export.json`: the supplied inputs, unchanged.

The initial `docs/RESULTS.*`, `docs/BEGINNER_JA.*`, `docs/PRESENTATION_EN.*` and root archived simulation results are **v1 snapshots**. Their old “Not run” status describes the initial creation, before the user supplied physical pilot counts. Use the new improvement reports for current status. `docs/README_v1.md` preserves the original instructions.

## Setup and local reproduction

Use Python 3.12. From the project folder:

```bash
bash scripts/setup.sh
.venv/bin/python scripts/run_tests.py
bash scripts/reproduce_improvement.sh
```

The untouched baseline was run before source changes: **300 passed**. The updated suite has **718 passing tests**, zero failures/errors/skips. Baseline JUnit and the reproduced 150-case/76,800-shot output are under `results/improvement/baseline/`. All 78 Level-4 cases are checked on the original, placement-only and rewritten exact compiled circuits: **234 state/shot cases**, with data preservation verified after mapping physical wires back to source order. Both rewritten source encoders are additionally checked across all 78 cases.

The reproduction script runs the regression suite, the original 150 cases, the optimization and noise study, and report generation. It **does not submit any hardware job**. Dependencies remain pinned in `requirements-lock.txt`.

Individual commands:

```bash
.venv/bin/python scripts/improve_and_compare.py
.venv/bin/python scripts/report_improvement.py
.venv/bin/python -m minesweeper compare --mode prepare --shots 256 --out results/comparison-prepared
.venv/bin/python -m minesweeper compare --mode simulate --noise --noise-seed 49157 --shots 512 --out results/comparison-local-noise
```

## Next hardware command

Keep your existing `results/iqm-pilot` folder. Apply the source patch in place to the original 300-test release, or extract the full updated ZIP into a new folder and copy your original pilot receipt there. Do not overwrite or discard existing physical-job evidence. The old 13-CZ optimization patch is superseded; do not apply it on top of this release.

This command submits one interleaved comparison job: four cases (+i with I, X1, Y1, Z1), two variants, 256 shots each, **2048 total shots**:

```bash
.venv/bin/python -m minesweeper compare --mode run --calibration data/calibration.json --suite balanced --shots 256 --out results/iqm-comparison --prompt-token
```

Server/QPU configuration is read in order from `--url`/`--computer`, `IQM_SERVER_URL`/`IQM_QUANTUM_COMPUTER`, then `results/iqm-pilot/job.json`. For a receipt elsewhere, pass `--connection-from /absolute/path/to/original/results/iqm-pilot/job.json`. No token is read from or written to that file. `--prompt-token` privately prompts for a missing `IQM_TOKEN` in your terminal.

If no receipt is available, set the exact event/IQM URL and authorized **physical QPU name** you used for the original run:

```bash
export IQM_SERVER_URL='https://YOUR-ACTUAL-IQM-SERVER'
export IQM_QUANTUM_COMPUTER='YOUR-AUTHORIZED-PHYSICAL-QPU'
```

Both variants are compiled against the same live backend/calibration instance. The current topology is checked against the quality snapshot. The selected improved layout/seed is fixed before evaluation and reused across every input/error. By default the live backend's current calibration is used; snapshot identity matches/mismatches are saved. Use a fresh snapshot where possible. `--pin-calibration` optionally requests the attached snapshot's calibration ID if still supported by the device.

The runner validates native operations/connectivity, checks the exact native quantum state locally, and validates the IQM job definition before submitting. Only syndrome ancillas are measured. Explicit `HeraldingMode.NONE` preserves all shots for the primary metric.

If polling times out, retrieve the saved job rather than resubmitting:

```bash
.venv/bin/python -m minesweeper compare --mode retrieve --out results/iqm-comparison --prompt-token
.venv/bin/python -m minesweeper compare --mode analyze --result-file results/iqm-comparison/job.json
```

`job.json` contains the job ID immediately after submission. `submission.json` also guards uncertain submissions, so rerunning into the same directory cannot silently submit a duplicate. Use a new output directory only for a deliberately new experiment.

For a larger planned comparison, change `--shots 256` to `--shots 1024`. `--suite locations` compares all 13 error configurations on +i; `--suite full` compares all 78 cases. `--include-placement` adds the placement-only ablation. Circuit order alternates AB/BA case blocks in a single job. Check the total requested shots in the saved manifest before choosing a larger protocol.

The analysis saves raw histograms, per-case metrics, confusion counts, row-normalized confusion matrices, aggregate and macro-type success, Wilson intervals and the absolute change with a Newcombe/Wilson interval. All shots are retained. **Judge improvement against the matching original circuits in the new job, not by subtracting the old 32-shot pilot rate from a new balanced average.**

## Original pilot retrieval stays available

This existing workflow is unchanged (set the token privately as before):

```bash
.venv/bin/python -m minesweeper iqm --mode retrieve --result-file results/iqm-pilot/job.json
.venv/bin/python -m minesweeper iqm --mode analyze --result-file results/iqm-pilot/job.json
```

It is separate from `compare --mode retrieve`, which handles the new multi-circuit protocol.

## Why the circuit is shorter

The codewords are unchanged: `(0000+1111)/sqrt(2)` and `(0011+1100)/sqrt(2)`. A three-CNOT encoder prepares them using the chord of a six-qubit cycle. Conjugating the checks by two pair CNOTs reduces ZZZZ to Z1Z3 and XXXX to X0X2; inverse pair CNOTs restore the data. This is still a complete QND stabilizer extraction, not a precomputed answer.

The test error remains between complete encoding and extraction. The injection barriers stay in place. Only the experiment harness sees the injected Pauli/location or input label; the classifier reads the two syndrome bits. Exact isometry, complex-superposition, native-state and X/Z ordering tests guard these requirements.

The selected offline layout is `(d0,d1,d2,d3,aZ,aX) = (QB5,QB2,QB9,QB4,QB1,QB10)`. It has 11 CZs, no SWAP routing and depth 17. Live selection uses the available target and calibration rather than assuming those indices always apply.

## Bit order and evidence labels

- Source wires: q0–q3 are d0–d3, q4 is the ZZZZ ancilla, q5 the XXXX ancilla.
- Human syndrome: `(s0,s1)=(ZZZZ,XXXX)`, where 0=+1 and 1=−1.
- Qiskit count string: `s1s0`; I→00, X→01, Y→11, Z→10.
- Native physical layout and measurement sites are saved per compiled circuit; initial/final mappings can differ after routing.
- The old IQM UI export contains only a symmetric target `11`, so its off-diagonal raw 01/10 counts are not assigned X/Z labels without the original receipt or asymmetric controls. The updated Qiskit adapter mapping is explicitly tested with X and Z.
- Root `results/iqm-fake-noise` is an archived **generic fake-Garnet simulation**, not physical data and not the new calibration model.
- `results/improvement/noise-*` uses the same approximate calibration-informed model for all candidates, with held-out seeds 49157/82799.
- `data/pilot-export.json` is the archived **user-supplied hardware export**. Improved hardware results do not exist until you run the new job.

## Calibration/noise limitations

Parsing checks the snapshot timestamp, validity, finite values, units, duplicates and required metrics. It reads unheralded asymmetric readout errors and PRX/CZ fidelities for 20 qubits/30 links. The snapshot topology matches the offline target; physical pilot calibration linkage is unknown.

Layout ranking uses conservative gate estimates and worst-bit readout error as a **heuristic**, not a predicted accuracy. Evaluation noise is a separate independent-depolarizing/asymmetric-readout approximation. It treats exported fidelities as average gate fidelities and assigns one PRX metric to each native R. Pulse durations are absent, so no guessed idle/T1/T2 timing is used. Leakage, crosstalk, coherent errors, initialization faults and drift are omitted. This model cannot guarantee a physical rate of 93.77%.

Current exact-Aer comparison supports Crystal-style IQM qubit targets. Resonator/MOVE targets are rejected before submission rather than simulated incorrectly.

## Preserved Levels 1–3 and teaching demo

```bash
.venv/bin/python -m minesweeper simulate --shots 512 --seed 2026
.venv/bin/python -m minesweeper demo --level 1 --input +i --error X --location 1 --shots 512
.venv/bin/python -m minesweeper demo --level 2 --input +i --error Z --location 1 --shots 512
.venv/bin/python -m minesweeper demo --level 3 --input + --error Y --location 1 --shots 512
```

The offline Japanese `docs/live-demo.html` and initial tutorial files remain available as v1 teaching artifacts. For current hardware claims and three short English sentences, use `docs/IMPROVEMENT_JA.md`. The challenge PDF remains in `docs/source/challenge.pdf`.

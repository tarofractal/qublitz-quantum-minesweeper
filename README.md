# QUBLITZ 2026 - Quantum Minesweeper

Levels 1-4, exhaustive quantum-state verification, an 11-CZ Level-4 classifier, and reproducible analysis of the supplied IQM hardware results.

**Current hardware evidence:** the supplied 8-circuit / 2048-shot export, assigned using the saved Run Ready protocol, gives **759/1024 = 74.12% original** and **921/1024 = 89.94% improved**, a **+15.82 percentage-point** change (approximate 95% interval +12.55 to +19.07 points). All shots are retained. This is **syndrome-classification success**, not logical-state fidelity.

**Execution evidence:** the supplied terminal transcript records the comparison command on IQM **Garnet**, `--suite balanced --shots 256`, the returned job ID `01a20070-6eb5-7033-942a-a41474a1922e`, and the SDK analysis reporting the same **+15.8203125 percentage-point** change. See [the sanitized execution log](docs/iqm-execution-log.txt) and [its machine-readable evidence](data/iqm-comparison-01a20070/execution-evidence.json). The original 32-shot pilot's retrieved analysis JSON is also preserved in `data/pilot-sdk-analysis-from-transcript.json`.

**Provenance:** this is now supported by the recorded execution command and matching job ID, in addition to the prepared eight-circuit protocol and asymmetric X/Z controls. The dashboard export itself has no experiment labels. The full submitted native-circuit payload, live layout and run-time calibration linkage are still unavailable; they must not be inferred from the offline compilation. No additional physical job was submitted while preparing this repository.

| Evidence source | Original | Improved |
|---|---:|---:|
| Supplied hardware export, protocol-reconstructed assignment | 759/1024 = 74.12% | 921/1024 = 89.94% |
| 95% Wilson interval for those counts | 71.35-76.71% | 87.95-91.64% |
| Verified offline native compilation, +i/Y1 example | 24 CZ, 52 R, depth 45 | 11 CZ, 33 R, depth 17 |
| Ideal exact-native Level-4 cases | 78/78 pass | 78/78 pass |
| Archived calibration-noise simulation, balanced four types | 89.65% | 93.77% |
| Earlier archived 32-shot physical pilot, likely +i/Y1 | 24/32 = 75% | Not included in that job |

The 11-CZ circuit is a verified improvement over the reconstructed local baseline, not a claim of global optimality. Offline topology matches the supplied calibration; live identity/layout linkage cannot be established from a count export. Hardware causes are not isolated by the combined rewrite/placement experiment.

## Start here

From the extracted `quantum-minesweeper` folder, with Python 3.12:

```bash
bash scripts/setup.sh
bash scripts/reproduce_submission.sh
```

The second command checks dependencies, runs the full test suite, regenerates 150 input/error cases at 512 ideal shots each, imports the physical counts, replays all eight exact saved native circuits, and builds current reports and the live demo. **It does not submit a hardware job.** The included test evidence gives the actual test count and outcomes in `results/test-outcome.json` and `results/pytest.txt`.

Current materials:

- `docs/iqm-execution-log.txt`: normalized comparison command/output and retrieved pilot JSON from the user-supplied terminal transcript; account names, hostnames, local paths and credential-entry interactions are omitted.
- `data/iqm-comparison-01a20070/execution-evidence.json`: requested Garnet backend, balanced protocol, shots, returned job ID, exported-count fingerprint and the transcript's comparison-analysis JSON.

- `docs/SUBMISSION_REPORT.pdf` / `.md` / `.html`: current submission report, requirements, circuits, evidence limits, metrics, raw counts, confidence intervals and exact commands.
- `docs/HARDWARE_JA.pdf` / `.md`: beginner Japanese explanation and three English demo sentences.
- `docs/LIVE_PRESENTATION_EN.pdf` / `.md`: short script, demonstration steps and judge questions.
- `docs/live-demo.html`: offline interactive Japanese state walkthrough, with a separately labeled hardware-results section.
- `results/iqm-hardware-analysis/`: unchanged/normalized counts, per-case CSV, analysis, confusion matrices and exact native replay.
- `data/iqm-comparison-01a20070/export.json`: byte-for-byte supplied new hardware export.
- `results/comparison-prepared/`: unchanged Run Ready protocol, QPY/QASM native circuits, layouts and ideal checks.
- `docs/source/challenge.pdf`: authoritative eight-page challenge PDF, identical to the latest supplied attachment.

The earlier `docs/RESULTS.*`, `BEGINNER_JA.*`, `PRESENTATION_EN.*`, `IMPROVEMENT_REPORT.*` and `IMPROVEMENT_JA.*` are **dated prior-stage records**. Their old hardware status describes those stages. `SUBMISSION_REPORT.*` contains the current count analysis and verification; it predates the newly supplied terminal transcript. For the additional command/job-ID evidence, use this README and `docs/iqm-execution-log.txt`. The old README is retained in `docs/README_before_physical_comparison.md`; the original development README is `docs/README_v1.md`.

## Import the supplied hardware result explicitly

```bash
.venv/bin/python -m minesweeper compare --mode import-export \
  --export-file data/iqm-comparison-01a20070/export.json \
  --protocol-file results/comparison-prepared/manifest.json \
  --export-bit-order measurement-keys \
  --job-id 01a20070-6eb5-7033-942a-a41474a1922e \
  --out results/iqm-hardware-analysis
```

`measurement-keys` means exported character j corresponds to `measurement_keys[j]`. Here the keys are `syn_2_0_0`, `syn_2_0_1`. The importer keeps the original export and normalizes to Qiskit's reversed display order; it never silently swaps bits to increase accuracy. `--export-bit-order qiskit` is for exports that already use Qiskit display strings, not for this file.

| Type | Human `(ZZZZ,XXXX)` bits | This export's declared key order | Qiskit `syn1syn0` |
|---|---|---|---|
| I | 00 | 00 | 00 |
| X | 10 | 10 | 01 |
| Y | 11 | 11 | 11 |
| Z | 01 | 01 | 10 |

The classifier receives only the two measured bits. Input/error/location labels belong to preparation and scoring, never classification. Both asymmetric controls are checked. All per-case results retain the input, error, location, expected/observed syndromes, raw counts, success rates and intervals.

## Retrieve the completed comparison without resubmitting

If the original execution folder contains `results/iqm-comparison/job.json`, preserve it and use:

```bash
.venv/bin/python -m minesweeper compare --mode retrieve \
  --out results/iqm-comparison --prompt-token
```

If that receipt is missing, use the original event connection settings and the completed job ID:

```bash
export IQM_SERVER_URL='YOUR_ORIGINAL_EVENT_SERVER_URL'
export IQM_QUANTUM_COMPUTER='YOUR_ORIGINAL_QPU_NAME'
.venv/bin/python -m minesweeper compare --mode retrieve \
  --job-id 01a20070-6eb5-7033-942a-a41474a1922e \
  --protocol-file results/comparison-prepared/manifest.json \
  --out results/iqm-comparison-retrieved --prompt-token
```

The SDK reads `IQM_TOKEN` / `IQM_TOKENS_FILE` privately if configured, or prompts without echoing a token. Credentials are not written to code, reports or receipts. Avoid passing an environment token a second time as a provider argument; the Run Ready authentication fix is retained.

Retrieval writes `job.json` and `iqm-result.json`, including the actual submitted IQM circuits, parameters, calibration IDs and server timeline exposed by the installed SDK. **Audit their circuit names/order, physical instructions, measurements and calibration against the prepared packet.** Retrieval counts alone do not certify a reconstructed protocol. Import with the genuine receipt as `--protocol-file` when available. A pending fetch retains the job ID and can be retried with the same command; do not submit again merely because polling times out.

The old single-pilot workflow is preserved:

```bash
.venv/bin/python -m minesweeper iqm --mode retrieve \
  --out results/iqm-pilot --job-id 01a1fff5-31e3-744f-89da-cb1d14f7bacb
```

That command requires its original `job.json` (or `--result-file`) and connection/credential settings. The old 32-shot export cannot establish X/Z ordering because its expected Y syndrome is symmetric 11.

## Optional future hardware comparison

The existing results can be analyzed without spending more hardware shots. For a separately authorized repeat, use a **new output folder**:

```bash
.venv/bin/python -m minesweeper compare --mode run \
  --calibration data/calibration.json --suite balanced --shots 256 \
  --out results/iqm-repeat-new --prompt-token
```

Configure the authorized server/QPU first. The runner loads the live backend, validates its topology/native gates, chooses one layout/seed per variant using calibration only, verifies every submitted circuit locally, and sends eight circuits in one job. Cases are +i with I, X1, Y1 and Z1, ordered original/improved, improved/original, original/improved, improved/original. Same device, shot counts and case sets; heralding/post-selection disabled. No comparison-specific noisy outcomes tune the placement.

`--suite locations` gives all 13 configurations on +i; `--suite full` gives 78 cases per variant. `--include-placement` adds the placement-only ablation. Review shot budgets before using those larger suites. `--pin-calibration` requests the snapshot's ID if the server supports it; otherwise the current backend calibration mismatch is recorded. Pulse durations are absent from the supplied snapshot, so no physical time estimate is invented. MOVE/resonator backends are rejected by the exact-Aer path.

## Verification and teaching commands

```bash
.venv/bin/python scripts/run_tests.py
.venv/bin/python -m minesweeper simulate --shots 512 --seed 2026 --out results/submission-simulation
.venv/bin/python scripts/analyze_hardware.py
.venv/bin/python scripts/report_submission.py
.venv/bin/python -m minesweeper demo --level 1 --input +i --error X --location 1 --shots 512 --out results/submission-demo
.venv/bin/python -m minesweeper demo --level 2 --input +i --error Z --location 1 --shots 512 --out results/submission-demo
.venv/bin/python -m minesweeper demo --level 3 --input + --error Y --location 1 --shots 512 --out results/submission-demo
```

All six logical inputs and every permitted error are covered: 24 cases per recovery level and 78 Level-4 cases. Exact state comparisons and finite-shot inverse-preparation checks are distinct metrics. Levels 1-3 also restore both logical basis states with the same phase, giving arbitrary-amplitude recovery by linearity. The Level-4 extraction isometry agrees on all 16 data columns; the final data equals its post-error encoded state in ideal simulation.

The original 300-test baseline and original 150-case output are archived in `results/improvement/baseline/`. The pre-import improved suite and Run Ready suite each passed 718 tests. Current regression adds real-export analysis, strict bit-order/shot validation, QPY reload layout checks, authentication precedence, and retrieval-without-resubmission tests. The reproducible seeded calibration-noise study remains available:

```bash
bash scripts/reproduce_improvement.sh
```

That is the **earlier offline study**, with model limitations documented in `docs/IMPROVEMENT_REPORT.md`. It regenerates the prepared protocol; retain the packet corresponding to a physical run before recompiling. The current hardware import never recompiles or selects a new packet to fit the counts.

## Submission status

The supplied hardware export supports Level-4 classification under the saved protocol assignment. Hardware logical-state fidelity and Level-1-3 recovery were not measured. Before submitting: recover/audit the original hardware receipt and native circuit to verify configuration/backend/calibration linkage, publish this repository with the raw evidence, and rehearse the live demonstration. Perfect hardware accuracy is not required by the challenge PDF.

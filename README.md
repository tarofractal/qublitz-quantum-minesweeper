# QUBLITZ 2026 - Quantum Minesweeper

Levels 1-4, exhaustive quantum-state verification, an 11-CZ Level-4 classifier, and reproducible analysis of the supplied IQM hardware results.

**Current hardware evidence:** the supplied 8-circuit / 2048-shot export, assigned using the saved Run Ready protocol, gives **759/1024 = 74.12% original** and **921/1024 = 89.94% improved**, a **+15.82 percentage-point** change (approximate 95% interval +12.55 to +19.07 points). All shots are retained. This is **syndrome-classification success**, not logical-state fidelity.

**Execution evidence:** the original completed [job receipt](results/iqm-comparison/job.json), [client-saved native definition](results/iqm-comparison/iqm-job-definition.json), and execution QPY are now included. They identify IQM **Garnet**, eight balanced circuits, 256 shots each, and job `01a20070-6eb5-7033-942a-a41474a1922e`. The complete original [execution archive](data/iqm-comparison-01a20070/execution-artifacts.zip) is preserved. The [local receipt audit](results/iqm-hardware-analysis/receipt-audit.json) checks every native instruction, layout, calibration ID and dashboard/SDK count. The [terminal excerpt](docs/iqm-execution-log.txt) remains supporting evidence; the original 32-shot pilot analysis is in `data/pilot-sdk-analysis-from-transcript.json`.

**Provenance:** the completed receipt supplies the actual experiment order and labels. Re-serializing all eight execution QPY circuits with the pinned IQM SDK exactly reproduces every instruction in the client-saved native definition, including physical loci, angles and measurement keys. Dashboard counts converted from measurement-key order exactly equal the SDK receipt counts in every circuit; X/Z controls also agree. The snapshot, recorded live target, native definition and SDK-reported result share calibration ID `ea681de1-9661-41e5-bd6f-cb524fa056a6`. These are local checks of user-supplied runtime records; no fresh server query or new hardware job was performed. The independently server-returned `iqm-result.json` was not supplied, and hardware logical-state fidelity was not measured.

| Evidence source | Original | Improved |
|---|---:|---:|
| Supplied hardware export matched to completed execution receipt | 759/1024 = 74.12% | 921/1024 = 89.94% |
| 95% Wilson interval for those counts | 71.35-76.71% | 87.95-91.64% |
| Verified execution artifacts, +i/Y1 example | 24 CZ, 52 R, depth 45 | 11 CZ, 33 R, depth 17 |
| Ideal exact-native Level-4 cases | 78/78 pass | 78/78 pass |
| Archived calibration-noise simulation, balanced four types | 89.65% | 93.77% |
| Earlier archived 32-shot physical pilot, likely +i/Y1 | 24/32 = 75% | Not included in that job |

The receipt binds the original/improved classification comparison to the supplied hardware counts. In the recorded execution, syndrome sites `(s0,s1)` are `(QB2,QB4)` for original and `(QB1,QB10)` for improved. Initial improved source wires `(d0,d1,d2,d3,a0,a1)` occupy `(QB5,QB2,QB9,QB4,QB1,QB10)`. The prior offline packet remains in `results/comparison-prepared/`; its binary fingerprint differs from the execution packet, so current hardware analysis uses `results/iqm-comparison/` directly. No claim of globally optimal compilation or an isolated causal explanation of the gain is made.

## Start here

From the extracted `quantum-minesweeper` folder, with Python 3.12:

```bash
bash scripts/setup.sh
bash scripts/reproduce_submission.sh
```

The second command checks dependencies, runs the full test suite, regenerates 150 input/error cases at 512 ideal shots each, imports the physical counts, replays all eight exact saved native circuits, and rebuilds teaching materials. For analysis only, run `.venv/bin/python scripts/analyze_hardware.py`; this audits the receipt and replays the exact execution packet without generating a new PDF report. **It does not submit a hardware job.** The included test evidence gives the actual test count and outcomes in `results/test-outcome.json` and `results/pytest.txt`.

Current materials:

- `docs/iqm-execution-log.txt`: normalized comparison command/output and retrieved pilot JSON from the user-supplied terminal transcript; account names, hostnames, local paths and credential-entry interactions are omitted.
- `data/iqm-comparison-01a20070/execution-evidence.json`: requested Garnet backend, balanced protocol, shots, returned job ID, exported-count fingerprint and the transcript's comparison-analysis JSON.

- `docs/SUBMISSION_REPORT.pdf` / `.md` / `.html`: current submission report, requirements, circuits, evidence limits, metrics, raw counts, confidence intervals and exact commands.
- `docs/HARDWARE_JA.pdf` / `.md`: beginner Japanese explanation and three English demo sentences.
- `docs/LIVE_PRESENTATION_EN.pdf` / `.md`: short script, demonstration steps and judge questions.
- `docs/live-demo.html`: offline interactive Japanese state walkthrough, with a separately labeled hardware-results section.
- `results/iqm-hardware-analysis/`: unchanged/normalized counts, per-case CSV, analysis, confusion matrices and exact native replay.
- `data/iqm-comparison-01a20070/export.json`: byte-for-byte supplied new hardware export.
- `results/iqm-comparison/`: byte-preserved original execution receipt, native definition, QPY/QASM circuits, layouts and original analysis.
- `results/iqm-hardware-analysis/receipt-audit.json`: reproducible receipt/native/count/calibration checks.
- `results/comparison-prepared/`: separate prior offline protocol and circuits, retained as historical evidence.
- `docs/source/challenge.pdf`: authoritative eight-page challenge PDF, identical to the latest supplied attachment.

The earlier `docs/RESULTS.*`, `BEGINNER_JA.*`, `PRESENTATION_EN.*`, `IMPROVEMENT_REPORT.*` and `IMPROVEMENT_JA.*` are **dated prior-stage records**. Their old hardware status describes those stages. `SUBMISSION_REPORT.*` predates the terminal transcript and newly supplied execution archive. Its missing-receipt qualifications describe that earlier stage. For current receipt verification, use this README and `results/iqm-hardware-analysis/receipt-audit.json`. No new PDF report was generated for this update. The old README is retained in `docs/README_before_physical_comparison.md`; the original development README is `docs/README_v1.md`.

## Import the supplied hardware result explicitly

```bash
.venv/bin/python -m minesweeper compare --mode import-export \
  --export-file data/iqm-comparison-01a20070/export.json \
  --protocol-file results/iqm-comparison/job.json \
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

The original execution folder is now preserved in `results/iqm-comparison/`. Local analysis needs no IQM credentials. To optionally retrieve additional server-returned evidence for this same job, preserve these originals and use:

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

The original 300-test baseline and original 150-case output are archived in `results/improvement/baseline/`. The pre-import improved suite and Run Ready suite each passed 718 tests. The pre-receipt baseline passed 744 tests; the current suite passed **803 tests**, zero failures/errors/skips. Current regression adds real-export analysis, strict bit-order/shot validation, QPY reload layout checks, authentication precedence, retrieval-without-resubmission tests, receipt/definition/calibration binding, and six-input isometry probes on each of the eight execution circuits. QPY initial-layout reading uses the unfiltered input-index mapping before slicing; it avoids Qiskit 2.1.2 dictionary-order failures without changing any archived circuit gates. These additional input probes are ideal simulations, not additional hardware cases. The reproducible seeded calibration-noise study remains available:

```bash
bash scripts/reproduce_improvement.sh
```

That is the **earlier offline study**, with model limitations documented in `docs/IMPROVEMENT_REPORT.md`. It regenerates the prepared protocol; retain the packet corresponding to a physical run before recompiling. The current hardware import never recompiles or selects a new packet to fit the counts.

## Submission status

The supplied hardware counts now match the completed original receipt and client-saved native definition. Experiment assignment, physical measurement sites and recorded calibration linkage pass the local audit. Hardware logical-state fidelity and Level-1-3 recovery were not measured. Before submitting, give judges access to this currently private repository (or review its contents and make it public) and rehearse the live demonstration. A fresh server retrieval can add independently returned native/timeline evidence, but another hardware submission is unnecessary for this audit. Perfect hardware accuracy is not required by the challenge PDF.

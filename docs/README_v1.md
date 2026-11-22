# QUBLITZ 2026 — Quantum Minesweeper

Levels 1–4 implemented and verified across **150 input/error cases**. The attached challenge PDF (8 pages) is the requirements authority. The project includes exact state checks, real finite-shot Aer executions, a Japanese interactive teaching demo, circuit artifacts, a short English presentation script, and an IQM runner.

**IQM hardware status: Not run on IQM hardware.** No authenticated QPU endpoint/token was available in the creation environment. IQM fake backends are explicitly labeled simulations. The hardware requirement in PDF pp. 5–6 is still outstanding.

## Start here

Extract the project, open a terminal in `quantum-minesweeper`, and run the first command:

```bash
bash scripts/setup.sh
```

Use **Python 3.12**. Setup installs the pinned, mutually compatible dependencies into `.venv`. No IQM credentials are needed for local work.

```bash
.venv/bin/python scripts/run_tests.py
.venv/bin/python -m minesweeper simulate --shots 512 --seed 2026
.venv/bin/python -m minesweeper demo --level 1 --input +i --error X --location 1 --shots 512
```

Open `docs/live-demo.html` in a browser for the self-contained Japanese visual demo. It uses precomputed Qiskit amplitudes and saved simulation results, and needs no server. Read `docs/BEGINNER_JA.md` for the lesson and `docs/PRESENTATION_EN.md` for the presentation. `docs/RESULTS.md` and `docs/RESULTS.pdf` contain the generated report. All are included in the ZIP.

Regenerate tests, all results, the three walkthroughs, the IQM preflight, the illustrative noise experiment, and the documents:

```bash
bash scripts/reproduce.sh
```

Optional JavaScript artifact checks use Node 24 and pinned development tools:

```bash
npm install
npm run check:demo:dom
npx playwright install chromium
npm run check:demo:browser
```

The DOM interaction check was run successfully for 72 repetition selections and all 78 Level-4 selections. The rendered-browser check could not launch Chromium in the creation environment because local sockets were restricted; browser layout is not claimed as tested. PDF pages were rendered and reviewed. Python simulation and IQM execution do not require Node.

The exact Linux/Python 3.12 environment is also frozen in `requirements-lock.txt`:

```bash
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e . --no-deps
```

The public IQM adapter is now distributed as `iqm-client[qiskit]`. Do not install the deprecated standalone `qiskit-iqm` distribution in this environment. See `docs/SOURCES.md`.

## Results already produced

| Level | Allowed errors | Inputs | Cases | Ideal check | Finite-shot result |
|---|---|---|---:|---|---|
| 1 | I, X0, X1, X2 | 0, 1, +, −, +i, −i | 24 | Decoded fidelity 1 | 512/512 per case |
| 2 | I, Z0, Z1, Z2 | Same six | 24 | Decoded fidelity 1 | 512/512 per case |
| 3 | I, Y0, Y1, Y2 | Same six | 24 | Decoded fidelity 1 | 512/512 per case |
| 4 | I; X, Y, Z on any of d0–d3 | Same six | 78 | Classification and data preservation | 512/512 per case |

Floating point deviations are below 1e-10. The 76,800 ideal simulator shots use no post-selection. The saved test run has **300 passing tests**, including 72 actual measured/feed-forward state checks and eight routed IQM-target circuit checks. These totals count additional checks beyond the 150 promised input/error cases. See `results/test-outcome.json` and `results/pytest.xml`.

The deliberate Level-3 control applies X recovery to a Y error on input `+`: computational-basis probabilities remain 50/50, but recovered-state fidelity is 0. The correct Y recovery gives fidelity 1.

## Qubit and bit order

| Item | Explicit order |
|---|---|
| Human three-data-qubit ket | d0 d1 d2 = left middle right |
| Levels 1–3 source wires | q0=d0, q1=d1, q2=d2, q3=a0, q4=a1 |
| Levels 1–3 human syndrome | (s0,s1) = (left–middle, middle–right) |
| Level 4 source wires | q0–q3=d0–d3, q4=a0 for ZZZZ, q5=a1 for XXXX |
| Level 4 human syndrome | (s0,s1) = (ZZZZ bit, XXXX bit), 0→+1, 1→−1 |
| Qiskit statevector ket | Highest-index qubit first, opposite to the human ket |
| Levels 1–3 raw count string | `v2v1v0 s1s0`, e.g. left error → `000 01` |
| Level 4 raw count string | `s1s0`, e.g. X → `01`, Z → `10` |
| Native IQM physical mapping | Saved per compilation in `backend.json`, including device names, initial/final layouts and actual measurement sites |

Source wire indices are logical circuit indices, not fixed IQM chip addresses. Routing can move their states. Never infer physical hardware addresses from `d0`, and never read raw `s1s0` as human `s0s1`.

## Circuit design and information boundary

`circuits.py` implements encoding, extraction, recovery and classification. Recovery receives only the level and a measured syndrome or syndrome ancillas. It never receives the actual injected error, its location, or the input-state label. `experiments.py` is the test harness: it prepares an input, calls the separate injection function at a marked boundary, and later checks the result against known truth.

Levels 1–3 have two equivalent recovery implementations. The default simulator circuit measures both ancillas and uses Qiskit `if_test` branches. The coherent implementation leaves the syndrome in the ancillas and uses controlled X or Y gates, then measures at the end. Neither assumes a revealed error location. The Level-1 hardware option uses coherent recovery because the generic two-bit branches are not assumed to be supported by IQM.

Level 2 applies H to all data qubits after repetition encoding, injects Z there, and applies H again before the Level-1 checks. Recovery is X in that rotated-back basis. Verification is after repetition decoding, before applying the inverse preparation as a measurement test.

Level 3 uses the promised Y-only model. Its bit-parity syndrome finds the location; Y on that location repairs both components. Independent X and Z errors, or two errored qubits, are outside the promise.

Level 4 uses `(0000+1111)/sqrt(2)` and `(0011+1100)/sqrt(2)`. Only syndrome ancillas are measured; data remains encoded. It classifies the error type and does not claim to locate or correct it.

## IQM: inspect and run

The default hardware candidate is a complete six-qubit **Level-4 classifier**, with input `+i` and a Y error on d1. It reads only q4 and q5. All measurements are terminal. No mid-circuit measurement, reset, classical feed-forward, input inversion, or data measurement is needed.

The following offline preparation uses IQM's 20-qubit Garnet *fake target*. It compiles against the target's R/CZ gates and coupling map, validates native operations and routing, and simulates the precise routed circuit that would be submitted:

```bash
.venv/bin/python -m minesweeper iqm --mode prepare --level 4 --input +i --error Y --location 1 --shots 32 --out results/iqm-prepared
```

An optional illustrative local noise experiment is separate from the actual hardware path:

```bash
.venv/bin/python -m minesweeper iqm --mode fake --level 4 --input +i --error Y --location 1 --shots 512 --out results/iqm-fake-noise
```

This mode uses seeded Aer with the official fake target's native R/CZ noise model. The installed IQM fake-backend convenience `run` method ignores the seed option, so it is deliberately bypassed for reproducible noise sampling; identical-circuit/seed counts are regression-checked.

For real IQM execution, get the exact server URL and authorized **physical QPU name** from the event/IQM dashboard. This project has no event starter code or backend address in its source PDF. Set the public configuration in your shell, substituting those actual values:

```bash
export IQM_SERVER_URL='https://YOUR-ACTUAL-IQM-SERVER'
export IQM_QUANTUM_COMPUTER='YOUR-AUTHORIZED-PHYSICAL-QPU'
```

Enter the token privately and submit a **32-shot pilot** using `getpass`, so the token is not printed or saved in shell history:

```bash
.venv/bin/python - <<'PY'
import getpass, os, subprocess, sys
os.environ['IQM_TOKEN'] = getpass.getpass('IQM token (hidden): ')
subprocess.run([sys.executable, '-m', 'minesweeper', 'iqm',
  '--mode', 'run', '--level', '4', '--input', '+i', '--error', 'Y',
  '--location', '1', '--shots', '32', '--out', 'results/iqm-pilot'], check=True)
PY
```

The runner checks the live backend's qubit count, native operations and coupling map, compiles the source, simulates the **exact compiled circuit**, validates IQM serialization, then submits one job. `backend.json`, source/native `.qpy`, source/native OpenQASM when exportable, and diagrams are retained. `job.json` records the job ID immediately after submission, before waiting for the result.

If the result is still pending after 60 seconds, retrieve that job rather than resubmitting. Repeat the private token-entry wrapper above with this argument list:

```python
[sys.executable, '-m', 'minesweeper', 'iqm', '--mode', 'retrieve',
 '--result-file', 'results/iqm-pilot/job.json']
```

Analyze saved counts independently; this command needs no credentials:

```bash
.venv/bin/python -m minesweeper iqm --mode analyze --result-file results/iqm-pilot/job.json
```

Inspect the pilot's `analysis.json`, counts and 95% Wilson interval. For the full run, use the private token wrapper again with `--shots 1024 --out results/iqm-full`. A 32-shot pilot is already a real challenge-circuit execution if it completed on a physical IQM QPU; the larger run gives a clearer success estimate. Include both if performed. Do not average selected shots or silently discard errors. The runner uses no heralding or post-selection.

The live runner supports IQM **Crystal-style targets whose native routed circuits can be verified with Aer**. If MOVE/resonator instructions appear, it stops before submitting because Aer cannot faithfully model those as ordinary qubit gates. Choose an authorized Crystal QPU or implement a resonator-aware simulation before using a Star device. No live QPU availability is assumed here.

On a five-qubit Crystal QPU, the coherent Level-1 alternative is:

```bash
.venv/bin/python -m minesweeper iqm --mode prepare --level 1 --input +i --error X --location 1 --shots 32 --out results/iqm-L1-prepared
```

Use the same private token wrapper with `--mode run --level 1 --error X` to submit it. Its raw expected result is `000 11`. This circuit corrects and decodes the state, applies the inverse preparation and checks return to 000. Three doubly controlled recovery gates make it deeper than the Level-4 classifier.

## Results and project map

| Path | Content |
|---|---|
| `src/minesweeper/circuits.py` | Quantum primitives and syndrome-only recovery/classification |
| `src/minesweeper/experiments.py` | Separate state preparation and error injection |
| `src/minesweeper/verification.py` | Quantum-state fidelity, QND comparison, bit parsing, shot analysis |
| `src/minesweeper/hardware.py` | IQM compilation, pilot/run/retrieve/analyze |
| `tests/` | All promised cases, feed-forward density matrices, global-phase proof checks, bit ordering, IQM compilation |
| `results/simulation.json` | Every input/error, expected/observed syndrome, fidelity, raw counts, metrics |
| `results/cases.csv` | Portable per-case table |
| `results/pytest.*`, `test-outcome.json` | Actual test execution evidence |
| `results/circuits/` | Per-level diagrams and executable QPY/OpenQASM |
| `results/iqm-prepared/` | Local IQM target metadata, exact native circuit, 32-shot preflight |
| `results/iqm-fake-noise/` | Explicitly simulated illustrative noise results |
| `docs/` | Report, Japanese lesson, live HTML demo, English script, official references |
| `docs/source/` | Entire provided PDF, complete text extraction, source fingerprint |

## Finish the submission

1. Run a challenge circuit on an authorized physical IQM QPU and retain its job receipt, raw counts, compiled circuit, backend metadata and analysis.
2. Explain the actual simulation/experiment difference. Gate errors, measurement errors and decoherence are possible explanations; a single histogram cannot identify their individual contributions. No device fidelity is inferred from the Level-4 syndrome histogram.
3. Regenerate `docs/RESULTS.md`/PDF with `python scripts/build_deliverables.py`; it includes completed IQM receipts automatically. Check source labels in the report.
4. Create a GitHub repository, add the project files including result evidence, and push. The repository has not been published automatically.
5. Present `docs/live-demo.html`, run the CLI demo, and use `docs/PRESENTATION_EN.md` for a short explanation.

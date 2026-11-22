"""Build current submission materials from physical exports and actual checks.

The older improvement study remains a dated pre-hardware record. This report
is the current entry point and does not turn reconstructed metadata into a
verified submission receipt.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT / "results/iqm-hardware-analysis"
TYPES = ("I", "X", "Y", "Z")


def load(path):
    return json.loads(path.read_text())


def pct(value):
    return f"{100 * value:.2f}%"


def ci(bounds):
    return f"{100 * bounds[0]:.2f}-{100 * bounds[1]:.2f}%"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
                      + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def figures(analysis):
    colors = ("#607d8b", "#168b73")
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.4))
    x = np.arange(4)
    for offset, (variant, color) in enumerate(zip(("original", "improved"), colors)):
        rows = {row["injected_error"]: row for row in analysis["variants"][variant]["cases"]}
        rates = np.array([rows[t]["classification_success_rate"] for t in TYPES])
        bounds = [rows[t]["joint_success_wilson_95"] for t in TYPES]
        err = 100 * np.array([[p - b[0] for p, b in zip(rates, bounds)], [b[1] - p for p, b in zip(rates, bounds)]])
        positions = x + (offset - .5) * .35
        axes[0].bar(positions, 100 * rates, width=.34, label=variant.capitalize(), color=color, yerr=err, capsize=3)
    axes[0].set_xticks(x, TYPES)
    axes[0].set_ylabel("Correct syndrome classification (%)")
    axes[0].set_ylim(0, 106)
    axes[0].legend(frameon=False)
    axes[0].set_title("Each case: +i, error on d1, 256 shots")
    groups = [analysis["variants"][v] for v in ("original", "improved")]
    values = [g["success_rate"] for g in groups]
    error = 100 * np.array([[p - g["wilson_95"][0] for p, g in zip(values, groups)],
                            [g["wilson_95"][1] - p for p, g in zip(values, groups)]])
    axes[1].bar([0, 1], 100 * np.array(values), color=colors, yerr=error, capsize=5)
    for i, group in enumerate(groups):
        axes[1].text(i, 100 * values[i] + 4, f"{pct(values[i])}\n{group['successes']}/{group['shots']}", ha="center", fontsize=10)
    axes[1].set_xticks([0, 1], ["Original", "Improved"])
    axes[1].set_ylim(0, 108)
    axes[1].set_title("Balanced aggregate; all shots retained")
    fig.suptitle("Supplied IQM hardware counts - assignment reconstructed from saved protocol", fontsize=11)
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(OUT / f"hardware-comparison.{extension}", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.6))
    for axis, variant in zip(axes, ("original", "improved")):
        group = analysis["variants"][variant]
        matrix = np.array([[group["confusion_row_fractions"][t][c] for c in TYPES] for t in TYPES])
        axis.imshow(matrix, vmin=0, vmax=1, cmap="Blues")
        axis.set_xticks(range(4), TYPES)
        axis.set_yticks(range(4), TYPES)
        axis.set_xlabel("Classified type from syndrome")
        axis.set_ylabel("Injected type in protocol")
        axis.set_title(variant.capitalize())
        for i, t in enumerate(TYPES):
            for j, c in enumerate(TYPES):
                count = group["confusion_counts"][t][c]
                axis.text(j, i, f"{count}\n{100 * matrix[i,j]:.1f}%", ha="center", va="center",
                          color="white" if matrix[i, j] > .5 else "#163b53", fontsize=9)
    fig.suptitle("Supplied hardware export: counts and row percentages; no mitigation", fontsize=11)
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(OUT / f"hardware-confusion.{extension}", dpi=170)
    plt.close(fig)


def build():
    analysis = load(OUT / "analysis.json")
    native = load(OUT / "native-verification.json")
    tests = load(ROOT / "results/test-outcome.json")
    simulation = load(ROOT / "results/submission-simulation/simulation.json")
    study = load(ROOT / "results/improvement/summary.json")
    metrics = study["metrics"]
    original, improved = (analysis["variants"][v] for v in ("original", "improved"))
    change = analysis["changes_against_original"]["improved"]
    interval = change["newcombe_wilson_95_percentage_points"]
    export = load(ROOT / "data/iqm-comparison-01a20070/export.json")
    protocol = load(ROOT / "results/comparison-prepared/manifest.json")
    job = analysis["job_id"]
    assert tests["returncode"] == 0 and tests["failures"] == tests["errors"] == tests["skipped"] == 0
    assert simulation["cases"] == 150 and simulation["shots_per_case"] == 512
    assert analysis["provenance"]["asymmetric_controls_support_declared_order"]
    figures(analysis)

    per_type = []
    for pauli in TYPES:
        rows = [next(row for row in group["cases"] if row["injected_error"] == pauli) for group in (original, improved)]
        n = [round(row["classification_success_rate"] * row["shots"]) for row in rows]
        per_type.append([pauli, f"{n[0]}/256 = {pct(rows[0]['classification_success_rate'])}",
                         f"{n[1]}/256 = {pct(rows[1]['classification_success_rate'])}",
                         f"{100 * (rows[1]['classification_success_rate']-rows[0]['classification_success_rate']):+.2f}"])
    raw_rows = [[i, experiment["variant"], experiment["error"],
                 *[item["sorted_counts"].get(key, 0) for key in ("00", "01", "10", "11")],
                 "".join(map(str, experiment["expected_syndrome"]))]
                for i, (item, experiment) in enumerate(zip(export, protocol["experiments"]))]
    case_metrics = []
    for check in native["native_cases"]:
        backend = check["backend"]
        case_metrics.append([check["export_index"], check["variant"], check["case_id"],
                             backend["compiled_operation_counts"].get("cz", 0),
                             backend["compiled_operation_counts"].get("r", 0), backend["compiled_depth"]])
    layout_rows = []
    for variant in ("original", "placement", "improved"):
        m = metrics[variant]
        layout_rows.append([variant, ",".join(f"QB{i+1}" for i in m["initial_source_indices"]),
                            ",".join(f"QB{i+1}" for i in m["final_source_indices"]),
                            ",".join(m["syndrome_device_sites"])])
    level_rows = [[row["level"], row["cases"], row["error_configurations"],
                   f"{row['minimum_ideal_fidelity']:.12f}", f"{row['finite_shots']:,}", "100%"]
                  for row in simulation["levels"]]
    test_count = tests["tests"]

    report = f'''# QUBLITZ 2026 - Quantum Minesweeper: current submission report

## 1. Result and evidence boundaries

The supplied IQM export for job `{job}` contains eight circuits with 256 shots each. **Using the experiment order in QUBLITZ_Improved_Run_Ready.zip, original classification success is 759/1024 = {pct(original['success_rate'])}; improved success is 921/1024 = {pct(improved['success_rate'])}.** The absolute change is **+{change['change_percentage_points']:.2f} percentage points**, approximate 95% Newcombe/Wilson interval **+{interval[0]:.2f} to +{interval[1]:.2f} points**. All 2,048 shots are used, without post-selection or readout mitigation.

**Provenance limitation:** the supplied export has counts and measurement keys, but no circuit names, input/error labels, backend name, layout, calibration link or timestamps. Array indices are associated with the unchanged prepared Run Ready protocol. The eight-circuit count, shot totals and asymmetric controls agree with it, but the original submitted job receipt was not supplied. Therefore the original/improved assignment and +i/d1 configurations are **reconstructed from that protocol, not independently verified from a receipt**. The job UUID comes from the supplied filename. These are user-supplied physical-result counts; no new job was submitted from this environment.

| Evidence source | Original | Improved |
|---|---|---|
| New supplied IQM export, protocol-reconstructed assignments | 759/1024 = {pct(original['success_rate'])} | 921/1024 = {pct(improved['success_rate'])} |
| 95% Wilson interval, same export | {ci(original['wilson_95'])} | {ci(improved['wilson_95'])} |
| Offline native compilation of +i/Y1 on IQM fake Garnet target | 24 CZ, 52 R, depth 45 | 11 CZ, 33 R, depth 17 |
| Ideal simulation, exact compiled Level-4 circuits | 78/78 input/error cases pass | 78/78 input/error cases pass |
| Archived calibration-noise simulation, same balanced cases | 89.65% | 93.77% |
| Earlier archived IQM pilot, likely +i/Y1 | 24/32 = 75% | No improved circuit in that pilot |

The resource reduction is 54.17% in native CZ instructions and 62.22% in gate-layer depth for the pilot case. Those are verified offline metrics, not measured pulse duration or independently recovered live-layout metrics. Physical logical-state fidelity was **not measured** by either export. The quantum-data preservation claim is verified in ideal simulation only.

![Hardware success by type and balanced aggregate, with 95% Wilson error bars](../results/iqm-hardware-analysis/hardware-comparison.png)

## 2. Authoritative requirements and completion

All eight pages of `docs/source/challenge.pdf` were read; the latest attachment has identical SHA-256 `{load(ROOT/'data/iqm-comparison-01a20070/provenance.json')['challenge_pdf']['sha256']}`. Pages 2-4 define Levels 1-4, page 5 requires at least one challenge circuit on IQM and explicitly does not require perfect experimental performance, and page 6 lists repository, challenge results, hardware evidence and a live demonstration.

Levels 1-3 recover the unknown state for all promised single-error locations and no error in ideal simulation. Level 4 classifies error type, without claiming correction or location identification. The supplied new hardware export provides a balanced four-type Level-4 experiment under the saved protocol. It does not experimentally test all 78 Level-4 inputs/locations or any Level-1-3 recovery. A public GitHub repository still needs to be published by the team; this ZIP is organized for that submission.

## 3. Bit ordering: asymmetric controls are essential

Source wires for Level 4 are q0-q3=d0-d3, q4=aZ, q5=aX. aZ writes `syn[0]`, the ZZZZ check; aX writes `syn[1]`, the XXXX check. A measured bit 0 means stabilizer +1; 1 means -1. Human syndrome order is `(s0,s1)=(ZZZZ,XXXX)`.

| Error | Check eigenvalues (ZZZZ,XXXX) | Human s0s1 | Export, declared key order | Qiskit display syn1syn0 |
|---|---|---|---|---|
| I | (+1,+1) | 00 | 00 | 00 |
| X | (-1,+1) | 10 | 10 | 01 |
| Y | (-1,-1) | 11 | 11 | 11 |
| Z | (+1,-1) | 01 | 01 | 10 |

Every export item lists `['syn_2_0_0','syn_2_0_1']`. The importer explicitly declares that character j belongs to measurement_keys[j], then normalizes to Qiskit display order. It never chooses an order by maximizing accuracy. The installed IQM SDK formatter independently confirms that native syn[0]=1/syn[1]=0 becomes Qiskit 01. Under the saved protocol, both X controls have mode export 10 and both Z controls have mode export 01, supporting the declared export convention. The symmetric Y=11 alone cannot establish that convention, and this new check does not retroactively prove the old pilot export order.

Raw counts below are **unchanged exported strings in the declared measurement-key order**, not Qiskit strings. Indices are zero based and assigned using the saved protocol. Input is +i throughout; X/Y/Z act on d1.

{table(['Index','Variant','Error','00','01','10','11','Expected export'], raw_rows)}

{table(['Type','Original correct / shots','Improved correct / shots','Change (pp)'], per_type)}

Per-case Wilson intervals and both the unchanged export and normalized Qiskit counts are in `results/iqm-hardware-analysis/analysis.json`, `per-case.csv` and `imported-comparison.json`.

![Hardware confusion matrices: each row contains 256 shots](../results/iqm-hardware-analysis/hardware-confusion.png)

Rows above are protocol-injected types, columns are classified solely from measured syndrome. Every row sum is 256. The aggregate is equally weighted across I, X, Y and Z. Wilson intervals describe binomial shot uncertainty. The difference interval is an independent-binomial approximation; it does not quantify correlated drift, protocol-assignment uncertainty or unmeasured logical fidelity. The observed gain is evidence for this supplied batch and protocol assignment, not a guarantee for future calibrations.

## 4. Level 1: correct an unknown X error

Data d0,d1,d2 are left,middle,right. Ancillas q3=a0 and q4=a1 store (d0 XOR d1,d1 XOR d2). Start with `(alpha|0>+beta|1>)|00>` and encode with CX(d0,d1), CX(d0,d2). For a middle X error, the data evolves as follows:

| Stage | Data, human order d0 d1 d2 | Ancillas a0 a1 |
|---|---|---|
| Prepare | alpha 000 + beta 100 | 00 |
| Encode | alpha 000 + beta 111 | 00 |
| Inject X on d1 | alpha 010 + beta 101 | 00 |
| Extract, then measure syndrome | alpha 010 + beta 101 | 11 |
| Syndrome-controlled X on d1 | alpha 000 + beta 111 | 11 |
| Decode | (alpha 0 + beta 1) tensor 00 | 11 |

Each parity is computed with two CNOTs into an initially zero ancilla. Both logical components receive the same ancilla value 11, so the final state factors into data superposition tensor ancilla 11. Reading those ancillas learns neither alpha nor beta nor which component the data occupies. This argument applies to the promised encoded-error subspace, not to unrestricted data states.

| Human syndrome (left-middle,middle-right) | Recovery location |
|---|---|
| 00 | None |
| 10 | Left d0 |
| 11 | Middle d1 |
| 01 | Right d2 |

The chosen X is squared with the injected X, so both encoded basis states are restored with the same global phase +1. By linearity every alpha/beta superposition is restored. The circuit diagram measures syndrome before dynamic recovery; the IQM-compatible Level-1 alternative defers measurement and uses coherent syndrome control.

![Level-1 circuit, source wire order d0 d1 d2 a0 a1](../results/circuits/demo-L1.png)

## 5. Level 2: turn Z into X by interference

For one qubit, H|+>=|0> and H|->=|1>. Before H both inputs yield equal 0/1 probabilities; H adds or cancels their amplitudes so their relative sign becomes distinguishable. H acts on one qubit, with H|0>=(|0>+|1>)/sqrt(2) and H|1>=(|0>-|1>)/sqrt(2).

Encode the repetition state, apply H to all three data qubits, **inject the test Z here**, then apply H to all three again. H Z H = X turns the phase error into the matching bit error. Extract the Level-1 parities and recover with X in this restored computational basis; decode and verify d0 **before** inverse input preparation. Both encoded basis states again receive phase +1. Test harness labels are used for preparation/scoring, never for recovery selection.

![Level-2 circuit with marked injection and recovery basis](../results/circuits/demo-L2.png)

## 6. Level 3: promised Y requires Y recovery

Y maps 0 to i1 and 1 to -i0. A middle Y gives `i alpha 010 - i beta 101`; both bit patterns still have syndrome 11. Because the error model promises Y, the syndrome locates the qubit and the recovery applies Y there. Y squared is I, with global phase +1 on both logical basis states.

The controlled + input comparison gives fidelity 1 with Y recovery and fidelity 0 with X-only recovery. X-only restores the encoded bit patterns but leaves `i(alpha 000-beta 111)`, or a logical Z phase after decoding. Equal computational-basis probabilities do not prove quantum-state restoration.

![Level-3 circuit: recover with Y selected from the syndrome](../results/circuits/demo-L3.png)

## 7. Level 4 and the shallower equivalent circuit

The orthogonal codewords, in human d0 d1 d2 d3 order, are `|0L>=(|0000>+|1111>)/sqrt(2)` and `|1L>=(|0011>+|1100>)/sqrt(2)`. They select two dimensions of the four-dimensional common +1 eigenspace of ZZZZ and XXXX. Both stabilizers act identically on the two logical codewords. A Pauli error changes a stabilizer sign exactly when it anticommutes with that check, independently of alpha and beta and of the data location. Thus X changes ZZZZ, Z changes XXXX and Y changes both.

The preserved original encoder is CX(0,1), H(2), CX(2,0), CX(2,1), CX(2,3). The improved encoder is **H(3), CX(3,0), CX(0,1), CX(3,2)**. With input bit b and H-generated bit g, its output is `(b XOR g,b XOR g,g,g)`, giving exactly the same two codewords with the same relative phase.

Let C be CX(0,1) followed by CX(2,3). Conjugation maps ZZZZ to Z1 Z3 and XXXX to X0 X2. Apply C; extract Z1 Z3 with CX(1,aZ), CX(3,aZ); extract X0 X2 with H(aX), CX(aX,0), CX(aX,2), H(aX); apply C again. The undo is essential: it restores the post-error encoded data after writing the checks. The check map agrees with the original on all 16 data basis vectors with ancillas zero, so it also agrees on arbitrary superpositions by linearity.

Encoding finishes before the labeled injection barrier. The injected Pauli is never absorbed into preparation or used by the classifier. Only ancillas are finally measured, and no mid-circuit measurements or classical feed-forward are needed.

![Original Level-4 source circuit](../results/improvement/circuits/original-source.png)

![Improved Level-4 source circuit with injection point](../results/improvement/circuits/improved-source.png)

## 8. Calibration and supported target

The unchanged quality-metric snapshot was created at `{study['calibration']['timestamp_utc']}`, with described calibration ID `{study['calibration']['calibration_set_id']}`, device label `{study['calibration']['device_label']}`. It provides 20 qubits and 30 CZ edges; invalid observations, units, probabilities, timestamps and duplicates are checked. The unheralded asymmetric readout metrics are used separately for 0-to-1 and 1-to-0 errors. Pulse durations are absent, so execution time cannot be estimated defensibly from this snapshot.

The official offline IQM fake Garnet topology has exactly those qubit names and CZ edges. Native R, CZ, barriers and terminal measurements are checked against that supported target, including each physical two-qubit edge. The live QPU identity and its run-time calibration were not present in the export; topology compatibility does not establish them. All reported physical layouts below belong to **verified offline compiled artifacts**, and need the original receipt to certify their use in this job.

Placement searches bounded layout/seed candidates using one calibration ranking heuristic across all inputs/errors. It combines conservative gate fidelities, worst-bit unheralded readout cost, CZ count and a depth tie breaker; it is not a predicted accuracy. Selected layouts are frozen before evaluation. The placement-only candidate uses 24 CZ, depth 46, with no new physical result. The selected rewrite plus placement uses 11 CZ, depth 17 for +i/Y1. This experiment cannot separate the causal contributions of rewriting and placement.

Layout order is `(d0,d1,d2,d3,aZ,aX)`; backend indices are zero based, and QBn is index n-1.

{table(['Variant','Initial device names','Final device names','Measured ZZZZ,XXXX'], layout_rows)}

Exact saved packet metrics, including every input/error pair used in the supplied batch:

{table(['Index','Variant','Case ID','CZ','R','Depth'], case_metrics)}

Software used locally: Python {native['software']['python']}, Qiskit {native['software']['qiskit']}, Aer {native['software']['qiskit-aer']}, iqm-client {native['software']['iqm-client']}, NumPy {native['software']['numpy']}. Hardware compilation was validated on `IQMFakeGarnetBackend`; do not replace that label with a claimed physical backend name. The live runner obtains the actual backend and revalidates its target. Resonator/MOVE targets are explicitly rejected by this exact-Aer comparison implementation.

## 9. Tests, exact native replay and noise simulations

Before new edits, the existing improved project passed **718 tests**, and the latest Run Ready SDK-token fixes also passed **718 tests**. The original development baseline has archived **300 passing tests**; it was reproduced in the earlier improvement study, not rerun from the untouched ZIP during this import. Current full regression: **{test_count} passed, zero failures/errors/skips**. Evidence is `results/pytest.txt`, `pytest.xml`, `test-outcome.json`, and the two pre-import JUnit files.

{table(['Level','Input/error cases','Error configurations','Minimum ideal fidelity','Finite shots','Every case success'], level_rows)}

For Levels 1-3 the fidelity is the decoded state against the input, before inverse preparation; finite shots use inverse input preparation and verify the expected all-zero data outcome and syndrome. For Level 4 the fidelity compares data after extraction with the encoded data immediately after injection, not with an uncorrupted codeword. The original 150 cases include 24 cases per recovery level and 78 classification cases, six logical inputs each.

The full regression also checks all 13 Level-4 errors across six inputs on each of original, placement and improved exact native variants: 234 statevector cases. Source isometry checks include both encoder codewords and all 16 extraction columns. X and Z controls fail under a bit swap. Fresh replay of the exact eight saved QPY circuits verifies their gate/register/global-phase fingerprints, layout metadata and target compatibility; data-preservation fidelity is at least **{native['minimum_native_data_preservation_fidelity']:.15f}**, and all **2048/2048 ideal shots** are correct. This certifies the saved offline packet, not an unavailable live native circuit.

The archived calibration-noise model predicts 89.65% original versus 93.77% improved on the balanced subset: +4.13 points, with separate evaluation seeds 49157 and 82799 and 4096 shots per variant. These are **noise simulations**, distinct from both the generic fake Garnet archive and physical counts. Independent depolarization and asymmetric unheralded readout omit leakage, coherent/correlated errors, crosstalk, initialization faults, drift and idle timing. Their physical-rate mismatch is observed; these attachments do not identify its cause. Reducing entanglers and routing is a plausible contributor to the measured gain, not a proven causal explanation.

## 10. Reproduction, receipt retrieval and live demonstration

From an extracted project folder, install with `bash scripts/setup.sh` (Python 3.12). Then run `bash scripts/reproduce_submission.sh`. It checks dependencies, runs all tests, regenerates the 150-case simulation, imports all physical counts, replays the exact native packet and rebuilds this report, Japanese guide and offline demo. It makes **no hardware submission**.

The explicit import command is:

```bash
.venv/bin/python -m minesweeper compare --mode import-export \\
  --export-file data/iqm-comparison-01a20070/export.json \\
  --protocol-file results/comparison-prepared/manifest.json \\
  --export-bit-order measurement-keys \\
  --job-id {job} --out results/iqm-hardware-analysis
```

To retrieve the already completed job and archive its actual submitted IQM circuits, parameters, calibration IDs and timeline, use the original event server/QPU configuration and your private credentials. Do not resubmit merely to obtain a receipt:

```bash
export IQM_SERVER_URL='YOUR_ORIGINAL_EVENT_SERVER_URL'
export IQM_QUANTUM_COMPUTER='YOUR_ORIGINAL_QPU_NAME'
.venv/bin/python -m minesweeper compare --mode retrieve \\
  --job-id {job} \\
  --protocol-file results/comparison-prepared/manifest.json \\
  --out results/iqm-comparison-retrieved --prompt-token
```

This writes `job.json` and `iqm-result.json`. Inspect returned circuit names/order, physical instructions, measurement keys and calibration linkage against the saved packet; retrieval alone does not certify a reconstructed protocol. Use the original receipt as `--protocol-file` when importing if you have it. The old single-pilot `iqm --mode retrieve` workflow remains available.

Live demo: open `docs/live-demo.html` offline, select Level 1/+i/middle X, and step through preparation, encoding, injection, extraction, correction, decoding and inverse-preparation verification. The beginning shows 010 and 101 with the same parity 11. Scroll to the hardware section for the actual supplied counts and their provenance label. A reproducible terminal walkthrough is:

```bash
.venv/bin/python -m minesweeper demo --level 1 --input +i \\
  --error X --location 1 --shots 512 --out results/submission-demo
```

English presentation: “We compare the original and optimized Level 4 circuits using a balanced I, X, Y, and Z protocol. Under the saved protocol's circuit-order assignment, the supplied IQM job export gives 74.12% correct syndrome classifications for the original and 89.94% for the optimized circuit. Ideal simulations verify that both checks preserve the encoded data, while these hardware counts measure classification accuracy, not logical-state fidelity.”

## Final submission checklist and first command

**First command:** `bash scripts/setup.sh` from the extracted project folder. If dependencies are already installed, `bash scripts/reproduce_submission.sh` reproduces the current evidence without contacting IQM.

**Tests actually run:** the two pre-import suites each passed 718 tests; the updated full suite passed {test_count}, with zero failures/errors/skips. The fresh exhaustive benchmark passed 150/150 cases and 76,800/76,800 ideal shots. Exact archived native replay passed 8/8 circuits and 2048/2048 ideal shots. The Level-1 middle-X demo verifies the original complex superposition after decoding.

**Verified on IQM hardware by the supplied evidence:** eight count histograms, 256 shots each, supplied as job `{job}`. Under the saved protocol assignment, Level-4 classification is {pct(original['success_rate'])} original and {pct(improved['success_rate'])} improved. No logical-state fidelity, Levels 1-3 recovery, complete 78-case hardware coverage or live physical layout is established by this export.

**Still needed before submission:** recover and audit the original receipt/native circuit/backend/calibration linkage to remove the protocol-assignment qualification; publish the GitHub repository with these files and raw evidence; rehearse the Japanese explanation and English demo. A repeat hardware job can test reproducibility, but should use a fresh, explicitly authorized output directory and is not needed merely to analyze these counts. Perfect experimental accuracy is not a challenge requirement.
'''

    japanese = f'''# 実機結果と改良点を説明するための日本語ガイド

## 010も101も「違う、違う」

010は左と中央が違い、中央と右も違います。101でも同じです。「同じ」を0、「違う」を1とすると、どちらの比較結果も11になります。

データが `alpha|010>+beta|101>` という重ね合わせなら、補助の量子ビット（アンシラ）に、両方の成分で同じ11を書きます。最後は `(alpha|010>+beta|101>)|11>`。アンシラを読んでも、元が010か101かは分かりません。だから、この符号と許された誤りの条件では、alphaとbetaの関係を保てます。重ね合わせ全体を直接測ってよいという意味ではありません。

## 最小限のゲートの見方

Xは1個のビットを0と1で入れ替えます。Hは1個に作用し、0を+、1を-の重ね合わせにします。Zは1の成分の係数にだけマイナスを付けます。Yは0をi1、1を-i0に変えます。Sは1の係数にiを掛け、Sの逆操作はそれを取り消します。

CZは2個に作用し、11の成分の符号だけをマイナスにします。00・01・10はそのままです。IQMのRは1個を回転させるゲートで、例えばR(pi,0)は、全体位相を除いてXと同じ入れ替えになります。CCXは制御2個と標的1個に作用し、両方の制御が1の成分だけ標的を反転します。

CNOTは制御と標的の2個に作用します。制御が1の成分だけ標的を反転するので、制御・標的の順で10は11に、11は10になります。a0を0から始めてCNOT(d0,a0)、CNOT(d1,a0)を使うと、a0には2個が同じか違うかだけが残ります。a1にはd1とd2の比較を書きます。

Level 1の中央Xなら、準備 → alpha000+beta111に符号化 → alpha010+beta101 → 比較11 → 中央にX → alpha000+beta111 → 復号、という順です。元の情報はd0に戻ります。訂正係が使うのは比較結果だけです。

Level 2の前に1個だけ考えると、+と-はそのまま測るとどちらも半々です。Hを通すと成分が足し合わされたり打ち消されたりして、H|+>=|0>、H|->=|1>となります。これが干渉です。3個の符号でも全員にHを掛け、**そこでZを入れ**、全員にもう一度Hを掛けます。HZH=Xなので、戻した0/1の基底でLevel 1のX訂正が使えます。元の状態を調べるのは復号後、準備の逆操作より前です。

Level 3はYだけが入る約束です。比較で場所を探し、同じ場所にYを掛けるとYの2回で元に戻ります。Xだけだと並びは直っても相対的なマイナスが残ります。+入力の比較では、正しいY訂正の忠実度は1、Xだけでは0でした（理想シミュレーション）。

## 以前の75%は何を意味する？

以前の32ショットの実機ファイルでは、期待する11が24回でした。24/32=75%は、**誤りの種類を正しく分類できた割合**です。量子状態が75%保存された、という意味ではありません。32回と少ないため、95% Wilson区間は約57.89-86.75%です。以前の+i/Y1という設定は、文書中のコマンドからの推定です。

## 新しい実機ファイルでは？

8回路それぞれ256ショット、合計2048ショットです。保存済みRun Readyプロトコルの回路順に対応させると、次の結果になります。

{table(['誤り','元の回路','改良回路','差（ポイント）'], per_type)}

合計は **元759/1024={pct(original['success_rate'])}、改良921/1024={pct(improved['success_rate'])}**。差は**+{change['change_percentage_points']:.2f}ポイント**でした。元の95%区間は{ci(original['wilson_95'])}、改良は{ci(improved['wilson_95'])}、差の概算区間は+{interval[0]:.2f}-+{interval[1]:.2f}ポイントです。全ショットを使い、都合のよい結果だけ選んでいません。

ただし、アップロードされた結果には回路名・実機名・配置・実行時刻がありません。**回路の対応付けは、保存済みプロトコルを使った再構成です。実際の送信記録からの独立確認はまだです。** 提出時は元のjob.jsonなどを回収し、名前・回路順・配置を照合します。この点を隠さず説明してください。

## ビットの順番を間違えない

Level 4では4個のデータを使い、ZZZZとXXXXの比較結果だけを2個のアンシラで読みます。場所を当てたり誤りを直したりする段階ではありません。

{table(['誤り','人が読む順（ZZZZ,XXXX）','今回のIQM export','Qiskitの表示'], [['I','00','00','00'],['X','10','10','01'],['Y','11','11','11'],['Z','01','01','10']])}

今回は、文字がmeasurement_keysの並びに対応すると明示して読みました。Xの例では10、Zでは01が最も多く、どちらの回路でもこの読み方と一致します。Yの11だけでは、左右を逆に読んでも同じなので、順番の確認になりません。プログラムは順番を勝手に入れ替えて成功率を上げません。

## コードで何を改良した？

符号化した情報と検査するZZZZ・XXXXは同じまま、ゲートを並べ直して接続に合う回路にしました。符号化用CNOTは4個から3個へ。検査の途中でデータ2組を一時的に変換し、短い比較をしたあと必ず変換を戻します。誤りを入れる点は、符号化が終わった直後に保っています。

校正データを使い、二量子ビット操作の品質・読み出し誤り・必要な移動を合わせて配置を順位付けしました。この点数は**比較用の目安**です。入力や隠した誤りに応じて、有利な配置を選び直していません。

保存済みオフライン回路の+i/Y1例では、CZが**24個から11個**、深さが**45から17**へ減りました。誤りが入る機会が減ることは、成績が良くなる理由の候補です。ただし、今回の結果だけで改善原因を一つに断定できません。これらの配置・ゲート数を実機の送信記録と照合する作業は残っています。

今回さらに、IQM exportを安全に読み込む処理、X/Zの順序確認、元データを残す分析、再取得した実回路・校正IDの保存を追加しました。保存したQPYを読み直すと配置表示が失敗する問題も修正しました。Run Ready版の認証設定の修正も引き継いでいます。

## 実演で使う英語3文

We compare the original and optimized Level 4 circuits using a balanced I, X, Y, and Z protocol.

Under the saved protocol's circuit-order assignment, the supplied IQM job export gives 74.12% correct syndrome classifications for the original and 89.94% for the optimized circuit.

Ideal simulations verify that both checks preserve the encoded data, while these hardware counts measure classification accuracy, not logical-state fidelity.

## 実演と提出までの手順

`docs/live-demo.html`を開き、Level 1/+i/中央を選びます。準備から復号まで進め、途中のiの係数が最後にも残ることを見せます。下部の実機結果は、この説明用シミュレーションと区別してあります。

**最初のコマンド：** 展開したプロジェクト内で `bash scripts/setup.sh`。続けて `bash scripts/reproduce_submission.sh`。後者は新しい実機ジョブを送らず、同じ分析を再現します。

**実際のテスト：** 変更前は718件成功。更新後は{test_count}件成功、失敗・エラー・スキップ0件。全150入力/誤りケース、76800理想ショットが成功。保存済みネイティブ8回路の2048理想ショットも成功しました。

**IQMで確認できた内容：** 提供された8個の256ショットの測定結果です。上記プロトコルの対応付けなら分類成功率は{pct(original['success_rate'])}から{pct(improved['success_rate'])}へ上がっています。量子状態の忠実度やLevels 1-3の実機訂正を測った結果ではありません。

**提出前に残る作業：** 元の送信記録・実機名・回路順・配置・校正との対応を回収して照合すること、GitHubへこのプロジェクトを掲載すること、実演を練習することです。再取得コマンドはREADMEと英語レポートにあります。新しく実機ジョブを送らなくても、今回の結果の分析は完了しています。
'''

    presentation = '''# Live demonstration - current evidence

## Reproduce the state walkthrough

```bash
.venv/bin/python -m minesweeper demo --level 1 --input +i --error X --location 1 --shots 512 --out results/submission-demo
```

Open `docs/live-demo.html`. Use Level 1, input +i, middle error. Step through preparation, encoding, X injection, comparison extraction, syndrome measurement, X recovery, decoding and inverse-preparation verification. Point to 010 and 101: both share syndrome 11, so the ancillas do not reveal which logical component is present. The decoded state retains its relative i. These walkthrough states and fidelity checks are ideal simulation.

## Three English sentences for the hardware slide

We compare the original and optimized Level 4 circuits using a balanced I, X, Y, and Z protocol.

Under the saved protocol's circuit-order assignment, the supplied IQM job export gives 74.12% correct syndrome classifications for the original and 89.94% for the optimized circuit.

Ideal simulations verify that both checks preserve the encoded data, while these hardware counts measure classification accuracy, not logical-state fidelity.

## Questions to be ready for

Why no measurement collapse of the logical superposition? Both logical components have the same stabilizer eigenvalues for a fixed promised error; the measured ancilla factors from the encoded amplitudes.

Why does X-only fail in Level 3? It restores the bit pattern but leaves a logical Z relative phase. The + input becomes -, so the state fidelity is zero despite the same computational-basis probabilities.

Why are X and Z controls needed? Reversing the two bits exchanges their types. Y=11 and I=00 cannot detect that mistake.

What is still unknown experimentally? The supplied export does not contain logical-state fidelity, physical native circuit/layout, calibration linkage, or the original job receipt. Circuit-to-histogram assignments currently come from the saved Run Ready protocol.

What caused the improvement? Reduced routed entanglers and calibration-aware placement are plausible contributors. This combined comparison does not isolate a causal contribution, and the simplified noise model omits several real-device effects.
'''

    spec = importlib.util.spec_from_file_location("submission_render", ROOT / "scripts/build_deliverables.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    for name, text, is_japanese in (("SUBMISSION_REPORT", report, False), ("HARDWARE_JA", japanese, True),
                                     ("LIVE_PRESENTATION_EN", presentation, False)):
        text = renderer.escape_table_kets(text)
        (DOCS / f"{name}.md").write_text(text)
        (DOCS / f"{name}.html").write_text(renderer.render_html(text, name))
        renderer.render_pdf(text, DOCS / f"{name}.pdf", japanese=is_japanese, compact=is_japanese)
    renderer.generate_demo(simulation, tests)
    print("Built current submission report, Japanese guide, English demo script and offline interactive demo.")


if __name__ == "__main__":
    build()

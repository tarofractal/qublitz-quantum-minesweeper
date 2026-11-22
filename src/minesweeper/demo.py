"""A live CLI walkthrough. All displayed amplitudes come from Qiskit."""
from __future__ import annotations

from pathlib import Path
import numpy as np
from qiskit import transpile
from qiskit.quantum_info import Statevector, partial_trace, state_fidelity
from qiskit_aer import AerSimulator

from .artifacts import save_circuit, write_json
from .circuits import decode_repetition, recover_observed
from .experiments import Error, expected_syndrome, repetition_experiment, repetition_stages
from .states import preparation, target_state
from .verification import ideal_case, shot_metrics


def terms(circuit) -> list[dict]:
    values = Statevector.from_instruction(circuit).data
    answer = []
    for index, value in enumerate(values):
        if abs(value) > 1e-9:
            human = f"{index:0{circuit.num_qubits}b}"[::-1]
            answer.append({"data": human[:3], "ancillas": human[3:],
                           "amplitude_real": float(value.real), "amplitude_imag": float(value.imag)})
    return answer


def run_demo(level: int, label: str, error: Error, shots: int, seed: int, out: Path) -> dict:
    record = ideal_case(level, label, error)
    prep = preparation(label)
    stages = repetition_stages(prep, level, error)
    observed = tuple(record["observed_syndrome"])
    circuit = stages["extracted"].copy()
    recover_observed(circuit, level, observed)
    stages["recovered"] = circuit.copy()
    decode_repetition(circuit)
    stages["decoded"] = circuit.copy()
    circuit.compose(prep.inverse(), [0], inplace=True)
    stages["verification"] = circuit.copy()
    data = {name: terms(stage) for name, stage in stages.items()}
    measured = repetition_experiment(prep, level, error)
    backend = AerSimulator(max_parallel_threads=1)
    counts = backend.run(transpile(measured, backend, seed_transpiler=seed),
                         shots=shots, seed_simulator=seed).result().get_counts()
    lines = [f"Level {level}; input |{label}>; injected {error.pauli} on {error.location}",
             "Human ket order: d0 d1 d2 | a0 a1. Raw counts: v2v1v0 s1s0.",
             "Ancilla 0 compares left/middle; ancilla 1 compares middle/right."]
    for name, components in data.items():
        rendered = " + ".join(f"({t['amplitude_real']:+.6f}{t['amplitude_imag']:+.6f}i)"
                              f"|{t['data']}>|{t['ancillas']}>" for t in components)
        lines.append(f"{name}: {rendered}")
    lines += [f"Measured syndrome (left-middle,middle-right): {observed}",
              f"Quantum-state fidelity before inverse preparation: {record['ideal_state_fidelity']:.12f}",
              f"Raw finite-shot counts: {counts}", "No post-selection. These are simulation results."]
    if level == 3 and error.pauli == "Y":
        wrong = stages["extracted"].copy()
        recover_observed(wrong, 1, observed)
        decode_repetition(wrong)
        wrong_density = partial_trace(Statevector.from_instruction(wrong), [1, 2, 3, 4])
        wrong_fidelity = float(state_fidelity(wrong_density, target_state(prep)))
        record["x_only_control_fidelity"] = wrong_fidelity
        lines.append(f"CONTROL: replace Y recovery with X only => fidelity {wrong_fidelity:.12f}")
    metrics = shot_metrics(level, counts, expected_syndrome(level, error))
    payload = {"source": "Qiskit ideal simulation", "case": record, "stages": data, "finite_shots": metrics}
    out.mkdir(parents=True, exist_ok=True)
    prefix = f"demo-L{level}"
    (out / f"{prefix}.txt").write_text("\n".join(lines) + "\n")
    write_json(out / f"{prefix}.json", payload)
    save_circuit(measured, out / "circuits", prefix)
    print("\n".join(lines))
    return payload

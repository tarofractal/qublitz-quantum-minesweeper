"""Exhaustive run: 24+24+24+78 cases, exact checks and genuine Aer shots."""
from __future__ import annotations

import csv
from pathlib import Path
from qiskit import transpile
from qiskit_aer import AerSimulator

from .artifacts import timestamp, versions, write_json
from .experiments import expected_syndrome, level4_experiment, permitted_errors, repetition_experiment
from .states import INPUTS, preparation
from .verification import ideal_case, shot_metrics


def run_suite(out: Path, shots: int = 512, seed: int = 2026, levels=(1, 2, 3, 4)) -> dict:
    if shots <= 0:
        raise ValueError("Shots must be positive")
    records, circuits = [], []
    for level in levels:
        for error in permitted_errors(level):
            for label in INPUTS:
                record = ideal_case(level, label, error)
                record["case_id"] = f"L{level}_{label}_{error.pauli}_{error.location}"
                records.append(record)
                prep = preparation(label)
                circuit = level4_experiment(prep, error) if level == 4 else repetition_experiment(prep, level, error)
                circuits.append(circuit)
    simulator = AerSimulator(method="statevector", max_parallel_threads=1)
    compiled = transpile(circuits, simulator, optimization_level=0, seed_transpiler=seed)
    result = simulator.run(compiled, shots=shots, seed_simulator=seed).result()
    assert result.success
    for index, record in enumerate(records):
        counts = result.get_counts(index)
        metrics = shot_metrics(record["level"], counts, tuple(record["expected_syndrome"]))
        record["finite_shots"] = {"source": "ideal_Aer_finite_shots", **metrics}
        assert metrics["shots"] == shots
        assert metrics["joint_success_rate"] == 1.0, record
    summaries = []
    for level in levels:
        cases = [record for record in records if record["level"] == level]
        fidelity_name = "ideal_data_preservation_fidelity" if level == 4 else "ideal_state_fidelity"
        summaries.append({"level": level, "cases": len(cases),
                          "error_configurations": len(permitted_errors(level)),
                          "minimum_ideal_fidelity": min(c[fidelity_name] for c in cases),
                          "fidelity_meaning": "data preservation after extraction" if level == 4 else "decoded logical state",
                          "finite_shots": sum(c["finite_shots"]["shots"] for c in cases),
                          "minimum_case_success_rate": min(c["finite_shots"]["joint_success_rate"] for c in cases)})
    # Explicit cross-input invariance check for every level-4 error configuration.
    if 4 in levels:
        for error in permitted_errors(4):
            related = [r for r in records if r["level"] == 4 and r["injected_error"] == error.pauli
                       and r["error_location"] == error.location]
            assert len(related) == 6
            assert len({tuple(r["observed_syndrome"]) for r in related}) == 1
    out.mkdir(parents=True, exist_ok=True)
    payload = {"created_at_utc": timestamp(), "software": versions(), "seed": seed,
               "shots_per_case": shots, "cases": len(records), "levels": summaries,
               "hardware_status": "Simulation only; physical IQM evidence is tracked separately.",
               "postselection": "none", "records": records}
    write_json(out / "simulation.json", payload)
    fields = ["case_id", "level", "input", "injected_error", "error_location", "expected_syndrome",
              "observed_syndrome", "ideal_state_fidelity", "ideal_data_preservation_fidelity",
              "shots", "joint_success_rate", "retained_fraction", "raw_counts"]
    with (out / "cases.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key, "") for key in fields}
            row.update({key: record["finite_shots"].get(key, "") for key in
                        ("shots", "joint_success_rate", "retained_fraction", "raw_counts")})
            writer.writerow(row)
    write_json(out / "summary.json", {key: value for key, value in payload.items() if key != "records"})
    return payload

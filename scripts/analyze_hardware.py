"""Reproduce the supplied physical-count analysis and verify its offline protocol.

No network call or hardware submission is made by this script.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from qiskit import qpy
from qiskit_aer import AerSimulator
from iqm.qiskit_iqm.fake_backends.fake_garnet import IQMFakeGarnet

from minesweeper.artifacts import timestamp, versions, write_json
from minesweeper.comparison_analysis import analyze_comparison
from minesweeper.experiments import Error
from minesweeper.hardware import backend_metadata, validate_native
from minesweeper.iqm_export import fingerprint, import_export
from minesweeper.native_verification import verify_native
from minesweeper.placement import Plan, circuit_signature, source_for_plan

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/iqm-hardware-analysis"
JOB = "01a20070-6eb5-7033-942a-a41474a1922e"


def main():
    packet = ROOT / "results/comparison-prepared"
    protocol_path = packet / "manifest.json"
    protocol = json.loads(protocol_path.read_text())
    analysis = import_export(ROOT / "data/iqm-comparison-01a20070/export.json", protocol_path, OUT,
                             bit_order="measurement-keys", job_id=JOB)
    with (packet / "all-native.qpy").open("rb") as stream:
        circuits = qpy.load(stream)
    if len(circuits) != len(protocol["experiments"]):
        raise AssertionError("Saved native packet has the wrong number of circuits")
    backend = IQMFakeGarnet()
    checks = []
    for index, (experiment, circuit) in enumerate(zip(protocol["experiments"], circuits)):
        if circuit_signature(circuit) != experiment["signature"]:
            raise AssertionError(f"Packet circuit {index} differs from its protocol fingerprint")
        if [(register.name, len(register)) for register in circuit.cregs] != [("syn", 2)]:
            raise AssertionError("Native packet classical register is not syn[2]")
        measurement_bits = [circuit.find_bit(instruction.clbits[0]).index for instruction in circuit.data
                            if instruction.operation.name == "measure"]
        if sorted(measurement_bits) != [0, 1]:
            raise AssertionError("Native packet must measure exactly the two syndrome bits")
        plan = Plan.from_dict(experiment["plan"])
        error = Error() if experiment["error"] == "I" else Error(experiment["error"], experiment["location"])
        source = source_for_plan(plan, experiment["input"], error)
        validate_native(circuit, backend)
        check = verify_native(plan, source, circuit, experiment["input"], error)
        checks.append({"export_index": index, "variant": experiment["variant"], "case_id": experiment["case_id"],
                       "native_fingerprint_matches": True, "backend": backend_metadata(backend, circuit), **check})
    simulator = AerSimulator(method="matrix_product_state", max_parallel_threads=1)
    result = simulator.run(circuits, shots=256, seed_simulator=2026).result()
    if not result.success:
        raise AssertionError("Exact saved native circuit simulation failed")
    ideal = analyze_comparison({**protocol, "source": "ideal replay of exact archived native QPY; not hardware",
                                "raw_counts": [result.get_counts(i) for i in range(len(circuits))]})
    if any(group["successes"] != group["shots"] for group in ideal["variants"].values()):
        raise AssertionError("Exact archived packet failed an ideal classification control")
    write_json(OUT / "ideal-packet-analysis.json", ideal)
    write_json(OUT / "native-verification.json", {
        "source": "ideal simulation of prepared offline artifacts; actual submitted native circuits not supplied",
        "created_at_utc": timestamp(), "software": versions(), "packet": fingerprint(packet / "all-native.qpy"),
        "protocol": fingerprint(protocol_path), "native_cases": checks,
        "minimum_native_data_preservation_fidelity": min(row["native_data_preservation_fidelity"] for row in checks),
        "ideal_shots": 2048, "ideal_successes": 2048,
    })
    with (OUT / "per-case.csv").open("w", newline="") as stream:
        fields = ["export_index", "variant", "input", "error", "location", "expected_human_s0s1",
                  "expected_export_string", "export_00", "export_01", "export_10", "export_11",
                  "correct", "shots", "success_rate", "wilson_95_low", "wilson_95_high"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        export = json.loads((ROOT / "data/iqm-comparison-01a20070/export.json").read_text())
        for index, (experiment, metrics) in enumerate(zip(protocol["experiments"], analysis["per_case"])):
            bits = "".join(map(str, experiment["expected_syndrome"]))
            raw = export[index]["sorted_counts"]
            writer.writerow({"export_index": index, "variant": experiment["variant"], "input": experiment["input"],
                             "error": experiment["error"], "location": experiment["location"],
                             "expected_human_s0s1": bits, "expected_export_string": bits,
                             **{f"export_{key}": raw.get(key, 0) for key in ("00", "01", "10", "11")},
                             "correct": raw.get(bits, 0), "shots": metrics["shots"],
                             "success_rate": metrics["classification_success_rate"],
                             "wilson_95_low": metrics["joint_success_wilson_95"][0],
                             "wilson_95_high": metrics["joint_success_wilson_95"][1]})
    print(json.dumps({"source": analysis["source"], "protocol_assignment_verified_from_receipt": False,
                      "asymmetric_controls_support_declared_order": analysis["provenance"]["asymmetric_controls_support_declared_order"],
                      "counts": {v: f"{g['successes']}/{g['shots']}" for v, g in analysis["variants"].items()},
                      "change": analysis["changes_against_original"], "exact_native_replay": "8/8 pass, 2048/2048 ideal shots"}, indent=2))


if __name__ == "__main__":
    main()

"""Bind a saved execution receipt to its native circuits and dashboard counts.

This is a local consistency audit of supplied evidence, not a server query.
No hardware jobs are submitted and no circuit order is guessed from accuracy.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from uuid import UUID

from iqm.qiskit_iqm.qiskit_to_iqm import serialize_instructions

from .comparison_analysis import analyze_comparison
from .iqm_export import KEYS, normalize_export
from .native_verification import source_layout_indices
from .placement import circuit_signature


def audit_packet(receipt, definition, circuits, exported, *, job_id,
                 calibration_id, calibration_sha256):
    """Reject mismatched job IDs, counts, calibration, wires, or native gates."""
    if (str(UUID(job_id)) != receipt.get("job_id")
            or receipt.get("source") != "IQM_QPU_comparison"
            or receipt.get("status") != "completed" or receipt.get("result_success") is not True):
        raise ValueError("Need the completed matching IQM comparison receipt")
    shots = receipt.get("shots_per_circuit")
    if (not isinstance(shots, int) or isinstance(shots, bool) or shots <= 0
            or definition.get("shots") != shots):
        raise ValueError("Receipt and native definition shot counts differ")
    if (receipt.get("raw_bit_order") != "syn1syn0"
            or receipt.get("syndrome_order") != "ZZZZ,XXXX"):
        raise ValueError("Receipt syndrome register order is not syn1syn0 / ZZZZ,XXXX")
    if receipt.get("postselection") != "none" or definition.get("heralding_mode") != "none":
        raise ValueError("Primary audit requires all shots without heralding or postselection")
    if definition.get("qubit_mapping") is not None:
        raise ValueError("Audit requires explicit physical loci, without a separate qubit mapping")
    experiments = receipt["experiments"]
    if not (len(circuits) == len(definition["circuits"]) == len(experiments) > 0):
        raise ValueError("Native circuit count differs from the receipt")
    if receipt.get("total_requested_shots") != shots * len(circuits):
        raise ValueError("Receipt total shot budget differs from its circuit array")
    normalized = normalize_export(exported, bit_order="measurement-keys", shots=shots)
    if normalized != receipt.get("raw_counts"):
        raise ValueError("Dashboard counts or measurement-key order differ from SDK receipt counts")
    calibration = receipt["calibration"]
    ids = [calibration_id, calibration.get("calibration_set_id"),
           definition.get("calibration_set_id"), receipt.get("reported_calibration_set_id"),
           receipt["compatibility"].get("backend_calibration_set_id")]
    if not all(value == calibration_id for value in ids):
        raise ValueError("Snapshot, native definition, backend and reported calibration IDs differ")
    if calibration.get("sha256") != calibration_sha256:
        raise ValueError("Calibration snapshot fingerprint differs from the execution receipt")
    plans = {}
    checks = []
    for index, (experiment, circuit, native) in enumerate(
            zip(experiments, circuits, definition["circuits"])):
        if circuit_signature(circuit) != experiment["signature"]:
            raise ValueError(f"Circuit {index}: QPY fingerprint differs from the receipt")
        if circuit.name != native["name"]:
            raise ValueError(f"Circuit {index}: native circuit name/order mismatch")
        if [(r.name, len(r)) for r in circuit.cregs] != [("syn", 2)]:
            raise ValueError(f"Circuit {index}: expected exactly the syn[2] register")
        backend = experiment["backend"]
        if backend.get("name") != receipt.get("quantum_computer"):
            raise ValueError(f"Circuit {index}: backend identity differs from receipt")
        if backend["architecture"]["calibration_set_id"] != calibration_id:
            raise ValueError(f"Circuit {index}: recorded target calibration differs")
        names = {int(k): v for k, v in backend["device_qubit_names"].items()}
        if set(names) != set(range(circuit.num_qubits)) or len(set(names.values())) != len(names):
            raise ValueError(f"Circuit {index}: incomplete or ambiguous physical qubit names")
        # The installed, pinned IQM serializer independently recovers all gate
        # angles, ordered physical loci and classical measurement keys from QPY.
        serialized = json.loads(json.dumps([asdict(x) for x in serialize_instructions(circuit, names)]))
        if serialized != native["instructions"]:
            raise ValueError(f"Circuit {index}: native instructions differ from saved QPY")
        operations = backend["architecture"]["gates"]
        for operation in serialized:
            if operation["name"] == "barrier":
                continue
            allowed = {tuple(locus) for impl in operations[operation["name"]]["implementations"].values()
                       for locus in impl["loci"]}
            locus = tuple(operation["locus"])
            if locus not in allowed and not (operation["name"] == "cz" and locus[::-1] in allowed):
                raise ValueError(f"Circuit {index}: instruction unsupported by recorded backend target")
        measurements = [op for op in serialized if op["name"] == "measure"]
        sites = {}
        for item in circuit.data:
            if item.operation.name == "measure":
                sites[circuit.find_bit(item.clbits[0]).index] = names[circuit.find_bit(item.qubits[0]).index]
        if (set(sites) != {0, 1} or len(measurements) != 2
                or {op["args"]["key"] for op in measurements} != set(KEYS)
                or {m["classical_bit_index"]: m["device_name"] for m in backend["measurement_map"]} != sites):
            raise ValueError(f"Circuit {index}: syndrome measurement sites/order differ")
        if circuit.layout is None:
            raise ValueError(f"Circuit {index}: missing source-to-device layout")
        initial, final = source_layout_indices(circuit)
        for saved_key, current in [
            ("initial_indices_of_source_wires", initial),
            ("final_indices_of_source_wires", final),
        ]:
            if backend[saved_key] != current:
                raise ValueError(f"Circuit {index}: recorded layout differs from QPY")
        counts = dict(circuit.count_ops())
        if counts != backend["compiled_operation_counts"] or circuit.depth() != backend["compiled_depth"]:
            raise ValueError(f"Circuit {index}: recorded native metrics differ from QPY")
        variant = experiment["variant"]
        plan = experiment["plan"]
        if variant in plans and plans[variant] != plan:
            raise ValueError("Variant layout/seed must be fixed across inputs and error types")
        plans[variant] = plan
        checks.append({"index": index, "variant": variant, "case_id": experiment["case_id"],
                       "native_name": native["name"], "signature": experiment["signature"],
                       "native_definition_matches_qpy": True, "recorded_target_supported": True,
                       "native_cz": counts.get("cz", 0), "native_r": counts.get("r", 0),
                       "depth": circuit.depth(), "syndrome_sites_s0s1": [sites[0], sites[1]],
                       "initial_source_device_sites": [names[q] for q in backend["initial_indices_of_source_wires"]],
                       "final_source_device_sites": [names[q] for q in backend["final_indices_of_source_wires"]]})
    # Also validates equal cases/shots across variants and syndrome/type labels.
    analysis = analyze_comparison(receipt)
    return {"source": "local audit of user-supplied IQM execution evidence; no new hardware run",
            "job_id": job_id, "backend": receipt["quantum_computer"],
            "circuits": len(checks), "shots_per_circuit": shots, "total_shots": shots * len(checks),
            "receipt_counts_match_dashboard_export": True,
            "export_bit_order_verified_against_sdk_receipt": "measurement-keys; Qiskit display syn1syn0",
            "matching_job_receipt_supplied": True, "native_definition_matches_qpy": True,
            "recorded_layout_verified": True, "recorded_calibration_linkage_verified": True,
            "calibration_set_id": calibration_id, "calibration_snapshot_sha256": calibration_sha256,
            "fresh_server_query_performed": False, "postselection": "none", "retained_fraction": 1.0,
            "case_checks": checks,
            "variants": {v: {k: g[k] for k in ("successes", "shots", "success_rate", "wilson_95")}
                         for v, g in analysis["variants"].items()},
            "changes_against_original": analysis["changes_against_original"],
            "limitations": ["Native definition is client-saved, not an independently retrieved server payload.",
                            "Only syndrome ancillas were measured; hardware logical-state fidelity is unavailable."]}

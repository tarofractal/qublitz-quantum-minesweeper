"""Import dashboard counts without guessing bit or circuit order from success.

An IQM dashboard export has no experiment labels, circuit, layout, or backend
receipt. A prepared protocol supplies a reproducible reconstruction, not proof
that that protocol was submitted. Both the original export and this distinction
are retained in the imported result.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

from .artifacts import timestamp, write_json
from .comparison_analysis import analyze_file

KEYS = ("syn_2_0_0", "syn_2_0_1")
BIT_ORDERS = ("measurement-keys", "qiskit")


def fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    return {"filename": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def normalize_export(items, *, bit_order: str, shots: int) -> list[dict[str, int]]:
    """Return Qiskit syn1syn0 counts; character convention is supplied explicitly.

    measurement-keys: character j belongs to measurement_keys[j].
    qiskit: the export is already a syn1syn0 display string.
    Neither convention is selected by maximizing the apparent accuracy.
    """
    if bit_order not in BIT_ORDERS:
        raise ValueError("Declare export bit order: measurement-keys or qiskit")
    if not isinstance(items, list) or not items:
        raise ValueError("Expected a nonempty IQM export array")
    if not isinstance(shots, int) or isinstance(shots, bool) or shots <= 0:
        raise ValueError("Expected positive integer shots per circuit")
    converted = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Export circuit {index} must be an object")
        keys = item.get("measurement_keys")
        if (not isinstance(keys, list) or len(keys) != 2
                or any(not isinstance(key, str) for key in keys) or set(keys) != set(KEYS)):
            raise ValueError(f"Export circuit {index}: need unique syn[0] and syn[1] measurement keys")
        raw = item.get("sorted_counts")
        if not isinstance(raw, dict) or not raw:
            raise ValueError(f"Export circuit {index}: missing counts")
        normalized = Counter()
        for string, count in raw.items():
            if not isinstance(string, str) or len(string) != 2 or any(bit not in "01" for bit in string):
                raise ValueError(f"Export circuit {index}: expected exactly two binary characters")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(f"Export circuit {index}: counts must be nonnegative integers")
            if bit_order == "measurement-keys":
                by_key = dict(zip(keys, string))
                string = by_key[KEYS[1]] + by_key[KEYS[0]]
            normalized[string] += count
        total = item.get("total_counts")
        if (not isinstance(total, (int, float)) or isinstance(total, bool)
                or not math.isfinite(total) or total != shots or sum(normalized.values()) != shots):
            raise ValueError(f"Export circuit {index}: shot mismatch; all requested shots must be retained")
        converted.append(dict(normalized))
    return converted


def import_export(export_path: Path, protocol_path: Path, out: Path, *, bit_order: str, job_id: str) -> dict:
    """Associate array indices with a fixed protocol and analyze every shot."""
    job_id = str(UUID(job_id))
    protocol = json.loads(protocol_path.read_text())
    exported = json.loads(export_path.read_text())
    experiments = protocol.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        raise ValueError("Protocol must provide the fixed experiment array")
    counts = normalize_export(exported, bit_order=bit_order, shots=protocol["shots_per_circuit"])
    if len(counts) != len(experiments):
        raise ValueError("Export circuit count does not match the supplied protocol")
    if protocol.get("job_id") and str(protocol["job_id"]) != job_id:
        raise ValueError("Protocol receipt belongs to a different job")
    receipt_linked = (protocol.get("source") == "IQM_QPU_comparison" and protocol.get("job_id") == job_id
                      and protocol.get("configuration_verified_from_submission") is not False
                      and protocol.get("provenance", {}).get("matching_job_receipt_supplied") is not False)
    basis = ("experiment metadata from matching job receipt" if receipt_linked else
             "array indices associated with prepared Run Ready protocol; submitted order not independently verified")
    provenance = {
        "export": fingerprint(export_path), "protocol": fingerprint(protocol_path),
        "job_id_basis": "user-supplied export filename/argument",
        "configuration_basis": basis, "matching_job_receipt_supplied": receipt_linked,
        "original_export_bit_order": bit_order,
        "bit_order_basis": "explicit character convention; independently checked with asymmetric X and Z controls",
        "conversion": "measurement_keys indexed by syn clbit, then displayed syn1syn0" if bit_order == "measurement-keys" else "none",
        "live_backend_identity_verified": False, "live_layout_verified": False,
        "calibration_linkage_verified": False, "run_timestamps_available_in_export": False,
        "native_artifact_scope": "prepared offline circuits; correspondence to actual submitted native circuits needs original receipt",
        "logical_state_fidelity": "not measured; only the two syndrome ancillas were read",
    }
    saved = deepcopy(protocol)
    saved.update(source="user-supplied IQM hardware dashboard export", status="imported hardware counts",
                 imported_at_utc=timestamp(), job_id=job_id, raw_bit_order="syn1syn0",
                 raw_counts=counts, original_export=exported, provenance=provenance)
    # Validate all pairings, expected syndromes and all-shot metrics before writing.
    from .comparison_analysis import analyze_comparison
    analysis = analyze_comparison(saved)
    controls = [row for row in analysis["per_case"] if row["injected_error"] in ("X", "Z")]
    provenance["asymmetric_control_checks"] = [
        {"variant": row["variant"], "case_id": row["case_id"],
         "expected_syndrome": row["expected_syndrome"],
         "observed_syndrome_counts": row["observed_syndrome_counts_human_order"],
         "expected_is_unique_mode": (
             row["observed_syndrome_counts_human_order"].get("".join(map(str, row["expected_syndrome"])), 0)
             > max((n for key, n in row["observed_syndrome_counts_human_order"].items()
                    if key != "".join(map(str, row["expected_syndrome"]))), default=-1))}
        for row in controls]
    provenance["asymmetric_controls_support_declared_order"] = (
        {row["injected_error"] for row in controls} == {"X", "Z"}
        and all(row["expected_is_unique_mode"] for row in provenance["asymmetric_control_checks"]))
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "imported-comparison.json", saved)
    return analyze_file(out / "imported-comparison.json")

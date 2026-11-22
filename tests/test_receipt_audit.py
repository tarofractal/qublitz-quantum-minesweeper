"""Real execution artifacts must bind counts, bit order, gates and calibration."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from qiskit import qpy

from minesweeper.experiments import Error
from minesweeper.native_verification import source_layout_indices, verify_native
from minesweeper.placement import Plan, source_for_plan
from minesweeper.receipt_audit import audit_packet
from minesweeper.states import preparation

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "results/iqm-comparison"
JOB = "01a20070-6eb5-7033-942a-a41474a1922e"


@pytest.fixture(scope="module")
def packet():
    calibration = (ROOT / "data/calibration.json").read_bytes()
    with (PACKET / "all-native.qpy").open("rb") as stream:
        circuits = qpy.load(stream)
    return {"receipt": json.loads((PACKET / "job.json").read_text()),
            "definition": json.loads((PACKET / "iqm-job-definition.json").read_text()),
            "circuits": circuits,
            "exported": json.loads((ROOT / "data/iqm-comparison-01a20070/export.json").read_text()),
            "job_id": JOB, "calibration_id": json.loads(calibration)["describes_id"],
            "calibration_sha256": hashlib.sha256(calibration).hexdigest()}


def test_real_receipt_binds_native_definition_counts_layout_and_calibration(packet):
    audit = audit_packet(**packet)
    assert audit["circuits"] == 8 and audit["total_shots"] == 2048
    assert audit["receipt_counts_match_dashboard_export"] is True
    assert audit["recorded_calibration_linkage_verified"] is True
    assert audit["native_definition_matches_qpy"] is True
    assert audit["fresh_server_query_performed"] is False
    assert audit["variants"]["original"]["successes"] == 759
    assert audit["variants"]["improved"]["successes"] == 921
    assert {tuple(row["syndrome_sites_s0s1"]) for row in audit["case_checks"]
            if row["variant"] == "improved"} == {("QB1", "QB10")}


@pytest.mark.parametrize("mutation", ["job_id", "export_order", "counts", "calibration", "snapshot",
                                      "instruction", "measure_key", "layout", "target_edge", "heralding"])
def test_inconsistent_execution_artifacts_are_rejected(packet, mutation):
    value = deepcopy(packet)
    if mutation == "job_id":
        value["job_id"] = "01a1fff5-31e3-744f-89da-cb1d14f7bacb"
    elif mutation == "export_order":
        for item in value["exported"]:
            item["measurement_keys"].reverse()
    elif mutation == "counts":
        value["receipt"]["raw_counts"][0]["00"] -= 1
        value["receipt"]["raw_counts"][0]["11"] += 1
    elif mutation == "calibration":
        value["definition"]["calibration_set_id"] = "wrong-calibration"
    elif mutation == "snapshot":
        value["calibration_sha256"] = "0" * 64
    elif mutation == "instruction":
        value["definition"]["circuits"][0]["instructions"][0]["args"]["angle"] += 0.1
    elif mutation == "measure_key":
        instructions = value["definition"]["circuits"][0]["instructions"]
        next(op for op in instructions if op["name"] == "measure")["args"]["key"] = "syn_2_0_1"
    elif mutation == "layout":
        value["receipt"]["experiments"][0]["backend"]["final_indices_of_source_wires"].reverse()
    elif mutation == "target_edge":
        value["receipt"]["experiments"][0]["backend"]["architecture"]["gates"]["cz"]["implementations"] = {}
    elif mutation == "heralding":
        value["definition"]["heralding_mode"] = "zeros"
    with pytest.raises(ValueError):
        audit_packet(**value)


@pytest.mark.parametrize("index", range(8))
@pytest.mark.parametrize("label", ["0", "1", "+", "-", "+i", "-i"])
def test_execution_native_isometry_preserves_six_logical_inputs(packet, index, label):
    experiment = packet["receipt"]["experiments"][index]
    native = packet["circuits"][index]
    plan = Plan.from_dict(experiment["plan"])
    error = Error() if experiment["error"] == "I" else Error(experiment["error"], experiment["location"])
    if label == experiment["input"]:
        probe = native  # Test the exact unmodified execution circuit as well.
    else:
        # Factor out the submitted input preparation at its INITIAL physical
        # wire. This tests the same compiled encoding/check isometry on another
        # logical input; these prepended probes are local simulations only.
        probe = native.copy_empty_like()
        probe.global_phase = 0
        initial = source_layout_indices(native)[0][0]
        probe.compose(preparation(label), qubits=[initial], inplace=True)
        probe.compose(preparation(experiment["input"]).inverse(), qubits=[initial], inplace=True)
        probe.compose(native, inplace=True)
        probe._layout = native.layout
    check = verify_native(plan, source_for_plan(plan, label, error), probe, label, error)
    assert check["native_data_preservation_fidelity"] == pytest.approx(1, abs=1e-10)
    assert check["observed_syndrome"] == experiment["expected_syndrome"]

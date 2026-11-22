"""Dashboard ordering, raw evidence, protocol provenance and SDK auth regressions."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from minesweeper.comparison import _token, run_comparison
from minesweeper.iqm_export import import_export, normalize_export

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "data/iqm-comparison-01a20070/export.json"
PROTOCOL = ROOT / "results/comparison-prepared/manifest.json"
JOB = "01a20070-6eb5-7033-942a-a41474a1922e"


def test_real_hardware_export_has_reproducible_all_shot_gain(tmp_path):
    result = import_export(EXPORT, PROTOCOL, tmp_path, bit_order="measurement-keys", job_id=JOB)
    original, improved = (result["variants"][v] for v in ("original", "improved"))
    assert (original["successes"], original["shots"]) == (759, 1024)
    assert (improved["successes"], improved["shots"]) == (921, 1024)
    assert result["changes_against_original"]["improved"]["change_percentage_points"] == pytest.approx(15.8203125)
    assert result["postselection"] == "none" and result["retained_fraction"] == 1
    p = result["provenance"]
    assert p["asymmetric_controls_support_declared_order"] is True
    assert p["matching_job_receipt_supplied"] is False
    assert p["live_layout_verified"] is False
    assert p["calibration_linkage_verified"] is False
    saved = json.loads((tmp_path / "imported-comparison.json").read_text())
    assert saved["original_export"] == json.loads(EXPORT.read_text())
    assert saved["raw_counts"][2]["01"] == 231  # X1: human 10, Qiskit 01.
    assert saved["raw_counts"][6]["10"] == 225  # Z1: human 01, Qiskit 10.
    assert result["logical_state_fidelity"] == "not measured by syndrome counts"
    assert original["confusion_counts"]["X"]["Z"] == 11
    assert improved["confusion_counts"]["Z"]["X"] == 2


def test_wrong_explicit_order_is_reported_not_silently_swapped(tmp_path):
    result = import_export(EXPORT, PROTOCOL, tmp_path, bit_order="qiskit", job_id=JOB)
    assert result["provenance"]["asymmetric_controls_support_declared_order"] is False
    assert result["variants"]["improved"]["successes"] == 470
    assert result["variants"]["original"]["successes"] == 398


def test_measurement_key_order_is_used_even_when_the_key_array_is_reversed():
    item = {"measurement_keys": ["syn_2_0_1", "syn_2_0_0"],
            "sorted_counts": {"01": 3, "10": 1}, "total_counts": 4.0}
    assert normalize_export([item], bit_order="measurement-keys", shots=4) == [{"01": 3, "10": 1}]


@pytest.mark.parametrize("mutation", ["empty", "keys", "duplicate_keys", "negative", "fractional", "boolean",
                                      "nonbinary", "width", "spaces", "total", "missing_shots", "nan"])
def test_malformed_exports_cannot_be_scored(mutation):
    items = deepcopy(json.loads(EXPORT.read_text()))
    if mutation == "empty": items = []
    elif mutation == "keys": items[0]["measurement_keys"] = ["a", "b"]
    elif mutation == "duplicate_keys": items[0]["measurement_keys"] = ["syn_2_0_0"] * 2
    elif mutation == "negative": items[0]["sorted_counts"]["00"] = -1
    elif mutation == "fractional": items[0]["sorted_counts"]["00"] = 186.5
    elif mutation == "boolean": items[0]["sorted_counts"]["00"] = True
    elif mutation == "nonbinary": items[0]["sorted_counts"] = {"0x": 256}
    elif mutation == "width": items[0]["sorted_counts"] = {"001": 256}
    elif mutation == "spaces": items[0]["sorted_counts"] = {"0 0": 256}
    elif mutation == "total": items[0]["total_counts"] = 255
    elif mutation == "missing_shots": items[0]["sorted_counts"]["00"] = 185
    elif mutation == "nan": items[0]["total_counts"] = float("nan")
    with pytest.raises(ValueError):
        normalize_export(items, bit_order="measurement-keys", shots=256)


def test_missing_order_is_rejected():
    with pytest.raises(ValueError, match="Declare export bit order"):
        normalize_export(json.loads(EXPORT.read_text()), bit_order=None, shots=256)


def test_mismatched_export_and_protocol_lengths_are_rejected(tmp_path):
    protocol = json.loads(PROTOCOL.read_text())
    protocol["experiments"].pop()
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="circuit count"):
        import_export(EXPORT, path, tmp_path, bit_order="measurement-keys", job_id=JOB)


def test_a_receipt_for_a_different_job_cannot_be_used(tmp_path):
    protocol = json.loads(PROTOCOL.read_text())
    protocol["source"] = "IQM_QPU_comparison"
    protocol["job_id"] = "01a1fff5-31e3-744f-89da-cb1d14f7bacb"
    path = tmp_path / "job.json"
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="different job"):
        import_export(EXPORT, path, tmp_path, bit_order="measurement-keys", job_id=JOB)


def test_retrieved_counts_cannot_promote_reconstructed_configuration_to_verified(tmp_path):
    protocol = json.loads(PROTOCOL.read_text())
    protocol.update(source="IQM_QPU_comparison", job_id=JOB, configuration_verified_from_submission=False,
                    provenance={"matching_job_receipt_supplied": False})
    path = tmp_path / "retrieved-counts-with-inferred-protocol.json"
    path.write_text(json.dumps(protocol))
    result = import_export(EXPORT, path, tmp_path, bit_order="measurement-keys", job_id=JOB)
    assert result["provenance"]["matching_job_receipt_supplied"] is False
    assert "not independently verified" in result["provenance"]["configuration_basis"]


def test_export_import_cli_needs_explicit_inputs(tmp_path):
    args = SimpleNamespace(mode="import-export", out=tmp_path, export_file=EXPORT,
                           export_bit_order=None, job_id=JOB)
    with pytest.raises(SystemExit, match="import-export needs"):
        run_comparison(args)


@pytest.mark.parametrize("env_name", ["IQM_TOKEN", "IQM_TOKENS_FILE"])
def test_run_ready_env_auth_is_not_passed_twice(monkeypatch, env_name):
    monkeypatch.delenv("IQM_TOKEN", raising=False)
    monkeypatch.delenv("IQM_TOKENS_FILE", raising=False)
    monkeypatch.setenv(env_name, "placeholder-for-unit-test-only")
    # SDK reads the environment. Passing its value as token= again causes an
    # ambiguous credential-source error in this IQM client release.
    assert _token(prompt=True) is None


def test_missing_credentials_do_not_prompt_in_a_noninteractive_process(monkeypatch):
    monkeypatch.delenv("IQM_TOKEN", raising=False)
    monkeypatch.delenv("IQM_TOKENS_FILE", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit, match="Set IQM_TOKEN privately"):
        _token(prompt=True)


def test_every_qpy_reloaded_native_layout_matches_its_saved_manifest():
    from qiskit import qpy
    from iqm.qiskit_iqm.fake_backends.fake_garnet import IQMFakeGarnet
    from minesweeper.hardware import backend_metadata, validate_native
    from minesweeper.placement import circuit_signature
    protocol = json.loads(PROTOCOL.read_text())
    with (PROTOCOL.parent / "all-native.qpy").open("rb") as stream:
        circuits = qpy.load(stream)
    assert len(circuits) == len(protocol["experiments"]) == 8
    backend = IQMFakeGarnet()
    for circuit, experiment in zip(circuits, protocol["experiments"]):
        validate_native(circuit, backend)
        assert circuit_signature(circuit) == experiment["signature"]
        actual = backend_metadata(backend, circuit)
        expected = experiment["backend"]
        for name in ("initial_indices_of_source_wires", "final_indices_of_source_wires",
                     "measurement_map", "compiled_operation_counts", "compiled_depth"):
            assert actual[name] == expected[name]


def test_retrieve_existing_job_without_receipt_never_submits_a_new_job(tmp_path, monkeypatch):
    import iqm.qiskit_iqm
    import minesweeper.comparison as comparison
    calls = []
    class Backend:
        def retrieve_job(self, job_id):
            assert job_id == JOB
            calls.append("retrieve")
            return "existing-job-placeholder"
        def run(self, *args, **kwargs):
            raise AssertionError("Retrieval must not submit")
    class Provider:
        def __init__(self, url, quantum_computer, token):
            assert url == "https://example.invalid/unit-test-only"
            assert quantum_computer == "unit-test-not-a-QPU" and token is None
        def get_backend(self):
            return Backend()
    def finished(job, manifest, out):
        assert job == "existing-job-placeholder" and out == tmp_path
        assert manifest["job_id"] == JOB
        assert manifest["provenance"]["matching_job_receipt_supplied"] is False
        return manifest
    monkeypatch.setattr(iqm.qiskit_iqm, "IQMProvider", Provider)
    monkeypatch.setattr(comparison, "finish_comparison_job", finished)
    monkeypatch.setenv("IQM_TOKEN", "placeholder-for-unit-test-only")
    args = SimpleNamespace(mode="retrieve", out=tmp_path, result_file=None, job_id=JOB,
                           protocol_file=PROTOCOL, url="https://example.invalid/unit-test-only",
                           computer="unit-test-not-a-QPU", prompt_token=False)
    result = run_comparison(args)
    assert result["source"] == "IQM_QPU_comparison" and calls == ["retrieve"]


def test_completed_receipt_retains_submitted_native_circuits_and_calibration(tmp_path):
    from iqm.pulse import Circuit
    from minesweeper.comparison import finish_comparison_job
    from test_calibration_and_analysis import sample_manifest
    manifest = sample_manifest()
    counts = manifest.pop("raw_counts")
    class Result:
        success = True
        circuits = [Circuit(name="synthetic-retrieval-evidence", instructions=())]
        results = [SimpleNamespace(calibration_set_id="synthetic-calibration-not-hardware")]
        def to_dict(self):
            return {"circuits": self.circuits, "timeline": {"completed": "unit-test-only"}}
        def get_counts(self, index):
            return counts[index]
    class Job:
        def job_id(self):
            return "mock-completed-evidence-not-hardware"
        def result(self, *, timeout):
            return Result()
    saved = finish_comparison_job(Job(), manifest, tmp_path)
    evidence = json.loads((tmp_path / "iqm-result.json").read_text())
    assert evidence["circuits"][0]["name"] == "synthetic-retrieval-evidence"
    assert evidence["circuits"][0]["instructions"] == []
    assert saved["returned_calibration_set_ids"] == ["synthetic-calibration-not-hardware"]

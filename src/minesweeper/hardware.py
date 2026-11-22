"""IQM execution with pilot shots, local validation and recoverable job receipts.

prepare/fake are LOCAL SIMULATIONS. Only run/retrieve connect to IQM.
Hardware circuits have terminal measurements and require no feed-forward.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from qiskit import transpile
from qiskit_aer import AerSimulator

from .artifacts import save_circuit, timestamp, versions, write_json
from .experiments import Error, expected_syndrome, level4_experiment, repetition_experiment
from .states import preparation
from .verification import ideal_case, shot_metrics


def challenge_circuit(level: int, label: str, error: Error):
    prep = preparation(label)
    if level == 4:
        return level4_experiment(prep, error)
    if level == 1:
        return repetition_experiment(prep, 1, error, mode="coherent")
    raise ValueError("Hardware runner supports L4 classification or L1 coherent recovery")


def terminal_measurements_only(circuit) -> bool:
    measured = False
    for item in circuit.data:
        if item.operation.name == "measure":
            measured = True
        elif measured and item.operation.name != "barrier":
            return False
    return True


def backend_metadata(backend, compiled) -> dict:
    def name_at(index):
        try:
            return backend.index_to_qubit_name(index)
        except (KeyError, ValueError, IndexError):
            return f"index_{index}"
    measurement_map = []
    for item in compiled.data:
        if item.operation.name == "measure":
            q = compiled.find_bit(item.qubits[0]).index
            c = compiled.find_bit(item.clbits[0])
            measurement_map.append({"backend_qubit_index": q, "device_name": name_at(q),
                                    "classical_bit_index": c.index,
                                    "classical_registers": [[reg.name, idx] for reg, idx in c.registers]})
    result = {"name": backend.name, "num_qubits": backend.num_qubits,
              "native_operations": sorted(backend.operation_names),
              "coupling_map": [list(edge) for edge in backend.coupling_map.get_edges()],
              "device_qubit_names": {str(i): name_at(i) for i in range(backend.num_qubits)},
              "measurement_map": measurement_map,
              "dynamic_support": "not required: all measurements are terminal",
              "compiled_operation_counts": dict(compiled.count_ops()),
              "compiled_depth": compiled.depth()}
    architecture = getattr(backend, "architecture", None)
    if architecture is not None:
        result["architecture"] = architecture.model_dump(mode="json") if hasattr(architecture, "model_dump") else str(architecture)
    if compiled.layout is not None:
        final = compiled.layout.final_index_layout(filter_ancillas=True)
        # Qiskit 2.1.2 can iterate QPY-reloaded ancilla virtual bits while
        # allocating a source-only list in initial_index_layout(True), raising
        # IndexError. The unfiltered list is in input_qubit_mapping order:
        # original source wires first, then compiler-allocated ancillas.
        initial = compiled.layout.initial_index_layout(filter_ancillas=False)
        if len(initial) < len(final):
            raise ValueError("Compiled initial/final source layout sizes disagree")
        result["initial_indices_of_source_wires"] = initial[:len(final)]
        result["final_indices_of_source_wires"] = final
    return result


def validate_native(circuit, backend) -> None:
    """Catch unsupported operations or routing errors before any hardware job."""
    assert terminal_measurements_only(circuit), "Unexpected mid-circuit operation"
    for item in circuit.data:
        if item.operation.name == "barrier":
            continue
        qargs = tuple(circuit.find_bit(bit).index for bit in item.qubits)
        assert backend.target.instruction_supported(operation_name=item.operation.name, qargs=qargs), (
            item.operation.name, qargs)


def simulate_exact(circuit, level: int, expected: tuple[int, int], shots: int, seed: int) -> dict:
    # MPS handles routing through idle physical wires without a 2**N allocation.
    if any(item.operation.name == "move" for item in circuit.data):
        raise ValueError("Aer cannot faithfully model IQM MOVE as a qubit gate. "
                         "Use a Crystal QPU for this runner; no job was submitted.")
    backend = AerSimulator(method="matrix_product_state", max_parallel_threads=1)
    compiled = transpile(circuit, backend, optimization_level=0, seed_transpiler=seed)
    counts = backend.run(compiled, shots=shots, seed_simulator=seed).result().get_counts()
    metrics = shot_metrics(level, counts, expected)
    assert metrics["joint_success_rate"] == 1.0, metrics
    return {"source": "ideal_Aer_of_exact_hardware_circuit", **metrics}


def sample_fake_noise(circuit, backend, shots: int, seed: int) -> dict[str, int]:
    """Seeded Aer sampling using the official IQM fake backend's noise model.

    iqm-client 36.0.0 IQMFakeBackend.run forwards only shots, silently ignoring
    seed_simulator and method. Use Aer directly with unchanged native gate names
    so R/CZ noise still attaches. Crystal circuits only; no MOVE approximation.
    """
    validate_native(circuit, backend)
    if any(item.operation.name == "move" for item in circuit.data):
        raise ValueError("Resonator MOVE noise is not supported in this runner")
    simulator = AerSimulator(noise_model=backend.noise_model,
                             method="matrix_product_state", max_parallel_threads=1)
    return simulator.run(circuit, shots=shots, seed_simulator=seed).result().get_counts()


def analyze_saved(path: Path) -> dict:
    saved = json.loads(path.read_text())
    if "raw_counts" not in saved:
        raise ValueError("This job receipt has no results yet; retrieve the recorded job ID first")
    metrics = shot_metrics(saved["level"], saved["raw_counts"], tuple(saved["expected_syndrome"]))
    analysis = {"source": saved["source"], "job_id": saved.get("job_id"),
                "level": saved["level"], "input": saved["input"],
                "expected_syndrome": saved["expected_syndrome"], **metrics,
                "hardware_data_fidelity": "not measured"}
    write_json(path.parent / "analysis.json", analysis)
    print(json.dumps(analysis, indent=2))
    return analysis


def _finish_job(job, manifest: dict, out: Path) -> dict:
    manifest["job_id"] = str(job.job_id())
    manifest["status"] = "submitted; result pending"
    write_json(out / "job.json", manifest)  # Save the ID BEFORE any waiting.
    print(f"Job ID: {manifest['job_id']}", flush=True)
    try:
        result = job.result(timeout=60)
    except Exception as exc:
        manifest["result_fetch_exception_type"] = type(exc).__name__
        write_json(out / "job.json", manifest)
        print("Results are not available in this call. Retrieve the existing job; do not resubmit.")
        return manifest
    if not result.success:
        manifest.update(status="failed", completed_at_utc=timestamp(), result_success=False)
        write_json(out / "job.json", manifest)
        raise RuntimeError("IQM returned an unsuccessful result; inspect the saved job receipt")
    manifest.update(status="completed", completed_at_utc=timestamp(),
                    result_success=True, raw_counts=result.get_counts())
    write_json(out / "job.json", manifest)
    analyze_saved(out / "job.json")
    return manifest


def run_iqm(args):
    if args.mode == "analyze":
        return analyze_saved(args.result_file or args.out / "job.json")
    from iqm.qiskit_iqm import IQMProvider
    args.out.mkdir(parents=True, exist_ok=True)
    if args.mode == "run" and (args.out / "job.json").exists():
        raise SystemExit("This directory already contains a job receipt. Retrieve that job, "
                         "or choose a new --out directory for another experiment.")
    if args.mode == "retrieve":
        receipt = args.result_file or args.out / "job.json"
        manifest = json.loads(receipt.read_text())
        if manifest.get("source") != "IQM_QPU":
            raise ValueError("Retrieve expects a genuine IQM submission receipt")
        token = os.environ.get("IQM_TOKEN")
        if not token:
            raise SystemExit("Set IQM_TOKEN privately, then retrieve the saved job")
        provider = IQMProvider(args.url or os.environ.get("IQM_SERVER_URL") or manifest["server_url"],
                               quantum_computer=args.computer or manifest.get("quantum_computer"))
        backend = provider.get_backend()
        job = backend.retrieve_job(args.job_id or manifest["job_id"])
        return _finish_job(job, manifest, receipt.parent)

    error = Error() if args.error == "I" else Error(args.error, args.location)
    ideal = ideal_case(args.level, args.input, error)  # Reject illegal experiment configurations.
    expected = expected_syndrome(args.level, error)
    source = challenge_circuit(args.level, args.input, error)
    assert terminal_measurements_only(source)
    if args.level == 4:
        assert all(source.find_bit(item.qubits[0]).index in (4, 5)
                   for item in source.data if item.operation.name == "measure")
    save_circuit(source, args.out / "circuits", "source")
    local = simulate_exact(source, args.level, expected, args.shots, args.seed)
    write_json(args.out / "source-local-simulation.json", {"ideal": ideal, "finite_shots": local})

    live = args.mode == "run"
    url = args.url or os.environ.get("IQM_SERVER_URL")
    computer = args.computer or os.environ.get("IQM_QUANTUM_COMPUTER")
    if live:
        token = os.environ.get("IQM_TOKEN")
        if not url or not token:
            status = {"hardware_status": "Not run on IQM hardware.",
                      "reason": "IQM_SERVER_URL and IQM_TOKEN are required for authenticated access",
                      "source_circuit_local_verification": local}
            write_json(args.out / "hardware-status.json", status)
            raise SystemExit(status["reason"])
        provider = IQMProvider(url, quantum_computer=computer)
        backend = provider.get_backend()
    else:
        if args.level == 4:
            from iqm.qiskit_iqm.fake_backends.fake_garnet import IQMFakeGarnet
            backend = IQMFakeGarnet()
        else:
            from iqm.qiskit_iqm.fake_backends.fake_adonis import IQMFakeAdonis
            backend = IQMFakeAdonis()
    if backend.num_qubits < source.num_qubits:
        raise ValueError(f"Need {source.num_qubits} physical qubits; backend has {backend.num_qubits}")
    compiled = transpile(source, backend=backend, optimization_level=1, seed_transpiler=args.seed)
    validate_native(compiled, backend)
    # Verify precisely the routed circuit to be passed to backend.run.
    routed_local = simulate_exact(compiled, args.level, expected, args.shots, args.seed)
    save_circuit(compiled, args.out / "circuits", "native", render=False)
    metadata = backend_metadata(backend, compiled)
    write_json(args.out / "backend.json", metadata)
    write_json(args.out / "native-local-simulation.json", routed_local)
    manifest = {"created_at_utc": timestamp(), "software": versions(),
                "source": "IQM_QPU" if live else "IQM_fake_backend_SIMULATION",
                "level": args.level, "input": args.input, "injected_error": error.pauli,
                "error_location": error.location, "expected_syndrome": list(expected),
                "shots_requested": args.shots, "seed": args.seed, "backend": metadata,
                "raw_measurement_order": "s1s0" if args.level == 4 else "v2v1v0 s1s0",
                "local_source_check": local, "local_native_check": routed_local,
                "postselection": "none", "hardware_data_fidelity": "not measured"}
    if args.mode == "prepare":
        manifest.update(status="prepared locally", hardware_status="Not run on IQM hardware.")
        write_json(args.out / "hardware-status.json", manifest)
        print(f"Prepared {backend.name}; source and native-circuit simulation passed.")
        print("Not run on IQM hardware.")
        return manifest
    if args.mode == "fake":
        # IQM's bundled illustrative noise model; NOT measured device behavior.
        counts = sample_fake_noise(compiled, backend, args.shots, args.seed)
        manifest.update(status="completed locally", raw_counts=counts,
                        noise_execution="Seeded AerSimulator with official IQM fake noise_model; native R/CZ retained",
                        hardware_status="Not run on IQM hardware.")
        write_json(args.out / "job.json", manifest)
        analyze_saved(args.out / "job.json")
        return manifest
    manifest.update(server_url=url, quantum_computer=computer)
    # Validate the IQM serialization without submitting, then submit this circuit once.
    definition = backend.create_circuit_job_definition(compiled, shots=args.shots)
    if hasattr(definition, "model_dump"):
        write_json(args.out / "iqm-job-definition.json", definition.model_dump(mode="json"))
    write_json(args.out / "submission-plan.json", manifest)
    job = backend.run(compiled, shots=args.shots)
    return _finish_job(job, manifest, args.out)

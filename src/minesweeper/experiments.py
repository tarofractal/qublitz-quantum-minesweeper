"""Trusted experiment harness. ONLY this layer knows injected error and input.

The injection callable can be replaced by an unknown-error oracle. Recovery
functions in circuits.py never receive that oracle's configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

from .circuits import (decode_repetition, encode_repetition, extract_repetition,
                       recover_coherent, recover_dynamic, repetition_registers,
                       encoder_level4, extract_level4)


@dataclass(frozen=True)
class Error:
    pauli: str = "I"
    location: int | None = None

    def __post_init__(self):
        if self.pauli not in ("I", "X", "Y", "Z"):
            raise ValueError("Pauli must be I, X, Y or Z")
        if (self.pauli == "I") != (self.location is None):
            raise ValueError("Only I has location None")


def inject(circuit: QuantumCircuit, error: Error, n_data: int) -> None:
    if error.pauli != "I":
        if not 0 <= error.location < n_data:
            raise ValueError("Error location must identify a data qubit")
        getattr(circuit, error.pauli.lower())(error.location)


def repetition_stages(prep: QuantumCircuit, level: int, error: Error) -> dict[str, QuantumCircuit]:
    if level not in (1, 2, 3):
        raise ValueError("Expected repetition level 1, 2 or 3")
    if error.pauli not in ("I", {1: "X", 2: "Z", 3: "Y"}[level]):
        raise ValueError("Injected error is outside this level's promise")
    circuit = repetition_registers()
    stages = {"initial": circuit.copy()}
    circuit.compose(prep, [0], inplace=True)
    stages["prepared"] = circuit.copy()
    circuit.barrier(label="encode")
    encode_repetition(circuit)
    if level == 2:
        circuit.h([0, 1, 2])
    stages["encoded"] = circuit.copy()
    circuit.barrier(label="INJECT HERE")
    inject(circuit, error, 3)
    stages["injected"] = circuit.copy()
    circuit.barrier(label="recovery basis")
    if level == 2:
        circuit.h([0, 1, 2])
    stages["recovery_basis"] = circuit.copy()
    extract_repetition(circuit)
    stages["extracted"] = circuit.copy()
    return stages


def repetition_experiment(prep: QuantumCircuit, level: int, error: Error,
                          mode: str = "dynamic", measure: bool = True,
                          verify: bool = True, save_logical: bool = False) -> QuantumCircuit:
    if mode not in ("dynamic", "coherent"):
        raise ValueError("Recovery mode must be dynamic or coherent")
    if mode == "dynamic" and not measure:
        raise ValueError("Use coherent mode for a unitary, unmeasured circuit")
    circuit = repetition_stages(prep, level, error)["extracted"]
    syn = ClassicalRegister(2, "syn")
    if measure:
        circuit.add_register(syn)
    circuit.barrier(label="syndrome / recovery")
    if mode == "dynamic":
        circuit.measure([3, 4], syn)
        recover_dynamic(circuit, level, syn)
    else:
        recover_coherent(circuit, level)
    circuit.barrier(label="decode")
    decode_repetition(circuit)
    circuit.barrier(label="LOGICAL STATE HERE")
    if save_logical:
        # Aer-only diagnostic, before input-dependent verification gates.
        from qiskit_aer.library import save_density_matrix
        save_density_matrix(circuit, [0], label="logical")
    if verify:
        circuit.compose(prep.inverse(), [0], inplace=True)
    if measure:
        if mode == "coherent":
            circuit.measure([3, 4], syn)
        out = ClassicalRegister(3, "verify")
        circuit.add_register(out)
        circuit.measure([0, 1, 2], out)
    circuit.name = f"L{level}_{mode}_{error.pauli}{error.location}"
    return circuit


def level4_stages(prep: QuantumCircuit, error: Error) -> dict[str, QuantumCircuit]:
    circuit = QuantumCircuit(QuantumRegister(4, "d"), QuantumRegister(2, "a"))
    circuit.compose(prep, [0], inplace=True)
    stages = {"prepared": circuit.copy()}
    circuit.barrier(label="encode")
    circuit.compose(encoder_level4(), [0, 1, 2, 3], inplace=True)
    stages["encoded"] = circuit.copy()
    circuit.barrier(label="INJECT HERE")
    inject(circuit, error, 4)
    stages["injected"] = circuit.copy()
    circuit.barrier(label="ZZZZ and XXXX")
    extract_level4(circuit)
    stages["extracted"] = circuit.copy()
    return stages


def level4_experiment(prep: QuantumCircuit, error: Error, measure=True) -> QuantumCircuit:
    """Classify by reading ONLY a0=q4 and a1=q5. Data is never measured."""
    circuit = level4_stages(prep, error)["extracted"]
    circuit.name = f"L4_classify_{error.pauli}{error.location}"
    if measure:
        syn = ClassicalRegister(2, "syn")
        circuit.add_register(syn)
        circuit.measure([4, 5], syn)
    return circuit


def permitted_errors(level: int) -> tuple[Error, ...]:
    if level == 4:
        return (Error(),) + tuple(Error(p, j) for p in ("X", "Z", "Y") for j in range(4))
    if level not in (1, 2, 3):
        raise ValueError("Level must be 1, 2, 3 or 4")
    p = {1: "X", 2: "Z", 3: "Y"}[level]
    return (Error(),) + tuple(Error(p, j) for j in range(3))


def expected_syndrome(level: int, error: Error) -> tuple[int, int]:
    """Harness ground truth, deliberately separate from the recovery decoder."""
    if error not in permitted_errors(level):
        raise ValueError("Error outside level promise")
    if level == 4:
        # Anticommutation with ZZZZ, then XXXX.
        return (int(error.pauli in ("X", "Y")), int(error.pauli in ("Z", "Y")))
    return {None: (0, 0), 0: (1, 0), 1: (1, 1), 2: (0, 1)}[error.location]

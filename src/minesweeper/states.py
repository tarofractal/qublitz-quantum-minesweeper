"""Unitary preparation, including complex superpositions (no initialize/reset)."""
from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

INPUTS = ("0", "1", "+", "-", "+i", "-i")


def preparation(label: str) -> QuantumCircuit:
    circuit = QuantumCircuit(1, name=f"prepare_{label}")
    if label not in INPUTS:
        raise ValueError(f"Unknown input {label!r}; choose from {INPUTS}")
    if label == "1":
        circuit.x(0)
    elif label in ("+", "-", "+i", "-i"):
        circuit.h(0)
        if label == "-":
            circuit.z(0)
        elif label == "+i":
            circuit.s(0)
        elif label == "-i":
            circuit.sdg(0)
    return circuit


def amplitudes(alpha: complex, beta: complex) -> QuantumCircuit:
    """Prepare alpha|0>+beta|1> exactly, including alpha's global phase."""
    norm = np.sqrt(abs(alpha) ** 2 + abs(beta) ** 2)
    if not np.isclose(norm, 1.0):
        raise ValueError("Amplitudes must be normalized")
    theta = 2 * np.arctan2(abs(beta), abs(alpha))
    phi0 = np.angle(alpha) if abs(alpha) > 1e-15 else 0.0
    phi1 = np.angle(beta) if abs(beta) > 1e-15 else phi0
    circuit = QuantumCircuit(1, name="arbitrary_input")
    circuit.ry(float(theta), 0)
    circuit.p(float(phi1 - phi0), 0)
    circuit.global_phase = float(phi0)
    return circuit


def target_state(prep: QuantumCircuit) -> Statevector:
    if prep.num_qubits != 1 or prep.num_clbits:
        raise ValueError("Preparation must be a unitary one-qubit circuit")
    return Statevector.from_instruction(prep)

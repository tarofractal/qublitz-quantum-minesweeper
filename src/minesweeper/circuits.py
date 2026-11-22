"""Circuit primitives: recovery receives ONLY the level and syndrome.

Logical wires d0,d1,d2 are left,middle,right. Ancillas a0=q3 and a1=q4
store (d0 XOR d1,d1 XOR d2). Human ket order is d0 d1 d2.
Qiskit statevector ket order is the reverse, q4 q3 q2 q1 q0.
Classical registers are added syn, then verify, so raw counts print
"v2v1v0 s1s0". Never read raw "10" as human syndrome "10".
"""
from __future__ import annotations

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

LOCATION_BY_SYNDROME = {(0, 0): None, (1, 0): 0, (1, 1): 1, (0, 1): 2}


def encode_repetition(circuit: QuantumCircuit, data=(0, 1, 2)) -> None:
    circuit.cx(data[0], data[1])
    circuit.cx(data[0], data[2])


def decode_repetition(circuit: QuantumCircuit, data=(0, 1, 2)) -> None:
    circuit.cx(data[0], data[2])
    circuit.cx(data[0], data[1])


def extract_repetition(circuit: QuantumCircuit, data=(0, 1, 2), anc=(3, 4)) -> None:
    circuit.cx(data[0], anc[0])
    circuit.cx(data[1], anc[0])
    circuit.cx(data[1], anc[1])
    circuit.cx(data[2], anc[1])


def recovery_gate(level: int) -> str:
    if level not in (1, 2, 3):
        raise ValueError("Recovery applies to levels 1, 2, 3")
    return "y" if level == 3 else "x"


def recover_observed(circuit: QuantumCircuit, level: int, syndrome: tuple[int, int], data=(0, 1, 2)) -> None:
    """Classical branch for exact branch simulation; no access to injected error."""
    location = LOCATION_BY_SYNDROME[syndrome]
    if location is not None:
        getattr(circuit, recovery_gate(level))(data[location])


def recover_dynamic(circuit: QuantumCircuit, level: int, syn: ClassicalRegister, data=(0, 1, 2)) -> None:
    """Real mid-circuit measurements followed by Qiskit if_test branches."""
    for syndrome, location in LOCATION_BY_SYNDROME.items():
        if location is not None:
            value = syndrome[0] + 2 * syndrome[1]
            with circuit.if_test((syn, value)):
                getattr(circuit, recovery_gate(level))(data[location])


def recover_coherent(circuit: QuantumCircuit, level: int, data=(0, 1, 2), anc=(3, 4)) -> None:
    """Deferred-measurement alternative: syndrome-controlled X/Y gates."""
    gate = recovery_gate(level)
    for syndrome, location in LOCATION_BY_SYNDROME.items():
        if location is None:
            continue
        for bit, a in zip(syndrome, anc):
            if bit == 0:
                circuit.x(a)
        if gate == "y":
            circuit.sdg(data[location])
        circuit.ccx(anc[0], anc[1], data[location])
        if gate == "y":
            circuit.s(data[location])
        for bit, a in zip(syndrome, anc):
            if bit == 0:
                circuit.x(a)


def repetition_registers() -> QuantumCircuit:
    return QuantumCircuit(QuantumRegister(3, "d"), QuantumRegister(2, "a"))


def encoder_level4() -> QuantumCircuit:
    """Input on d0. Human order d0 d1 d2 d3:

    |0_L> = (|0000>+|1111>)/sqrt(2)
    |1_L> = (|0011>+|1100>)/sqrt(2).
    This selects two dimensions of the four-dimensional +1,+1 eigenspace.
    """
    circuit = QuantumCircuit(4, name="encode_L4")
    circuit.cx(0, 1)
    circuit.h(2)
    circuit.cx(2, 0)
    circuit.cx(2, 1)
    circuit.cx(2, 3)
    return circuit


def extract_level4(circuit: QuantumCircuit, data=(0, 1, 2, 3), anc=(4, 5)) -> None:
    """Nondemolition ZZZZ and XXXX checks; only ancillas need measurement."""
    for d in data:
        circuit.cx(d, anc[0])
    circuit.h(anc[1])
    for d in data:
        circuit.cx(anc[1], d)
    circuit.h(anc[1])


TYPE_BY_SYNDROME = {(0, 0): "I", (1, 0): "X", (0, 1): "Z", (1, 1): "Y"}


def classify(syndrome: tuple[int, int]) -> str:
    return TYPE_BY_SYNDROME[syndrome]

"""Equivalent QND checks on a six-cycle; a data chord permits 11 native CZs.

Source order is still d0,d1,d2,d3,aZ,aX. CNOT pair conjugation maps
ZZZZ -> Z1 Z3 and XXXX -> X0 X2. Undo the pairs to preserve all data.
"""
from __future__ import annotations

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from .experiments import Error, inject


def encode(circuit: QuantumCircuit, encoder: str = "root3") -> None:
    if encoder == "root3":
        # Source data graph: d1--d0--d3--d2; input on internal node d0.
        circuit.h(3)
        circuit.cx(3,0)
        circuit.cx(0,1)
        circuit.cx(3,2)
    elif encoder == "bridge":
        circuit.h(2)
        circuit.cx(2,5)
        circuit.cx(5,0)
        circuit.cx(2,5)  # aX returns to zero BEFORE error injection.
        circuit.cx(0,1)
        circuit.cx(2,3)
    else:
        raise ValueError("Encoder must be root3 or bridge")


def extract(circuit: QuantumCircuit) -> None:
    circuit.cx(0,1)
    circuit.cx(2,3)
    circuit.cx(1,4)
    circuit.cx(3,4)
    circuit.h(5)
    circuit.cx(5,0)
    circuit.cx(5,2)
    circuit.h(5)
    circuit.cx(0,1)
    circuit.cx(2,3)


def stages(prep: QuantumCircuit, error: Error, encoder="root3") -> dict:
    circuit=QuantumCircuit(QuantumRegister(4,"d"),QuantumRegister(2,"a"))
    circuit.compose(prep,[0],inplace=True)
    circuit.barrier(label="encode")
    encode(circuit,encoder)
    snapshots={"encoded":circuit.copy()}
    circuit.barrier(label="INJECT HERE")
    inject(circuit,error,4)
    snapshots["injected"]=circuit.copy()
    circuit.barrier(label="ZZZZ and XXXX")
    extract(circuit)
    snapshots["extracted"]=circuit.copy()
    return snapshots


def optimized_level4_experiment(prep: QuantumCircuit,error: Error,encoder="root3",measure=True):
    circuit=stages(prep,error,encoder)["extracted"]
    circuit.name=f"L4_{encoder}_{error.pauli}{error.location}"
    if measure:
        syn=ClassicalRegister(2,"syn")
        circuit.add_register(syn)
        circuit.measure([4,5],syn)
    return circuit


def six_cycle_layouts(backend,require_data_chord=True) -> list[list[int]]:
    """Enumerate deterministically, without a hardcoded chip placement."""
    adjacency={i:set() for i in range(backend.num_qubits)}
    for a,b in backend.target["cz"]:
        if a!=b:
            adjacency[a].add(b);adjacency[b].add(a)
    cycles=set()
    def visit(path):
        if len(path)==6:
            if path[0] in adjacency[path[-1]]:
                # Every oriented cycle placement matters: the ancilla roles differ.
                c=path
                if not require_data_chord or c[3] in adjacency[c[0]]:
                    cycles.add((c[0],c[1],c[4],c[3],c[2],c[5]))
            return
        for neighbor in sorted(adjacency[path[-1]]):
            if neighbor not in path:visit((*path,neighbor))
    for start in sorted(adjacency):visit((start,))
    return [list(layout) for layout in sorted(cycles)]


def cycle_layout(backend) -> list[int]:
    options=six_cycle_layouts(backend)
    if not options:
        raise ValueError("No six-cycle with a data chord; use bridge or the original routing path")
    return options[0]

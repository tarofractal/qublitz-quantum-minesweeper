"""State verification of exactly routed native circuits, with wire permutation."""
from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector,partial_trace,state_fidelity
from .circuits import classify
from .experiments import expected_syndrome,level4_stages
from .optimized_level4 import stages as optimized_stages
from .states import preparation


def source_layout_indices(compiled):
    """Return source-wire mappings without relying on layout dictionary order.

    QPY can restore Layout entries in physical rather than source order.
    Qiskit 2.1.2's filtered initial_index_layout iterates only its first N
    entries, which can then IndexError or omit source wires. The unfiltered
    array is indexed by input_qubit_mapping and is safe to slice afterwards.
    """
    if compiled.layout is None:
        raise ValueError("Native state verification needs the compiled final layout")
    final = compiled.layout.final_index_layout(filter_ancillas=True)
    initial = compiled.layout.initial_index_layout(filter_ancillas=False)[:len(final)]
    for indices in (initial, final):
        if (len(indices) != len(final) or len(set(indices)) != len(indices)
                or any(not isinstance(q, int) or not 0 <= q < compiled.num_qubits for q in indices)):
            raise ValueError("Invalid source-to-physical wire mapping")
    return initial, final


def _compact_unitary(compiled):
    unitary=compiled.remove_final_measurements(inplace=False)
    _,final=source_layout_indices(compiled)
    if len(final)!=6:raise ValueError("Expected six source wires in final layout")
    active=set(final)
    for item in unitary.data:
        if item.operation.name not in ("barrier","id"):
            active.update(unitary.find_bit(q).index for q in item.qubits)
    indices=sorted(active);lookup={p:i for i,p in enumerate(indices)}
    compact=QuantumCircuit(len(indices))
    compact.global_phase=unitary.global_phase
    for item in unitary.data:
        if item.operation.name in ("barrier","id"):continue
        if item.clbits or item.operation.name in ("measure","reset","if_else"):
            raise ValueError("Level-4 native verifier expects a unitary followed by final measurements")
        compact.append(item.operation,[lookup[unitary.find_bit(q).index] for q in item.qubits])
    return compact,[lookup[p] for p in final],indices


def verify_native(plan,source,compiled,label,error) -> dict:
    prep=preparation(label)
    snapshots=(level4_stages(prep,error) if plan.encoder=="original" else
               optimized_stages(prep,error,plan.encoder))
    post_error=Statevector.from_instruction(snapshots["injected"])
    data_target=Statevector(post_error.data[:16])
    if not np.isclose(np.vdot(data_target.data,data_target.data),1):
        raise AssertionError("Encoding ancillas were not zero at error injection")
    source_after=Statevector.from_instruction(snapshots["extracted"])
    source_fidelity=float(state_fidelity(partial_trace(source_after,[4,5]),data_target))
    compact,final,indices=_compact_unitary(compiled)
    actual=Statevector.from_instruction(compact)
    expected=QuantumCircuit(compact.num_qubits)
    expected.compose(source.remove_final_measurements(inplace=False),qubits=final,inplace=True)
    full_fidelity=float(state_fidelity(actual,Statevector.from_instruction(expected)))
    # Reorder physical amplitudes so logical d0..d3 become the low four axes.
    order=final[:4]+[q for q in range(compact.num_qubits) if q not in final[:4]]
    axes=[compact.num_qubits-1-q for q in order[::-1]]
    reordered=Statevector(actual.data.reshape([2]*compact.num_qubits).transpose(axes).reshape(-1))
    data=partial_trace(reordered,list(range(4,compact.num_qubits)))
    preservation=float(state_fidelity(data,data_target))
    p=actual.probabilities(qargs=final[4:6])
    index=int(np.argmax(p));bits=(index&1,(index>>1)&1)
    target=expected_syndrome(4,error)
    record={"source":"ideal native-circuit statevector", "source_data_preservation_fidelity":source_fidelity,
            "native_full_state_fidelity":full_fidelity,"native_data_preservation_fidelity":preservation,
            "expected_syndrome":list(target),"observed_syndrome":list(bits),
            "classification_from_syndrome":classify(bits),"syndrome_probability":float(p[index]),
            "compact_physical_indices":indices,"final_source_indices_in_compact_circuit":final}
    if min(source_fidelity,full_fidelity,preservation,float(p[index]))<1-1e-10 or bits!=target:
        raise AssertionError(record)
    return record

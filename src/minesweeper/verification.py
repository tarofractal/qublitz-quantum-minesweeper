"""Exact quantum-state checks and finite-shot analysis, with explicit bit order."""
from __future__ import annotations

from collections import Counter
import numpy as np
from qiskit.quantum_info import Statevector, partial_trace, state_fidelity

from .circuits import classify, decode_repetition, recover_observed
from .experiments import (Error, expected_syndrome, level4_stages,
                          repetition_experiment, repetition_stages)
from .states import preparation, target_state

TOLERANCE = 1e-10


def syndrome_distribution(state: Statevector, anc: list[int]) -> dict[str, float]:
    # Qargs are little endian; index = s0 + 2*s1, human text is s0s1.
    p = state.probabilities(anc)
    return {f"{i & 1}{(i >> 1) & 1}": float(prob) for i, prob in enumerate(p)}


def observed_bits(distribution: dict[str, float]) -> tuple[int, int]:
    key = max(distribution, key=distribution.get)
    return tuple(int(x) for x in key)


def project_syndrome(state: Statevector, anc_start: int, bits: tuple[int, int]) -> tuple[Statevector, float]:
    """Project onto the OBSERVED branch, not the known injected location."""
    wanted = bits[0] + 2 * bits[1]
    indices = np.arange(len(state.data))
    vector = np.where(((indices >> anc_start) & 3) == wanted, state.data, 0)
    probability = float(np.vdot(vector, vector).real)
    if probability < 1e-15:
        raise AssertionError("Cannot condition on a zero-probability syndrome")
    return Statevector(vector / np.sqrt(probability)), probability


def ideal_case(level: int, label: str, error: Error) -> dict:
    prep = preparation(label)
    expected = expected_syndrome(level, error)
    record = {"source": "ideal_statevector", "level": level, "input": label,
              "injected_error": error.pauli, "error_location": error.location,
              "expected_syndrome": list(expected),
              "syndrome_order": "ZZZZ,XXXX" if level == 4 else "left-middle,middle-right",
              "qiskit_raw_order": "s1s0" if level == 4 else "v2v1v0 s1s0"}
    if level < 4:
        stages = repetition_stages(prep, level, error)
        state = Statevector.from_instruction(stages["extracted"])
        distribution = syndrome_distribution(state, [3, 4])
        bits = observed_bits(distribution)
        projected, branch_probability = project_syndrome(state, 3, bits)
        recovery = stages["initial"].copy()
        recover_observed(recovery, level, bits)
        decode_repetition(recovery)
        recovered = projected.evolve(recovery)
        density = partial_trace(recovered, [1, 2, 3, 4])
        fidelity = float(state_fidelity(density, target_state(prep)))
        full_target = Statevector.from_label("00").tensor(target_state(prep))
        full_fidelity = float(state_fidelity(partial_trace(recovered, [3, 4]), full_target))
        coherent = repetition_experiment(prep, level, error, mode="coherent", measure=False, verify=False)
        coherent_density = partial_trace(Statevector.from_instruction(coherent), [1, 2, 3, 4])
        coherent_fidelity = float(state_fidelity(coherent_density, target_state(prep)))
        record.update(ideal_state_fidelity=fidelity,
                      ideal_decoded_data_fidelity=full_fidelity,
                      coherent_state_fidelity=coherent_fidelity,
                      observed_branch_probability=branch_probability,
                      recovery="I" if bits == (0, 0) else ("Y" if level == 3 else "X"))
        assert fidelity >= 1 - TOLERANCE, record
        assert full_fidelity >= 1 - TOLERANCE, record
        assert coherent_fidelity >= 1 - TOLERANCE, record
    else:
        stages = level4_stages(prep, error)
        before = Statevector.from_instruction(stages["injected"])
        state = Statevector.from_instruction(stages["extracted"])
        distribution = syndrome_distribution(state, [4, 5])
        bits = observed_bits(distribution)
        before_data = partial_trace(before, [4, 5])
        after_data = partial_trace(state, [4, 5])
        # Pure target comparison avoids numerical instability of mixed-state sqrtm.
        data_vector = Statevector(before.data[:16])
        qnd_fidelity = float(state_fidelity(after_data, data_vector))
        trace_distance_bound = float(np.linalg.norm(after_data.data - before_data.data, ord="fro"))
        record.update(classified_error=classify(bits),
                      ideal_data_preservation_fidelity=qnd_fidelity,
                      data_density_frobenius_difference=trace_distance_bound)
        assert classify(bits) == error.pauli, record
        assert qnd_fidelity >= 1 - TOLERANCE, record
        assert trace_distance_bound < TOLERANCE, record
    record.update(observed_syndrome=list(bits), ideal_syndrome_probabilities=distribution)
    assert bits == expected, record
    assert distribution["".join(map(str, expected))] >= 1 - TOLERANCE, record
    return record


def parse_measurement_key(level: int, key: str) -> tuple[tuple[int, int], str | None]:
    """Convert Qiskit's displayed high-to-low classical order into human order."""
    compact = key.replace(" ", "")
    width = 2 if level == 4 else 5
    if len(compact) != width or any(c not in "01" for c in compact):
        raise ValueError(f"Expected {width} binary bits; got {key!r}")
    syndrome = (int(compact[-1]), int(compact[-2]))
    return syndrome, None if level == 4 else compact[:-2]


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        raise ValueError("Need at least one shot")
    p = successes / total
    denominator = 1 + z*z / total
    center = (p + z*z / (2*total)) / denominator
    radius = z * np.sqrt(p*(1-p)/total + z*z/(4*total*total)) / denominator
    return [max(0.0, float(center-radius)), min(1.0, float(center+radius))]


def shot_metrics(level: int, counts: dict[str, int], expected: tuple[int, int]) -> dict:
    total = sum(counts.values())
    if total <= 0 or any(n < 0 or int(n) != n for n in counts.values()):
        raise ValueError("Counts must contain positive total shots and nonnegative integer values")
    syndromes = Counter()
    syndrome_ok = logical_ok = all_data_ok = joint_ok = 0
    classes = Counter()
    for raw, n in counts.items():
        bits, verification = parse_measurement_key(level, raw)
        syndromes["".join(map(str, bits))] += n
        syndrome_ok += n * (bits == expected)
        if level == 4:
            classes[classify(bits)] += n
            joint_ok += n * (bits == expected)
        else:
            logical_ok += n * (verification[-1] == "0")
            all_data_ok += n * (verification == "000")
            joint_ok += n * (bits == expected and verification == "000")
    result = {"shots": total, "raw_counts": dict(counts),
              "observed_syndrome_counts_human_order": dict(syndromes),
              "syndrome_success_rate": syndrome_ok/total,
              "joint_success_rate": joint_ok/total,
              "joint_success_wilson_95": wilson(joint_ok, total),
              "postselection": "none", "retained_shots": total, "retained_fraction": 1.0}
    if level == 4:
        result.update(classification_success_rate=syndrome_ok/total,
                      observed_classification_counts=dict(classes))
    else:
        result.update(logical_return_success_rate=logical_ok/total,
                      all_data_return_success_rate=all_data_ok/total)
    return result

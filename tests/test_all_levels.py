"""All 150 promised cases, both quantum-state and shot-based checks."""
import numpy as np
import pytest
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Pauli, Statevector, partial_trace, state_fidelity
from qiskit_aer import AerSimulator

from minesweeper.circuits import decode_repetition, encoder_level4, recover_observed
from minesweeper.experiments import (Error, expected_syndrome, permitted_errors,
                                    repetition_experiment, repetition_stages)
from minesweeper.states import INPUTS, amplitudes, preparation, target_state
from minesweeper.verification import ideal_case, parse_measurement_key, shot_metrics

CASES = [(level, label, error) for level in (1,2,3,4) for error in permitted_errors(level) for label in INPUTS]
REP_CASES = [(level,label,error) for level,label,error in CASES if level < 4]


@pytest.mark.parametrize("level,label,error", CASES)
def test_all_promised_cases(level,label,error):
    ideal_case(level,label,error)


@pytest.fixture(scope="module")
def measured_results():
    circuits=[repetition_experiment(preparation(label),level,error,save_logical=True)
              for level,label,error in REP_CASES]
    backend=AerSimulator(method="density_matrix",max_parallel_threads=1)
    compiled=transpile(circuits,backend,optimization_level=0,seed_transpiler=2026)
    return backend.run(compiled,shots=64,seed_simulator=2026).result()


@pytest.mark.parametrize("index,case", list(enumerate(REP_CASES)))
def test_actual_measured_feedforward(index,case,measured_results):
    level,label,error=case
    # Save is before inverse preparation; this is the recovered quantum state.
    density=measured_results.data(index)["logical"]
    assert state_fidelity(density,target_state(preparation(label))) >= 1-1e-10
    metrics=shot_metrics(level,measured_results.get_counts(index),expected_syndrome(level,error))
    assert metrics["joint_success_rate"] == 1


@pytest.mark.parametrize("level,error",[(l,e) for l in (1,2,3) for e in permitted_errors(l)])
def test_same_global_phase_on_both_logical_basis_states(level,error):
    overlaps=[]
    s=expected_syndrome(level,error)
    ancilla_index=(s[0]+2*s[1]) << 3
    for basis in (0,1):
        circuit=repetition_experiment(preparation(str(basis)),level,error,
                                      mode="coherent",measure=False,verify=False)
        actual=Statevector.from_instruction(circuit).data
        wanted=np.zeros(32,dtype=complex);wanted[ancilla_index+basis]=1
        overlap=np.vdot(wanted,actual)
        assert np.isclose(abs(overlap),1)
        assert np.allclose(actual,overlap*wanted)
        overlaps.append(overlap)
    assert np.allclose(overlaps[0],overlaps[1])


def test_level4_codewords_and_stabilizers():
    vectors=[]
    for basis,support in [(0,[0,15]),(1,[3,12])]:
        circuit=QuantumCircuit(4)
        if basis: circuit.x(0)
        circuit.compose(encoder_level4(),inplace=True)
        actual=Statevector.from_instruction(circuit)
        expected=np.zeros(16,dtype=complex);expected[support]=1/np.sqrt(2)
        assert np.allclose(actual.data,expected)
        for stabilizer in ("ZZZZ","XXXX"):
            assert np.allclose(actual.evolve(Pauli(stabilizer)).data,actual.data)
        vectors.append(actual.data)
    assert np.isclose(np.vdot(*vectors),0)


@pytest.mark.parametrize("error",permitted_errors(4))
def test_level4_syndrome_independent_of_logical_input(error):
    distributions=[ideal_case(4,label,error)["ideal_syndrome_probabilities"] for label in INPUTS]
    for distribution in distributions[1:]:
        assert np.allclose(list(distribution.values()),list(distributions[0].values()))


def test_y_correction_needs_relative_phase_recovery():
    prep=preparation("+")
    circuit=repetition_stages(prep,3,Error("Y",1))["extracted"]
    recover_observed(circuit,1,(1,1))  # Deliberately wrong: use X for a Y error.
    decode_repetition(circuit)
    density=partial_trace(Statevector.from_instruction(circuit),[1,2,3,4])
    assert state_fidelity(density,target_state(prep)) < 1e-12
    assert np.allclose(np.diag(density.data),[.5,.5])
    assert state_fidelity(density,target_state(preparation("-"))) > 1-1e-12


@pytest.mark.parametrize("level,key,bits",[
    (1,"000 01",(1,0)),(1,"000 10",(0,1)),(1,"000 11",(1,1)),
    (4,"01",(1,0)),(4,"10",(0,1)),(4,"11",(1,1))])
def test_explicit_raw_string_order(level,key,bits):
    assert parse_measurement_key(level,key)[0] == bits


@pytest.mark.parametrize("key",["001","0x1","12","", "00000"])
def test_invalid_measurement_keys_are_rejected(key):
    with pytest.raises(ValueError): parse_measurement_key(4,key)


@pytest.mark.parametrize("level",[1,2,3])
def test_arbitrary_complex_amplitudes(level):
    alpha=np.sqrt(.37)*np.exp(.4j);beta=np.sqrt(.63)*np.exp(-.8j)
    prep=amplitudes(alpha,beta)
    assert np.allclose(target_state(prep).data,[alpha,beta])
    for error in permitted_errors(level):
        state=Statevector.from_instruction(repetition_experiment(prep,level,error,
                                         mode="coherent",measure=False,verify=False))
        assert state_fidelity(partial_trace(state,[1,2,3,4]),target_state(prep)) > 1-1e-10


def test_promised_coverage_counts():
    assert len(CASES)==150
    assert [sum(level==n for level,_,_ in CASES) for n in (1,2,3,4)] == [24,24,24,78]

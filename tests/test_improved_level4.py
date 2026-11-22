import json
from pathlib import Path
import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator,Statevector,partial_trace,state_fidelity

from minesweeper.calibration import load_calibration,calibration_noise_model
from minesweeper.circuits import encoder_level4,extract_level4
from minesweeper.experiments import expected_syndrome,permitted_errors
from minesweeper.hardware import validate_native
from minesweeper.native_verification import verify_native
from minesweeper.optimized_level4 import encode,extract,optimized_level4_experiment,stages
from minesweeper.placement import Plan,choose_plans,compile_plan,source_for_plan
from minesweeper.states import INPUTS,preparation

ROOT=Path(__file__).resolve().parents[1]
CASES=[(label,error) for error in permitted_errors(4) for label in INPUTS]


@pytest.fixture(scope="module")
def selected():
    from iqm.qiskit_iqm.fake_backends.fake_garnet import IQMFakeGarnet
    backend=IQMFakeGarnet()
    cal=load_calibration(ROOT/'data/calibration.json')
    plans,search=choose_plans(backend,cal,max_layouts=8,seeds=(7,19))
    return backend,cal,plans,search


@pytest.mark.parametrize("encoder",["root3","bridge"])
def test_rewritten_encoders_preserve_both_basis_codewords(encoder):
    baseline=QuantumCircuit(6);baseline.compose(encoder_level4(),range(4),inplace=True)
    improved=QuantumCircuit(6);encode(improved,encoder)
    np.testing.assert_allclose(Operator(improved).data[:,:2],Operator(baseline).data[:,:2],atol=1e-12)


def test_qnd_extraction_isometry_matches_for_all_data_superpositions():
    baseline=QuantumCircuit(6);extract_level4(baseline)
    improved=QuantumCircuit(6);extract(improved)
    # Equality of ALL 16 columns with ancillas zero proves equality on any data vector.
    np.testing.assert_allclose(Operator(improved).data[:,:16],Operator(baseline).data[:,:16],atol=1e-12)


@pytest.mark.parametrize("encoder",["root3","bridge"])
@pytest.mark.parametrize("label,error",CASES)
def test_all_rewritten_source_cases_preserve_post_error_data(label,error,encoder):
    snapshots=stages(preparation(label),error,encoder)
    target=Statevector.from_instruction(snapshots['injected'])
    actual=Statevector.from_instruction(snapshots['extracted'])
    data=partial_trace(actual,[4,5])
    assert state_fidelity(data,Statevector(target.data[:16]))>1-1e-10
    s=expected_syndrome(4,error)
    assert actual.probabilities([4,5])[s[0]+2*s[1]]>1-1e-10


@pytest.mark.parametrize("variant",["original","placement","improved"])
@pytest.mark.parametrize("label,error",CASES)
def test_all_exact_compiled_cases_and_register_mappings(selected,variant,label,error):
    backend,cal,plans,_=selected
    plan=plans[variant]
    source=source_for_plan(plan,label,error)
    native=compile_plan(plan,backend,label,error)
    validate_native(native,backend)
    result=verify_native(plan,source,native,label,error)
    assert result['classification_from_syndrome']==error.pauli
    if variant=='improved':assert native.count_ops()['cz']==11


def test_calibration_topology_and_selector_policy(selected):
    backend,cal,plans,search=selected
    assert cal.compatibility(backend)['topology_matches_snapshot'] is True
    assert cal.compatibility(backend)['physical_device_identity_confirmed'] is False
    assert search['selection_independent_of_evaluation_input_and_error'] is True
    assert set(search['noise_evaluation_seeds']).isdisjoint(search['transpiler_seeds'])
    plan=plans['improved'];assert len(set(plan.layout))==6
    for label,error in CASES:
        # One selected plan, never selected again from hidden ground truth.
        assert source_for_plan(plan,label,error).num_qubits==6


def test_calibration_noise_matches_average_gate_fidelity(selected):
    from qiskit.quantum_info import average_gate_fidelity
    backend,cal,_,_=selected
    model=calibration_noise_model(cal,backend)
    first=model._local_quantum_errors['r'][(0,)].to_quantumchannel()
    assert average_gate_fidelity(first)==pytest.approx(cal.qubits['QB1'].prx.value,abs=1e-12)
    a,b=next(iter(backend.target['cz']))
    channel=model._local_quantum_errors['cz'][(a,b)].to_quantumchannel()
    from minesweeper.calibration import edge_key
    key=edge_key(backend.index_to_qubit_name(a),backend.index_to_qubit_name(b))
    assert average_gate_fidelity(channel)==pytest.approx(cal.cz[key].value,abs=1e-12)

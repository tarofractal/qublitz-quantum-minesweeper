"""First milestone: Level 1 must work before extending the challenge."""
import numpy as np
import pytest
from qiskit.quantum_info import Statevector, partial_trace, state_fidelity

from minesweeper.experiments import Error, repetition_experiment, repetition_stages
from minesweeper.states import INPUTS, preparation, target_state


@pytest.mark.parametrize("label", INPUTS)
@pytest.mark.parametrize("location,expected", [(None, (0,0)), (0, (1,0)), (1, (1,1)), (2, (0,1))])
def test_level1_first(label, location, expected):
    prep = preparation(label)
    error = Error() if location is None else Error("X", location)
    extracted = Statevector.from_instruction(repetition_stages(prep, 1, error)["extracted"])
    expected_integer = expected[0] + 2*expected[1]
    assert np.isclose(extracted.probabilities([3,4])[expected_integer], 1)
    circuit = repetition_experiment(prep, 1, error, mode="coherent", measure=False, verify=False)
    state = Statevector.from_instruction(circuit)
    decoded = partial_trace(state, [1,2,3,4])
    assert state_fidelity(decoded, target_state(prep)) > 1-1e-12

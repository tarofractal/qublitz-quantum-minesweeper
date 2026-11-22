"""Compile genuine challenge circuits for IQM targets; no network or real QPU."""
import pytest
from qiskit import transpile

from minesweeper.experiments import Error, expected_syndrome
from minesweeper.hardware import (backend_metadata, challenge_circuit, simulate_exact,
                                 terminal_measurements_only, validate_native, sample_fake_noise)


@pytest.mark.parametrize("level,error",[
    (1,Error()),(1,Error("X",0)),(1,Error("X",1)),(1,Error("X",2)),
    (4,Error()),(4,Error("X",0)),(4,Error("Z",2)),(4,Error("Y",3))])
def test_native_compilation_and_exact_circuit_shots(level,error):
    pytest.importorskip("iqm.qiskit_iqm")
    from iqm.qiskit_iqm.fake_backends.fake_adonis import IQMFakeAdonis
    from iqm.qiskit_iqm.fake_backends.fake_garnet import IQMFakeGarnet
    backend=IQMFakeGarnet() if level==4 else IQMFakeAdonis()
    source=challenge_circuit(level,"+i",error)
    assert terminal_measurements_only(source)
    assert not any(item.operation.name in ("if_else","reset") for item in source.data)
    if level==4:
        assert all(source.find_bit(item.qubits[0]).index in (4,5)
                   for item in source.data if item.operation.name=="measure")
    compiled=transpile(source,backend=backend,optimization_level=1,seed_transpiler=2026)
    validate_native(compiled,backend)
    metrics=simulate_exact(compiled,level,expected_syndrome(level,error),64,2026)
    assert metrics["joint_success_rate"]==1
    metadata=backend_metadata(backend,compiled)
    assert len(metadata["measurement_map"])==(2 if level==4 else 5)
    assert len(metadata["final_indices_of_source_wires"])==source.num_qubits
    if level==4 and error==Error("Y",3):
        first=sample_fake_noise(compiled,backend,128,2026)
        second=sample_fake_noise(compiled,backend,128,2026)
        assert first==second, "Same native circuit/noise model/seed must reproduce raw counts"
        assert sum(first.values())==128

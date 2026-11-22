"""Exercise real-run bookkeeping without credentials or QPU claims."""
import json
from types import SimpleNamespace
import pytest

from minesweeper.hardware import _finish_job, run_iqm


def receipt():
    return {"source":"mock_job_for_bookkeeping_test_only", "level":4,
            "input":"+i", "expected_syndrome":[1,0]}


def test_pending_job_id_saved_before_wait(tmp_path):
    class Job:
        def job_id(self): return "test-pending-not-a-physical-job"
        def result(self,*,timeout):
            saved=json.loads((tmp_path/'job.json').read_text())
            assert saved['job_id']==self.job_id()
            assert timeout==60
            raise TimeoutError('simulated pending result')
    saved=_finish_job(Job(),receipt(),tmp_path)
    assert saved['status']=='submitted; result pending'
    assert saved['result_fetch_exception_type']=='TimeoutError'
    assert 'raw_counts' not in saved


def test_failed_job_receipt_is_retained(tmp_path):
    class Job:
        def job_id(self): return "test-failed-not-a-physical-job"
        def result(self,*,timeout): return SimpleNamespace(success=False)
    with pytest.raises(RuntimeError): _finish_job(Job(),receipt(),tmp_path)
    saved=json.loads((tmp_path/'job.json').read_text())
    assert saved['status']=='failed' and saved['result_success'] is False
    assert 'raw_counts' not in saved


def test_completed_job_analysis_preserves_raw_bit_order(tmp_path):
    class Result:
        success=True
        def get_counts(self): return {'01':30,'10':2}
    class Job:
        def job_id(self): return "test-completed-not-a-physical-job"
        def result(self,*,timeout): return Result()
    _finish_job(Job(),receipt(),tmp_path)
    analysis=json.loads((tmp_path/'analysis.json').read_text())
    assert analysis['classification_success_rate']==30/32
    assert analysis['observed_classification_counts']=={'X':30,'Z':2}
    assert analysis['retained_shots']==32


def test_existing_receipt_prevents_duplicate_submission(tmp_path,monkeypatch):
    iqm=pytest.importorskip('iqm.qiskit_iqm')
    (tmp_path/'job.json').write_text('{"job_id":"keep-this-id"}')
    def forbidden(*args,**kwargs): raise AssertionError('Provider must not be initialized')
    monkeypatch.setattr(iqm,'IQMProvider',forbidden)
    with pytest.raises(SystemExit,match='already contains a job receipt'):
        run_iqm(SimpleNamespace(mode='run',out=tmp_path))
    assert json.loads((tmp_path/'job.json').read_text())['job_id']=='keep-this-id'

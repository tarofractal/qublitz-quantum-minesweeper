import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from minesweeper.calibration import load_calibration
from minesweeper.comparison import experiment_cases,finish_comparison_job,run_comparison
from minesweeper.comparison_analysis import archive_pilot,analyze_comparison

ROOT=Path(__file__).resolve().parents[1]


def altered(tmp_path,edit):
    doc=json.loads((ROOT/'data/calibration.json').read_text());edit(doc)
    path=tmp_path/'calibration.json';path.write_text(json.dumps(doc));return path


def test_real_snapshot_uses_unheralded_asymmetric_readout_and_units():
    c=load_calibration(ROOT/'data/calibration.json')
    assert len(c.qubits)==20 and len(c.cz)==30
    assert c.qubits['QB1'].readout_0_to_1.value==.007
    assert c.qubits['QB1'].readout_1_to_0.value==.018
    assert c.qubits['QB1'].t1_seconds==pytest.approx(2.603369272937432e-5)
    assert not c.summary()['heralded_metrics_used']


def test_heralded_values_cannot_silently_improve_primary_model(tmp_path):
    def edit(doc):
        for item in doc['observations']:
            if ':herald=' in item['dut_field']:item['value']=0
    cal=load_calibration(altered(tmp_path,edit))
    assert cal.qubits['QB1'].readout_1_to_0.value==.018


@pytest.mark.parametrize("mutation",['invalid','unit','probability','nonfinite','future','duplicate','missing'])
def test_invalid_calibration_inputs_are_rejected(tmp_path,mutation):
    def edit(doc):
        target=next(x for x in doc['observations'] if x['dut_field']=='metrics.ssro.measure.constant.QB1.error_0_to_1')
        if mutation=='invalid':doc['invalid']=True
        elif mutation=='unit':target['unit']='s'
        elif mutation=='probability':target['value']=1.5
        elif mutation=='nonfinite':target['value']=float('nan')
        elif mutation=='future':doc['created_timestamp']='2100-01-01T00:00:00Z'
        elif mutation=='duplicate':
            other=copy.deepcopy(target);other['value']=.01;doc['observations'].append(other)
        elif mutation=='missing':target['invalid']=True
    with pytest.raises(ValueError):load_calibration(altered(tmp_path,edit))


def test_archived_pilot_is_75_percent_classification_not_fidelity():
    result=archive_pilot(ROOT/'data/pilot-export.json')
    assert result['shots']==32 and result['successes']==24
    assert result['syndrome_classification_success']==.75
    assert result['wilson_95']==pytest.approx([.578934,.867474],abs=2e-5)
    assert result['configuration_verified_from_receipt'] is False
    assert result['logical_state_fidelity']=='not measured'
    with pytest.raises(ValueError,match='ordering is unconfirmed'):
        archive_pilot(ROOT/'data/pilot-export.json',expected=(1,0))


def sample_manifest(swapped=False):
    experiments=[];counts=[]
    table={'I':(0,0),'X':(1,0),'Y':(1,1),'Z':(0,1)}
    for variant in ['original','improved']:
        for error,bits in table.items():
            experiments.append({'variant':variant,'case_id':error,'input':'+i','error':error,
                                'location':None if error=='I' else 1,'expected_syndrome':list(bits)})
            raw=f'{bits[1]}{bits[0]}'
            if swapped and variant=='improved':raw=raw[::-1]
            counts.append({raw:32})
    return {'source':'synthetic analysis test, not hardware','raw_bit_order':'syn1syn0',
            'shots_per_circuit':32,'experiments':experiments,'raw_counts':counts}


def test_asymmetric_x_z_controls_catch_bit_swap():
    good=analyze_comparison(sample_manifest())
    assert good['variants']['improved']['success_rate']==1
    wrong=analyze_comparison(sample_manifest(swapped=True))
    assert wrong['variants']['improved']['success_rate']==.5
    assert wrong['variants']['improved']['confusion_counts']['X']['Z']==32
    assert wrong['variants']['improved']['confusion_counts']['Z']['X']==32


def test_ground_truth_metadata_cannot_disagree_with_expected_syndrome():
    sample=sample_manifest()
    for item in sample['experiments']:
        if item['error']=='X':item['expected_syndrome']=[0,1]
    with pytest.raises(ValueError,match='does not match the declared'):
        analyze_comparison(sample)


@pytest.mark.parametrize("mutation",['order','shots','cases','input','duplicates'])
def test_unfair_or_malformed_comparisons_are_rejected(mutation):
    sample=sample_manifest()
    if mutation=='order':sample['raw_bit_order']='unknown'
    elif mutation=='shots':sample['raw_counts'][0]={'00':31}
    elif mutation=='cases':sample['experiments'].pop();sample['raw_counts'].pop()
    elif mutation=='input':sample['experiments'][-1]['input']='-i'
    elif mutation=='duplicates':sample['experiments'][-1]=copy.deepcopy(sample['experiments'][-2])
    with pytest.raises(ValueError):analyze_comparison(sample)


def test_balanced_suite_contains_documented_pilot_and_controls():
    cases=experiment_cases('balanced')
    assert len(cases)==4 and {error.pauli for _,error in cases}=={'I','X','Y','Z'}
    assert any(label=='+i' and error.pauli=='Y' and error.location==1 for label,error in cases)
    assert len(experiment_cases('locations'))==13 and len(experiment_cases('full'))==78


def test_comparison_pending_receipt_keeps_job_id(tmp_path):
    class Job:
        def job_id(self):return 'mock-pending-no-QPU'
        def result(self,*,timeout):
            assert json.loads((tmp_path/'job.json').read_text())['job_id']==self.job_id()
            raise TimeoutError()
    manifest=sample_manifest();manifest.pop('raw_counts')
    saved=finish_comparison_job(Job(),manifest,tmp_path)
    assert saved['status']=='submitted; result pending'
    assert 'raw_counts' not in json.loads((tmp_path/'job.json').read_text())


def test_iqm_adapter_orders_asymmetric_measurement_keys_correctly():
    from iqm.qiskit_iqm.iqm_job import IQMJob
    from minesweeper.verification import parse_measurement_key
    from minesweeper.circuits import classify
    native_results={'syn_2_0_0':[[1],[0]],'syn_2_0_1':[[0],[1]]}
    raw=IQMJob._iqm_format_measurement_results(native_results,2)
    assert raw==['01','10']
    assert [classify(parse_measurement_key(4,k)[0]) for k in raw]==['X','Z']


def test_completed_comparison_retains_all_circuit_results(tmp_path):
    manifest=sample_manifest();counts=manifest.pop('raw_counts')
    class Result:
        success=True
        def get_counts(self,index):return counts[index]
    class Job:
        def job_id(self):return 'mock-completed-not-hardware'
        def result(self,*,timeout):return Result()
    saved=finish_comparison_job(Job(),manifest,tmp_path)
    assert saved['raw_counts']==counts and saved['status']=='completed'
    analysis=json.loads((tmp_path/'analysis.json').read_text())
    assert analysis['variants']['improved']['shots']==128
    assert analysis['changes_against_original']['improved']['change_percentage_points']==0


def test_failed_comparison_retains_receipt_without_requesting_counts(tmp_path):
    manifest=sample_manifest();manifest.pop('raw_counts')
    class Job:
        def job_id(self):return 'mock-failure-not-hardware'
        def result(self,*,timeout):return SimpleNamespace(success=False)
    with pytest.raises(RuntimeError):finish_comparison_job(Job(),manifest,tmp_path)
    saved=json.loads((tmp_path/'job.json').read_text())
    assert saved['status']=='failed' and 'raw_counts' not in saved


def test_comparison_duplicate_submission_is_blocked_before_connect(tmp_path):
    (tmp_path/'submission.json').write_text('{}')
    args=SimpleNamespace(mode='run',out=tmp_path)
    with pytest.raises(SystemExit,match='Existing submission'):
        run_comparison(args)

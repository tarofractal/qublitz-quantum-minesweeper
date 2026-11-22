"""Reproduce the optimization, full native-state checks and held-out noise study.

No hardware access or job submission. Physical comparison uses the compare CLI.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

from qiskit import qpy
from qiskit_aer import AerSimulator

from minesweeper.artifacts import save_circuit,timestamp,versions,write_json
from minesweeper.calibration import load_calibration,calibration_noise_model
from minesweeper.comparison import prepare_packet,simulate_packet
from minesweeper.comparison_analysis import archive_pilot,analyze_comparison
from minesweeper.experiments import Error,expected_syndrome,permitted_errors
from minesweeper.hardware import backend_metadata,validate_native
from minesweeper.native_verification import verify_native
from minesweeper.placement import choose_plans,compile_plan,source_for_plan,ranking,circuit_signature,Plan,_prefilter
from minesweeper.optimized_level4 import six_cycle_layouts
from minesweeper.states import INPUTS
from minesweeper.verification import shot_metrics

ROOT=Path(__file__).resolve().parents[1]


def study(calibration_path: Path,out: Path,noise_shots=512,max_layouts=24):
    from iqm.qiskit_iqm.fake_backends.fake_garnet import IQMFakeGarnet
    backend=IQMFakeGarnet();calibration=load_calibration(calibration_path)
    out.mkdir(parents=True,exist_ok=True)
    pilot=archive_pilot(ROOT/'data/pilot-export.json')
    write_json(out/'baseline/pilot-analysis.json',pilot)
    write_json(out/'calibration-summary.json',calibration.summary())
    plans,search=choose_plans(backend,calibration,max_layouts=max_layouts,seeds=(7,19,43))
    write_json(out/'search.json',search)
    write_json(out/'plans.json',{v:p.to_dict() for v,p in plans.items()})
    print('Selected fixed plans', {v:p.to_dict() for v,p in plans.items()},flush=True)
    metrics={};examples={}
    error=Error('Y',1)
    for variant,plan in plans.items():
        source=source_for_plan(plan,'+i',error)
        native=compile_plan(plan,backend,'+i',error)
        save_circuit(source,out/'circuits',variant+'-source')
        save_circuit(native,out/'circuits',variant+'-native',render=False)
        meta=backend_metadata(backend,native)
        write_json(out/'circuits'/f'{variant}-backend.json',meta)
        metrics[variant]={**ranking(native,backend,calibration),'plan':plan.to_dict(),
                          'initial_source_indices':meta['initial_indices_of_source_wires'],
                          'final_source_indices':meta['final_indices_of_source_wires'],
                          'measurement_map':meta['measurement_map']}
        examples[variant]=native
    with (ROOT/'results/iqm-prepared/circuits/native.qpy').open('rb') as stream:archived=qpy.load(stream)[0]
    reconstructed=circuit_signature(archived)==circuit_signature(examples['original'])
    write_json(out/'baseline/archive-reconstruction.json',{
        'archived_local_native_gate_register_mapping_signature_matches':reconstructed,
        'archived_signature':circuit_signature(archived),'reconstructed_signature':circuit_signature(examples['original']),
        'physical_pilot_native_circuit_match':'unknown: physical receipt/native circuit not included',
        'target':'IQMFakeGarnetBackend offline target; topology matches calibration, not physical identity'})
    # Earlier 13-CZ patch is retained as an independently verified candidate.
    bridge_options=sorted(six_cycle_layouts(backend,False),key=lambda x:(_prefilter(x,backend,calibration,'bridge'),x))[:max_layouts]
    bridge=[]
    for layout in bridge_options:
        plan=Plan('bridge13',tuple(layout),7,'bridge')
        native=compile_plan(plan,backend,'+i',error)
        bridge.append((ranking(native,backend,calibration)['ranking_score'],plan,native))
    _,bridge_plan,bridge_native=min(bridge,key=lambda x:(x[0],x[1].layout))
    metrics['bridge13']={**ranking(bridge_native,backend,calibration),'plan':bridge_plan.to_dict()}
    verify_native(bridge_plan,source_for_plan(bridge_plan,'+i',error),bridge_native,'+i',error)
    write_json(out/'circuit-metrics.json',metrics)

    records=[];circuits=[];experiments=[]
    for variant,plan in plans.items():
        for error in permitted_errors(4):
            for label in INPUTS:
                source=source_for_plan(plan,label,error);native=compile_plan(plan,backend,label,error)
                validate_native(native,backend)
                verification=verify_native(plan,source,native,label,error)
                row={'variant':variant,'case_id':f'{label}_{error.pauli}_{error.location}',
                     'input':label,'error':error.pauli,'location':error.location,
                     'expected_syndrome':list(expected_syndrome(4,error)),**verification}
                records.append(row);circuits.append(native)
                experiments.append({k:row[k] for k in ['variant','case_id','input','error','location','expected_syndrome']})
    simulator=AerSimulator(method='matrix_product_state',max_parallel_threads=1)
    result=simulator.run(circuits,shots=512,seed_simulator=37097).result()
    if not result.success:raise RuntimeError('Ideal suite failed')
    for i,row in enumerate(records):
        counts=result.get_counts(i)
        row['finite_shots']=shot_metrics(4,counts,tuple(row['expected_syndrome']))
        assert row['finite_shots']['classification_success_rate']==1.0
    write_json(out/'ideal-native-cases.json',{'source':'ideal native-circuit SIMULATION','cases':len(records),
               'shots_per_case':512,'records':records})
    with (out/'ideal-native-cases.qpy').open('wb') as stream:qpy.dump(circuits,stream)
    columns=['variant','case_id','input','error','location','expected_syndrome','observed_syndrome',
             'native_full_state_fidelity','native_data_preservation_fidelity','syndrome_probability']
    with (out/'ideal-native-cases.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        writer.writerows({key:row[key] for key in columns} for row in records)
    print(f'Exact compiled state and shot checks passed: {len(records)} cases.',flush=True)

    model=calibration_noise_model(calibration,backend)
    indices=[i for i,e in enumerate(experiments) if e['input']=='+i']
    noise_circuits=[circuits[i] for i in indices];noise_experiments=[experiments[i] for i in indices]
    aggregate=[Counter() for _ in indices];seed_reports=[]
    for seed in (49157,82799):
        result=AerSimulator(method='matrix_product_state',max_parallel_threads=1,noise_model=model).run(
            noise_circuits,shots=noise_shots,seed_simulator=seed).result()
        raw=[result.get_counts(i) for i in range(len(noise_circuits))]
        manifest={'source':'calibration-informed noise SIMULATION','raw_bit_order':'syn1syn0',
                  'noise_seed':seed,'shots_per_circuit':noise_shots,'experiments':noise_experiments,'raw_counts':raw}
        analysis=analyze_comparison(manifest)
        write_json(out/f'noise-seed-{seed}.json',manifest)
        write_json(out/f'noise-seed-{seed}-analysis.json',analysis)
        seed_reports.append(analysis)
        for total,counts in zip(aggregate,raw):total.update(counts)
        print(f'Held-out noise seed {seed}: '+str({v:g['success_rate'] for v,g in analysis['variants'].items()}),flush=True)
    noise_manifest={'source':'calibration-informed noise SIMULATION, two held-out seeds',
                    'raw_bit_order':'syn1syn0','shots_per_circuit':2*noise_shots,'seeds':[49157,82799],
                    'experiments':noise_experiments,'raw_counts':[dict(c) for c in aggregate]}
    write_json(out/'noise-comparison.json',noise_manifest)
    noise_analysis=analyze_comparison(noise_manifest)
    write_json(out/'noise-analysis.json',noise_analysis)
    balanced=[i for i,e in enumerate(noise_experiments) if e['error']=='I' or e['location']==1]
    balanced_manifest={**noise_manifest,'experiments':[noise_experiments[i] for i in balanced],
                       'raw_counts':[dict(aggregate[i]) for i in balanced]}
    balanced_analysis=analyze_comparison(balanced_manifest)
    write_json(out/'noise-balanced-comparison.json',balanced_manifest)
    write_json(out/'noise-balanced-analysis.json',balanced_analysis)
    assumptions={'source':'approximate calibration-informed simulation, not measured QPU performance',
                 'metric_snapshot':calibration.summary(),'unheralded_readout_only':True,
                 'gate_model':'Independent depolarizing; exported F treated as average fidelity. lambda=2*(1-F) for R, 4/3*(1-F) for CZ.',
                 'readout':'Per-qubit asymmetric 0->1 and 1->0 rates; no post-selection or mitigation',
                 'limitations':['One PRX fidelity used for every native R angle/implementation',
                                'No pulse durations in snapshot; no idle/T1/T2 timing model',
                                'No leakage, crosstalk, correlated errors, coherent errors or calibration drift',
                                'Topology compatibility does not establish physical pilot calibration linkage'],
                 'tuning':'Calibration heuristic and transpiler seeds only; no evaluation shots used for selection',
                 'evaluation_seeds':[49157,82799]}
    write_json(out/'noise-model-assumptions.json',assumptions)
    packet,circs=prepare_packet(backend,calibration,ROOT/'results/comparison-prepared',shots=256,
                              suite='balanced',plans=plans,search=search)
    simulate_packet(packet,circs,ROOT/'results/comparison-prepared',seed=37097)
    summary={'created_at_utc':timestamp(),'software':versions(),'archived_physical_pilot':pilot,
             'archived_local_circuit_reproduced':reconstructed,'calibration':calibration.summary(),
             'metrics':metrics,'ideal_native_cases':len(records),'ideal_cases_per_primary_variant':78,
             'minimum_native_data_preservation_fidelity':min(r['native_data_preservation_fidelity'] for r in records),
             'noise_balanced':{v:{k:g[k] for k in ['shots','successes','success_rate','wilson_95']}
                               for v,g in balanced_analysis['variants'].items()},
             'noise_changes':balanced_analysis['changes_against_original'],
             'new_IQM_hardware_status':'Not run on IQM hardware: no authenticated server/QPU configured in this environment.',
             'prepared_comparison_circuits':len(circs),'prepared_shots_per_circuit':256}
    write_json(out/'summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration',type=Path,default=ROOT/'data/calibration.json')
    parser.add_argument('--out',type=Path,default=ROOT/'results/improvement')
    parser.add_argument('--noise-shots',type=int,default=512)
    parser.add_argument('--max-layouts',type=int,default=24)
    args=parser.parse_args()
    if args.noise_shots<=0:parser.error('--noise-shots must be positive')
    summary=study(args.calibration,args.out,args.noise_shots,args.max_layouts)
    print(json.dumps({k:summary[k] for k in ['ideal_native_cases','archived_local_circuit_reproduced','noise_balanced','new_IQM_hardware_status']},indent=2))

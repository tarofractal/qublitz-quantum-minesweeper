"""Bounded calibration ranking. The selector never receives a test input/error."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict,dataclass
from itertools import permutations
import hashlib
import json
import math

from qiskit import transpile
from .calibration import Calibration,edge_key
from .experiments import Error,level4_experiment
from .optimized_level4 import optimized_level4_experiment,six_cycle_layouts
from .states import preparation


@dataclass(frozen=True)
class Plan:
    variant: str
    layout: tuple[int,...] | None
    seed: int
    encoder: str = "original"
    optimization_level: int = 1

    def to_dict(self):return asdict(self)

    @classmethod
    def from_dict(cls,value):
        return cls(value["variant"],tuple(value["layout"]) if value["layout"] is not None else None,
                   int(value["seed"]),value.get("encoder","original"),value.get("optimization_level",1))


def source_for_plan(plan: Plan,label: str,error: Error):
    prep=preparation(label)
    return (level4_experiment(prep,error) if plan.encoder=="original" else
            optimized_level4_experiment(prep,error,encoder=plan.encoder))


def compile_plan(plan: Plan,backend,label: str,error: Error):
    kwargs={}
    if plan.layout is not None:kwargs["initial_layout"]=list(plan.layout)
    if plan.encoder!="original":kwargs["routing_method"]="none"
    return transpile(source_for_plan(plan,label,error),backend=backend,
                     optimization_level=plan.optimization_level,seed_transpiler=plan.seed,**kwargs)


def circuit_signature(circuit) -> str:
    rows=[]
    for item in circuit.data:
        rows.append([item.operation.name,[str(x) for x in item.operation.params],
                     [circuit.find_bit(q).index for q in item.qubits],
                     [circuit.find_bit(c).index for c in item.clbits],getattr(item.operation,"label",None)])
    payload={"qubits":circuit.num_qubits,"cregs":[[r.name,r.size] for r in circuit.cregs],
             "global_phase":str(circuit.global_phase),"instructions":rows}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def duration_estimate(circuit,backend):
    """ASAP critical path only when every needed duration is supplied by target."""
    clocks=[0.0]*circuit.num_qubits
    for item in circuit.data:
        q=tuple(circuit.find_bit(x).index for x in item.qubits)
        if not q:continue
        if item.operation.name=="barrier":
            for i in q:clocks[i]=max(clocks[j] for j in q)
            continue
        table=backend.target[item.operation.name]
        props=table.get(q)
        if props is None and item.operation.name=="cz":props=table.get(q[::-1])
        if props is None or props.duration is None:return None
        end=max(clocks[i] for i in q)+float(props.duration)
        for i in q:clocks[i]=end
    return max(clocks,default=0.0)


def ranking(circuit,backend,calibration: Calibration,uncertainty_sigma=2.0) -> dict:
    names=[backend.index_to_qubit_name(i) for i in range(backend.num_qubits)]
    cost=0.0
    sites=[]
    for item in circuit.data:
        q=[circuit.find_bit(x).index for x in item.qubits]
        gate=item.operation.name
        if gate=="cz":
            estimate=calibration.cz[edge_key(names[q[0]],names[q[1]])]
            cost-=math.log(max(1e-6,estimate.value-uncertainty_sigma*estimate.uncertainty))
        elif gate=="r":
            estimate=calibration.qubits[names[q[0]]].prx
            cost-=math.log(max(1e-6,estimate.value-uncertainty_sigma*estimate.uncertainty))
        elif gate=="measure":
            quality=calibration.qubits[names[q[0]]]
            # Worst bit value, not a choice based on the injected error/type.
            worst=max(e.value+uncertainty_sigma*e.uncertainty for e in
                      [quality.readout_0_to_1,quality.readout_1_to_0])
            cost-=math.log(max(1e-6,1-worst));sites.append(names[q[0]])
    cz=int(circuit.count_ops().get("cz",0))
    score=cost+0.001*cz+0.00001*circuit.depth()
    return {"ranking_score":score,"calibration_negative_log_proxy":cost,
            "native_cz":cz,"depth":circuit.depth(),"native_r":int(circuit.count_ops().get("r",0)),
            "syndrome_device_sites":sites,"estimated_duration_seconds":duration_estimate(circuit,backend),
            "score_is_accuracy_prediction":False,
            "rule":"-log conservative gate fidelities + worst-bit unheralded readout cost + 0.001*CZ + 1e-5*depth"}


def _prefilter(layout,backend,calibration,encoder):
    names=[backend.index_to_qubit_name(i) for i in layout]
    pairs=[(0,1),(2,3),(1,4),(3,4),(5,0),(5,2)]
    if encoder=="root3":pairs.append((3,0))
    gate_cost=sum(-math.log(max(1e-6,calibration.cz[edge_key(names[a],names[b])].value)) for a,b in pairs)
    readout=sum(max(calibration.qubits[names[i]].readout_0_to_1.value,
                    calibration.qubits[names[i]].readout_1_to_0.value) for i in (4,5))
    return gate_cost+readout


def _original_layout_pool(backend,calibration,cycles,max_layouts):
    """At most 16 connected six-cycle footprints x 720 role permutations.

    Use shortest-path distance/edge quality only as a cheap prefilter. The final
    decision always uses the ACTUALLY ROUTED native gates, not this estimate.
    """
    names=[backend.index_to_qubit_name(i) for i in range(backend.num_qubits)]
    n=len(names);distance=[[float('inf')]*n for _ in range(n)]
    cost=[[float('inf')]*n for _ in range(n)]
    for i in range(n):distance[i][i]=cost[i][i]=0.0
    for a,b in backend.target['cz']:
        v=-math.log(calibration.cz[edge_key(names[a],names[b])].value)+.005
        distance[a][b]=distance[b][a]=1
        cost[a][b]=cost[b][a]=v
    for k in range(n):
        for i in range(n):
            for j in range(n):
                distance[i][j]=min(distance[i][j],distance[i][k]+distance[k][j])
                cost[i][j]=min(cost[i][j],cost[i][k]+cost[k][j])
    interactions=[(0,1),(2,0),(2,1),(2,3)]+[(q,a) for a in (4,5) for q in range(4)]
    footprints=sorted({tuple(sorted(c)) for c in cycles})[:16]
    pool=[]
    for footprint in footprints:
        for layout in permutations(footprint):
            route=sum(.007*(distance[layout[a]][layout[b]]-1)+cost[layout[a]][layout[b]] for a,b in interactions)
            readout=sum(max(calibration.qubits[names[layout[i]]].readout_0_to_1.value,
                            calibration.qubits[names[layout[i]]].readout_1_to_0.value) for i in (4,5))
            pool.append((route+readout,layout))
    pool.sort()
    return [list(layout) for _,layout in pool[:max_layouts]]


def choose_plans(backend,calibration: Calibration,max_layouts=24,seeds=(7,19,43)):
    if max_layouts<1 or not seeds:raise ValueError("Positive layout budget and at least one seed required")
    compatibility=calibration.compatibility(backend)
    if compatibility["missing_qubit_names"] or compatibility["uncalibrated_target_edges"]:
        raise ValueError("Target contains qubits/CZ edges absent from this calibration; use a matching snapshot")
    chord=six_cycle_layouts(backend,True)
    cycles=six_cycle_layouts(backend,False)
    if not cycles:raise ValueError("No supported six-cycle; original circuit remains available")
    encoder="root3" if chord else "bridge"
    choices=chord or cycles
    choices=sorted(choices,key=lambda x:(_prefilter(x,backend,calibration,encoder),x))[:max_layouts]
    baseline=Plan("original",None,2026)
    plans={"original":baseline}
    search=[]
    # Same fixed reference for every layout. Actual test error/input is not an API argument.
    original_choices=_original_layout_pool(backend,calibration,cycles,max_layouts)
    # Include the baseline initial placement as a candidate as well.
    base_reference=compile_plan(baseline,backend,"+i",Error())
    base_layout=base_reference.layout.initial_index_layout(filter_ancillas=True)
    if base_layout not in original_choices:
        original_choices=original_choices[:max(0,max_layouts-1)]+[base_layout]
    for variant,encoding in [("placement","original"),("improved",encoder)]:
        candidates=[]
        layouts=original_choices if variant=="placement" else choices
        for layout in layouts:
            for seed in seeds:
                plan=Plan(variant,tuple(layout),int(seed),encoding)
                circuit=compile_plan(plan,backend,"+i",Error())
                metrics=ranking(circuit,backend,calibration)
                row={"plan":plan.to_dict(),**metrics}
                candidates.append((metrics["ranking_score"],metrics["native_cz"],layout,seed,plan))
                search.append(row)
        plans[variant]=min(candidates,key=lambda x:x[:4])[-1]
    return plans,{"compatibility":compatibility,"reference_input":"+i","reference_error":"I",
                  "selection_independent_of_evaluation_input_and_error":True,
                  "layouts_available":len(choices if len(choices)<max_layouts else (chord or cycles)),
                  "layouts_compiled_per_variant":len(choices),"transpiler_seeds":list(seeds),
                  "noise_evaluation_seeds":[49157,82799],"candidates":search}

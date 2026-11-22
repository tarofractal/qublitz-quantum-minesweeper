"""Source-aware counts analysis: primary metric uses ALL shots."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import numpy as np
from .artifacts import write_json
from .circuits import classify
from .verification import parse_measurement_key,shot_metrics,wilson

TYPES=("I","X","Y","Z")


def archive_pilot(path: Path,expected=(1,1)) -> dict:
    exported=json.loads(path.read_text())
    if not isinstance(exported,list) or len(exported)!=1:
        raise ValueError("Expected one pilot circuit in IQM export")
    item=exported[0]
    counts=item["sorted_counts"]
    if any(int(n)!=n or n<0 for n in counts.values()):raise ValueError("Invalid pilot counts")
    total=sum(counts.values())
    if total!=item["total_counts"]:raise ValueError("Pilot shot count mismatch")
    if len(item["measurement_keys"])!=2:raise ValueError("Pilot must contain two measured keys")
    if expected not in ((0,0),(1,1)):
        raise ValueError("Archived export bit ordering is unconfirmed; asymmetric scoring requires the receipt")
    wanted="".join(map(str,expected))
    for key in counts:parse_measurement_key(4,key)
    matched=int(counts.get(wanted,0))
    return {"source":"archived user-supplied IQM hardware export",
            "job_id":"01a1fff5-31e3-744f-89da-cb1d14f7bacb", "raw_counts":counts,
            "measurement_keys":item["measurement_keys"],"shots":total,"successes":matched,
            "syndrome_classification_success":matched/total,"wilson_95":wilson(matched,total),
            "configuration":"likely L4, +i, Y on d1; inferred from documented pilot command",
            "configuration_verified_from_receipt":False,"native_physical_circuit_available":False,
            "physical_layout_available":False,"calibration_linkage_verified":False,
            "raw_01_10_error_types":"not assigned: physical export ordering unconfirmed",
            "logical_state_fidelity":"not measured"}


def newcombe_difference(first_success,first_total,second_success,second_total):
    """Independent-binomial Newcombe/Wilson score interval, no pooling."""
    pa,pb=first_success/first_total,second_success/second_total
    la,ua=wilson(first_success,first_total);lb,ub=wilson(second_success,second_total)
    difference=pb-pa
    lower=difference-np.sqrt((pb-lb)**2+(ua-pa)**2)
    upper=difference+np.sqrt((ub-pb)**2+(pa-la)**2)
    return {"change_percentage_points":100*difference,
            "newcombe_wilson_95_percentage_points":[100*max(-1.,float(lower)),100*min(1.,float(upper))],
            "method":"Newcombe/Wilson independent-binomial approximation; no model for correlated device drift"}


def analyze_comparison(manifest: dict) -> dict:
    experiments=manifest["experiments"]
    counts=manifest["raw_counts"]
    if len(counts)!=len(experiments):raise ValueError("Circuit count/order mismatch")
    if manifest.get("raw_bit_order")!="syn1syn0":
        raise ValueError("Need verified Qiskit syn1syn0 order, not guessed IQM export order")
    cases=[];groups={};configurations={}
    for experiment,raw in zip(experiments,counts):
        if sum(raw.values())!=manifest["shots_per_circuit"]:
            raise ValueError("Shot mismatch: primary comparison must retain every requested shot")
        bits=tuple(experiment["expected_syndrome"])
        metric=shot_metrics(4,raw,bits)
        true=experiment["error"]
        if true not in TYPES or len(bits)!=2 or classify(bits)!=true:
            raise ValueError("Expected syndrome does not match the declared injected Pauli type")
        config=(experiment["input"],true,experiment["location"],tuple(experiment["expected_syndrome"]))
        case_id=experiment["case_id"]
        if case_id in configurations and configurations[case_id]!=config:
            raise ValueError("Variant case configuration mismatch")
        configurations[case_id]=config
        classified=Counter()
        for key,n in raw.items():classified[classify(parse_measurement_key(4,key)[0])]+=n
        row={"variant":experiment["variant"],"case_id":experiment["case_id"],
             "input":experiment["input"],"injected_error":true,"location":experiment["location"],
             "expected_syndrome":list(bits),**metric}
        cases.append(row)
        group=groups.setdefault(experiment["variant"],{"shots":0,"successes":0,"case_ids":set(),
                     "confusion_counts":{t:{c:0 for c in TYPES} for t in TYPES},"cases":[]})
        if experiment["case_id"] in group["case_ids"]:raise ValueError("Duplicate variant/case")
        group["case_ids"].add(experiment["case_id"]);group["shots"]+=metric["shots"]
        group["successes"]+=classified[true];group["cases"].append(row)
        for predicted,n in classified.items():group["confusion_counts"][true][predicted]+=n
    if "original" not in groups:raise ValueError("Comparison needs the original variant")
    reference=groups["original"]["case_ids"]
    for group in groups.values():
        if group.pop("case_ids")!=reference:raise ValueError("Variants must have identical input/error cases")
        group["success_rate"]=group["successes"]/group["shots"]
        group["wilson_95"]=wilson(group["successes"],group["shots"])
        confusion=group["confusion_counts"]
        group["confusion_row_fractions"]={t:{c:(confusion[t][c]/sum(confusion[t].values()) if sum(confusion[t].values()) else None)
                                                for c in TYPES} for t in TYPES}
        present=[t for t in TYPES if sum(confusion[t].values())]
        group["macro_type_success"]=sum(confusion[t][t]/sum(confusion[t].values()) for t in present)/len(present)
    original=groups["original"]
    changes={v:newcombe_difference(original["successes"],original["shots"],g["successes"],g["shots"])
             for v,g in groups.items() if v!="original"}
    return {"source":manifest["source"],"job_id":manifest.get("job_id"),"raw_bit_order":"syn1syn0",
            "provenance":manifest.get("provenance",{}),
            "classification_syndrome_order":"ZZZZ,XXXX", "postselection":"none","retained_fraction":1.0,
            "variants":groups,"changes_against_original":changes,
            "logical_state_fidelity":"not measured by syndrome counts", "per_case":cases}


def analyze_file(path: Path) -> dict:
    manifest=json.loads(path.read_text())
    result=analyze_comparison(manifest)
    write_json(path.parent/"analysis.json",result)
    return result

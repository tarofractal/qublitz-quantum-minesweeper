"""Interleaved original/improved experiments; one backend instance, one IQM job.

Preparation/scoring knows injected errors. The classifier still reads two bits.
No physical-job submission occurs in prepare/simulate/analyze modes.
"""
from __future__ import annotations

import getpass
import dataclasses
import json
import os
from pathlib import Path
import sys
from uuid import UUID

from qiskit import qpy
from qiskit_aer import AerSimulator

from .artifacts import save_circuit,timestamp,versions,write_json
from .calibration import calibration_noise_model,load_calibration
from .comparison_analysis import analyze_file
from .experiments import Error,expected_syndrome,permitted_errors
from .hardware import backend_metadata,validate_native
from .native_verification import verify_native
from .placement import Plan,choose_plans,circuit_signature,compile_plan,ranking,source_for_plan
from .states import INPUTS


def experiment_cases(suite="balanced"):
    if suite=="balanced":
        return [("+i",Error()),("+i",Error("X",1)),("+i",Error("Y",1)),("+i",Error("Z",1))]
    if suite=="locations":return [("+i",e) for e in permitted_errors(4)]
    if suite=="full":return [(label,e) for e in permitted_errors(4) for label in INPUTS]
    raise ValueError("Suite must be balanced, locations or full")


def prepare_packet(backend,calibration,out: Path,shots=256,suite="balanced",
                   include_placement=False,max_layouts=24,seeds=(7,19,43),plans=None,search=None):
    if shots<=0:raise ValueError("Shots must be positive")
    if plans is None:plans,search=choose_plans(backend,calibration,max_layouts,seeds)
    variants=["original","placement","improved"] if include_placement else ["original","improved"]
    out.mkdir(parents=True,exist_ok=True)
    experiments=[];circuits=[];native_checks=[]
    for case_index,(label,error) in enumerate(experiment_cases(suite)):
        # AB/BA blocks balance positions in the single job. Never use noisy
        # outcomes to change this order or to choose a layout.
        order=variants if case_index%2==0 else variants[::-1]
        for variant in order:
            plan=plans[variant]
            source=source_for_plan(plan,label,error)
            compiled=compile_plan(plan,backend,label,error)
            compiled.name=f"QM_{variant}_{case_index:03d}"
            validate_native(compiled,backend)
            check=verify_native(plan,source,compiled,label,error)
            stem=f"{len(circuits):03d}-{variant}-{case_index:03d}"
            save_circuit(compiled,out/"circuits",stem,render=False)
            metadata=backend_metadata(backend,compiled)
            row={"variant":variant,"case_id":f"{label}_{error.pauli}_{error.location}",
                 "input":label,"error":error.pauli,"location":error.location,
                 "expected_syndrome":list(expected_syndrome(4,error)),"plan":plan.to_dict(),
                 "circuit_file":f"circuits/{stem}.qpy","signature":circuit_signature(compiled),
                 "backend":metadata,"calibration_ranking_heuristic":ranking(compiled,backend,calibration)}
            experiments.append(row);circuits.append(compiled);native_checks.append(check)
    with (out/"all-native.qpy").open("wb") as stream:qpy.dump(circuits,stream)
    manifest={"format_version":1,"created_at_utc":timestamp(),"source":"prepared; no QPU execution yet",
              "status":"prepared","software":versions(),"shots_per_circuit":shots,"suite":suite,
              "case_count_per_variant":len(experiment_cases(suite)),"total_requested_shots":shots*len(circuits),
              "ordering":"case blocks alternate original/improved and improved/original",
              "raw_bit_order":"syn1syn0","syndrome_order":"ZZZZ,XXXX","postselection":"none",
              "calibration":calibration.summary(),"compatibility":calibration.compatibility(backend),
              "plans":{name:plans[name].to_dict() for name in variants},"experiments":experiments,
              "native_ideal_verification":native_checks,"hardware_data_fidelity":"not measured"}
    if search is not None:write_json(out/"layout-search.json",search)
    write_json(out/"manifest.json",manifest)
    return manifest,circuits


def simulate_packet(manifest,circuits,out: Path,noise_model=None,seed=49157):
    # Native R/CZ names MUST stay unchanged so the gate noise attaches.
    simulator=AerSimulator(method="matrix_product_state",max_parallel_threads=1,noise_model=noise_model)
    result=simulator.run(circuits,shots=manifest["shots_per_circuit"],seed_simulator=seed).result()
    if not result.success:raise RuntimeError("Aer comparison failed")
    saved={**manifest,"source":"calibration-informed noise SIMULATION" if noise_model else "ideal native-circuit SIMULATION",
           "status":"completed locally","noise_seed":seed,
           "raw_counts":[result.get_counts(i) for i in range(len(circuits))]}
    write_json(out/"comparison.json",saved)
    return analyze_file(out/"comparison.json")


def finish_comparison_job(job,manifest,out: Path):
    manifest["job_id"]=str(job.job_id());manifest["status"]="submitted; result pending"
    write_json(out/"job.json",manifest)
    print(f"IQM comparison job ID: {manifest['job_id']}",flush=True)
    try:result=job.result(timeout=60)
    except TimeoutError:
        print("Job still pending. Retrieve this job; do not submit again.")
        return manifest
    except Exception as exc:
        manifest["result_fetch_exception_type"]=type(exc).__name__
        write_json(out/"job.json",manifest)
        print("Result fetch did not complete. The job ID is saved; retrieve it before considering another job.")
        return manifest
    if not result.success:
        manifest.update(status="failed",result_success=False)
        write_json(out/"job.json",manifest)
        raise RuntimeError("IQM comparison failed; saved receipt retained")
    # The SDK Result carries the actual submitted IQM Circuit dataclasses,
    # parameters, calibration IDs and server timeline. Retain that evidence
    # rather than leaving only an inferred circuit order and a histogram.
    if hasattr(result,"to_dict"):
        payload=result.to_dict()
        for key in ("circuits","parameters","timeline"):
            value=payload.get(key)
            if key=="circuits" and value is not None:
                payload[key]=[dataclasses.asdict(c) if dataclasses.is_dataclass(c) else c for c in value]
            elif hasattr(value,"model_dump"):
                payload[key]=value.model_dump(mode="json")
        write_json(out/"iqm-result.json",payload)
        manifest["retrieved_result_evidence_file"]="iqm-result.json"
        manifest["returned_circuit_names"]=[getattr(c,"name",None) for c in getattr(result,"circuits",())]
        manifest["returned_calibration_set_ids"]=[str(getattr(r,"calibration_set_id",None))
                                                 for r in getattr(result,"results",())]
    manifest.update(status="completed",result_success=True,completed_at_utc=timestamp(),
                    raw_counts=[result.get_counts(i) for i in range(len(manifest["experiments"]))])
    parameters=getattr(result,"parameters",None)
    if parameters is not None:
        manifest["reported_calibration_set_id"]=str(getattr(parameters,"calibration_set_id","unknown"))
    write_json(out/"job.json",manifest)
    analyze_file(out/"job.json")
    return manifest


def _token(prompt=False) -> str | None:
    """Return an explicit token only when the SDK has no environment credential."""
    if os.environ.get("IQM_TOKEN") or os.environ.get("IQM_TOKENS_FILE"):
        return None
    if prompt and sys.stdin.isatty():
        token = getpass.getpass("IQM token (hidden): ").strip()
        if token:
            return token
    raise SystemExit("Set IQM_TOKEN privately, or run with --prompt-token in your terminal")


def run_comparison(args):
    out=args.out
    if args.mode=="import-export":
        from .iqm_export import import_export
        if not args.export_file or not args.export_bit_order or not args.job_id:
            raise SystemExit("import-export needs --export-file, --export-bit-order and --job-id")
        result=import_export(args.export_file,args.protocol_file,out,
                             bit_order=args.export_bit_order,job_id=args.job_id)
        print(json.dumps({"source":result["source"],"job_id":result["job_id"],
                          "configuration_basis":result["provenance"]["configuration_basis"],
                          "asymmetric_controls_support_declared_order":result["provenance"]["asymmetric_controls_support_declared_order"],
                          "variants":{v:{k:g[k] for k in ("successes","shots","success_rate","wilson_95")}
                                      for v,g in result["variants"].items()},
                          "changes":result["changes_against_original"]},indent=2))
        return result
    if args.mode=="analyze":
        path=args.result_file or out/"job.json"
        result=analyze_file(path)
        print(json.dumps({"source":result["source"],"changes":result["changes_against_original"]},indent=2))
        return result
    if args.mode=="retrieve":
        from iqm.qiskit_iqm import IQMProvider
        receipt=args.result_file or out/"job.json"
        if receipt.is_file():
            manifest=json.loads(receipt.read_text())
            if getattr(args,"job_id",None) and manifest["job_id"]!=args.job_id:
                raise ValueError("Requested job ID disagrees with the saved receipt")
        elif getattr(args,"job_id",None):
            manifest=json.loads(args.protocol_file.read_text())
            manifest.update(source="IQM_QPU_comparison",job_id=str(UUID(args.job_id)),
                            configuration_verified_from_submission=False,
                            configuration_metadata_source="prepared protocol; compare retrieved submitted circuits before certifying configuration",
                            provenance={"matching_job_receipt_supplied":False,
                                        "configuration_basis":"prepared protocol reconstruction; actual submitted circuits saved in iqm-result.json for audit"})
        else:
            raise SystemExit("No receipt found. Supply --job-id and --protocol-file to retrieve an existing job")
        if manifest.get("source")!="IQM_QPU_comparison":raise ValueError("Expected an IQM comparison receipt")
        url=args.url or os.environ.get("IQM_SERVER_URL") or manifest.get("server_url")
        computer=args.computer or os.environ.get("IQM_QUANTUM_COMPUTER") or manifest.get("quantum_computer")
        if not url:raise SystemExit("Set IQM_SERVER_URL or --url for the existing job's server")
        manifest.update(server_url=url,quantum_computer=computer)
        provider=IQMProvider(url,quantum_computer=computer,token=_token(args.prompt_token))
        backend=provider.get_backend()
        return finish_comparison_job(backend.retrieve_job(manifest["job_id"]),manifest,receipt.parent)
    if args.mode=="run" and any((out/name).exists() for name in ("job.json","submission.json")):
        raise SystemExit("Existing submission/receipt found. Retrieve it or inspect the IQM dashboard; use a new output directory for a distinct comparison.")
    calibration=load_calibration(args.calibration)
    if args.mode=="run":
        from iqm.qiskit_iqm import IQMProvider
        connection={}
        if args.connection_from and args.connection_from.is_file():
            connection=json.loads(args.connection_from.read_text())
        url=args.url or os.environ.get("IQM_SERVER_URL") or connection.get("server_url")
        computer=args.computer or os.environ.get("IQM_QUANTUM_COMPUTER") or connection.get("quantum_computer")
        if not url:raise SystemExit("Set the event/IQM server URL in IQM_SERVER_URL or --url")
        provider=IQMProvider(url,quantum_computer=computer,token=_token(args.prompt_token))
        kwargs={"calibration_set_id":UUID(calibration.calibration_set_id)} if args.pin_calibration else {}
        backend=provider.get_backend(**kwargs)
    else:
        from iqm.qiskit_iqm.fake_backends.fake_garnet import IQMFakeGarnet
        backend=IQMFakeGarnet()
    # Reject resonator compilation before enumerating dense virtual CZ graphs.
    if getattr(backend.architecture,"computational_resonators",()):
        raise ValueError("This exact-Aer comparison supports Crystal-style targets, not resonator MOVE devices")
    manifest,circuits=prepare_packet(backend,calibration,out,args.shots,args.suite,
                                      args.include_placement,args.max_layouts,tuple(args.transpiler_seeds))
    if args.mode=="prepare":
        print(f"Prepared {len(circuits)} verified native circuits, {manifest['total_requested_shots']} shots planned.")
        print("No new IQM hardware run. Submit with compare --mode run on the authorized physical QPU.")
        return manifest
    if args.mode=="simulate":
        model=calibration_noise_model(calibration,backend) if args.noise else None
        result=simulate_packet(manifest,circuits,out,model,args.noise_seed)
        print(json.dumps({v:{"success":g["success_rate"],"shots":g["shots"]}
                          for v,g in result["variants"].items()},indent=2))
        return result
    from iqm.iqm_client import CircuitCompilationOptions,HeraldingMode
    options=CircuitCompilationOptions(heralding_mode=HeraldingMode.NONE)
    maximum=getattr(backend,"max_circuits",None)
    if maximum is not None and len(circuits)>maximum:raise ValueError("Batch exceeds live backend limit; use the balanced suite")
    definition=backend.create_circuit_job_definition(circuits,shots=args.shots,circuit_compilation_options=options)
    manifest.update(source="IQM_QPU_comparison",server_url=url,quantum_computer=computer,
                    calibration_pinned=args.pin_calibration,configuration_verified_from_submission=True)
    write_json(out/"submission.json",manifest)  # Guard even an uncertain network submission.
    if hasattr(definition,"model_dump"):write_json(out/"iqm-job-definition.json",definition.model_dump(mode="json"))
    job=backend.run(circuits,shots=args.shots,circuit_compilation_options=options)
    return finish_comparison_job(job,manifest,out)

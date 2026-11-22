"""Strict IQM quality-metric parsing and an explicitly approximate noise model.

Unheralded readout metrics only. Fidelities are dimensionless; T1/T2 are seconds.
The snapshot has no pulse durations, so we add no guessed idle/thermal channels.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re


def qb_key(name: str):
    match = re.fullmatch(r"QB(\d+)", name)
    return int(match[1]) if match else name


def edge_key(first: str, second: str) -> tuple[str, str]:
    return tuple(sorted((first, second), key=qb_key))


@dataclass(frozen=True)
class Estimate:
    value: float
    uncertainty: float


@dataclass(frozen=True)
class QubitQuality:
    prx: Estimate
    readout_0_to_1: Estimate
    readout_1_to_0: Estimate
    t1_seconds: float | None
    t2_seconds: float | None


@dataclass(frozen=True)
class Calibration:
    calibration_set_id: str
    metric_set_id: str
    device_label: str
    timestamp: str
    sha256: str
    qubits: dict[str, QubitQuality]
    cz: dict[tuple[str, str], Estimate]
    ignored_invalid_observations: int
    readout_implementation: str

    def compatibility(self, backend) -> dict:
        names = [backend.index_to_qubit_name(i) for i in range(backend.num_qubits)]
        edges = {edge_key(names[a], names[b]) for a, b in backend.target["cz"] if a != b}
        missing_names = sorted(set(self.qubits) - set(names), key=qb_key)
        uncalibrated_edges = sorted(edges - set(self.cz))
        unavailable_edges = sorted(set(self.cz) - edges)
        backend_id = str(getattr(getattr(backend, "architecture", None), "calibration_set_id", "unknown"))
        return {"device_label_from_snapshot": self.device_label,
                "backend_name": backend.name, "backend_calibration_set_id": backend_id,
                "snapshot_calibration_set_id": self.calibration_set_id,
                "calibration_id_matches": backend_id == self.calibration_set_id,
                "missing_qubit_names": missing_names,
                "uncalibrated_target_edges": [list(e) for e in uncalibrated_edges],
                "unavailable_calibrated_edges": [list(e) for e in unavailable_edges],
                "topology_matches_snapshot": not (missing_names or uncalibrated_edges or unavailable_edges),
                "physical_device_identity_confirmed": backend_id == self.calibration_set_id}

    def summary(self) -> dict:
        moment = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        return {"source": "user-supplied IQM quality-metric snapshot", "sha256": self.sha256,
                "device_label": self.device_label, "calibration_set_id": self.calibration_set_id,
                "metric_set_id": self.metric_set_id, "timestamp_utc": self.timestamp,
                "age_hours_at_analysis": (datetime.now(timezone.utc)-moment).total_seconds()/3600,
                "qubits": len(self.qubits), "cz_edges": len(self.cz),
                "cz_fidelity_range": [min(v.value for v in self.cz.values()), max(v.value for v in self.cz.values())],
                "ignored_invalid_observations": self.ignored_invalid_observations,
                "readout_implementation": self.readout_implementation, "heralded_metrics_used": False,
                "pulse_durations_available": False}


def load_calibration(path: Path, readout_implementation: str = "measure") -> Calibration:
    raw = path.read_bytes()
    document = json.loads(raw)
    if document.get("observation_set_type") != "quality-metric-set" or document.get("invalid") is not False:
        raise ValueError("Expected a valid, non-invalid IQM quality-metric-set")
    moment = datetime.fromisoformat(document["created_timestamp"].replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("Snapshot timestamp must include a timezone")
    if moment > datetime.now(timezone.utc)+timedelta(minutes=5):
        raise ValueError("Calibration timestamp is in the future")
    values = {}
    invalid = 0
    for observation in document["observations"]:
        if observation.get("invalid") is not False:
            invalid += 1
            continue
        name = observation["dut_field"]
        # Exact keys are important: :herald=... is a different experiment.
        value = float(observation["value"])
        uncertainty = float(observation.get("uncertainty", 0))
        if not math.isfinite(value) or not math.isfinite(uncertainty) or uncertainty < 0:
            raise ValueError(f"Nonfinite value or invalid uncertainty: {name}")
        item = (Estimate(value, uncertainty), observation.get("unit", ""))
        if name in values and values[name] != item:
            raise ValueError(f"Conflicting duplicate metric: {name}")
        values[name] = item

    def get(name, unit_kind="probability"):
        if name not in values:
            raise ValueError(f"Missing valid metric: {name}")
        estimate, unit = values[name]
        if unit_kind == "probability":
            if unit not in ("", "1", "dimensionless") or not 0 <= estimate.value <= 1:
                raise ValueError(f"Expected a dimensionless probability: {name}")
        elif unit != "s" or estimate.value <= 0:
            raise ValueError(f"Expected a positive time in seconds: {name}")
        return estimate

    prx = {}
    for name in values:
        match = re.fullmatch(r"metrics\.rb\.prx\.[^.]+\.(QB\d+)\.fidelity:par=d2", name)
        if match:
            if match[1] in prx:
                raise ValueError(f"Ambiguous PRX implementation for {match[1]}")
            prx[match[1]] = get(name)
    if not prx:
        raise ValueError("No supported PRX fidelity metrics")
    qubits = {}
    for name in sorted(prx, key=qb_key):
        prefix = f"metrics.ssro.{readout_implementation}.constant.{name}."
        t1key, t2key = f"characterization.model.{name}.t1_time", f"characterization.model.{name}.t2_time"
        qubits[name] = QubitQuality(prx[name], get(prefix+"error_0_to_1"), get(prefix+"error_1_to_0"),
                                    get(t1key,"seconds").value if t1key in values else None,
                                    get(t2key,"seconds").value if t2key in values else None)
    edges = {}
    for name in values:
        match = re.fullmatch(r"metrics\.irb\.cz\.[^.]+\.(QB\d+)__(QB\d+)\.fidelity:par=d2", name)
        if match:
            edge = edge_key(match[1], match[2])
            if edge[0] == edge[1] or any(q not in qubits for q in edge):
                raise ValueError(f"Invalid CZ locus: {name}")
            if edge in edges:
                raise ValueError(f"Ambiguous CZ implementation: {edge}")
            edges[edge] = get(name)
    if not edges:
        raise ValueError("No supported CZ fidelity metrics")
    return Calibration(str(document["describes_id"]), str(document["observation_set_id"]),
                       str(document["dut_label"]), moment.astimezone(timezone.utc).isoformat(),
                       hashlib.sha256(raw).hexdigest(), qubits, edges, invalid, readout_implementation)


def calibration_noise_model(calibration: Calibration, backend):
    """Independent depolarizing + asymmetric readout approximation, NOT a QPU forecast.

    Treat exported F as average gate fidelity: lambda=d/(d-1)*(1-F).
    One PRX metric per native R. No guessed pulse durations, idle noise, crosstalk,
    coherent miscalibration, leakage or additional initialization model.
    """
    from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error
    model = NoiseModel(basis_gates=["r", "cz", "id"])
    names = [backend.index_to_qubit_name(i) for i in range(backend.num_qubits)]
    for i, name in enumerate(names):
        if name not in calibration.qubits:
            raise ValueError(f"Missing calibration for {name}")
        q = calibration.qubits[name]
        model.add_quantum_error(depolarizing_error(2*(1-q.prx.value),1), "r", [i])
        e0,e1 = q.readout_0_to_1.value,q.readout_1_to_0.value
        model.add_readout_error(ReadoutError([[1-e0,e0],[e1,1-e1]]),[i])
    for first,second in backend.target["cz"]:
        key=edge_key(names[first],names[second])
        if key not in calibration.cz:
            raise ValueError(f"Missing calibrated CZ edge {key}")
        error=depolarizing_error(4/3*(1-calibration.cz[key].value),2)
        model.add_quantum_error(error,"cz",[first,second])
        if (second,first) not in backend.target["cz"]:
            model.add_quantum_error(error,"cz",[second,first])
    return model

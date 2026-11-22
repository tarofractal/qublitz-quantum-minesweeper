"""Plain, portable artifacts; no credentials or machine-specific paths saved."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform


def versions() -> dict:
    result = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("qiskit", "qiskit-aer", "iqm-client", "numpy", "pytest", "matplotlib"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "not installed"
    return result


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def save_circuit(circuit, directory: Path, stem: str, render: bool = True) -> None:
    from qiskit import qpy, qasm3
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{stem}.qpy").open("wb") as stream:
        qpy.dump(circuit, stream)
    (directory / f"{stem}.txt").write_text(str(circuit.draw(output="text", fold=120, idle_wires=False)))
    try:
        (directory / f"{stem}.qasm").write_text(qasm3.dumps(circuit))
    except Exception as exc:
        (directory / f"{stem}-qasm-export.txt").write_text(type(exc).__name__ + ": " + str(exc))
    if render:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure = circuit.draw(output="mpl", fold=30, idle_wires=False, cregbundle=False,
                              style={"fontsize": 9, "subfontsize": 7})
        if circuit.num_qubits == 5:
            legend = ("Source wires: q0=d0 (left), q1=d1 (middle), q2=d2 (right), q3=a0, q4=a1.\n"
                      "Human syndrome (s0,s1)=(left-middle,middle-right). Raw counts: v2v1v0 s1s0.\n"
                      "Source indices are not fixed device addresses; hardware routing is recorded in backend.json.")
        elif circuit.num_qubits == 6:
            legend = ("Source wires: q0-q3=d0-d3, q4=a0 (ZZZZ), q5=a1 (XXXX). Only ancillas measured.\n"
                      "Human syndrome (s0,s1)=(ZZZZ bit,XXXX bit); 0=+1, 1=-1. Raw counts: s1s0.\n"
                      "Source indices are not fixed device addresses; hardware routing is recorded in backend.json.")
        else:
            legend = ("Input logical qubit: q0=d0. Human ket order: d0 d1 d2 d3.\n"
                      "Qiskit statevector ket order: q3 q2 q1 q0. This encoder contains no measurements.")
        figure.text(.015, -.012, legend, ha="left", va="top", fontsize=8, color="#233d55")
        figure.savefig(directory / f"{stem}.svg", bbox_inches="tight")
        figure.savefig(directory / f"{stem}.png", dpi=135, bbox_inches="tight")
        plt.close(figure)

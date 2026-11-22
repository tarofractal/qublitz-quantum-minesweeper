# Requirements and official technical sources

Checked 21 November 2026. The provided PDF is authoritative for the challenge. It does not specify a different SDK, event starter repository, QPU name, or endpoint. We therefore use Python/Qiskit and the current IQM adapter distribution.

| Source | Use |
|---|---|
| `source/challenge.pdf`, 8 pages | Challenge definition, allowed error sets, testing, judging and submission requirements |
| PDF p. 2 | Levels 1 and 2; three data qubits, I and one X/Z |
| PDF p. 3 | Promised Y-only Level 3; error-type classification for Level 4 |
| PDF pp. 4–5 | Preserve quantum information, test different inputs/errors, demonstrate circuits |
| PDF pp. 5–6 | At least one IQM hardware circuit and experimental results; code repository, results and live demonstration |
| [IQM Qiskit user guide](https://docs.iqm.tech/iqm-client/user_guide_qiskit.html) | Current installation, authentication, transpilation, backend inspection and conditional-gate limitations |
| [Official adapter archive notice](https://github.com/iqm-finland/qiskit-on-iqm) | The standalone qiskit-iqm package is deprecated; new releases live in iqm-client[qiskit] |
| [IQM fake backend API](https://docs.iqm.tech/iqm-client/api/iqm.qiskit_iqm.fake_backends.html) | Official local fake targets and noise models; these are simulations |
| [IQM backend API](https://docs.iqm.tech/iqm-client/api/iqm.qiskit_iqm.iqm_provider.IQMBackend.html) | Circuit job definitions, run and job retrieval |
| [Qiskit bit ordering](https://quantum.cloud.ibm.com/docs/en/guides/bit-ordering) | Statevector and classical string ordering |
| [Qiskit Statevector API](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.quantum_info.Statevector) | Exact state evolution and probabilities |
| [Qiskit quantum-information API](https://quantum.cloud.ibm.com/docs/en/api/qiskit/quantum_info) | Partial trace and fidelity |
| [Qiskit Aer simulator API](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.AerSimulator.html) | Shot simulation, density-matrix diagnostics and MPS simulation |

Only primary documentation is used for SDK claims. The specific fake backend operations, coupling map, layouts and shot outcomes in the report were obtained by running the installed adapter, not inferred from a generic backend description. No live device configuration was available.

The original PDF is included as supplied and is not relicensed by this project. Code originality is not a challenge requirement; understanding and verification are. AI assistance is permitted by PDF p. 5. Teams should review the code and practice the explanations themselves.

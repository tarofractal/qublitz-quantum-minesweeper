# Live demonstration - current evidence

## Reproduce the state walkthrough

```bash
.venv/bin/python -m minesweeper demo --level 1 --input +i --error X --location 1 --shots 512 --out results/submission-demo
```

Open `docs/live-demo.html`. Use Level 1, input +i, middle error. Step through preparation, encoding, X injection, comparison extraction, syndrome measurement, X recovery, decoding and inverse-preparation verification. Point to 010 and 101: both share syndrome 11, so the ancillas do not reveal which logical component is present. The decoded state retains its relative i. These walkthrough states and fidelity checks are ideal simulation.

## Three English sentences for the hardware slide

We compare the original and optimized Level 4 circuits using a balanced I, X, Y, and Z protocol.

Under the saved protocol's circuit-order assignment, the supplied IQM job export gives 74.12% correct syndrome classifications for the original and 89.94% for the optimized circuit.

Ideal simulations verify that both checks preserve the encoded data, while these hardware counts measure classification accuracy, not logical-state fidelity.

## Questions to be ready for

Why no measurement collapse of the logical superposition? Both logical components have the same stabilizer eigenvalues for a fixed promised error; the measured ancilla factors from the encoded amplitudes.

Why does X-only fail in Level 3? It restores the bit pattern but leaves a logical Z relative phase. The + input becomes -, so the state fidelity is zero despite the same computational-basis probabilities.

Why are X and Z controls needed? Reversing the two bits exchanges their types. Y=11 and I=00 cannot detect that mistake.

What is still unknown experimentally? The supplied export does not contain logical-state fidelity, physical native circuit/layout, calibration linkage, or the original job receipt. Circuit-to-histogram assignments currently come from the saved Run Ready protocol.

What caused the improvement? Reduced routed entanglers and calibration-aware placement are plausible contributors. This combined comparison does not isolate a causal contribution, and the simplified noise model omits several real-device effects.

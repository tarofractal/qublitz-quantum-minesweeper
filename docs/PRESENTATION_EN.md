# Short English presentation script

Approximately three minutes. Open `docs/live-demo.html` and select Level 1, input +i, middle error. Alternatively run:

```bash
.venv/bin/python -m minesweeper demo --level 1 --input +i --error X --location 1 --shots 512
```

## 0:00 — The problem

“Our project finds hidden quantum errors without reading the information we are trying to protect. We implemented all four Quantum Minesweeper levels and tested every permitted error configuration against six quantum inputs. Our recovery functions receive only the level and syndrome. The hidden error and original input stay in the experiment harness.”

## 0:25 — Show preparation and encoding

“Here the input is plus-i: zero plus i times one, divided by square root two. Two CNOT gates spread it across three data qubits, giving zero-zero-zero plus i times one-one-one. This is an entangled encoding, not three independent copies of an unknown state.”

## 0:45 — Advance to the injected middle error

“The test harness flips the middle qubit. Now the two components are zero-one-zero and one-zero-one. We compare left with middle, and middle with right, using two ancillas. Both components give ‘different, different’, or one-one.”

## 1:05 — Show syndrome extraction and recovery

“Reading one-one tells us the error was in the middle. It does not reveal which logical component we had. The data and syndrome factor into a superposition times the same ancilla state, so this measurement preserves the relative coefficient i. We apply X to the middle and reverse the encoding. The original plus-i state is back on the first data qubit.”

## 1:30 — Show verification

“We check the exact decoded quantum-state fidelity in simulation. We also apply the inverse input preparation and measure return to zero. Every one of the 150 input/error cases passed at 512 shots per case, without post-selection. We separately tested actual measured feed-forward, coherent recovery, bit ordering, and equal global phase on the two logical basis states.”

## 1:55 — Explain the other levels

“For phase errors, Hadamard gates change the basis: H Z H equals X, so we reuse the bit-flip recovery. For promised Y errors, the same parity syndrome finds the location, but recovery must be Y. Our deliberate X-only control restores the bit pattern while turning plus into minus: its state fidelity is zero.”

“Level 4 uses four data qubits stabilized by ZZZZ and XXXX. X changes only the ZZZZ outcome, Z changes only XXXX, and Y changes both. We measure only the ancillas. This classifies the type while preserving the errored encoded state; it does not identify the location or correct it.”

## 2:40 — IQM status: use the statement matching the evidence

Current, truthful statement:

“We prepared a complete Level-4 circuit, compiled it to an IQM Garnet fake target, and verified the exact routed circuit locally. We have not run on IQM hardware because authenticated access was unavailable. That required step is still outstanding. Our repository includes a pilot runner that saves the real job ID, circuit, backend metadata and raw counts once access is configured.”

After actually completing the IQM run, replace that paragraph with facts from `results/iqm-pilot/job.json` and `analysis.json`:

“We ran this Level-4 classifier on [physical QPU name] with [shots] shots, job [ID]. The observed correct classification rate was [successes/shots], compared with 100% in ideal simulation. We retained all shots. The histogram alone cannot separate gate, readout and decoherence effects, and we did not measure data-state fidelity on hardware.”

Do not fill those fields with fake-backend results.

## Quick judge answers

- **Why do arbitrary amplitudes work?** Both logical basis states recover with the same global phase. Linearity preserves any alpha and beta.
- **Does the decoder see the injected location?** No. Its API accepts the level and observed syndrome only.
- **Why does the Y syndrome look like X?** Both anticommute with the neighboring Z-parity checks. The promised error type determines the recovery gate.
- **Does Level 4 correct an arbitrary Pauli?** It classifies type only. Two stabilizer bits do not reveal location.
- **Are the three-qubit circuits fault tolerant?** They solve the promised single-data-error model. They do not correct arbitrary gate/ancilla/measurement faults.
- **Why use Level 4 for IQM?** Six qubits, final ancilla measurements only, and no classical feed-forward requirement. Five-qubit coherent Level 1 is also provided.

## Demo order for a longer presentation

1. Level 1 +i/middle: preparation → encoding → injection → ancillas → correction → decoding.
2. One-qubit interference: H|+> = |0>, H|-> = |1>.
3. Level 2 +i/middle Z: point out the exact injection and recovery bases.
4. Level 3 +/middle Y: compare correct Y with deliberately wrong X.
5. Level-4 classifier panel: change type and input independently; the syndrome depends on type.
6. Show `results/cases.csv`, test outcomes, then genuine IQM evidence when available.

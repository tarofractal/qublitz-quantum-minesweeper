"""Generate current comparison report and figures from retained evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/improvement'
DOCS=ROOT/'docs'


def read(name):return json.loads((OUT/name).read_text())
def percent(p):return f'{100*p:.2f}%'
def interval(bounds):return f'{100*bounds[0]:.2f}–{100*bounds[1]:.2f}%'
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+
                      ['| '+' | '.join(map(str,row))+' |' for row in rows])


def build():
    summary=read('summary.json');metrics=summary['metrics'];noise=read('noise-balanced-analysis.json')
    tests=json.loads((ROOT/'results/test-outcome.json').read_text())
    base=summary['archived_physical_pilot'];delta=summary['noise_changes']['improved']
    variants=['original','placement','improved']
    colors=['#607d8b','#4b94a8','#159179']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(10.8,3.9))
    x=np.arange(3)
    axes[0].bar(x,[metrics[v]['native_cz'] for v in variants],color=colors)
    axes[0].set_xticks(x,['Original','Placement only','Rewrite + placement'])
    axes[0].set_ylabel('Native CZ instructions');axes[0].set_title('Offline compilation on matching IQM target')
    for i,v in enumerate(variants):axes[0].text(i,metrics[v]['native_cz']+.35,str(metrics[v]['native_cz']),ha='center')
    rates=np.array([noise['variants'][v]['success_rate'] for v in variants])
    bounds=[noise['variants'][v]['wilson_95'] for v in variants]
    error=np.array([[p-b[0] for p,b in zip(rates,bounds)],[b[1]-p for p,b in zip(rates,bounds)]])*100
    axes[1].bar(x,100*rates,color=colors,yerr=error,capsize=5)
    axes[1].set_xticks(x,['Original','Placement only','Rewrite + placement'])
    axes[1].set_ylim(0,104);axes[1].set_ylabel('Correct classification (%)')
    axes[1].set_title('Approximate calibration-noise SIMULATION')
    for i,p in enumerate(rates):axes[1].text(i,100*p+2.0,f'{100*p:.2f}%',ha='center')
    fig.suptitle('Circuit and shared-model comparison — no new hardware measurement',fontsize=12)
    fig.tight_layout();fig.savefig(OUT/'comparison.png',dpi=170);fig.savefig(OUT/'comparison.svg');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(9.5,4.3))
    types=['I','X','Y','Z']
    for ax,v in zip(axes,['original','improved']):
        rows=noise['variants'][v]['confusion_row_fractions']
        matrix=np.array([[rows[t][c] for c in types] for t in types])
        ax.imshow(matrix,vmin=0,vmax=1,cmap='Blues')
        ax.set_xticks(range(4),types);ax.set_yticks(range(4),types)
        ax.set_xlabel('Classified from syndrome');ax.set_ylabel('Injected type (scoring only)')
        ax.set_title(v.capitalize())
        for i in range(4):
            for j in range(4):ax.text(j,i,f'{100*matrix[i,j]:.1f}%',ha='center',va='center',color='white' if matrix[i,j]>.5 else '#19374b')
    fig.suptitle('Balanced confusion matrices: calibration-noise simulation, all shots',fontsize=12)
    fig.tight_layout();fig.savefig(OUT/'confusion.png',dpi=170);fig.savefig(OUT/'confusion.svg');plt.close(fig)

    compiled_rows=[]
    for key,label in [('original','Original path'),('placement','Calibration placement only'),('bridge13','Earlier bridge rewrite'),('improved','Selected rewrite + placement')]:
        m=metrics[key]
        compiled_rows.append([label,m['native_cz'],m['native_r'],m['depth'],', '.join(m['syndrome_device_sites']),f"{m['ranking_score']:.6f}"])
    noise_rows=[]
    for v in variants:
        n=summary['noise_balanced'][v]
        noise_rows.append([v,f"{n['successes']}/{n['shots']}",percent(n['success_rate']),interval(n['wilson_95'])])
    layout_rows=[]
    for v in variants:
        m=metrics[v]
        initial=[f'QB{i+1}' for i in m['initial_source_indices']]
        final=[f'QB{i+1}' for i in m['final_source_indices']]
        layout_rows.append([v,', '.join(initial),', '.join(final)])
    text=f'''# QUBLITZ 2026 — Verified hardware-circuit improvements

## Evidence summary

The attached project was updated in place after verifying the source ZIP and running its untouched regression suite: **300 passed in 17.88 seconds**. The original 150-case suite was reproduced at 512 shots per case: 76,800 ideal shots, 100% expected results, no shot exclusion. The updated full suite has **{tests['tests']} passing tests**, {tests['failures']} failures, {tests['errors']} errors and {tests['skipped']} skipped. Levels 1–3 and the original Level-4 builder remain available.

**No new IQM hardware comparison has been run in this environment.** Authenticated server/QPU configuration was not present. The user-supplied physical pilot export is included; it is distinct from archived fake Garnet results and the new simulations.

| Evidence source | Original | Improved |
|---|---|---|
| Archived user-supplied IQM export, expected 11 | 24/32 = 75%; 95% Wilson 57.89–86.75% | No new hardware result |
| Verified offline native compilation, pilot example | 24 CZ, depth 45 | 11 CZ, depth 17 |
| Ideal exact-native verification | 78/78 input/error cases pass | 78/78 input/error cases pass |
| Shared approximate calibration-noise simulation, balanced four types | {percent(summary['noise_balanced']['original']['success_rate'])} | {percent(summary['noise_balanced']['improved']['success_rate'])} |

The rewrite removes **54.17% of native CZ instructions** and reduces gate-layer depth by **62.22%** on the verified offline target. The modeled gain is **{delta['change_percentage_points']:.2f} percentage points**, with approximate 95% Newcombe/Wilson interval **{delta['newcombe_wilson_95_percentage_points'][0]:.2f} to {delta['newcombe_wilson_95_percentage_points'][1]:.2f} points**. This interval measures simulation shot uncertainty, not uncertainty about whether the model describes the real device.

## 1. What the physical baseline establishes

Job ID: `01a1fff5-31e3-744f-89da-cb1d14f7bacb`. The supplied export contains measurement keys `syn_2_0_0`, `syn_2_0_1`, and these counts:

{table(['Exported raw string','Count'],[[k,base['raw_counts'][k]] for k in ['00','01','10','11']])}

Assuming the documented Level-4, +i, Y-on-d1 pilot command, the expected outcome is 11. It occurred 24 times out of 32: **75% syndrome-classification success**, not logical-state fidelity. The configuration is **likely, inferred from the documented command**. The source ZIP contains no `results/iqm-pilot/job.json`, physical submitted circuit, physical layout, server/QPU name or verified physical calibration linkage. Those require the original pilot receipt and its submitted-circuit metadata. The calibration snapshot alone cannot establish that linkage.

The original archived *local* native QPY is available. Its gate parameters, operation order, qubit/classical-bit mappings, global phase and classical registers match the reconstructed original path exactly: **{summary['archived_local_circuit_reproduced']}**. Circuit names are not part of this computational fingerprint. This validates the reconstruction of the local baseline; it does not establish that the physical pilot used exactly that native circuit.

The symmetric 11 result cannot resolve which raw character represents which check. We therefore do not assign the archived raw 01/10 counts to X/Z. The updated Qiskit path is independently checked with asymmetric controls and the installed IQM adapter formatter: native `syn[0]=1,syn[1]=0` becomes Qiskit `01` and classifies X; `syn[0]=0,syn[1]=1` becomes `10` and classifies Z. The prepared physical comparison includes both controls.

## 2. Calibration, placement and compiler metrics

The snapshot is a valid IQM `quality-metric-set`, device label `{summary['calibration']['device_label']}`, created `{summary['calibration']['timestamp_utc']}`. Its described calibration ID is `{summary['calibration']['calibration_set_id']}`. All 598 observations were inspected; 0 were marked invalid. Parsing checks timestamps, finite values, uncertainties, units, probabilities, required metrics and conflicting duplicates.

It supplies PRX metrics for 20 qubits and CZ metrics for 30 edges. CZ fidelities range from 0.9908567 to 0.9990728. The 20 names and all 30 links match the official offline `IQMFakeGarnetBackend` topology. This is topology compatibility, not proof of physical device identity. The fake target has calibration ID zero; it is not the physical calibration.

Unheralded `metrics.ssro.measure.constant` rates are used separately for 0-to-1 and 1-to-0 readout errors. The parser deliberately excludes `:herald=...` values from the primary metric. T1/T2 values are checked as seconds. The snapshot lacks pulse durations, so **physical duration estimates and idle-decoherence timing are unavailable**; no duration is invented from depth.

The selector takes only the backend, calibration and search budgets. A fixed +i/no-error reference is used before constructing any evaluation cases. It searches at most 24 layouts per main variant and transpiler seeds 7, 19 and 43. Original placement candidates are prefiltered from at most 16 six-cycle footprints and their role permutations; every final rank uses the actual routed native circuit. The selected layout/seed is frozen for all evaluation inputs and errors.

The ranking heuristic is a conservative negative-log gate/readout proxy: gate fidelities minus two reported standard uncertainties, worst-bit unheralded readout cost, a 0.001-per-CZ routing penalty and a small depth tie-breaker. **It is not an accuracy prediction.** No evaluation shot counts were used for selection. Full candidate scores are retained in `results/improvement/search.json`.

Metrics below are for the documented +i/Y1 example on the offline target:

{table(['Candidate','CZ','Native R','Depth','ZZZZ / XXXX measurement sites','Ranking heuristic'],compiled_rows)}

The placement-only change does not reduce CZ count in this bounded search and adds one layer. Its lower heuristic score is not evidence of a hardware improvement. The rewrite has no SWAP routing on the selected six physical qubits. The earlier 13-CZ bridge strategy remains available and was checked; its pilot metrics are shown for comparison.

Layouts are listed in source-wire order `(d0,d1,d2,d3,aZ,aX)`. Initial and final layouts differ when routing moves quantum states:

{table(['Variant','Initial physical names','Final physical names'],layout_rows)}

The improved assignment is d0=QB5, d1=QB2, d2=QB9, d3=QB4, aZ=QB1, aX=QB10 for this snapshot/target. It is selected from the target rather than hardcoded. Live preparation repeats the topology validation and ranking using the actual selected backend. `--pin-calibration` optionally requests the snapshot calibration ID; otherwise current backend calibration and its ID match/mismatch are recorded.

![Native resource counts and shared-model classification](../results/improvement/comparison.png)

## 3. Why the shallower circuit is equivalent

The codewords remain `(0000+1111)/sqrt(2)` and `(0011+1100)/sqrt(2)`. Input is on d0. The improved encoder is H(d3), CNOT(d3,d0), CNOT(d0,d1), CNOT(d3,d2): three CNOTs rather than four. For logical input b and the H-generated bit g, output is `(b XOR g,b XOR g,g,g)`, giving exactly the original codewords with the same phase. Both encoding columns are explicitly compared as an isometry.

Let C be CNOT(d0,d1) followed by CNOT(d2,d3). Conjugation by C maps ZZZZ to Z1 Z3 and XXXX to X0 X2. Apply C, write those two shorter checks into aZ and aX, then apply C again to restore the data. This still uses eight check CNOTs, but the interaction graph is a nearest-neighbor six-cycle. A chord between d3 and d0 supports the three-CNOT encoder, so all 11 source entanglers compile directly to 11 native CZs.

The error-injection barrier remains after complete encoding and before extraction. We do not commute the known injected error into preparation or cancel the protected encoding across that boundary. Recovery/classification never receives the hidden error, its location or input label. Only the harness knows those for preparation and scoring; error type is obtained from the two measured syndrome bits.

![Improved source circuit with injection boundary and bit-order legend](../results/improvement/circuits/improved-source.png)

Source wire order is q0–q3=d0–d3, q4=aZ for ZZZZ and q5=aX for XXXX. Human syndrome order is `(ZZZZ,XXXX)`, with bit 0 meaning +1 and bit 1 meaning −1. Qiskit raw strings are `syn1syn0`: I=00, X=01, Y=11, Z=10. Only the two ancillas are measured.

## 4. Verification and retained results

The updated regression suite has {tests['tests']} passes. New tests cover strict calibration parsing, unheralded/asymmetric readout, the IQM measurement-key adapter, fair-analysis rejection of mismatched cases/shots, pending/completed/failed job receipts and duplicate-submission protection.

All 13 errors across all six logical inputs were checked for each main candidate: **234 exact compiled-native cases**. The verifier accounts for the compiler's final wire permutation, traces out the correct physical ancillas and compares data to the encoded state immediately after the injected error. Minimum data-preservation fidelity is **{summary['minimum_native_data_preservation_fidelity']:.15f}**, within floating point error of 1. Every case also passed 512 ideal finite shots. This checks preservation of complex superpositions, not just classical bit frequencies.

The source extraction rewrite is also compared to the original as an isometry on all 16 data basis states with ancillas zero. Equality of those columns establishes the same linear measurement map for arbitrary data superpositions. Preservation without collapse applies to the promised encoded-and-errored stabilizer eigenstates. Both source encoders, including the 13-CZ bridge fallback, pass all 78 source cases.

Full records, raw counts and exact circuits are retained in `ideal-native-cases.json`, `.csv`, `.qpy`, `circuits/`, the test JUnit file and `study.log`. Levels 1–3 and the original 150-case simulation remain regression-tested; the untouched baseline evidence is under `results/improvement/baseline/`.

## 5. Shared approximate calibration-noise comparison

The model uses independent depolarizing errors from exported fidelities and asymmetric unheralded readout errors. Exported F is treated as average gate fidelity, giving depolarization parameter `2*(1-F)` for one qubit and `4/3*(1-F)` for two qubits. One PRX metric is assigned per native R instruction, regardless of its angle/implementation. Native R/CZ names are retained so those channels actually attach.

No pulse durations are available, so there is no guessed idle/T1/T2 model. Leakage, coherent errors, crosstalk, correlations, initialization faults and drift are omitted. Consequently this model is not a forecast of physical accuracy and is not established by the 32-shot pilot. It does not reproduce all real-device effects that may explain the pilot's lower rate; the attachments do not identify the cause.

Evaluation uses seeds 49157 and 82799, separate from all transpiler tuning seeds. All 13 locations/type configurations on +i were sampled at 512 shots per seed, per variant. The directly comparable balanced subset below is I, X1, Y1, Z1: 1024 shots per case, 4096 per variant. All shots are retained; no mitigation or post-selection is applied.

{table(['Variant','Correct / total','Classification success','95% Wilson interval'],noise_rows)}

Placement-only change: {summary['noise_changes']['placement']['change_percentage_points']:.2f} percentage points, with an interval spanning zero. Rewrite plus placement: **+{delta['change_percentage_points']:.2f} percentage points** in this model. Per-case histograms, confusion counts, row-normalized confusion matrices, macro-type success and uncertainty are in `noise-balanced-analysis.json`; the full 13-configuration results and both evaluation seeds are retained separately.

![Confusion matrices from the same calibration-noise simulation](../results/improvement/confusion.png)

## 6. Prepared fair physical comparison

The balanced protocol prepares **8 native circuits, 256 shots each, 2048 total shots**, all on the same backend/calibration instance and in one job. Cases are +i with I, X1, Y1, Z1, including the documented pilot and both asymmetric controls. Case blocks alternate original/improved and improved/original to reduce ordering bias. Inputs, errors and shots match within every pair. Each submitted circuit has a unique name and retains its exact native QPY, gate/register fingerprint, layout and measurement sites.

The new analysis reports raw histograms, per-case success, confusion matrices, aggregate all-shot success, macro-type success, Wilson intervals and absolute percentage-point changes with Newcombe/Wilson intervals. It refuses mismatched shots, case sets, input/error metadata, duplicate cases and unverified bit-order formats. The archived pilot is historical context; do not subtract its 75% from a new balanced aggregate. Improvement must be assessed against the paired original circuits in the new job.

After applying the source patch to the original folder (or copying its `results/iqm-pilot` receipt into the updated project), the next hardware command is:

```bash
.venv/bin/python -m minesweeper compare --mode run --calibration data/calibration.json --suite balanced --shots 256 --out results/iqm-comparison --prompt-token
```

The command reuses server/QPU settings from `results/iqm-pilot/job.json` if environment/CLI settings are absent. It never reads or stores a token from that receipt. `--prompt-token` enters a missing token privately. Choose the authorized physical QPU. If no receipt is present, supply the existing IQM_SERVER_URL and IQM_QUANTUM_COMPUTER settings or --url/--computer.

If polling times out, the job ID is already saved. Retrieve it without resubmitting:

```bash
.venv/bin/python -m minesweeper compare --mode retrieve --out results/iqm-comparison --prompt-token
.venv/bin/python -m minesweeper compare --mode analyze --result-file results/iqm-comparison/job.json
```

For more evidence, predeclare 1024 shots per circuit and use a new output directory. `--suite locations` covers all 13 configurations on +i; `--suite full` covers all 78 inputs/errors. The original single-pilot workflow remains unchanged: `python -m minesweeper iqm --mode retrieve --result-file results/iqm-pilot/job.json` with private token configuration.

## 7. Reproduce and submit

```bash
bash scripts/setup.sh
.venv/bin/python scripts/run_tests.py
.venv/bin/python scripts/improve_and_compare.py
.venv/bin/python scripts/report_improvement.py
```

Or run `bash scripts/reproduce_improvement.sh`. It submits no physical job. Dependency versions remain pinned to Python 3.12, Qiskit 2.1.2, Aer 0.17.2 and iqm-client 36.0.0. The original challenge PDF is in `docs/source/challenge.pdf`; Level 4 requires classification rather than location recovery. The present work preserves that requirement and the earlier levels.

**Still needed:** run the prepared paired comparison on the authorized physical device, retrieve its actual counts and confirm device/calibration identity. A positive matched-case/aggregate change, with uncertainty and controls reported, would be evidence of hardware improvement. The current evidence supports a shorter verified circuit and a model-based improvement, not a measured physical improvement. Retain the original pilot receipt to resolve the archived run's missing linkage.

Official references: [IQM Qiskit guide](https://docs.iqm.tech/iqm-client/user_guide_qiskit.html), [IQM backend API](https://docs.iqm.tech/iqm-client/api/iqm.qiskit_iqm.iqm_provider.IQMBackend.html), [Aer depolarizing channel](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.noise.depolarizing_error.html). Adapter ordering was additionally verified against the installed IQM 36.0.0 formatter with X/Z controls.
'''
    ja=f'''# 何を改善したか：日本語での説明

## 75%は何の割合？

今回のファイルでは、32回測って24回「11」が出ました。記載されたY誤りの実演だったとすると、その11が正解なので75%です。**「元の量子状態が75%復元できた」という意味ではありません。誤りの種類を正しく示す比較結果が出た割合です。** このファイルだけには、元の量子状態の測定結果は入っていません。

32回は少ないため、真の成功率には幅があります。95% Wilson区間は約57.9～86.7%です。また、入力+i、d1へのYという設定はREADMEのコマンドからの推定で、実機の送信回路やレシートによる確認はまだありません。

## 変更したこと

まず、0と1を守る符号語は変えていません。検査するのも同じZZZZとXXXXです。アンシラから得る比較結果だけを使って分類し、入力名や試験で入れた誤りを答えに使う処理はありません。

違いは、**同じ比較を、近くの量子ビット同士で短く計算する**ようにしたことです。旧回路はコンパイル後に24個のCZが必要でした。改良回路は11個、約54%減です。回路の深さも45から17になりました。これは保存された回路と今回のオフライン検証の値であり、旧実機ジョブそのものの回路が確認できたという意味ではありません。

CZは2個の量子ビットに作用する操作です。必要な2個が遠いと、情報を移す追加操作が入ります。今回は、量子ビットの配置と計算の順番を工夫して、その遠回りを減らしました。操作が少なくなれば、誤りが入り込む機会や待ち時間を減らせる可能性があります。

さらに、いただいたキャリブレーションから、CZの品質と、0を1／1を0と読み間違える率を読みました。読み取りの良いアンシラ位置などを評価します。ただし、配置を選ぶスコアは順位付けの目安で、実機の成功率そのものではありません。

## 何が確認できた？

元の300テストを変更前に実行し、すべて成功しました。更新後は**{tests['tests']}テストがすべて成功**しています。

Level 4は「誤りなし」と、4か所それぞれのX/Y/Zで13通り。それぞれ6種類の入力を使うので78ケースです。元の回路・配置だけの変更・改良回路について、変換後の正確な回路を全78ケースずつ、計234ケース検証しました。理想シミュレーションでは全成功し、検査後のデータも「誤りを入れた直後の符号化状態」と一致しました。

Xの人が読む比較結果は10ですが、Qiskitの測定文字列では01です。Zはその逆になります。11だけでは順序を確認できないため、XとZのテストも使って逆転の間違いを検出しています。古い実機エクスポートの01/10がどちらを表すかは、元の送信情報がないので決めつけていません。

## では、実機は何%になった？

**改良回路の実機比較は、まだ実行していません。** 同じ簡略ノイズモデルで比べると、元の回路が{percent(summary['noise_balanced']['original']['success_rate'])}、改良回路が{percent(summary['noise_balanced']['improved']['success_rate'])}、差は約{delta['change_percentage_points']:.2f}ポイントでした。これはシミュレーションの結果です。実機の新しい成功率ではありません。

このモデルには、待ち時間、漏れ、量子ビット同士の干渉など、扱えていない誤りがあります。現実の成功率を約94%と保証する根拠にはなりません。

## 次にすること

同じ実機で、元の回路と改良回路を並べて実行します。入力と誤りを同じにし、I/X/Y/Zの各ケースに同じ256ショットを使います。全部で8回路、2048ショットです。元と改良を交互に並べ、同じジョブで実行する準備をしました。

新しい比較結果では、両方の回路の正解率・誤分類の表・信頼区間を比べます。新しい改良回路の結果から古い75%だけを引くのではなく、同じジョブで走らせた元の回路との差を見ます。

元の`results/iqm-pilot`を残してコードを更新した後、最初の実機コマンドは次です。

```bash
.venv/bin/python -m minesweeper compare --mode run --calibration data/calibration.json --suite balanced --shots 256 --out results/iqm-comparison --prompt-token
```

送信後に60秒で結果が返らなくても、ジョブIDは保存されています。再送信せず、次で同じジョブを取得します。

```bash
.venv/bin/python -m minesweeper compare --mode retrieve --out results/iqm-comparison --prompt-token
```

## English demo sentences

The previous IQM pilot returned the expected syndrome in 24 of 32 shots; its input and error configuration are inferred from the documented command.

We reduced the verified compiled circuit from 24 to 11 CZ gates and passed all 78 Level 4 cases in ideal simulation.

Our calibration-based simulation improved from {100*summary['noise_balanced']['original']['success_rate']:.2f}% to {100*summary['noise_balanced']['improved']['success_rate']:.2f}%, but the paired hardware test is still pending.
'''
    (DOCS/'IMPROVEMENT_REPORT.md').write_text(text)
    (DOCS/'IMPROVEMENT_JA.md').write_text(ja)
    spec=importlib.util.spec_from_file_location('report_render',ROOT/'scripts/build_deliverables.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    for name,content,japanese in [('IMPROVEMENT_REPORT',text,False),('IMPROVEMENT_JA',ja,True)]:
        content=renderer.escape_table_kets(content)
        (DOCS/f'{name}.md').write_text(content)
        (DOCS/f'{name}.html').write_text(renderer.render_html(content,name))
        renderer.render_pdf(content,DOCS/f'{name}.pdf',japanese)
    print('Built current English comparison report and Japanese explanation, with figures.')


if __name__=='__main__':build()

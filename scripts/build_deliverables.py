"""Regenerate report, printable PDFs and a fully offline Japanese live demo."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import textwrap

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from minesweeper.artifacts import save_circuit, write_json
from minesweeper.circuits import decode_repetition, encoder_level4, recover_observed
from minesweeper.demo import terms
from minesweeper.experiments import Error, level4_experiment, permitted_errors, repetition_experiment, repetition_stages
from minesweeper.states import INPUTS, preparation

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
RESULTS = ROOT / "results"


def load(path):
    return json.loads(path.read_text())


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                       "| " + " | ".join("---" for _ in headers) + " |"] +
                      ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def escape_table_kets(text):
    # Unescaped ket bars otherwise become Markdown cell separators.
    return "\n".join(re.sub(r"(?<!\\)\|(?=[01ψ])", r"\\|", line) if line.startswith("|") else line
                     for line in text.splitlines()) + "\n"


def completed_iqm_jobs():
    jobs = []
    for path in sorted(RESULTS.glob("iqm*/job.json")):
        job = load(path)
        if job.get("source") == "IQM_QPU" and job.get("status") == "completed" and job.get("result_success"):
            jobs.append((path, job))
    return jobs


def generate_report(sim, tests):
    template = (DOCS / "RESULTS_TEMPLATE.md").read_text()
    rows = [[r["level"], r["cases"], r["error_configurations"],
             f"{r['minimum_ideal_fidelity']:.12f}", f"{r['finite_shots']:,}",
             f"{100*r['minimum_case_success_rate']:.1f}%"] for r in sim["levels"]]
    summary = table(["Level", "Cases", "Error configurations", "Minimum ideal fidelity", "Shots", "Minimum case success"], rows)
    test_sentence = (f"**Actual pytest run:** {tests['tests']-tests['skipped']-tests['failures']-tests['errors']} passed, "
                     f"{tests['failures']} failures, {tests['errors']} errors, {tests['skipped']} skipped. "
                     "Command: `python scripts/run_tests.py`. See `results/pytest.txt` and `results/pytest.xml`.")
    versions = table(["Component", "Version"], [[k, v] for k, v in sim["software"].items()])
    backend = load(RESULTS / "iqm-prepared/backend.json")
    ops = ", ".join(f"{k}={v}" for k, v in backend["compiled_operation_counts"].items())
    native = (f"**Observed local compiler target:** {backend['name']} ({backend['num_qubits']} qubits, a fake target). "
              f"Native supported operations: {', '.join(backend['native_operations'])}. "
              f"The selected Level-4 routed circuit has depth {backend['compiled_depth']} and operations {ops}. "
              "The full coupling map is in `results/iqm-prepared/backend.json`.\n\n")
    mapping_rows = []
    initial = backend["initial_indices_of_source_wires"]
    final = backend["final_indices_of_source_wires"]
    for i, label in enumerate(["d0", "d1", "d2", "d3", "a0 (ZZZZ)", "a1 (XXXX)"]):
        mapping_rows.append([f"q{i}: {label}", initial[i], backend["device_qubit_names"][str(initial[i])],
                             final[i], backend["device_qubit_names"][str(final[i])]])
    native += table(["Source wire", "Initial physical index", "Device name", "Final physical index", "Device name"], mapping_rows)
    native += "\n\nActual ancilla measurements: " + "; ".join(
        f"{m['device_name']} (physical index {m['backend_qubit_index']}) -> syn[{m['classical_registers'][0][1]}]"
        for m in backend["measurement_map"]) + ". This mapping belongs to the saved fake-target compilation only."
    noise = load(RESULTS / "iqm-fake-noise/job.json")
    analysis = load(RESULTS / "iqm-fake-noise/analysis.json")
    noise_text = (f"**Source: IQM_fake_backend_SIMULATION.** Input +i, injected Y1, "
                  f"{analysis['shots']} shots, seed {noise['seed']}. Raw counts are shown in Qiskit's s1s0 order:\n\n" +
                  table(["Raw s1s0", "Count", "Classified type"],
                        [[key, n, {"00": "I", "01": "X", "10": "Z", "11": "Y"}[key]]
                         for key, n in sorted(analysis["raw_counts"].items())]) +
                  f"\n\nCorrect Y classifications: {analysis['raw_counts'].get('11',0)}/{analysis['shots']} = "
                  f"{100*analysis['classification_success_rate']:.6f}%. "
                  f"95% Wilson interval [{analysis['joint_success_wilson_95'][0]:.6f}, "
                  f"{analysis['joint_success_wilson_95'][1]:.6f}]. "
                  "All shots retained; the corresponding ideal routed-circuit check succeeded in every shot. "
                  "No physical job ID exists for this local simulator run.")
    jobs = completed_iqm_jobs()
    status = "Not run on IQM hardware."
    iqm_text = ("**Actual IQM results: none. Not run on IQM hardware.** No IQM token or event-provided "
                "endpoint/QPU configuration was available. There is no physical backend measurement histogram, "
                "success rate or QPU job ID to report. The supplied hardware runner and local evidence "
                "must not be presented as experimental hardware results.")
    iqm_end = ("**Not run on IQM hardware.** Source and routed IQM fake-target circuits were verified "
               "locally; those are simulations, not physical QPU evidence.")
    remaining = ("Configure authorized physical IQM access; run the 32-shot pilot, retain the genuine job "
                 "ID/counts/backend/circuit and analyze it; if possible collect 1024 shots; add the actual "
                 "experimental comparison by rebuilding this report; publish the GitHub repository and rehearse the demo. "
                 "Until the physical run is completed, the PDF's minimum hardware requirement is unmet.")
    if jobs:
        status = "Completed IQM-provider job receipts are included below; verify the named backend is a physical QPU."
        job_rows = []
        from minesweeper.verification import shot_metrics
        for path, job in jobs:
            metric = shot_metrics(job["level"], job["raw_counts"], tuple(job["expected_syndrome"]))
            job_rows.append([job.get("quantum_computer") or job["backend"]["name"], job["job_id"],
                             job["level"], metric["shots"], f"{100*metric['joint_success_rate']:.4f}%", str(path.relative_to(ROOT))])
        iqm_text = ("**Source: IQM_QPU submission receipts.** Confirm in the event dashboard that these "
                    "backend names refer to physical hardware, then include this table and their raw counts "
                    "with the submission. No hardware data-state fidelity is inferred.\n\n" +
                    table(["QPU", "Job ID", "Level", "Shots", "Success", "Evidence"], job_rows))
        iqm_end = "Completed IQM-provider receipts above record the challenge circuits, backend, job IDs, raw counts and success rates. No data-state tomography was performed."
        remaining = "Verify the dashboard identifies a physical QPU; explain the measured rates using the saved counts and uncertainty; push the repository with evidence and rehearse the live demonstration."
    replacements = {"DATE": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    "HARDWARE_STATUS": status, "SUMMARY": summary, "TESTS": test_sentence,
                    "VERSIONS": versions, "NATIVE": native, "NOISE": noise_text,
                    "IQM": iqm_text, "IQM_END": iqm_end, "REMAINING": remaining,
                    "TEST_END": test_sentence.replace("**Actual pytest run:** ", "")}
    for key, value in replacements.items():
        template = template.replace(f"@@{key}@@", value)
    if re.search(r"@@\w+@@", template):
        raise AssertionError("Unexpanded report marker")
    text = escape_table_kets(template)
    (DOCS / "RESULTS.md").write_text(text)
    return text


def inline_html(text):
    code = []
    def protect(match):
        code.append("<code>" + html.escape(match[1]) + "</code>")
        return f"CODETOKEN{len(code)-1}ENDTOKEN"
    text = re.sub(r"`([^`]+)`", protect, text.replace("\\|", "|"))
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    for i, value in enumerate(code):
        text = text.replace(f"CODETOKEN{i}ENDTOKEN", value)
    return text


def blocks(text):
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            content = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                content.append(lines[i]); i += 1
            yield "code", "\n".join(content)
        elif line.startswith("#"):
            match = re.match(r"(#+)\s+(.*)", line)
            yield "heading", (len(match[1]), match[2])
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", lines[i])[1:-1]]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            yield "table", rows
            continue
        elif re.match(r"!\[.*\]\(.*\)", line):
            match = re.match(r"!\[(.*)\]\((.*)\)", line)
            yield "image", (match[1], match[2])
        elif re.match(r"^(?:\d+\.|-)\s+", line):
            yield "list", line
        else:
            content = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(?:#|\||```|!\[|\d+\.\s|-\s)", lines[i]):
                content.append(lines[i]); i += 1
            yield "paragraph", " ".join(content)
            continue
        i += 1


def render_html(text, title):
    rendered = []
    for kind, value in blocks(text):
        if kind == "heading":
            level, label = value
            rendered.append(f"<h{level}>{inline_html(label)}</h{level}>")
        elif kind == "paragraph":
            rendered.append(f"<p>{inline_html(value)}</p>")
        elif kind == "list":
            rendered.append(f"<p class='listitem'>{inline_html(value)}</p>")
        elif kind == "code":
            rendered.append("<pre><code>" + html.escape(value) + "</code></pre>")
        elif kind == "image":
            alt, target = value
            path = (DOCS / target).resolve()
            data = base64.b64encode(path.read_bytes()).decode()
            rendered.append(f"<figure><img alt='{html.escape(alt,quote=True)}' src='data:image/png;base64,{data}'><figcaption>{html.escape(alt)}</figcaption></figure>")
        elif kind == "table":
            rows = ["<tr>" + "".join(f"<{('th' if i==0 else 'td')}>{inline_html(c)}</{('th' if i==0 else 'td')}>" for c in row) + "</tr>" for i, row in enumerate(value)]
            rendered.append("<div class='tablewrap'><table>" + "".join(rows) + "</table></div>")
    css = """body{font:16px/1.85 system-ui,'Noto Sans JP',sans-serif;color:#1d2d3e;background:#f4f6f8;margin:0}main{max-width:1000px;background:white;margin:25px auto;padding:45px 55px}h1{font-size:34px;line-height:1.4;color:#112d46;border-bottom:4px solid #2c9a87;padding-bottom:20px}h2{font-size:23px;margin-top:44px;color:#145a58}h3{font-size:19px}code,pre{font-family:ui-monospace,monospace}code{font-size:.89em;background:#eef3f5;padding:1px 4px;border-radius:3px}pre{background:#12283e;color:#f4f9ff;padding:17px;border-radius:7px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}pre code{background:none;color:inherit;padding:0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.6}th,td{border:1px solid #d9e1e6;padding:10px;text-align:left;vertical-align:top}th{background:#e9f4f1;color:#134d46}.tablewrap{overflow-x:auto;margin:20px 0}img{max-width:100%;height:auto}figure{margin:28px 0}figcaption{font-size:13px;color:#52677b}a{color:#146d8e}.listitem{margin-left:12px}strong{color:#123c4f}@media(max-width:700px){main{padding:25px 18px;margin:0}h1{font-size:28px}}@media print{body{background:white}main{margin:0;padding:0;max-width:none}h2{break-after:avoid}table,figure{break-inside:avoid}pre{background:#f0f3f5;color:#112d46}a{color:inherit}}"""
    return f"<!doctype html><html lang='ja'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{css}</style><main>" + "\n".join(rendered) + "</main></html>"


def render_pdf(text, output: Path, japanese=False, *, compact=False):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, Preformatted, KeepTogether

    if japanese:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        body_font = bold_font = "HeiseiKakuGo-W5"
    else:
        normal = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if normal.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("ReportBody", str(normal)))
            pdfmetrics.registerFont(TTFont("ReportBold", str(bold)))
            pdfmetrics.registerFontFamily("ReportBody", normal="ReportBody", bold="ReportBold")
            body_font, bold_font = "ReportBody", "ReportBold"
        else:
            body_font, bold_font = "Helvetica", "Helvetica-Bold"
    width = 7.0 * inch
    base = ParagraphStyle("body", fontName=body_font, fontSize=9.4 if not japanese else (9.5 if compact else 10),
                          leading=14.8 if not japanese else (15.8 if compact else 17), textColor=colors.HexColor("#213448"),
                          spaceAfter=8, wordWrap="CJK" if japanese else "LTR", allowWidows=0, allowOrphans=0)
    small = ParagraphStyle("table", parent=base, fontSize=7.7 if not japanese else 8.3,
                           leading=11.3, spaceAfter=0)
    hstyles = {1: ParagraphStyle("h1", parent=base, fontName=bold_font, fontSize=22,
                                 leading=30, spaceAfter=18, textColor=colors.HexColor("#123b54"), keepWithNext=True),
               2: ParagraphStyle("h2", parent=base, fontName=bold_font, fontSize=14.2,
                                 leading=21, spaceBefore=16, spaceAfter=8, textColor=colors.HexColor("#13665e"), keepWithNext=True),
               3: ParagraphStyle("h3", parent=base, fontName=bold_font, fontSize=11.5,
                                 leading=16, spaceBefore=10, spaceAfter=7, keepWithNext=True)}
    code_style = ParagraphStyle("code", fontName="Courier", fontSize=7.1, leading=10,
                               spaceBefore=5, spaceAfter=10, backColor=colors.HexColor("#f0f3f6"), borderPadding=7)
    def inline(text):
        if japanese:
            # CID Japanese fonts have reliable ASCII ket brackets; the source
            # Markdown/HTML retains the mathematical U+27E8/U+27E9 characters.
            text = text.replace("⟩", ">").replace("⟨", "<")
        rendered = inline_html(text)
        rendered = rendered.replace("<strong>", "<b>").replace("</strong>", "</b>")
        code_font = body_font if japanese else "Courier"
        code_size = "9.3" if japanese else "8"
        rendered = rendered.replace("<code>", f'<font name="{code_font}" size="{code_size}">').replace("</code>", "</font>")
        rendered = re.sub(r'<a href="([^"]+)">', r'<link href="\1" color="#126b86">', rendered).replace("</a>", "</link>")
        return rendered
    story = []
    for kind, value in blocks(text):
        if kind == "heading":
            level, label = value
            story.append(Paragraph(inline(label), hstyles[min(level, 3)]))
        elif kind in ("paragraph", "list"):
            story.append(Paragraph(inline(value), base))
        elif kind == "code":
            wrapped = "\n".join("\n".join(textwrap.wrap(line, width=108, replace_whitespace=False,
                                                     drop_whitespace=False) or [""]) for line in value.splitlines())
            story.append(Preformatted(html.escape(wrapped), code_style))
        elif kind == "table":
            count = len(value[0])
            if not all(len(row) == count for row in value):
                raise AssertionError(f"Unequal table cells: {value}")
            lengths = [max(9, min(35, max(len(row[i]) for row in value))) for i in range(count)]
            widths = [width * length / sum(lengths) for length in lengths]
            cells = [[Paragraph(inline(cell), small) for cell in row] for row in value]
            t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5f2ed")),
                                   ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#ced9df")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                   ("TOPPADDING", (0, 0), (-1, -1), 7),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
            story.extend([t, Spacer(1, 10)])
        elif kind == "image":
            alt, target = value
            from PIL import Image as PILImage
            path = (DOCS / target).resolve()
            w, h = PILImage.open(path).size
            scale = min(width/w, 400/h)
            story.extend([Image(str(path), width=w*scale, height=h*scale), Paragraph(inline(alt), small), Spacer(1, 12)])
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#b9d1d4")); canvas.line(54, 39, 558, 39)
        canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.HexColor("#52677b"))
        canvas.drawString(54, 25, "QUBLITZ 2026 | Quantum Minesweeper")
        canvas.drawRightString(558, 25, f"{doc.page}")
    document = SimpleDocTemplate(str(output), pagesize=(612, 792), leftMargin=54, rightMargin=54,
                                 topMargin=45, bottomMargin=53, title=output.stem,
                                 author="Quantum Minesweeper project", allowSplitting=True)
    document.build(story, onFirstPage=footer, onLaterPages=footer)


def generate_demo(sim, tests):
    records = {(r["level"], r["input"], r["injected_error"], r["error_location"]): r for r in sim["records"]}
    payload = {"repetition": {}, "classification": {}, "diagrams": {}, "interference": {}}
    for level in (1, 2, 3):
        for label in INPUTS:
            for error in permitted_errors(level):
                prep = preparation(label)
                stages = repetition_stages(prep, level, error)
                record = records[(level, label, error.pauli, error.location)]
                bits = tuple(record["observed_syndrome"])
                stages["measured"] = stages["extracted"].copy()
                circuit = stages["measured"].copy()
                recover_observed(circuit, level, bits)
                stages["recovered"] = circuit.copy()
                decode_repetition(circuit)
                stages["decoded"] = circuit.copy()
                circuit.compose(prep.inverse(), [0], inplace=True)
                stages["verification"] = circuit.copy()
                location = "none" if error.location is None else str(error.location)
                payload["repetition"][f"{level}|{label}|{location}"] = {
                    "stages": {name: terms(circuit) for name, circuit in stages.items()},
                    "syndrome": record["observed_syndrome"], "fidelity": record["ideal_state_fidelity"],
                    "shots": record["finite_shots"]["shots"],
                    "successes": round(record["finite_shots"]["shots"] * record["finite_shots"]["joint_success_rate"])}
        image_data = base64.b64encode((RESULTS / f"circuits/demo-L{level}.png").read_bytes()).decode()
        payload["diagrams"][str(level)] = "data:image/png;base64," + image_data
    for record in sim["records"]:
        if record["level"] == 4:
            loc = "none" if record["error_location"] is None else str(record["error_location"])
            key = f"{record['input']}|{record['injected_error']}|{loc}"
            payload["classification"][key] = record
    for label in ("+", "-"):
        circuit = preparation(label); circuit.h(0)
        payload["interference"][label] = list(Statevector.from_instruction(circuit).probabilities())
    assert len(payload["repetition"]) == 72 and len(payload["classification"]) == 78
    template = (ROOT / "scripts/demo-template.html").read_text()
    hardware_path = RESULTS / "iqm-hardware-analysis/analysis.json"
    badge = "IQM実機：このデモ作成時点で結果なし"
    section = ""
    footer = ("このデモは理想シミュレーションの説明用再生です。実機ジョブの操作はREADMEで確認してください。")
    if hardware_path.is_file():
        hardware = load(hardware_path)
        groups = hardware["variants"]
        before, after = (groups[v] for v in ("original", "improved"))
        badge = "IQM結果ファイル：2048ショットを収録"
        hardware_rows = []
        for pauli in ("I", "X", "Y", "Z"):
            pair = [next(row for row in group["cases"] if row["injected_error"] == pauli) for group in (before, after)]
            hardware_rows.append("<tr><td>" + pauli + "</td>" + "".join(
                f"<td>{round(row['classification_success_rate']*row['shots'])}/{row['shots']} = {100*row['classification_success_rate']:.2f}%</td>"
                for row in pair) + "</tr>")
        delta = hardware["changes_against_original"]["improved"]["change_percentage_points"]
        section = (f'<section id="hardware-results"><h2>5. 提供されたIQM実機結果</h2>'
                   f'<p>保存済みプロトコルの回路順に対応させると、分類成功率は '
                   f'<strong>{100*before["success_rate"]:.2f}% → {100*after["success_rate"]:.2f}%</strong>。'
                   f'差は<strong>+{delta:.2f}ポイント</strong>です。</p>'
                   '<p class="warning">元の送信記録は未提供です。回路の対応はRun Readyプロトコルからの再構成で、'
                   '実際の送信記録から独立確認できていません。</p>'
                   '<table><thead><tr><th>誤り</th><th>元の回路</th><th>改良回路</th></tr></thead><tbody>'
                   + "".join(hardware_rows) + '</tbody></table>'
                   '<p class="mini">全2048ショットを使用。読み出し補正・ポストセレクションなし。'
                   'これはシンドロームから種類を正しく当てた割合で、論理状態の忠実度ではありません。'
                   '今回のexportはキー順s0s1、Qiskit表示はs1s0。XとZの両方で確認します。</p>'
                   f'<p class="mini muted">提供ファイルのジョブID：{html.escape(hardware["job_id"])}。'
                   '詳しい根拠と95%区間はSUBMISSION_REPORT.pdfにあります。</p></section>')
        footer = ("上の状態ウォークスルーは理想シミュレーションです。実機結果の節は、提供されたIQM exportの分析です。"
                  "元の送信記録の再取得は新規ジョブを送りません。READMEのretrieve手順を使ってください。")
    template = template.replace("@@HARDWARE_BADGE@@", badge).replace("@@HARDWARE_SECTION@@", section)
    template = template.replace("@@HARDWARE_FOOTER@@", footer)
    template = template.replace("@@TEST_COUNT@@", str(tests["tests"] - tests["skipped"]))
    template = template.replace("@@DATA@@", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    (DOCS / "live-demo.html").write_text(template)


def main():
    sim = load(RESULTS / "simulation.json")
    tests = load(RESULTS / "test-outcome.json")
    assert sim["cases"] == 150 and sim["shots_per_case"] == 512, "Rebuild with the documented 150-case/512-shot benchmark"
    assert tests["returncode"] == 0
    for level in (1, 2, 3):
        label = "+" if level == 3 else "+i"
        circuit = repetition_experiment(preparation(label), level, Error({1:"X", 2:"Z", 3:"Y"}[level], 1))
        save_circuit(circuit, RESULTS / "circuits", f"level{level}")
    save_circuit(encoder_level4(), RESULTS / "circuits", "level4-encoder")
    save_circuit(level4_experiment(preparation("+i"), Error("Y", 1)), RESULTS / "circuits", "level4")
    report = generate_report(sim, tests)
    ja_path = DOCS / "BEGINNER_JA.md"
    ja = escape_table_kets(ja_path.read_text()); ja_path.write_text(ja)
    script = (DOCS / "PRESENTATION_EN.md").read_text()
    for name, text, japanese in [("RESULTS", report, False), ("BEGINNER_JA", ja, True), ("PRESENTATION_EN", script, False)]:
        (DOCS / f"{name}.html").write_text(render_html(text, name))
        render_pdf(text, DOCS / f"{name}.pdf", japanese)
    generate_demo(sim, tests)
    print("Built report, Japanese guide, English script (MD/HTML/PDF), five circuit diagrams and offline live demo.")


if __name__ == "__main__":
    main()

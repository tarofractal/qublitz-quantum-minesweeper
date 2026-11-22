"""Save exact pytest output, JUnit evidence and a machine-readable outcome."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
out=root/'results';out.mkdir(exist_ok=True)
command=[sys.executable,'-m','pytest','-q','--junitxml=results/pytest.xml']
completed=subprocess.run(command,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(out/'pytest.txt').write_text(completed.stdout)
print(completed.stdout)
suite=ET.parse(out/'pytest.xml').getroot()
totals={name:sum(int(node.get(name,'0')) for node in suite.iter('testsuite'))
        for name in ['tests','failures','errors','skipped']}
totals.update(created_at_utc=datetime.now(timezone.utc).isoformat(),returncode=completed.returncode,
              command='python scripts/run_tests.py',pytest_command='python -m pytest -q --junitxml=results/pytest.xml')
(out/'test-outcome.json').write_text(json.dumps(totals,indent=2)+'\n')
raise SystemExit(completed.returncode)

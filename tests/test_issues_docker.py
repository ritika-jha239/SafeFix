"""Opt-in integration: exercises actual Docker; no model or network calls."""
import os
import subprocess
from pathlib import Path
import pytest
from safefix.issues import RepoTools

@pytest.mark.skipif(os.getenv('SAFEFIX_DOCKER_TESTS')!='1',reason='Set SAFEFIX_DOCKER_TESTS=1 with prepared Docker runner')
def test_isolated_runner_red_to_green(tmp_path):
    tmp_path.chmod(0o755)
    (tmp_path/'maths.py').write_text('def total(n):\n    return sum(range(n))\n')
    (tmp_path/'test_maths.py').write_text('from maths import total\n\ndef test_sum():\n    assert total(5)==15\n')
    subprocess.run(['git','init',str(tmp_path)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(tmp_path),'add','.'],check=True)
    tools=RepoTools(tmp_path)
    tools.select_tests(['test_maths.py'])
    before=tools.run_tests()
    assert before['code']==1 and before['failures']==1 and before['executed']==1, before
    tools.write_file('maths.py','def total(n):\n    return sum(range(n + 1))\n')
    after=tools.run_tests()
    assert after['code']==0 and after['executed']==1 and not after['errors'], after

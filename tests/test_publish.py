from pathlib import Path
import shutil
import pytest
from safefix import publish as module
from safefix.agent import FIXES, ROOT

@pytest.fixture
def repository(tmp_path, monkeypatch):
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    demo = 'bug1_offbyone'
    shutil.copytree(ROOT / 'repos' / demo, checkout / 'repos' / demo)
    module.git(checkout, 'init', '-b', 'main')
    module.git(checkout, 'add', '.')
    module.git(checkout, '-c', 'user.name=Test', '-c', 'user.email=test@example.org', 'commit', '-m', 'Initial')
    remote = tmp_path / 'remote.git'
    module.git(tmp_path, 'init', '--bare', str(remote))
    module.git(checkout, 'remote', 'add', 'origin', str(remote))
    module.git(checkout, 'push', 'origin', 'main')
    monkeypatch.setattr(module, 'ROOT', checkout)
    monkeypatch.setattr(module, 'destination', lambda: (str(remote), 'https://github.com/test/demo'))
    source = (checkout / 'repos' / demo / 'solution.py').read_text()
    return checkout, remote, demo, source

def test_verified_publish_and_idempotency(repository):
    checkout, remote, demo, source = repository
    job_id = module.retain(demo, source, FIXES[demo])
    main = module.git(remote, 'rev-parse', 'refs/heads/main')
    result = module.publish(job_id)
    assert module.git(remote, 'show', result['branch'] + ':repos/' + demo + '/solution.py') == FIXES[demo].strip()
    assert module.git(remote, 'rev-parse', 'refs/heads/main') == main
    assert module.git(remote, 'diff', '--name-only', 'main', result['branch']) == 'repos/' + demo + '/solution.py'
    assert module.publish(job_id) == result
    assert (checkout / 'repos' / demo / 'solution.py').read_text() == source

def test_unverified_or_stale_rejected(repository):
    _, remote, demo, source = repository
    with pytest.raises(ValueError, match='expired'): module.publish('missing')
    stale = module.retain(demo, source + '# stale', FIXES[demo])
    with pytest.raises(ValueError, match='changed'): module.publish(stale)
    assert module.git(remote, 'for-each-ref', '--format=%(refname)', 'refs/heads') == 'refs/heads/main'

def test_failing_patch_is_not_pushed(repository):
    _, remote, demo, source = repository
    job_id = module.retain(demo, source, source)
    with pytest.raises(ValueError, match='tests did not pass'): module.publish(job_id)
    assert module.git(remote, 'for-each-ref', '--format=%(refname)', 'refs/heads') == 'refs/heads/main'

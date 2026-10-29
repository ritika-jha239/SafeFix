"""Reproduce a selected real issue in Docker without spending any model tokens."""
import argparse
import json
from pathlib import Path
import tempfile
from .issues import git,RepoTools,scientific_revision,IssueError
from .prepare_runner import PROFILES

CASES={
 '71755':('pandas-dev/pandas','pandas_71755.py'),
 '35143':('scikit-learn/scikit-learn','sklearn_35143.py'),
 '35195':('scikit-learn/scikit-learn','sklearn_35195.py'),
 '30874':('sympy/sympy','sympy_30874.py'),
 '30849':('sympy/sympy','sympy_30849.py'),
}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('issue',choices=CASES)
    args=parser.parse_args()
    repository,testfile=CASES[args.issue]
    image=PROFILES[repository][1]
    sha=scientific_revision(repository,image)
    with tempfile.TemporaryDirectory(prefix='safefix-evaluate-') as directory:
        root=Path(directory)/'checkout'
        git(directory,'clone','--depth=1','--quiet',f'https://github.com/{repository}.git',str(root))
        git(root,'fetch','--depth=1','origin',sha)
        git(root,'checkout','--detach','FETCH_HEAD')
        tools=RepoTools(root);tools.image=image
        regression=tools.add_regression((Path(__file__).parent.parent/'evaluations'/testfile).read_text())
        tools.select_tests([regression])
        result=tools.run_tests()
        print(json.dumps({'issue':f'https://github.com/{repository}/issues/{args.issue}',
                         'commit':sha,'model_calls':0,**result},indent=2))
        if result['errors'] or not result['executed']:
            raise SystemExit('Setup failed; no valid reproduction result.')
        print('REPRODUCED: regression fails on real source.' if result['code']==1 else 'NOT REPRODUCED: regression passes at this revision.')

if __name__=='__main__':
    try:main()
    except IssueError as e:raise SystemExit(str(e)) from None

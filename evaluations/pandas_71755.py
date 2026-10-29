"""Regression from pandas #71755; no repair code or model response."""
import pandas as pd
import pytest

@pytest.mark.parametrize('nested,max_level', [({1:'x'},1), ({'a':'x',1:'y'},1), ({1:{2:'x'}},3)])
def test_integer_mapping_keys_with_max_level(nested,max_level):
    data=[{'top':nested}]
    expected=pd.json_normalize(data).to_dict('records')
    assert pd.json_normalize(data,max_level=max_level).to_dict('records')==expected

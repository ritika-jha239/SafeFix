"""Regression from scikit-learn #35143."""
import numpy as np
import pytest
from sklearn.preprocessing import MinMaxScaler, MaxAbsScaler

@pytest.mark.parametrize('cls',[MinMaxScaler,MaxAbsScaler])
def test_nan_batch_preserves_previous_statistics(cls):
    a=np.array([[1.,10.],[3.,20.]])
    b=np.array([[np.nan,30.],[np.nan,40.]])
    batch=cls().fit(np.vstack([a,b]))
    incremental=cls().partial_fit(a).partial_fit(b)
    np.testing.assert_allclose(incremental.transform([[2.,25.]]),batch.transform([[2.,25.]]))

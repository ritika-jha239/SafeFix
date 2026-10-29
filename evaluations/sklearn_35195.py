"""Regression from scikit-learn #35195."""
import numpy as np
import sklearn
from sklearn.datasets import make_regression
from sklearn.ensemble import StackingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline

def test_pipeline_score_without_sample_weight():
    with sklearn.config_context(enable_metadata_routing=True):
        x,y=make_regression(n_samples=40,n_features=4,random_state=0)
        pipe=make_pipeline(StackingRegressor([('lr',LinearRegression())])).fit(x,y)
        assert np.isfinite(pipe.score(x,y))

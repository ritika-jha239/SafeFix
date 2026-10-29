"""Regression from SymPy #30874: constructing the expression must terminate."""
from sympy import symbols,evaluate,And,Eq,Add,Mul,I

def test_unevaluated_and_does_not_recurse():
    x=symbols('x')
    with evaluate(False):
        And(Eq(0,Add(x,Mul(-1,I))))

"""Regression from SymPy #30849."""
from sympy import symbols,nonlinsolve,FiniteSet,simplify

def test_exponential_real_solution_is_complete_and_valid():
    m,n=symbols('m n',real=True)
    equations=[2**m-2**(2*n),4*2**m-2**(4*n)]
    result=nonlinsolve(equations,m,n)
    assert result==FiniteSet((2,1))
    for solution in result:
        assert all(simplify(eq.subs({m:solution[0],n:solution[1]}))==0 for eq in equations)

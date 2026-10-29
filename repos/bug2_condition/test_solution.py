from solution import eligible

def test_eligible():
    assert eligible(18)
    assert not eligible(17)
    assert eligible(19)

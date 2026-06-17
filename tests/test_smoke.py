def test_package_imports():
    import pana
    assert isinstance(pana.__version__, str)

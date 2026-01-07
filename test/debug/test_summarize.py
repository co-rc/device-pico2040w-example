from debug.soft_break import _summarize
import math

def test_summarize_string():
    assert _summarize("hello") == "[str]: len=5 'hello'"
    assert _summarize("a" * 130, max_len=10) == "[str]: len=130 'aaaaaaaaaa'"

def test_summarize_bytes():
    assert _summarize(b"hello") == "[bytes]: len=5 b'hello'"
    assert _summarize(bytearray(b"abc")) == "[bytearray]: len=3 bytearray(b'abc')"

def test_summarize_collections():
    assert _summarize([1, 2, 3]) == "[list]: len=3"
    assert _summarize((1, 2)) == "[tuple]: len=2"

def test_summarize_dict():
    d = {"a": 1, "b": 2}
    assert _summarize(d) == "[dict]: len=2 keys=['a', 'b']"
    
    d_large = {str(i): i for i in range(15)}
    expected_keys = [str(i) for i in range(10)]
    assert _summarize(d_large) == f"[dict]: len=15 keys={expected_keys!r}"

def test_summarize_fallback():
    assert _summarize(123) == "[int]: 123"
    
    class LongRepr:
        def __repr__(self):
            return "X" * 200
    
    res = _summarize(LongRepr(), max_len=20)
    assert res.startswith("[LongRepr]: ")
    assert res.endswith("…")

def test_summarize_skipping():
    assert _summarize(math) is None
    
    class MyClass:
        pass
    assert _summarize(MyClass) is None
    
    def my_func():
        pass
    assert _summarize(my_func) is None
    assert _summarize(len) is None

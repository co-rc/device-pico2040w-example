from debug.soft_break import _format_bytes

def test_format_bytes():
    assert _format_bytes(106496) == "106.496 bytes"
    assert _format_bytes(1234567) == "  1.234.567 bytes"
    assert _format_bytes(123) == "123 bytes"
    assert _format_bytes(0) == "  0 bytes"
    assert _format_bytes(1000) == "  1.000 bytes"

if __name__ == "__main__":
    test_format_bytes()
    print("test_format_bytes PASSED")

from debug.time_utils import format_timestamp_ms, get_timestamp_ms, format_current_stamp

def test_format_time_ms():
    assert format_timestamp_ms(0) == "00:00.000"
    assert format_timestamp_ms(500) == "00:00.500"
    assert format_timestamp_ms(1000) == "00:01.000"
    assert format_timestamp_ms(60000) == "01:00.000"
    assert format_timestamp_ms(61500) == "01:01.500"
    assert format_timestamp_ms(3600000) == "60:00.000"

def test_get_timestamp_ms():
    ts = get_timestamp_ms()
    assert isinstance(ts, int)
    assert ts >= 0

def test_format_now():
    now_str = format_current_stamp()
    assert isinstance(now_str, str)
    assert ":" in now_str
    assert "." in now_str

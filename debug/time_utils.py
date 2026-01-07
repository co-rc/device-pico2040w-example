import time

try:
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
except (ImportError, AttributeError):
    ticks_ms = lambda: int(time.monotonic() * 1000)
    ticks_diff = lambda a, b: a - b


_t0 = ticks_ms()


def get_timestamp_ms():
    return ticks_diff(ticks_ms(), _t0)


def format_timestamp_ms(diff_time_ms):
    mm = diff_time_ms // 60000
    ss = (diff_time_ms // 1000) % 60
    ms = diff_time_ms % 1000
    return f"{mm:02d}:{ss:02d}.{ms:03d}"


def format_current_stamp():
    return format_timestamp_ms(get_timestamp_ms())

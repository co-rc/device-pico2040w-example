from collections import OrderedDict

import logging
from debug.time_utils import format_current_stamp

_bp_logger = logging.getLogger("<=>")

DBG = {}
_TAG_SEQ = {}

_BP_COMMANDS = OrderedDict((
    ("", ("continue", "continue", None)),
    ("l", ("locals", "print locals() (if provided)", lambda short, ctx: _print_map_summary(short + ":", ctx[short]))),
    ("g", ("globals", "print globals() (if provided)", lambda short, ctx: _print_map_summary(short + ":", ctx[short]))),
    ("p", ("DBG", "print DBG snapshot", lambda short, ctx: _print_map_summary(short + ":", ctx[short]))),
    ("m", ("meminfo", "print memory info", lambda _short, _ctx: _print_memory_info())),
    ("s", ("strings", "qstr_info", lambda _short, _ctx: _print_qstr_info())),
    ("x", ("gc", "perform gc", lambda _short, _ctx: _perform_gc())),
    ("h", ("help", "help", lambda _short, _ctx: print(_BP_HELP_TEXT))),
))

_BP_PROMPT_KEYS = ", ".join(
    f"{('enter' if cmd == '' else cmd)}={short}"
    for cmd, (short, _desc, _action) in _BP_COMMANDS.items())

_BP_HELP_TEXT = "commands:\n" + "\n".join(
    f"  {('enter' if cmd == '' else cmd):10} {desc}"
    for cmd, (_short, desc, _action) in _BP_COMMANDS.items())


def _next_seq(tag):
    next_value = _TAG_SEQ.get(tag, 0) + 1
    _TAG_SEQ[tag] = next_value
    return next_value


# noinspection PyBroadException
def _summarize(value, max_len=120):
    try:
        type_name = type(value).__name__
    except Exception:
        type_name = "<?>"

    prefix = f"[{type_name}]:"

    if type_name in ("module", "type", "function", "bound_method", "builtin_function_or_method", "method"):
        return None

    try:
        if isinstance(value, (str, bytes, bytearray)):
            preview = value[:max_len]
            return f"{prefix} len={len(value)} {preview!r}"
        if isinstance(value, (list, tuple)):
            return f"{prefix} len={len(value)}"
        if isinstance(value, dict):
            keys = list(value.keys())
            return f"{prefix} len={len(value)} keys={keys[:10]!r}"
    except Exception:
        pass

    try:
        text = repr(value)
        if len(text) > max_len:
            text = text[:max_len] + "…"
        return f"{prefix} {text}"
    except Exception:
        return prefix.rstrip(":")


# noinspection PyBroadException
def _print_map_summary(title, mapping, limit=60):
    if mapping is None:
        print(f"{title} <not provided>")
        return

    print(title)
    printed = 0
    for key in sorted(mapping.keys()):
        if key.startswith("_"):
            continue
        if key in ("DBG", "_TAG_SEQ"):
            continue
        try:
            value = mapping[key]
            summary = _summarize(value)
            if summary is None:
                continue
            print(f"  {key} {summary}")
            printed += 1
            if printed >= limit:
                print("  …")
                break
        except Exception:
            print(f"  {key} <unprintable>")


def _format_bytes(value):
    s = str(value)
    result = []
    while s:
        part = s[-3:]
        if len(part) < 3:
            part = " " * (3 - len(part)) + part
        result.append(part)
        s = s[:-3]
    return ".".join(reversed(result)) + " bytes"


# noinspection PyBroadException
def _print_mem_status(title=None):
    import gc
    if getattr(gc, "mem_free", None) and getattr(gc, "mem_alloc", None):
        if title:
            print(title)
        mem_free = gc.mem_free()
        mem_alloc = gc.mem_alloc()
        mem_total = mem_free + mem_alloc
        print(f"  Mem free:\t{_format_bytes(mem_free)}, {(mem_free * 100) // mem_total}%")
        print(f"  Mem alloc:\t{_format_bytes(mem_alloc)}")
        print(f"  Mem total:\t{_format_bytes(mem_total)}")


def _print_deep_mem_info(title=None):
    import micropython
    if getattr(micropython, "mem_info", None) and getattr(micropython, "qstr_info", None):
        if title:
            print(title)
        micropython.mem_info()
        print()
        micropython.qstr_info()


def _print_fs_status(title=None):
    import os
    if getattr(os, "statvfs", None):
        if title:
            print(title)
        os.statvfs("/")
        stats = os.statvfs("/")
        block_size = stats[0]
        fs_free = block_size * stats[3]
        fs_total = block_size * stats[2]
        fs_allocated = fs_total - fs_free
        print(f"  FS free:\t{_format_bytes(fs_free)}, {(fs_free * 100) // fs_total}%")
        print(f"  FS allocated:\t{_format_bytes(fs_allocated)}")
        print(f"  FS total:\t{_format_bytes(fs_total)}")


def _print_qstr_info(title=None):
    import micropython
    if getattr(micropython, "qstr_info", None):
        if title:
            print(title)
        micropython.qstr_info(True)


def _print_memory_info():
    _print_mem_status()
    print()
    _print_fs_status()
    print()
    _print_deep_mem_info()
    print()


def _perform_gc():
    import gc
    _print_mem_status("before gc")
    gc.collect()
    _print_mem_status("after gc")


# noinspection PyArgumentList
def bp(tag, *, predicate=lambda: True, predicate_arg=None, with_log=False, locals_map=None, globals_map=None, **kw):
    sequence = _next_seq(tag)

    try:
        try:
            should_break = predicate(tag, sequence)
        except TypeError:
            try:
                should_break = predicate(predicate_arg)
            except TypeError:
                should_break = predicate()
    except Exception as exc:
        should_break = True
        kw = dict(kw)
        kw["predicate_error"] = repr(exc)

    if with_log:
        _bp_logger.info(f"inspect point: {tag} #{sequence}")

    if not should_break:
        return

    DBG.clear()
    DBG.update(kw)
    _print_map_summary("DBG:", DBG)

    ctx = {"locals": locals_map,
           "globals": globals_map,
           "DBG": DBG}
    prompt = f"inspect point: {tag} #{sequence} @{format_current_stamp()}> [{_BP_PROMPT_KEYS}] "

    while True:
        command = input(prompt).strip()[:1].lower()
        if not command:
            return

        entry = _BP_COMMANDS.get(command)
        if not entry:
            continue

        short, _desc, action = entry
        if action:
            action(short, ctx)

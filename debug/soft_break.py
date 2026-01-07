import logging

from debug.time_utils import format_current_stamp

_bp_logger = logging.getLogger(" BP")

DBG = {}
_TAG_SEQ = {}

_BP_COMMANDS = [
    ("Enter", "continue", "continue"),
    ("l", "locals", "print locals() (if provided)"),
    ("g", "globals", "print globals() (if provided)"),
    ("p", "DBG", "print DBG snapshot"),
    ("h", "help", "help"),
]


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
        _bp_logger.info(f"bp: {tag}#{sequence} @{format_current_stamp()}")

    if not should_break:
        return

    DBG.clear()
    DBG.update(kw)
    _print_map_summary("DBG:", DBG)

    commands = _BP_COMMANDS

    prompt_parts = [f"{cmd}={short}" if short else cmd for cmd, short, desc in commands]
    prompt = f"bp: {tag}#{sequence} @{format_current_stamp()}> [{', '.join(prompt_parts)}] "

    while True:
        command = input(prompt).strip()[:1].lower()

        if not command:
            return

        if command == "l":
            _print_map_summary("locals:", locals_map)
            continue

        if command == "g":
            _print_map_summary("globals:", globals_map)
            continue

        if command == "p":
            _print_map_summary("DBG:", DBG)
            continue

        if command == "h":
            print("commands:")
            for cmd, short, desc in commands:
                print(f"  {cmd.split('/')[0]:10} {desc}")
            continue

        print("unknown command:", command)

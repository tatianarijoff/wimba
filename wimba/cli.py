"""WIMBA command-line interface.

Subcommands:
  wimba setup    locate IW2D / pytlwall and write the config file
  wimba status   show which external tools WIMBA can find
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import config as cfg


def _auto_iw2d():
    for name in ("IW2D", "iw2d"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _ask(prompt, default):
    suffix = f" [{default}]" if default else " [skip]"
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def cmd_setup(args):
    interactive = sys.stdin.isatty() and not args.non_interactive
    data = cfg.load_config()
    tools = data.setdefault("tools", {})

    # IW2D: an external binary
    iw2d = args.iw2d or _auto_iw2d()
    if interactive and not args.iw2d:
        iw2d = _ask("Path to the IW2D binary (empty if you don't use IW2D)", iw2d)
    if iw2d:
        tools["iw2d"] = {"binary": str(Path(iw2d).expanduser())}

    # pytlwall: a Python package (path only needed for a non-installed checkout)
    if args.pytlwall_path:
        tools.setdefault("pytlwall", {})["path"] = str(Path(args.pytlwall_path).expanduser())
    elif interactive and not cfg.pytlwall_available():
        ans = _ask("Path to a pytlwall checkout (empty if pip-installed or unused)", None)
        if ans:
            tools.setdefault("pytlwall", {})["path"] = str(Path(ans).expanduser())

    path = cfg.save_config(data)
    print(f"Wrote {path}\n")
    return cmd_status(args)


def cmd_build(args):
    from .builders import load_machine
    from .store import materialize, ResultStore

    machine, freqs, times = load_machine(args.config)
    materialize(machine, args.out, freqs=freqs, times=times)
    store = ResultStore(args.out)

    print(f"Built '{args.config}' -> {args.out}")
    for g in store.groups():
        els = store.elements(g)
        print(f"  group '{g}': {len(els)} element(s) [{', '.join(els)}]")
    n_add = len(store.manifest.get("additional", []))
    if n_add:
        print(f"  additional: {n_add} element(s)")
    nf = 0 if freqs is None else len(freqs)
    nt = 0 if times is None else len(times)
    print(f"  grid: {nf} frequencies, {nt} times")
    return 0


def cmd_show(args):
    from .store import ResultStore

    store = ResultStore(args.results)
    print(f"Results in {args.results}")
    sections = list(store.manifest["groups"].items())
    if store.manifest.get("additional"):
        sections.append(("additional", store.manifest["additional"]))
    for name, records in sections:
        print(f"  {name}:")
        for rec in records:
            terms = sorted({e["term"] for e in rec["terms"]})
            origins = sorted({e["origin"] for e in rec["terms"]})
            weight = "pre-weighted" if rec.get("pre_weighted") else \
                f"beta=({rec.get('beta_x')}, {rec.get('beta_y')})"
            print(f"    {rec['name']}: terms[{', '.join(terms)}] "
                  f"origins[{', '.join(origins)}] {weight}")
    return 0


def cmd_status(args):
    s = cfg.tool_status()
    print("WIMBA external tools")
    print(f"  config file        : {s['config_file']} "
          f"({'found' if s['config_exists'] else 'not created yet'})")
    print(f"  IW2D binary        : {s['iw2d_binary'] or 'not configured'}")
    print(f"  pytlwall importable: {'yes' if s['pytlwall_available'] else 'no'}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wimba",
                                     description="WIMBA command-line interface")
    sub = parser.add_subparsers(dest="command")

    sp = sub.add_parser("setup", help="locate IW2D / pytlwall and write the config")
    sp.add_argument("--iw2d", metavar="PATH", help="path to the IW2D binary")
    sp.add_argument("--pytlwall-path", metavar="PATH",
                    help="path to a pytlwall checkout (if not pip-installed)")
    sp.add_argument("--non-interactive", action="store_true",
                    help="do not prompt; use flags and auto-detection only")
    sp.set_defaults(func=cmd_setup)

    st = sub.add_parser("status", help="show which external tools WIMBA can find")
    st.set_defaults(func=cmd_status)

    bp = sub.add_parser("build", help="build a machine from a YAML config and write per-element results")
    bp.add_argument("config", help="path to the machine YAML config")
    bp.add_argument("--out", default="results", help="output directory (default: results)")
    bp.set_defaults(func=cmd_build)

    sh = sub.add_parser("show", help="summarise a materialised results directory")
    sh.add_argument("results", help="path to a results directory")
    sh.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

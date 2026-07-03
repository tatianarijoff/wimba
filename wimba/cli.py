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
    from .builders import load_project
    from .store import materialize, ResultStore

    project = load_project(args.config)
    cfg_dir = Path(args.config).parent
    if args.out:
        out = args.out
    elif project.output:
        out = project.output
        if not Path(out).is_absolute():
            out = str(cfg_dir / out)
    else:
        out = str(cfg_dir / project.name / "output")
    resume = materialize(project, out)
    store = ResultStore(out)

    print(f"Built '{project.name}' from '{args.config}' -> {out}/")
    print(f"  resume: {resume.name}")
    for g in store.groups():
        els = store.elements(g)
        print(f"  group '{g}': {len(els)} element(s) [{', '.join(els)}]")
    n_add = len(store.resume.get("additional", []))
    if n_add:
        print(f"  additional: {n_add} element(s)")
    print(f"  components: {', '.join(store.resume.get('components', []))}")
    print(f"  totals in {out}/total/")
    return 0


def cmd_run(args):
    from .run import run

    plot = args.plot.split(",") if args.plot else None
    info = run(args.config, out_dir=args.out, plot=plot, part=args.part)
    st = info["stats"]
    print(f"Ran '{args.config}': {info['n_rows']} assignment(s) -> {info['out']}/")
    print(f"  computed: {st['computed']} | skipped: {st['skipped']} "
          f"| distinct geometries: {st['geometries']}")
    print(f"  total: {info['out']}/single_elements/total.csv")
    if info["plot"]:
        print(f"  plot:  {info['plot']}")
    return 0


def cmd_plot(args):
    from pathlib import Path
    from .plotting import plot_totals

    components = args.components.split(",") if args.components else None
    out = args.out or str(Path(args.totals).with_suffix(".png"))
    path = plot_totals(args.totals, components=components, part=args.part, save=out)
    which = ", ".join(components) if components else "all components"
    print(f"Plotted {which} ({args.part}) -> {path}")
    return 0


def cmd_assemble(args):
    from pathlib import Path
    from .assembly import load_assembly, write_csv

    result = load_assembly(args.config)
    out_dir = Path(args.out) if args.out else Path(args.config).parent
    path = write_csv(result, out_dir / f"{result.name}_assignments.csv")

    devices = sum(1 for r in result.rows if r.kind == "device")
    pipes = len(result.rows) - devices
    print(f"Assembled '{result.name}': {len(result.rows)} contribution(s) -> {path}")
    print(f"  devices: {devices} | default_pipe rows: {pipes}")
    if result.collisions:
        print(f"  collisions: {len(result.collisions)}")
        for c in result.collisions[:10]:
            tag = "intentional" if c.intentional else "ERROR"
            print(f"    s={c.position:.3f} m: {', '.join(c.names)}  [{tag}]")
    else:
        print("  collisions: none")
    return 0


def cmd_show(args):
    from .store import ResultStore

    store = ResultStore(args.results)
    r = store.resume
    print(f"Project '{r.get('name')}'  (grid: {r.get('grid')})")
    print(f"  components: {', '.join(r.get('components', []))}")
    sections = list(r["groups"].items())
    if r.get("additional"):
        sections.append(("additional", r["additional"]))
    for name, records in sections:
        print(f"  {name}:")
        for rec in records:
            comps = sorted(rec.get("impedance", {})) + sorted(rec.get("wake", {}))
            print(f"    {rec['name']}: optics{dict(rec['optics'])} "
                  f"info{dict(rec['info'])} origin={rec['origin']}")
            print(f"        computed: {', '.join(comps)}")
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
    bp.add_argument("--out", default=None, help="output directory (default: <name>_output)")
    bp.set_defaults(func=cmd_build)

    rn = sub.add_parser("run", help="assemble, compute, write the total and optional plot")
    rn.add_argument("config", help="path to the assembly YAML coordinator")
    rn.add_argument("--out", default=None, help="output directory (default: <name>_output)")
    rn.add_argument("--plot", default=None, help="components to plot, e.g. ZLong,ZDipX")
    rn.add_argument("--part", default="abs", choices=["abs", "re", "im"])
    rn.set_defaults(func=cmd_run)

    pl = sub.add_parser("plot", help="plot machine totals from a totals CSV")
    pl.add_argument("totals", help="path to a single_elements/total.csv")
    pl.add_argument("--components", default=None, help="comma-separated, e.g. ZLong,ZDipX")
    pl.add_argument("--part", default="abs", choices=["abs", "re", "im"])
    pl.add_argument("--out", default=None, help="output image (default: <totals>.png)")
    pl.set_defaults(func=cmd_plot)

    ap = sub.add_parser("assemble", help="assemble impedance assignments from optics + device files")
    ap.add_argument("config", help="path to the assembly YAML coordinator")
    ap.add_argument("--out", default=None, help="output directory (default: next to the config)")
    ap.set_defaults(func=cmd_assemble)

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

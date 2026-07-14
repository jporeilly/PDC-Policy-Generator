"""
cli.py — the Policy Generator's command line.

    python -m policy_generator author <registry.json> [-o out/] [--prefix CSCU] [--zip out.zip]
    python -m policy_generator info   <registry.json>

`author` turns the Registry's detection seeds into importable PDC Data
Identification files; `info` prints the contract summary (concepts, seeds,
resolved term ids, governed tags) so you can see what a Registry carries
before authoring.
"""
from __future__ import annotations
import argparse, io, sys

from . import __version__, author as author_mod, registry as registry_mod


def _resolve_registry(path):
    """The given path, or the newest auto-discovered Registry (a co-located
    Glossary checkout: nested ~/PDC-Demo clone, sibling repo, or
    POLICY_REGISTRY_DIR) when none was given."""
    if path:
        return path
    found = registry_mod.discover_registries()
    if not found:
        raise registry_mod.RegistryError(
            "no registry given and none found — pass a path, or clone this repo "
            "beside/inside the Glossary checkout, or set POLICY_REGISTRY_DIR")
    print(f"using {found[0]} (auto-discovered, newest of {len(found)})")
    return found[0]


def _cmd_info(args):
    reg = registry_mod.load_registry(_resolve_registry(args.registry))
    s = registry_mod.summary(reg)
    print(f"Classification Registry — {s['glossary']} (glossary_id: {s['glossary_id'] or 'unresolved'})")
    print(f"  concepts:            {s['concepts']}")
    print(f"  with detection seeds:{s['seeded']:>5}")
    print(f"  resolved term ids:   {s['resolved_term_ids']:>5}"
          + ("" if s["resolved_term_ids"] else "   (import the glossary in PDC and run Resolve, then re-export)"))
    print(f"  governed tags:       {s['governed_tags']:>5}")
    if s["off_vocabulary"]:
        print(f"  ⚠ concepts with off-vocabulary tags: {s['off_vocabulary']} — drift risk, fix in the Glossary app")
    return 0


def _cmd_author(args):
    reg = registry_mod.load_registry(_resolve_registry(args.registry))
    art = author_mod.author(reg, prefix=args.prefix)
    np, nd, ns = len(art["patterns"]), len(art["dictionaries"]), len(art["skipped"])
    if args.zip:
        with io.open(args.zip, "wb") as f:
            f.write(author_mod.to_zip_bytes(art))
        print(f"authored {np} pattern(s) + {nd} dictionar{'y' if nd == 1 else 'ies'} -> {args.zip}")
    else:
        written = author_mod.write_out(art, args.out)
        print(f"authored {np} pattern(s) + {nd} dictionar{'y' if nd == 1 else 'ies'} -> {args.out} ({len(written)} files)")
    if ns:
        print(f"skipped {ns} concept(s) without seeds:")
        for x in art["skipped"][:15]:
            print(f"  - {x['term']}: {x['why']}")
        if ns > 15:
            print(f"  … and {ns - 15} more")
    unresolved = registry_mod.unresolved_terms(reg)
    if unresolved:
        print(f"note: {len(unresolved)} term(s) have no term_id yet — rules bind by NAME until "
              "the glossary is imported and Resolve backfills the Registry.")
    return 0


def main(argv=None):
    # Windows consoles often run cp1252 — never let a glyph kill the CLI
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="policy_generator",
                                 description="PDC Policy Generator — Registry -> Data Identification")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="print what a Registry carries")
    p.add_argument("registry", nargs="?", default=None,
                   help="registry file (default: newest auto-discovered from a co-located Glossary checkout)")
    p.set_defaults(fn=_cmd_info)

    p = sub.add_parser("author", help="emit importable pattern/dictionary files from the Registry")
    p.add_argument("registry", nargs="?", default=None,
                   help="registry file (default: newest auto-discovered from a co-located Glossary checkout)")
    p.add_argument("-o", "--out", default="out", help="output directory (default: out/)")
    p.add_argument("--prefix", default=None, help="rule-name prefix (default: first word of the glossary name)")
    p.add_argument("--zip", default=None, help="write one zip instead of a directory")
    p.set_defaults(fn=_cmd_author)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except registry_mod.RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from agent_diagrams.renderers.images import (
    CONTAINER_ENGINES,
    DEFAULT_IMAGE,
    MERMAID_RUNTIMES,
    extract_mermaid_block,
    render_mermaid_image,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", type=Path, help="Input file (.mmd/.md/.txt).")
    ap.add_argument("--text", type=str, help="Mermaid text (or Markdown containing ```mermaid block).")
    ap.add_argument("--outdir", type=Path, default=Path("diagrams_out"))
    ap.add_argument("--name", type=str, default="diagram")
    ap.add_argument("--svg", action="store_true")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--theme", type=str, help="Optional theme override (default/dark/forest/neutral).")
    ap.add_argument("--background", type=str, default="transparent", help="transparent or white, etc.")
    ap.add_argument("--image", type=str, default=DEFAULT_IMAGE, help="Mermaid CLI container image.")
    ap.add_argument("--runtime", choices=MERMAID_RUNTIMES, default="auto")
    ap.add_argument("--container-engine", choices=CONTAINER_ENGINES, default="auto")
    args = ap.parse_args()

    if not args.svg and not args.png:
        args.svg = True
        args.png = True

    if not args.infile and not args.text:
        raise SystemExit("Provide either --infile or --text")

    args.outdir.mkdir(parents=True, exist_ok=True)

    raw = args.infile.read_text(encoding="utf-8") if args.infile else args.text
    mermaid = extract_mermaid_block(raw)
    staged_in = (args.outdir / f"{args.name}.mmd").resolve()
    staged_in.write_text(mermaid, encoding="utf-8")

    try:
        if args.svg:
            out_svg = (args.outdir / f"{args.name}.svg").resolve()
            render_mermaid_image(
                staged_in,
                out_svg,
                image=args.image,
                background=args.background,
                theme=args.theme,
                runtime=args.runtime,
                container_engine=args.container_engine,
            )
            print(f"Wrote {out_svg}")

        if args.png:
            out_png = (args.outdir / f"{args.name}.png").resolve()
            render_mermaid_image(
                staged_in,
                out_png,
                image=args.image,
                background=args.background,
                theme=args.theme,
                runtime=args.runtime,
                container_engine=args.container_engine,
            )
            print(f"Wrote {out_png}")
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

DEFAULT_IMAGE = "minlag/mermaid-cli:latest"


def extract_mermaid_block(text: str) -> str:
    fence = "```mermaid"
    if fence in text:
        start = text.index(fence) + len(fence)
        end = text.index("```", start)
        return text[start:end].strip()
    return text.strip()


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        command = shlex.join(cmd)
        raise RuntimeError(
            "Mermaid image render command failed\n"
            f"command: {command}\n"
            f"exit_code: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )


def render_mermaid_image(
    mermaid_path: Path,
    output_path: Path,
    *,
    image: str = DEFAULT_IMAGE,
    background: str = "transparent",
    theme: str | None = None,
) -> Path:
    mermaid_path = mermaid_path.resolve()
    output_path = output_path.resolve()

    mount_dir = output_path.parent
    if mermaid_path.parent != mount_dir:
        raise ValueError(
            "Mermaid source and image output must use the same directory for docker mounting: "
            f"source={mermaid_path.parent} output={mount_dir}"
        )

    cmd = [
        "docker",
        "run",
        "--rm",
        "-u",
        "1000:1000",
        "-v",
        f"{mount_dir}:/data",
        image,
        "-i",
        f"/data/{mermaid_path.name}",
        "-o",
        f"/data/{output_path.name}",
        "-b",
        background,
    ]
    if theme:
        cmd += ["-t", theme]

    _run(cmd)
    return output_path

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

DEFAULT_IMAGE = "ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0"
MERMAID_RUNTIMES = ("auto", "native", "container")
CONTAINER_ENGINES = ("auto", "docker", "podman")


def extract_mermaid_block(text: str) -> str:
    fence = "```mermaid"
    if fence in text:
        start = text.index(fence) + len(fence)
        end = text.index("```", start)
        return text[start:end].strip()
    return text.strip()


def _run(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True)
    except FileNotFoundError as exc:
        command = shlex.join(cmd)
        raise RuntimeError(
            "Mermaid image render executable was not found\n"
            f"command: {command}\n"
            f"executable: {cmd[0]}"
        ) from exc
    if proc.returncode != 0:
        command = shlex.join(cmd)
        raise RuntimeError(
            "Mermaid image render command failed\n"
            f"command: {command}\n"
            f"exit_code: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )


def _resolve_container_engine(requested: str) -> str:
    if requested not in CONTAINER_ENGINES:
        raise ValueError(
            f"Unsupported container engine '{requested}'. "
            f"Choose one of: {', '.join(CONTAINER_ENGINES)}."
        )

    if requested != "auto":
        if shutil.which(requested):
            return requested
        raise RuntimeError(
            f"Requested container engine '{requested}' was not found in PATH."
        )

    for candidate in ("docker", "podman"):
        if shutil.which(candidate):
            return candidate

    raise RuntimeError(
        "No supported container engine was found in PATH. Install Docker or Podman, "
        "or install mermaid-cli and use --mermaid-runtime native."
    )


def _host_user() -> tuple[int, int]:
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    return (
        getuid() if getuid is not None else 1000,
        getgid() if getgid is not None else 1000,
    )


def _native_command(
    mermaid_path: Path,
    output_path: Path,
    *,
    background: str,
    theme: str | None,
) -> list[str]:
    if not shutil.which("mmdc"):
        raise RuntimeError(
            "Native Mermaid rendering requested, but 'mmdc' was not found in PATH. "
            "Install @mermaid-js/mermaid-cli or use --mermaid-runtime container."
        )

    cmd = [
        "mmdc",
        "-i",
        str(mermaid_path),
        "-o",
        str(output_path),
        "-b",
        background,
    ]
    if theme:
        cmd += ["-t", theme]

    puppeteer_config = os.environ.get("MERMAID_PUPPETEER_CONFIG")
    if puppeteer_config:
        cmd += ["-p", puppeteer_config]
    return cmd


def _container_command(
    mermaid_path: Path,
    output_path: Path,
    *,
    image: str,
    background: str,
    theme: str | None,
    container_engine: str,
) -> list[str]:
    mount_dir = output_path.parent
    if mermaid_path.parent != mount_dir:
        raise ValueError(
            "Mermaid source and image output must use the same directory for container mounting: "
            f"source={mermaid_path.parent} output={mount_dir}"
        )

    engine = _resolve_container_engine(container_engine)
    uid, gid = _host_user()
    volume = f"{mount_dir}:/data"
    cmd = [engine, "run", "--rm"]
    if engine == "podman":
        cmd += ["--userns=keep-id"]
        volume += ":Z"
    cmd += [
        "-u",
        f"{uid}:{gid}",
        "-v",
        volume,
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
    return cmd


def render_mermaid_image(
    mermaid_path: Path,
    output_path: Path,
    *,
    image: str = DEFAULT_IMAGE,
    background: str = "transparent",
    theme: str | None = None,
    runtime: str = "auto",
    container_engine: str = "auto",
) -> Path:
    mermaid_path = mermaid_path.resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if runtime not in MERMAID_RUNTIMES:
        raise ValueError(
            f"Unsupported Mermaid runtime '{runtime}'. "
            f"Choose one of: {', '.join(MERMAID_RUNTIMES)}."
        )

    selected_runtime = runtime
    if selected_runtime == "auto":
        selected_runtime = "native" if shutil.which("mmdc") else "container"

    if selected_runtime == "native":
        cmd = _native_command(
            mermaid_path,
            output_path,
            background=background,
            theme=theme,
        )
    else:
        cmd = _container_command(
            mermaid_path,
            output_path,
            image=image,
            background=background,
            theme=theme,
            container_engine=container_engine,
        )

    _run(cmd)
    return output_path

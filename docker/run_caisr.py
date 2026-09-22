"""Headless orchestrator for the official CAISR docker pipeline.

This mirrors the contract of github.com/bdsp-core/CAISR-App ``caisr.py`` exactly,
so once the official images are present (``docker load`` of the release
``*.tar.gz``) an EDF/H5 upload is scored with the real CAISR models:

  * image names are ``caisr_{task}:latest`` (matched loosely on repository);
  * missing images are loaded from ``<dockers>/{task}.tar.gz``;
  * each task container mounts the host ``data/`` dir at ``/data/data/`` and the
    host ``caisr_output/`` dir at ``/data/caisr_output/`` (with the Windows path
    transform Docker Desktop expects);
  * per-task ``run_parameters/{task}.csv`` files are written with the same
    defaults CAISR uses (preprocess: overwrite=False + autoscale_signals=True;
    resp: multiprocess=True; all others: overwrite=True).

It is dependency-free (no pandas / docker SDK) so it runs in the API venv.

Expected work-dir layout (created by the API before calling this):
    <work>/data/raw/<recording>.edf|.h5
    <work>/caisr_output/
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys

TASKS = ["preprocess", "stage", "arousal", "resp", "limb", "report"]
INTERMEDIATE_TASKS = {"stage", "arousal", "resp", "limb"}

# Container-side paths. The host data/ dir is mounted at /data/data and the host
# caisr_output/ dir at /data/caisr_output (see _mounts).
CONTAINER_DATA = "/data/data"
CONTAINER_PARAMS = "/data/data/run_parameters"
# The four model scripts write to <out>/{task}/, and report reads them back from
# caisr_output/intermediate/{task}/ — so point the model tasks at .../intermediate.
CONTAINER_INTERMEDIATE = "/data/caisr_output/intermediate"

# Optional GPU passthrough. CAISR's own caisr.py does not add --gpus (the bundled
# TF builds are pinned to older CUDA), so default off; enable with CAISR_GPU=1.
GPU_FLAG = os.environ.get("CAISR_GPU", "0")


def _installed_repos() -> set[str]:
    try:
        res = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return set()
    return {line.strip() for line in res.stdout.splitlines() if line.strip()}


def _match_image(task: str, installed: set[str]) -> str | None:
    """Return the image ref for a task if installed (repo == caisr_{task})."""
    want = f"caisr_{task}"
    if f"{want}:latest" in installed:
        return f"{want}:latest"
    for ref in installed:
        if ref.split(":")[0] == want:
            return ref
    return None


def _ensure_image(task: str, dockers_dir: str, installed: set[str]) -> str:
    ref = _match_image(task, installed)
    if ref:
        return ref
    tarball = os.path.join(dockers_dir, f"{task}.tar.gz")
    if not os.path.exists(tarball):
        raise SystemExit(
            f"CAISR image 'caisr_{task}' is not installed and no tarball was found at "
            f"{tarball}. Load the official image first: docker load -i caisr_{task}.tar.gz"
        )
    print(f"[caisr] loading caisr_{task} from {tarball}…", flush=True)
    subprocess.run(["docker", "load", "-i", tarball], check=True)
    ref = _match_image(task, _installed_repos())
    if not ref:
        raise SystemExit(f"CAISR image for '{task}' still not found after docker load")
    return ref


def set_run_parameters(data_folder: str, tasks: list[str]) -> None:
    """Write run_parameters/{task}.csv matching CAISR-App defaults."""
    param_folder = os.path.join(data_folder, "run_parameters")
    os.makedirs(param_folder, exist_ok=True)
    for task in tasks:
        cols: dict[str, str] = {"overwrite": "True"}
        if task == "preprocess":
            cols = {"overwrite": "False", "autoscale_signals": "True"}
        elif task == "resp":
            cols = {"overwrite": "True", "multiprocess": "True"}
        header = ",".join(cols.keys())
        row = ",".join(cols.values())
        with open(os.path.join(param_folder, f"{task}.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(header + "\n" + row + "\n")


def _mounts(data_folder: str, output_folder: str) -> tuple[list[str], str, str]:
    data_folder = os.path.abspath(data_folder)
    output_folder = os.path.abspath(output_folder)
    if platform.system().lower() == "windows":
        d = data_folder.replace("\\", "/").replace(":", "")
        o = output_folder.replace("\\", "/").replace(":", "")
        data_mount = f"/{d[0]}{d[1:]}:/data/data/"
        output_mount = f"/{o[0]}{o[1:]}:/data/caisr_output/"
        base = ["docker", "run", "--rm"]
    else:
        data_mount = f"{data_folder}:/data/data/"
        output_mount = f"{output_folder}:/data/caisr_output/"
        base = ["docker", "run", "--rm"]  # no -t: headless (no TTY)
    return base, data_mount, output_mount


def _activate(task: str) -> str:
    """Shell snippet that activates the task's bundled python environment.

    stage uses a conda env (activated via ~/.bashrc); the others use a venv.
    """
    if task == "stage":
        return "source ~/.bashrc"
    return f"source /caisr_{task}/bin/activate"


def _script_args(task: str) -> str:
    """CLI args the (updated) caisr_{task}.py scripts require.

    The images' ENTRYPOINT runs the scripts with no args, but the current
    scripts require them, so we override the entrypoint and pass them here.
    """
    common = (
        f"--input_data_dir {CONTAINER_DATA} "
        f"--output_csv_dir {CONTAINER_INTERMEDIATE} "
        f"--param_dir {CONTAINER_PARAMS}"
    )
    if task == "stage":
        return f"{common} --model_dir /data/stage/models/"
    return common


def run_task(image: str, task: str, data_folder: str, output_folder: str) -> None:
    base, data_mount, output_mount = _mounts(data_folder, output_folder)
    gpu = ["--gpus", "all"] if GPU_FLAG == "1" else []
    cmd = [*base, *gpu, "-v", data_mount, "-v", output_mount]
    if task in INTERMEDIATE_TASKS:
        # Override the bare ENTRYPOINT to activate the env and pass required args.
        inner = f"{_activate(task)} && exec python caisr_{task}.py {_script_args(task)}"
        cmd += ["--entrypoint", "/bin/bash", image, "-c", inner]
    else:
        # preprocess and report run correctly with their ENTRYPOINT defaults.
        cmd += [image]
    print(f"[caisr] {task}: {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stdout:
        sys.stdout.write(res.stdout)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise SystemExit(f"CAISR task '{task}' failed with code {res.returncode}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="work dir containing data/ and caisr_output/")
    ap.add_argument(
        "--dockers",
        default=os.environ.get("CAISR_DOCKERS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "dockers")),
        help="folder with caisr_{task}.tar.gz images (used only if not already installed)",
    )
    ap.add_argument("--only", nargs="*", help="run only these tasks")
    args = ap.parse_args()

    tasks = [t for t in TASKS if (not args.only or t in args.only)]
    data_folder = os.path.join(args.work, "data")
    output_folder = os.path.join(args.work, "caisr_output")

    installed = _installed_repos()
    images = {t: _ensure_image(t, args.dockers, installed) for t in tasks}

    set_run_parameters(data_folder, tasks)

    for task in tasks:
        if task in INTERMEDIATE_TASKS:
            os.makedirs(os.path.join(output_folder, "intermediate", task), exist_ok=True)
        run_task(images[task], task, data_folder, output_folder)

    print(f"[caisr] pipeline complete: {tasks}", flush=True)


if __name__ == "__main__":
    main()

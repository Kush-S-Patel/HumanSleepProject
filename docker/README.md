# CAISR sleep-AI integration

Raw `.edf` / `.h5` uploads are scored by the **CAISR** pipeline
(Complete AI Sleep Report, https://github.com/bdsp-core/CAISR-App):

```
preprocess (edf -> 200 Hz h5)
   -> stage (ProductGraphSleepNet, 30 s sleep stages)
   -> arousal (ArousalNet)
   -> resp (rule-based apnea/hypopnea/RERA)
   -> limb (rule-based PLM)
   -> report (combined 2 Hz annotations + metrics)
```

The API converts CAISR's combined annotation CSV into the same compact artifact
schema used by cached studies (`psg_core.caisr.parse_caisr_csv`).

`docker/run_caisr.py` is a headless clone of CAISR-App's `caisr.py`: same image
names (`caisr_{task}:latest`), same task order, same container mounts
(`data/` → `/data/data/`, `caisr_output/` → `/data/caisr_output/`, with the
Docker-Desktop Windows path transform), and the same per-task
`run_parameters/{task}.csv` defaults. So once the official images are present,
an upload is scored by the real CAISR models with no further wiring.

## One-time setup

1. Obtain the CAISR image tarballs from the CAISR-App release
   (github.com/bdsp-core/CAISR-App — distributed as `*.tar.gz`, not on a public
   registry). Then either:

   **(a) load them yourself:**

   ```bash
   docker load -i caisr_preprocess.tar.gz
   docker load -i caisr_stage.tar.gz
   docker load -i caisr_arousal.tar.gz
   docker load -i caisr_resp.tar.gz
   docker load -i caisr_limb.tar.gz
   docker load -i caisr_report.tar.gz
   ```

   **(b) or drop the `*.tar.gz` files into `docker/dockers/`** — the runner
   loads any missing image automatically on first use (override the location
   with `CAISR_DOCKERS_DIR`).

2. Verify they are installed:

   ```bash
   docker images --format "{{.Repository}}:{{.Tag}}" | findstr caisr
   ```

3. Retry the EDF/H5 upload — it will now score with CAISR instead of returning
   `needs_setup`.

### Windows / GPU notes

- **File sharing**: Docker Desktop must be allowed to bind-mount the drive that
  holds the API's `data/` dir (Settings → Resources → File Sharing, or WSL2
  backend). The runner emits `/C/Users/...` mount paths exactly like CAISR's
  `caisr.py`.
- **GPU**: CAISR's bundled TensorFlow is pinned to older CUDA (stage = TF 1.15 ≤
  Turing, arousal = TF 2.8 ≤ Ada). Newer cards (e.g. RTX 50-series / Blackwell)
  fall back to **CPU** — still correct, just slower. The runner does not pass
  `--gpus` by default (matching CAISR); set `CAISR_GPU=1` to opt in if your card
  is supported.

## Without CAISR

If the images are not installed, EDF/H5 upload jobs return status
`needs_setup` with instructions. You can still get a full report immediately by
uploading an **HSP annotation `.csv`**, which `psg_core` parses directly.

## Stage code mapping

CAISR stage/resp/limb integer codes are mapped in `packages/psg_core/psg_core/caisr.py`.
If a CAISR release uses different codes, override without editing code:

```bash
set HSP_CAISR_STAGE_MAP=5:W,4:REM,3:N1,2:N2,1:N3,0:?
```

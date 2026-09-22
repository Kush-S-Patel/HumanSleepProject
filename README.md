# HSP Lab

A small sleep-clinic workbench on top of the
[Human Sleep Project](https://bdsp.io): triage overnight studies, glance at
CAISR (or human) scores, poke at a few epochs, sign off, and export a report.

It’s meant for **reviewing** automated scoring — not for replacing a full PSG
scoring station, and not for unsupervised diagnosis.

<p align="center">
  <img src="docs/images/walkthrough.gif" alt="Walkthrough: triage → epoch QC → sign-off → export (timestamp ticks so you can see it playing)" width="900" />
</p>

<p align="center">
  <em>GIF walkthrough — triage → report → epoch QC → sign-off → PDF.</em><br/>
  <a href="docs/media/walkthrough.mp4">MP4 (full speed)</a>
  · <a href="docs/CLINICAL_REFERENCES.md">Clinical references</a>
  · <a href="LICENSE">MIT License</a>
</p>

---

## Why this exists

Sleep labs are drowning in overnight studies. Models like CAISR can draft a
hypnogram and respiratory events in minutes — but someone still has to **look**,
correct the weird epochs, and own the report.

HSP Lab is that middle layer: a triage queue with AHI/severity, a study page
with hypnogram + CDS, light epoch QC, a sign-off lock, and exports (PDF / JSON /
BIDS TSV). Concordance metrics are there when you need a validation slide.

| What clinics actually need | What you get here |
| --- | --- |
| Queue by how bad the night looks | Worklist with AHI + OSA severity + review state |
| Read a scored night quickly | Study report, hypnogram, event rails, CDS |
| Fix a few bad epochs | Click hypnogram → EEG/flow/SpO₂ preview + overrides |
| Know who signed it | Pending → in review → reviewed → signed off |
| Hand something to a referring MD | PDF / HTML / JSON / BIDS-Events TSV |
| Show the model isn’t wild | Concordance (κ, AUROC, Bland–Altman) on held-out HSP |
| Full montage scoring like RemLogic | No — out of scope |
| Hospital login / EMR / PHI | No — de-identified research demo |

Severity cut-points (adult and pediatric AHI) follow common AASM / clinical
practice ranges — see [`docs/CLINICAL_REFERENCES.md`](docs/CLINICAL_REFERENCES.md).

---

## Try it locally

No S3 needed if you generate sample studies:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install -e packages/psg_core

python scripts/build_registry.py
python scripts/make_sample_data.py --n 30

$env:PYTHONPATH="packages/psg_core"
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir apps/api --port 8000

cd apps/web
npm install
npm run dev   # http://localhost:3000
```

Then: open `/` → filter **Moderate** → **Open** a study → click the hypnogram →
move through **In review → Reviewed → Signed off** → hit **PDF**.

Raw EDF scoring needs Docker + CAISR images ([`docker/README.md`](docker/README.md)).
Real HSP annotations need BDSP S3 credentials (`scripts/build_cache.py`).

---

## Screenshots

<details>
<summary>Worklist triage</summary>
<p align="center"><img src="docs/images/01-worklist.png" width="880" alt="Worklist" /></p>
</details>

<details>
<summary>Study report + review panel</summary>
<p align="center"><img src="docs/images/02-study-report.png" width="880" alt="Study report" /></p>
</details>

<details>
<summary>Epoch QC</summary>
<p align="center"><img src="docs/images/03-epoch-qc.png" width="880" alt="Epoch QC" /></p>
</details>

<details>
<summary>Concordance</summary>
<p align="center"><img src="docs/images/04-concordance.png" width="880" alt="Concordance" /></p>
</details>

<p align="center">
  <img src="docs/images/06-architecture.png" alt="Architecture" width="880" />
</p>

---

## How it’s put together

```
PSG upload / HSP archive
        │
        ▼
 CAISR (stage · resp · arousal · limb)   ← optional Docker path
        │
        ▼
 psg_core  →  metrics, SpO₂ fill-ins, CDS, exports
        │
        ▼
 FastAPI  →  Next.js triage console
```

| Bit | Where |
| --- | --- |
| Shared PSG logic | `packages/psg_core` |
| API | `apps/api` |
| UI | `apps/web` |
| Offline / S3 prep | `scripts/` |
| CAISR runner | `docker/` |

Artifacts per study: `meta`, `hypnogram`, `events`, `metrics`, `summary`, plus
optional `signals` / `comparison` / `overrides`.

---

## Safety (please read)

Every report says it out loud: **decision support, not a diagnosis.** Signed-off
studies lock edits until you reopen them. Pediatric thresholds, split-night /
titration caveats, and “not enough sleep to compute AHI” guards are in CDS.

Citations for the numbers we use: [`docs/CLINICAL_REFERENCES.md`](docs/CLINICAL_REFERENCES.md).

---

## Dev checks

```powershell
pip install ruff pytest
pip install -e packages/psg_core
ruff check packages/psg_core apps/api scripts tests
python -m pytest tests -q

cd apps/web
npx tsc --noEmit
```

GitHub Actions runs the same on every push to `main`.

---

## License & data

MIT — see [`LICENSE`](LICENSE). HSP recordings stay under BDSP agreements; `data/`
and `metadata/*.csv` are gitignored on purpose. Don’t commit PHI or raw EDFs.

# Clinical references

HSP Lab is **decision support for research review**, not a cleared medical device
and not a diagnosis. Severity labels and supporting flags in `psg_core.cds` use
widely cited AASM / clinical-practice cut-points. Machine-readable copies live in
[`packages/psg_core/psg_core/clinical_refs.py`](../packages/psg_core/psg_core/clinical_refs.py).

## Adult OSA severity (AHI, events per hour of sleep)

| Label | AHI range |
| --- | --- |
| Normal | &lt; 5 |
| Mild | 5 – &lt; 15 |
| Moderate | 15 – &lt; 30 |
| Severe | ≥ 30 |

**Sources**

1. Iber C et al. *The AASM Manual for the Scoring of Sleep and Associated Events*.
   Westchester, IL: American Academy of Sleep Medicine; 2007 (and subsequent updates).
2. Epstein LJ et al. Clinical guideline for the evaluation, management and long-term
   care of obstructive sleep apnea in adults. *J Clin Sleep Med*. 2009;5(3):263-276.
   https://doi.org/10.5664/jcsm.27497
3. Kapur VK et al. Clinical practice guideline for diagnostic testing for adult
   obstructive sleep apnea. *J Clin Sleep Med*. 2017;13(3):479-504.
   https://doi.org/10.5664/jcsm.6506

## Pediatric OSA severity

Pediatric cut-points are more sensitive than adult:

| Label | AHI range |
| --- | --- |
| Normal | &lt; 1 |
| Mild | 1 – &lt; 5 |
| Moderate | 5 – &lt; 10 |
| Severe | ≥ 10 |

**Sources**

1. American Academy of Sleep Medicine. *International Classification of Sleep Disorders*,
   3rd ed (ICSD-3). Darien, IL: AASM; 2014.
2. Marcus CL et al. Diagnosis and management of childhood obstructive sleep apnea
   syndrome. *Pediatrics*. 2012;130(3):e714-e755. https://doi.org/10.1542/peds.2012-1672
3. Berry RB et al. Rules for scoring respiratory events in sleep: update of the 2007
   AASM Manual. *J Clin Sleep Med*. 2012;8(5):597-619. https://doi.org/10.5664/jcsm.2172

## Supporting flags (not OSA grading alone)

- **Arousal index ≥ 15/h** — fragmentation finding of clinical interest (AASM scoring
  manuals); not a standalone OSA diagnosis.
- **PLMI ≥ 15/h (adults)** — commonly used threshold of interest (ICSD-3).
- **Minimum scored sleep** — local guard: if total sleep time is &lt; ~5 minutes, we
  refuse to assign OSA severity from AHI (avoids nonsense indices on wake-only /
  failed recordings).

## Automated scoring backend

EDF/H5 uploads are scored with [CAISR](https://github.com/bdsp-core/CAISR-App)
(BDSP / Human Sleep Project). Concordance metrics on the `/concordance` page compare
CAISR to human annotations on held-out HSP studies and are validation research, not
a clinical performance claim for a specific device clearance.

## What we do *not* claim

- FDA/CE clearance or fitness for unsupervised clinical use  
- Equivalence to a board-certified sleep physician reading the raw PSG  
- That export PDFs are final medical record documents without human review  

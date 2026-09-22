"""Clinical references for severity thresholds and scoring claims used by HSP Lab.

These are the guideline/paper sources behind ``psg_core.cds`` and related metrics.
They are citations for research transparency — not a claim of clinical clearance.
"""

# Adult OSA severity by AHI (events/hour of sleep)
# American Academy of Sleep Medicine — common adult cut-points used in practice:
#   normal <5, mild 5–14.9, moderate 15–29.9, severe ≥30.
ADULT_OSA_AHI = {
    "normal": (None, 5),
    "mild": (5, 15),
    "moderate": (15, 30),
    "severe": (30, None),
    "citations": [
        "Iber C et al. The AASM Manual for the Scoring of Sleep and Associated Events. "
        "Westchester, IL: American Academy of Sleep Medicine; 2007 (and subsequent updates).",
        "Epstein LJ et al. Clinical guideline for the evaluation, management and long-term "
        "care of obstructive sleep apnea in adults. J Clin Sleep Med. 2009;5(3):263-276. "
        "https://doi.org/10.5664/jcsm.27497",
        "Kapur VK et al. Clinical practice guideline for diagnostic testing for adult "
        "obstructive sleep apnea. J Clin Sleep Med. 2017;13(3):479-504. "
        "https://doi.org/10.5664/jcsm.6506",
    ],
}

# Pediatric AHI cut-points commonly used in pediatric sleep medicine (more sensitive).
PEDIATRIC_OSA_AHI = {
    "normal": (None, 1),
    "mild": (1, 5),
    "moderate": (5, 10),
    "severe": (10, None),
    "citations": [
        "American Academy of Sleep Medicine. International Classification of Sleep Disorders, "
        "3rd ed (ICSD-3). Darien, IL: AASM; 2014.",
        "Marcus CL et al. Diagnosis and management of childhood obstructive sleep apnea "
        "syndrome. Pediatrics. 2012;130(3):e714-e755. https://doi.org/10.1542/peds.2012-1672",
        "Berry RB et al. Rules for scoring respiratory events in sleep: update of the 2007 "
        "AASM Manual. J Clin Sleep Med. 2012;8(5):597-619. https://doi.org/10.5664/jcsm.2172",
    ],
}

# Supporting index conventions used in CDS findings (not OSA grading alone).
SUPPORTING_THRESHOLDS = {
    "arousal_index_elevated": {
        "adult_ge": 15,
        "note": "Elevated arousal index flag; fragmentation finding, not a diagnostic criterion alone.",
        "citations": [
            "Iber C et al. AASM Manual for the Scoring of Sleep and Associated Events. AASM; 2007+.",
        ],
    },
    "plm_index_elevated": {
        "adult_ge": 15,
        "note": "PLMI ≥15/h often used as a threshold of clinical interest in adults.",
        "citations": [
            "American Academy of Sleep Medicine. International Classification of Sleep Disorders, "
            "3rd ed (ICSD-3). Darien, IL: AASM; 2014.",
        ],
    },
    "min_tst_for_index_min": {
        "minutes": 5,
        "note": "Local guard: do not assign OSA severity when scored sleep is vanishingly short.",
    },
}

# CAISR automated scoring — research system behind EDF/H5 upload path.
CAISR = {
    "citations": [
        "Nasiri S et al. / BDSP CAISR (Computer-Aided Identification of Sleep Records) — "
        "see https://github.com/bdsp-core/CAISR-App and associated BDSP / HSP publications.",
        "Human Sleep Project (HSP) / Brain Data Science Platform: https://bdsp.io",
    ],
}

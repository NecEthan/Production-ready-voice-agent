"""
In-memory data store — peptide inventory and FAQs.
Replace with a real database in production.
"""

# ------------------------------------------------------------------
# Peptide stock
# ------------------------------------------------------------------
PEPTIDE_STOCK: dict[str, dict] = {
    "BPC-157": {
        "quantity": 24,
        "unit": "vials (5 mg)",
        "price": 65,
        "description": "Body protection compound. Accelerates healing of tendons, ligaments, gut lining, and muscle. Strong anti-inflammatory.",
        "goals": ["healing", "recovery", "gut health", "tendon", "ligament", "inflammation", "injury"],
    },
    "TB-500": {
        "quantity": 18,
        "unit": "vials (5 mg)",
        "price": 75,
        "description": "Thymosin Beta-4. Promotes tissue repair, reduces inflammation, improves flexibility and endurance.",
        "goals": ["healing", "recovery", "inflammation", "flexibility", "injury", "endurance"],
    },
    "CJC-1295": {
        "quantity": 30,
        "unit": "vials (2 mg)",
        "price": 55,
        "description": "GHRH analogue. Stimulates sustained growth hormone release, supports muscle gain, fat loss, and sleep quality.",
        "goals": ["muscle", "fat loss", "growth hormone", "anti-aging", "sleep", "body composition"],
    },
    "Ipamorelin": {
        "quantity": 30,
        "unit": "vials (2 mg)",
        "price": 50,
        "description": "Selective GHRP. Clean GH pulse with minimal side effects. Often stacked with CJC-1295.",
        "goals": ["muscle", "fat loss", "growth hormone", "anti-aging", "body composition", "sleep"],
    },
    "Sermorelin": {
        "quantity": 15,
        "unit": "vials (3 mg)",
        "price": 60,
        "description": "GHRH analogue. Stimulates natural GH production. Commonly used for anti-aging and recovery.",
        "goals": ["anti-aging", "growth hormone", "recovery", "sleep", "muscle"],
    },
    "AOD-9604": {
        "quantity": 20,
        "unit": "vials (2 mg)",
        "price": 70,
        "description": "Modified fragment of HGH. Targets fat metabolism without affecting blood sugar or IGF-1 levels.",
        "goals": ["fat loss", "weight loss", "metabolism", "body composition"],
    },
    "Semaglutide": {
        "quantity": 12,
        "unit": "vials (2 mg)",
        "price": 180,
        "description": "GLP-1 receptor agonist. Powerful appetite suppression and weight loss. Weekly injection.",
        "goals": ["weight loss", "fat loss", "appetite", "diabetes", "metabolism", "GLP-1"],
    },
    "Tirzepatide": {
        "quantity": 8,
        "unit": "vials (5 mg)",
        "price": 220,
        "description": "Dual GLP-1/GIP agonist. Superior weight loss vs semaglutide in trials. Weekly injection.",
        "goals": ["weight loss", "fat loss", "appetite", "metabolism", "GLP-1", "GIP"],
    },
    "PT-141": {
        "quantity": 22,
        "unit": "vials (10 mg)",
        "price": 90,
        "description": "Bremelanotide. Melanocortin receptor agonist. Improves sexual function in men and women.",
        "goals": ["libido", "sexual health", "erectile dysfunction", "sexual function"],
    },
    "GHK-Cu": {
        "quantity": 40,
        "unit": "vials (50 mg)",
        "price": 45,
        "description": "Copper peptide. Skin regeneration, collagen synthesis, anti-aging, wound healing.",
        "goals": ["skin", "anti-aging", "collagen", "wound healing", "hair loss"],
    },
    "Epithalon": {
        "quantity": 16,
        "unit": "vials (10 mg)",
        "price": 80,
        "description": "Telomerase activator. Anti-aging, sleep regulation, antioxidant. Cycled 1–2x per year.",
        "goals": ["anti-aging", "longevity", "sleep", "telomere", "antioxidant"],
    },
    "Thymosin Alpha-1": {
        "quantity": 14,
        "unit": "vials (1.5 mg)",
        "price": 95,
        "description": "Immune modulator. Enhances T-cell function, antiviral, used for chronic infections and immune dysfunction.",
        "goals": ["immune", "immune system", "infection", "autoimmune", "antiviral", "Lyme"],
    },
    "Semax": {
        "quantity": 10,
        "unit": "vials (1 mg)",
        "price": 70,
        "description": "ACTH analogue. Nootropic, neuroprotective, boosts BDNF. Used for focus, memory, and stroke recovery.",
        "goals": ["cognitive", "focus", "memory", "brain", "nootropic", "neuroprotection", "BDNF"],
    },
    "Selank": {
        "quantity": 10,
        "unit": "vials (5 mg)",
        "price": 65,
        "description": "Anxiolytic peptide. Reduces anxiety, improves mood and memory. Non-addictive alternative to benzos.",
        "goals": ["anxiety", "stress", "mood", "cognitive", "memory", "sleep"],
    },
    "DSIP": {
        "quantity": 12,
        "unit": "vials (2 mg)",
        "price": 55,
        "description": "Delta Sleep Inducing Peptide. Improves sleep quality and depth. Also has analgesic and stress-reducing effects.",
        "goals": ["sleep", "insomnia", "stress", "pain", "recovery"],
    },
    "GHRP-2": {
        "quantity": 20,
        "unit": "vials (5 mg)",
        "price": 48,
        "description": "GH releasing peptide. Strong GH pulse, increases appetite. Used for muscle building and recovery.",
        "goals": ["muscle", "growth hormone", "appetite", "recovery", "body composition"],
    },
}

# ------------------------------------------------------------------
# FAQs
# ------------------------------------------------------------------
FAQS: dict[str, str] = {
    "hours": "We're open Monday through Friday, 9 AM to 5 PM.",
    "location": "We're at 123 Wellness Drive, Suite 200, Austin TX 78701.",
    "services": (
        "We offer peptide therapy consultations, hormone optimisation, "
        "IV nutrient infusions, and personalised longevity wellness plans. "
        "We carry a wide range of research peptides in stock and can guide "
        "you to the right protocol for your goals."
    ),
    "pricing": (
        "Initial consultations start at $150. "
        "Peptide therapy packages range from $300 to $800 per month depending on protocol. "
        "Individual peptide vials range from $45 to $220. "
        "Ask about our new-patient special."
    ),
    "insurance": (
        "We are a cash-pay practice. We don't bill insurance directly, "
        "but we provide superbills for HSA/FSA reimbursement."
    ),
    "cancellation": (
        "Please cancel or reschedule at least 24 hours in advance "
        "to avoid a $50 late-cancellation fee."
    ),
    "new_patient": (
        "New patients should arrive 15 minutes early to complete intake forms. "
        "Bring a valid photo ID and any recent lab work if available."
    ),
    "storage": (
        "All peptides should be stored refrigerated at 2–8°C and kept away from light. "
        "Reconstituted peptides are typically stable for 28 days when refrigerated."
    ),
    "shipping": (
        "We ship refrigerated within the continental US via overnight courier. "
        "Shipping is $25 flat rate or free on orders over $300."
    ),
}

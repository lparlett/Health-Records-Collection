PRAGMA foreign_keys = ON;

-- =====================
-- Core Patient Table
-- =====================
CREATE TABLE IF NOT EXISTS patient (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    given_name TEXT,
    family_name TEXT,
    birth_date TEXT,
    gender TEXT,
    source_file TEXT
);

CREATE INDEX IF NOT EXISTS idx_patient_name ON patient(family_name, given_name);
CREATE INDEX IF NOT EXISTS idx_patient_dob ON patient(birth_date);

-- =====================
-- Encounters
-- =====================
CREATE TABLE IF NOT EXISTS encounter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_date TEXT,
    provider_name TEXT,
    encounter_type TEXT,
    notes TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_encounter_patient ON encounter(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounter_date ON encounter(encounter_date);

-- =====================
-- Medications
-- =====================
CREATE TABLE IF NOT EXISTS medication (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_id INTEGER,
    name TEXT,
    dose TEXT,
    route TEXT,
    frequency TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT,
    notes TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_med_patient ON medication(patient_id);
CREATE INDEX IF NOT EXISTS idx_med_name ON medication(name);

-- =====================
-- Lab Results
-- =====================
CREATE TABLE IF NOT EXISTS lab_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_id INTEGER,
    loinc_code TEXT,
    test_name TEXT,
    result_value TEXT,
    unit TEXT,
    reference_range TEXT,
    abnormal_flag TEXT,
    date TEXT,
    ordering_provider TEXT,
    performing_org TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_lab_patient ON lab_result(patient_id);
CREATE INDEX IF NOT EXISTS idx_lab_test_date ON lab_result(test_name, date);

-- =====================
-- Allergies
-- =====================
CREATE TABLE IF NOT EXISTS allergy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    substance TEXT,
    reaction TEXT,
    severity TEXT,
    status TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_allergy_patient ON allergy(patient_id);

-- =====================
-- Conditions / Problems
-- =====================
CREATE TABLE IF NOT EXISTS condition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    name TEXT,
    onset_date TEXT,
    status TEXT,
    notes TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_condition_patient ON condition(patient_id);

-- =====================
-- Immunizations
-- =====================
CREATE TABLE IF NOT EXISTS immunization (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    vaccine_name TEXT,
    cvx_code TEXT,
    date_administered TEXT,
    status TEXT,
    lot_number TEXT,
    notes TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_immunization_patient ON immunization(patient_id);
CREATE INDEX IF NOT EXISTS idx_immunization_date ON immunization(date_administered);

-- =====================
-- Vitals
-- =====================
CREATE TABLE IF NOT EXISTS vital (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_id INTEGER,
    vital_type TEXT,
    value TEXT,
    unit TEXT,
    date TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_vital_patient ON vital(patient_id);
CREATE INDEX IF NOT EXISTS idx_vital_type_date ON vital(vital_type, date);

-- =====================
-- Procedures
-- =====================
CREATE TABLE IF NOT EXISTS procedure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_id INTEGER,
    name TEXT,
    cpt_icd_code TEXT,
    date TEXT,
    notes TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_patient ON procedure(patient_id);

-- =====================
-- Attachments (PDFs, Images, etc.)
-- =====================
CREATE TABLE IF NOT EXISTS attachment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_id INTEGER,
    file_path TEXT,
    mime_type TEXT,
    description TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_attach_patient ON attachment(patient_id);

-- =====================
-- Provenance (where data came from)
-- =====================
CREATE TABLE IF NOT EXISTS provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    source_system TEXT,
    source_file TEXT,
    imported_on TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prov_patient ON provenance(patient_id);
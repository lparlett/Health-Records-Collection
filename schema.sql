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
-- Providers
-- =====================
CREATE TABLE IF NOT EXISTS provider (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
<<<<<<< HEAD
    name TEXT NOT NULL,
    npi TEXT,
    specialty TEXT,
    organization TEXT
=======
    name TEXT,
    given_name TEXT,
    family_name TEXT,
    credentials TEXT,
    npi TEXT,
    specialty TEXT,
    organization TEXT,
    normalized_key TEXT,
    entity_type TEXT NOT NULL DEFAULT 'person'
>>>>>>> 831c0d2f3d1f49be1cfebf4124c3ded16afacec9
);

CREATE INDEX IF NOT EXISTS idx_provider_name ON provider(name);

-- =====================
-- Encounters
-- =====================
CREATE TABLE IF NOT EXISTS encounter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_date TEXT,
    provider_id INTEGER,
    source_encounter_id TEXT,
    encounter_type TEXT,
    notes TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES provider(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_encounter_patient ON encounter(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounter_date ON encounter(encounter_date);
CREATE INDEX IF NOT EXISTS idx_encounter_provider ON encounter(provider_id);
<<<<<<< HEAD
CREATE UNIQUE INDEX IF NOT EXISTS idx_encounter_unique ON encounter(patient_id, encounter_date, provider_id, source_encounter_id);
=======
>>>>>>> 831c0d2f3d1f49be1cfebf4124c3ded16afacec9

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
    ordering_provider_id INTEGER,
    performing_org_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(ordering_provider_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(performing_org_id) REFERENCES provider(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_lab_patient ON lab_result(patient_id);
CREATE INDEX IF NOT EXISTS idx_lab_test_date ON lab_result(test_name, date);
CREATE INDEX IF NOT EXISTS idx_lab_ordering_provider ON lab_result(ordering_provider_id);
CREATE INDEX IF NOT EXISTS idx_lab_performing_org ON lab_result(performing_org_id);

-- =====================
<<<<<<< HEAD
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
=======
>>>>>>> 831c0d2f3d1f49be1cfebf4124c3ded16afacec9
-- Conditions / Problems
-- =====================
CREATE TABLE IF NOT EXISTS condition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    name TEXT,
    onset_date TEXT,
    status TEXT,
    notes TEXT,
    provider_id INTEGER,
    encounter_id INTEGER,
    code TEXT,
    code_system TEXT,
    code_display TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_condition_patient ON condition(patient_id);
CREATE INDEX IF NOT EXISTS idx_condition_code ON condition(code);

CREATE TABLE IF NOT EXISTS condition_code (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    code_system TEXT,
    display_name TEXT,
    FOREIGN KEY(condition_id) REFERENCES condition(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_condition_code_unique ON condition_code(condition_id, code, code_system);

-- =====================
<<<<<<< HEAD
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
=======
>>>>>>> 831c0d2f3d1f49be1cfebf4124c3ded16afacec9
-- Procedures
-- =====================
CREATE TABLE IF NOT EXISTS procedure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_id INTEGER,
    provider_id INTEGER,
    name TEXT,
    code TEXT,
    code_system TEXT,
    code_display TEXT,
    status TEXT,
    date TEXT,
    notes TEXT,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(provider_id) REFERENCES provider(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_patient ON procedure(patient_id);
CREATE INDEX IF NOT EXISTS idx_proc_provider ON procedure(provider_id);

CREATE TABLE IF NOT EXISTS procedure_code (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    code_system TEXT,
    display_name TEXT,
    FOREIGN KEY(procedure_id) REFERENCES procedure(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_procedure_code_unique ON procedure_code(procedure_id, code, code_system);

<<<<<<< HEAD
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
=======
-- Keep remaining tables as previously defined
>>>>>>> 831c0d2f3d1f49be1cfebf4124c3ded16afacec9

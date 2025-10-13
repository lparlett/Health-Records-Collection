PRAGMA foreign_keys = ON;

-- =====================
-- Data Sources
-- =====================
-- AI-assisted addition by Codex + Lauren, 2025-10-12.
CREATE TABLE IF NOT EXISTS data_source (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    source_archive TEXT,
    document_created TEXT,
    repository_unique_id TEXT,
    document_hash TEXT,
    document_size INTEGER,
    author_institution TEXT,
    attachment_id INTEGER,
    UNIQUE(file_sha256),
    FOREIGN KEY(attachment_id) REFERENCES attachment(id)
);

CREATE INDEX IF NOT EXISTS idx_data_source_ingested_at ON data_source(ingested_at);

-- =====================
-- Core Patient Table
-- =====================
CREATE TABLE IF NOT EXISTS patient (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    given_name TEXT,
    family_name TEXT,
    birth_date TEXT,
    gender TEXT,
    data_source_id INTEGER,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
);

CREATE INDEX IF NOT EXISTS idx_patient_name ON patient(family_name, given_name);
CREATE INDEX IF NOT EXISTS idx_patient_dob ON patient(birth_date);

-- =====================
-- Providers
-- =====================
CREATE TABLE IF NOT EXISTS provider (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    given_name TEXT,
    family_name TEXT,
    credentials TEXT,
    npi TEXT,
    specialty TEXT,
    organization TEXT,
    normalized_key TEXT,
    entity_type TEXT NOT NULL DEFAULT 'person'
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
    organization_id INTEGER,
    source_encounter_id TEXT,
    encounter_type TEXT,
    notes TEXT,
    reason_for_visit TEXT,
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(organization_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
);

CREATE INDEX IF NOT EXISTS idx_encounter_patient ON encounter(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounter_date ON encounter(encounter_date);
CREATE INDEX IF NOT EXISTS idx_encounter_provider ON encounter(provider_id);
CREATE INDEX IF NOT EXISTS idx_encounter_organization ON encounter(organization_id);
DROP INDEX IF EXISTS idx_encounter_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_encounter_unique ON encounter(
    patient_id,
    COALESCE(provider_id, -1),
    encounter_date
);

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
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
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
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(ordering_provider_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(performing_org_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
);

CREATE INDEX IF NOT EXISTS idx_lab_patient ON lab_result(patient_id);
CREATE INDEX IF NOT EXISTS idx_lab_test_date ON lab_result(test_name, date);
CREATE INDEX IF NOT EXISTS idx_lab_ordering_provider ON lab_result(ordering_provider_id);
CREATE INDEX IF NOT EXISTS idx_lab_performing_org ON lab_result(performing_org_id);

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
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
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
    provider_id INTEGER,
    encounter_id INTEGER,
    code TEXT,
    code_system TEXT,
    code_display TEXT,
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
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
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
);

CREATE INDEX IF NOT EXISTS idx_immunization_patient ON immunization(patient_id);
CREATE INDEX IF NOT EXISTS idx_immunization_date ON immunization(date_administered);
CREATE UNIQUE INDEX IF NOT EXISTS idx_immunization_unique
    ON immunization (
        patient_id,
        COALESCE(date_administered, ''),
        COALESCE(vaccine_name, '')
    );

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
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
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
    provider_id INTEGER,
    name TEXT,
    code TEXT,
    code_system TEXT,
    code_display TEXT,
    status TEXT,
    date TEXT,
    notes TEXT,
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(provider_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
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

-- =====================
-- Attachments (PDFs, Images, etc.)
-- =====================
CREATE TABLE IF NOT EXISTS attachment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    file_path TEXT,
    mime_type TEXT,
    description TEXT,
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
);

CREATE INDEX IF NOT EXISTS idx_attach_patient ON attachment(patient_id);

-- =====================
-- Progress Notes
-- =====================
CREATE TABLE IF NOT EXISTS progress_note (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    encounter_id INTEGER,
    provider_id INTEGER,
    note_title TEXT,
    note_datetime TEXT,
    note_text TEXT NOT NULL,
    note_hash TEXT NOT NULL,
    source_note_id TEXT,
    data_source_id INTEGER,
    FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
    FOREIGN KEY(encounter_id) REFERENCES encounter(id) ON DELETE SET NULL,
    FOREIGN KEY(provider_id) REFERENCES provider(id) ON DELETE SET NULL,
    FOREIGN KEY(data_source_id) REFERENCES data_source(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_progress_note_unique
    ON progress_note (
        patient_id,
        COALESCE(encounter_id, -1),
        COALESCE(provider_id, -1),
        note_hash
    );

CREATE INDEX IF NOT EXISTS idx_progress_note_patient ON progress_note(patient_id);
CREATE INDEX IF NOT EXISTS idx_progress_note_encounter ON progress_note(encounter_id);
CREATE INDEX IF NOT EXISTS idx_progress_note_provider ON progress_note(provider_id);

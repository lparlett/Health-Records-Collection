# Use of Generative AI / Codex Assistance

Parts of this codebase were developed with the help of the OpenAI Codex model (a generative AI assistant). Specifically:

- Some modules, utility routines, or prototyping code were initially scaffolded using Codex.
- These AI-generated portions have been reviewed, refactored, and integrated by human developers.
- Prompts or prompt templates used (non-confidential) are archived below. Some early conversation prompts were unavailable to be recorded.
- All such sections have been tested and audited to meet the project’s quality, style, and security standards.

**Disclaimer**: Use of AI in this repository does not absolve the authors of responsibility. Users should treat all code as subject to review and validation.  

All post-implementation of AGENTS.md prompts can be found in the /docs/AI_prompts.md file.

## pre-AGENTS.md Conversation Prompts by Function

### Development

- "Now move the find_encounter_id() to someplace more appropriate and all of the insert definitions into either a single document or across their associated concept ingestion files."
- "Recall that we worked on deduplicating the medications through the DB update.... we're getting duplicates again. Can you scan the repo to determine what changes need to be implemented to return to the non-duplicating behavioir?"
- "Let's talk about the best way to pull in progress notes to the DB. Is it to create a separate plan text progress note somewhere and provide a link to that location or is it to pull in the full text? What would the limit be for the amount of text a variable can hold?"
- "Let's do this. Let's create a progress note table that links to the patient and encounter and provider. We need to parse the progress note and insert into the DB. Let's make sure progress notes are not duplicated - what do you feel is the best way of doing this? I think a unique combination of patient, encounter ID, and provider ID would prevent duplicates. During the ingestion, note the number of progress notes added and the number duplicated."
- "I want the test_parsers.py to be revised to align with any changed parse_patient logic."
- "Hello again. Now I'd like to add a vitals table and ingest any information about heigh, weight, blood pressure, temperature, etc in the records."
- "The vaccine name isn't coming through."
- "Let's make the uniqueness dependent on the CVX code and date administered."
- "Let's update the encounter table to include a field for whatever is included in the CCDA 'reason for visit' section. If there are multiple values in that reason for visit, concatenate and separate with a semicolon."
- "Based on all of our interactions, can you create a memory file in this repo/project that details how you and I developed this code?"
- "I want the file to include all conversation prompts starting with 8 days ago."
- "I want you to evaluate this XML file currently open "DOC0025.XML" To better understand how to set up the lab parsing section in the "ingest.py" document."
- "Now evaluate "DOC0001.XML" currently open and see how that affects the ingest.py lab parsing logic if I wanted to pull the lab results from this file."
- "Update ingest.py with the next steps outlined above."
- "Is ingest.py fully updated with all code changes?"
- "Inserted patient Lauren Parlett with 20 meds and 0 labs Traceback (most recent call last): ... UnboundLocalError: cannot access local variable 'labs'"
- "See the results being imported.... interpretation normal / abnormal should instead be a flag and not a new row. No LOINC, no date, and no reference ranges pulled in."
- "Perfect! Let's move onto the medication ingestion. Review the same DOC0001.XML and DOC0025.XML files to ascertain the proper medication fields/layout. Revise ingest.py accordingly."
- "The last change for the night is to check the patient table before adding another row. Ultimately, there will only be one patient - me."
- "I want to pull out the parsing of different aspects of the ingest.py parsing code into their own files with their own def blocks. One for meds, one for labs, etc. Then, in ingest.py, reference those other scripts. I think this will make it easier for development of code and maintenance."
- "Is there a way for the \"insert into DB\" section to be a function called multiple times with parameters rather than separate code for each kind of data?"
- "OK. Slight update to the schema.... let's pull provider into a provider table and make other tables that reference a provider use a key to connect with the provider table."
- "Let's move onto parsing for the encounter table. Create a separate parser for encounters that is called by the ingest.py script. Use DOC0025.XML and DOC0001.XML to guide the parsing targeting."

### Troubleshooting

- "PS Microsoft.PowerShell.Core\FileSystem::\[REDACTED\]\\Health-Records-Collection> python .\ingest.py Traceback (most recent call last): ... sqlite3.OperationalError: duplicate column name: TEXT"
- "PS Microsoft.PowerShell.Core\FileSystem::\[REDACTED\]\\Health-Records-Collection> & "C:/Program Files/Python312/python.exe" \[REDACTED\]/Health-Records-Collection/ingest.py Traceback (most recent call last): ... sqlite3.IntegrityError: UNIQUE constraint failed: index 'uniq_medication_composite'"
- "PS Microsoft.PowerShell.Core\FileSystem::\[REDACTED\]\\Health-Records-Collection> python ingest.py ... (skipped duplicate meds)"
- ""PS Microsoft.PowerShell.Core\\FileSystem::\[REDACTED\]\\Health-Records-Collection> & \"C:/Program Files/Python312/python.exe\" \[REDACTED\]Health-Records-Collection/ingest.py Traceback (most recent call last): ... sqlite3.OperationalError: near ""<<"": syntax error""
- "PS Microsoft.PowerShell.Core\FileSystem::\[REDACTED\]\\Health-Records-Collection> & "C:/Program Files/Python312/python.exe" \[REDACTED\]/Health-Records-Collection/ingest.py Traceback (most recent call last): ... SyntaxError: invalid predicate"

### Documentation

- "In every file, I want complete docstrings for every def block."
- "Add all prompts from this conversation into the development_history.md file"
- "Can you insert the various prompts that I used with you in the development of this code?"

### Syntax issues

- "procedures.py problems:\n\"bool\" is not iterable\n  \"\__iter\__\" method not defined\n\"float\" is not iterable\n  \"\__iter\__\" method not defined\n\"Dict\" is not defined"
- "Why do I keep getting the etree import symbol error when I have already installed lxml?"
- "Why does ingest.py no longer have an insert_patient def?"
- "Why do we keep getting the bool and float not iterable check fails?"
- "For line 63 I'm getting that type error."
- "Fix the immunization service line 72 pylance problem"
- "Fix the immunization parser pylance problems"
- "Fix line 144 pylance problem in that same file"
- "That didn't fix row 63 since those are downstream of it."
- "Fix lines 75, 92,  95, line 109 to address Pylance problems"
- "Fix pylance problems in test_immunizations_service.py"
- "Fix lines 51 and 52"
- "Lines 51 and 52 are still thowing problems for type int"
- "Fix the encounter parser line 42 so that pylance does not complain of bool and float not being iterable"

### Code formatting

- "In the lab section, remove the blank line in the every other line way it is now"
- "This is a really long line - how do I appropriately add a line return to reduce it?\n\n proc_candidates: List\[etree._Element\] = \[el for el in raw_candidates if isinstance(el, etree._Element)\]"
- "This is also long - help me with the line break:\n\n notes = get_text_by_id(tree, ns, text_ref.get(\"value\")) if text_ref is not None and text_ref.get(\"value\") else None"
- "Now this bit:\n\n if id_el is not None:\n                    encounter_source_id = id_el.get(\"extension\") or id_el.get(\"root\")"
- "Similar to the procedures file, fix the bool/float type problem in the medications file."
- "Break up this line: encounter_date=cond.get(\"encounter_start\") or cond.get(\"start\") or cond.get(\"author_time\"),"
- "Help break this one up:\ncondition_id, existing_status, existing_notes, existing_provider_id, existing_encounter_id = existing"
- "Break up this beheamoth:\n\n print(f\"Inserted patient {patient\['given'\]} {patient\['family'\]} with {len(parsed\['encounters'\])} encounters, {len(parsed\['conditions'\])} conditions, {len(parsed\['procedures'\])} procedures, {len(parsed\['medications'\])} meds and {len(parsed\['labs'\])} labs\")"

### Git help

- "I was a bone head and messed up my git repo. Can you revise ingest.py again and the providers.py and medication.py parsers according to where we had left off?"
- "Help me fix my parsers/medications.py... it got messed up in a git repo snafu"

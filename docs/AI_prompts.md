# Prompt Log

[2025-10-11 19:48:25 UTC] Bring the repo to be in compliance with the instructions outlined in AGENTS.md
[2025-10-11 19:48:51 UTC] Create a new folder ""docs"" and in that folder, create a new file ""AI_prompts.md"". Use that file.
[2025-10-11 23:23:16 UTC] For all the files in the parser directory, bring them into compliance with the AGENTS.md file
[2025-10-11 23:52:01 UTC] For all of those files, ensure that there are no remaining Pylance problems.
[2025-10-11 23:52:01 UTC] Fix the parsers/conditions.py iterable issue
[2025-10-11 23:52:01 UTC] Same iterable problems now popped up for line 73 in common.py
[2025-10-11 23:52:01 UTC] The iterable pylance problem is now showing on line 80. Ensure this is resolved for the entirety of the common.py file.
[2025-10-11 23:52:02 UTC] Update the AGENTS.md file so that your work in the future will not have similar issues across these files.
[2025-10-11 23:52:02 UTC] Fix the parsers/conditions.py iterable issue
[2025-10-11 23:52:02 UTC] There's still an iterable problem at line 192
[2025-10-11 23:52:02 UTC] Fix the parsers/encounters.py Pylance problems:  {copy and pasted troubleshooting}
[2025-10-11 23:52:02 UTC] Check that all of my prompts for this session have been logged.
[2025-10-11 23:52:02 UTC] Yes, do
[2025-10-11 23:56:53 UTC] Remember to continue to log every prompt in our session.
[2025-10-11 23:58:55 UTC] Fix these pylance problems in the parsers/labs.py file: {copy and pasted troubleshooting}
[2025-10-12 00:00:27 UTC] Fix these pylance problems from parsers/vitals.py: {copy and pasted troubleshooting}
[2025-10-12 00:02:00 UTC] Fix the iterable Pylance problems in parsers/progress_notes.py.
[2025-10-12 00:07:48 UTC] Bring all files in the services directory into compliance with the AGENTS.md directions.
[2025-10-12 00:17:39 UTC] Resolve the Pylance argument type error in services/conditions.py.
[2025-10-12 00:19:51 UTC] Line 42 of the services/conditions.py file still has an argument problem from pylance.
[2025-10-12 00:19:56 UTC] Sorry. Line 72 - typo.
[2025-10-12 00:21:03 UTC] Services/labs.py has a pylance problem; resolve it.
[2025-10-12 00:23:10 UTC] The problem on line 102 persists.
[2025-10-12 00:25:50 UTC] Fix the services/patient.py issue on line 96 (Pylance return type).
[2025-10-12 00:27:58 UTC] Fix the services/procedures.py Pylance argument type issue.
[2025-10-12 00:30:17 UTC] Fix the Pylance argument type issue in services/providers.py.
[2025-10-12 00:35:27 UTC] Extract shared _clean helper into services/common.py and update services modules.
[2025-10-12 00:42:40 UTC] Fix the Pylance argument type issue in services/vitals.py.
[2025-10-12 00:45:49 UTC] Verify schema.sql and data/ scripts comply with AGENTS.md.
[2025-10-12 00:47:06 UTC] Review db folder files for AGENTS.md compliance.
[2025-10-12 15:21:36 UTC] 
I want to plan with you how to integrate data provenance into the ingestion and insertion code. Maybe a separate data source table that includes the original filename and the datetime of ingestion. Then, all associated tables can reference back to that data source - unless there is a CCDA standard, which we'd want to consider. Thoughts?
[2025-10-12 15:21:37 UTC]  Log this session's prompts at docs/AI_prompts.py by appending to the current document.
[2025-10-12 15:30:29 UTC] Another thing we would want to record, if present, is the original zip file name. That is likely not going to be unique (as the original_filename is not unique), but it would be good to have in case it contains contextual information.
[2025-10-12 15:32:45 UTC] Do not continue to log prompts to AI_prompts.py, only AI_prompts.md. Additionally, do not log IDE contextual information, follow the AGENTS.md standard of a timestamp and the literal prompt.
Next, thread source_archive into the ingestion pipeline.
[2025-10-12 15:37:40 UTC] Before we continue - hold that thought - I have a git repo branch I want this work to live on: 6-add-data-provenance-and-attachments but I forgot to check it out. Move all of these changes onto the new branch.
[2025-10-12 15:38:35 UTC] OK. Let's work through the threading of the data_source_id for the remaining tables.
[2025-10-12 15:50:02 UTC] I think I inadvertantly interrupted you, please continue.
[2025-10-12 16:10:10 UTC] I think you ran into a venv issue.
[2025-10-12 16:13:39 UTC] I will look into the venv issue. Do any of the ingest scripts need to be updated to account for the datasource ID?
[2025-10-12 16:14:21 UTC] Sorry, I meant, do any of the parsing scripts need to be updated?
[2025-10-12 17:00:24 UTC] Remove the data_provenance table from the schema - that functionality is now with the data_source table. Also remove the source_file field from patient.

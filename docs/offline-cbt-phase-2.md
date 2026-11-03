# Offline CBT Phase 2: Question bank and exam management

Phase 2 adds question authoring, examination setup/publication, frozen question snapshots, and student assignment to the Phase 1 entitlement foundation. It reuses the existing `School`, `Subject`, `ClassLevel`, `AcademicSession`, `Term`, `Student`, and `StudentEnrollment` models. It does not add another school, class, subject, session, or student identity model.

## Models

- `Question` belongs to a school, subject, class, and creator. It stores question text/type, topic, difficulty, marks, explanation, optional image, status, and timestamps.
- `QuestionOption` stores ordered options and correctness for single-choice and multiple-answer questions. Text-response questions have no options.
- `Examination` belongs to a school, subject, class, academic session, optional term, and creator. It stores instructions, schedule/duration, pass/total marks, lifecycle, attempts, selection strategy and randomization configuration.
- `ExaminationQuestion` stores the draft question selection. Publishing copies prompt, type, options including correctness, marks, and explanation into an immutable question snapshot. The API does not return answer-key snapshots.
- `ExaminationAssignment` records each eligible student and assignment status/timestamp. A database unique constraint prevents duplicate exam/student rows.

Question bank deletion is limited to unused draft questions. Published questions can be archived. A question referenced by exam history is protected from deletion. Published examinations cannot be edited/deleted; an unassigned draft can be deleted, while exams with history must be archived.

## Permissions and entitlement

Every CBT API requires authentication, an active school membership, an allowed school-role permission, and an active `offline_cbt` entitlement. Teachers can manage their own questions and create draft exams, but cannot publish exams or assign them. School owners/admins/principals can publish and manage lifecycle; managers can manage the bank and assignments. All querysets are scoped to the authorized school.

There is no student CBT API in Phase 2. Question bank responses with answer keys are available only through staff-authorized routes; examination snapshot responses omit the stored answer keys. Student exam sessions belong to Phase 3.

## API

School requests use the existing JWT and selected `X-School-ID` context.

| Endpoint | Methods | Purpose |
| --- | --- | --- |
| `/api/v1/cbt/setup/` | GET | Authorized school's class/subject/session/term selectors; optionally active eligible roster via `class_level` and `academic_session` query parameters |
| `/api/v1/cbt/questions/` | GET, POST | Paginated/searchable/filterable question bank and draft creation |
| `/api/v1/cbt/questions/{uuid}/` | GET, PATCH, DELETE | Retrieve/update; hard-delete only unused drafts |
| `/api/v1/cbt/questions/{uuid}/publish/` | POST | Validate answer options and publish a question |
| `/api/v1/cbt/questions/{uuid}/archive/` | POST | Archive a question without erasing history |
| `/api/v1/cbt/examinations/` | GET, POST | Paginated, filterable exam list and draft creation |
| `/api/v1/cbt/examinations/{uuid}/` | GET, PATCH, DELETE | Read/update a draft; delete only an unassigned draft |
| `/api/v1/cbt/examinations/{uuid}/publish/` | POST | Validate schedule/questions/pass mark, calculate total, freeze selected question snapshot |
| `/api/v1/cbt/examinations/{uuid}/status/` | POST | Explicitly move a published exam to active/completed/archived; frontend clocks do not change server state |
| `/api/v1/cbt/examinations/{uuid}/assignments/` | GET, POST | List assignments, assign whole class or selected active eligible students; retries are idempotent |

Manual selection accepts published question UUIDs with the same school, subject, and class as the exam. Random selection chooses only published questions from that same school/subject/class and optional difficulty/topic filters. Total marks are summed from the selected questions on the server. The examination window must contain the full duration and fall inside its academic session/optional term.

For class assignment, the system expands current active student enrollments for the exam's class/session into individual assignment rows. Individual selection is validated against that same eligible roster. Later enrollment changes do not silently alter an existing assignment set.

## Migration and frontend

Apply `cbt.0001_initial` with the standard Django migration command. The React route is `/app/cbt` and is linked from the authenticated dashboard. It provides question creation/editing, filtering, publishing/archive actions, exam configuration and draft editing, manual/random selection, publishing, and assignment management.

## Scope and limitations

Phase 2 does not include student sign-in/exam-taking, student answer autosave, local CBT deployment, package export/import, objective marking, results, or synchronization. Those require the next phases. Randomization settings are stored for the future student runner; Phase 2 does not generate per-student randomized presentation. Teachers can create exams but an authorized school leader must publish them. Service-plan checkout remains outside this phase; existing Phase 1 entitlement activation is required.

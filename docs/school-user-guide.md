# EDUstacked school user guide

This guide is for the person who registers a school and the staff members who use that school's workspace. Menu labels below match the current application.

## 1. Register the school and sign in

1. Open **Register a school** and enter the school, administrator, and contact details.
2. Open the verification message sent to the administrator's email and verify the address. If the message does not arrive, check Spam and use **Resend verification email** on the sign-in page.
3. Sign in with the verified email and password. The school owner is given access to the newly registered school. If the account belongs to more than one school, choose the school workspace to open.
4. Complete the initial school setup. The owner or authorized school administrator can add the school logo and principal signature under **School profile & settings**. They are used on report-card PDFs where appropriate.

Email verification confirms the account's email address. It is separate from school verification by EDUstacked, which may remain pending while the school continues its setup.

## 2. Set up the academic year

An owner, school administrator, school manager, or principal should open **Classes & subjects** (academic setup) and configure the school's structure in this order:

1. Create the academic session and its terms, with the correct start and end dates.
2. Create classes and their arms (for example, JSS 1 and arm A).
3. Add the school's subjects and assign each subject to the class that studies it. Students enrolled in a class receive that class's active subjects automatically.
4. Configure and activate a grading scale under the grading section before creating assessment plans.

The session, term, class, arm, and subject must agree with one another. A date outside the selected session or term can make enrollment, attendance, or report-card actions fail validation.

## 3. How grading scales work

A grading scale translates a completed score into a grade label and, optionally, a grade point. It is school-defined; EDUstacked does not silently assume a school's grade boundaries.

In **Classes & subjects → Grading scales**, create a scale name and maximum score (commonly 100), then add grade bands. Each band has a label, inclusive minimum and maximum, optional description, and optional grade point. For example, a school might define A as 70.00–100.00, B as 60.00–69.99, and continue downward to cover the full range. This is only an example; enter the grading policy approved by your school.

Before a scale can be activated, its active bands must:

- Start at 0.00 and end at the scale's maximum score.
- Cover every score in between in two-decimal increments.
- Have no gaps or overlaps.

The assessment plan determines how marks are calculated:

- **Raw score addition:** add component marks. The component maximums must add exactly to the grading scale maximum. Example: 1st CA / 20 + 2nd CA / 20 + Examination / 60 = 100.
- **Weighted components:** convert each component result to its percentage of that component's maximum, apply its configured weight, and add the weighted results. Weights must add to exactly 100%. The result is mapped onto the grading scale maximum.

When every component has a mark, the system calculates the total, percentage, grade, and optional grade point. It rounds to two decimal places. A partial result shows entered marks but has no final grade and cannot be submitted. The plan saves a snapshot of its grading scale, so later changes to a scale do not unexpectedly alter an already approved result. A report card uses the approved result; it does not recalculate it. Each report-card subject needs one approved result for the term. If a subject has multiple approved plans, generation asks the school to resolve that because the platform does not invent a rule for combining them.

## 4. Add staff and give them school access

The **Staff & teachers** page has two related records. They serve different purposes:

- **School access** is the person's login and permission to enter this school's workspace. The role selected during **Invite a staff member** determines what they can do. Invited accounts appear in **School login accounts** immediately after the invitation succeeds.
- **Staff profile** is the school's employment record: staff number, job title, dates, contact details, and employment status. It does not create a login and does not grant access by itself.

For a new teacher, the owner, school administrator, or principal should:

1. Use **Invite a staff member**, enter the teacher's email and name, and choose **Teacher**.
2. The teacher receives an email with account setup and verification links if this is a new account. They set their password, verify their email, then sign in using that email and password. If the person already has an EDUstacked account, the invitation links that existing login to the school; it does not reset their password.
3. Add the employment record using **Add staff**. Link it to the invited school login account. The invite and the employment profile are separate, so linking is important for teacher-specific access.
4. In the staff directory, choose **Designate teacher** for that active staff profile.
5. Under **Teaching assignments**, add the academic session, class, arm, subject, and start date for each responsibility. First assign the subject to the class in academic setup. An assignment connects the designated teacher to that existing class subject.

Teachers see **My assignments** in the school dashboard. If the teacher role is missing or wrong, an owner, school administrator, or principal can correct the role in **Staff & teachers → School login accounts**; have the staff member sign out and back in after a role change. The attendance page explains when no active assignment covers its selected date and links to the assignments list.

A teacher can have many active assignments. For example, the same teacher can be assigned Mathematics in JSS 1 A and Mathematics in JSS 2 A, plus Basic Science in JSS 1 A. Each class/arm/subject responsibility is a separate assignment, and the same subject may be assigned to different teachers. The system prevents that teacher from having a duplicate active assignment for the exact same session, class, arm, and subject; end or replace an existing assignment to change that responsibility. There is no fixed one-subject-per-teacher rule.

An invite alone grants school login access but does not create an employment profile, teacher designation, or class/subject assignment. A staff profile alone has no login access. A manager can manage staff profiles and teaching assignments, but cannot invite a new school login account. Reception and bursar roles do not receive teacher attendance or assessment permissions.

## 5. What “designated teacher” means

Designating a teacher creates the teacher-specific record associated with an active staff profile. It allows that staff member to be selected for teaching responsibilities; by itself, it does not assign a class or subject. The **Teaching assignment** is the actual responsibility: teacher + session + class + arm + subject + dates.

For the teacher's login to use teacher-scoped features, the teacher account must also be linked to the staff profile and have active **Teacher** school access. The assignment must be active and cover the date/session/class/subject being used. An unlinked account, inactive designation, or missing assignment will leave the teacher without the relevant class options.

## 6. Daily attendance for a teacher

Each teacher should sign in on their own phone, tablet, or computer using the invited account. Staff should not share a manager's password. Once signed in and in the correct school workspace:

1. Open **Attendance**.
2. Choose the date, academic session, class, and arm covered by an active assignment. The selected date must be within a term and cannot be in the future.
3. Select **Load eligible students**. Only eligible enrollments in that class and arm appear; pending enrollments are excluded.
4. Mark every student **Present**, **Absent**, **Late**, or **Excused**, then save and submit the register. A register cannot be submitted while any student is unmarked.
5. A school administrator or manager finalizes the submitted register. Finalized attendance feeds the attendance summary and report cards. Corrections to finalized records require an authorized administrator or manager to reopen the register with a reason.

If the school uses paper registers, an administrator or manager can enter the marks on behalf of the class. The system records the person who entered them. Individual teacher sign-in is recommended when teachers should take attendance themselves and have an auditable record under their own accounts.

## 7. Assessments and student results

An owner, school administrator, manager, or principal sets up reusable score components and an assessment plan in **Assessments & results**. Create a plan for the session, term, class, arm, subject, grading scale, and calculation method; then add its components (for example **1st CA**, **2nd CA**, and **Examination**) and publish it for score entry.

An assigned teacher opens the published plan, enters each eligible student's component marks, saves the draft, and submits the complete result. A result needs a mark for every configured component. The school administrator or owner approves submitted results. A teacher cannot approve their own result, and administrators cannot approve a result they entered themselves. Reopening an approved result for correction requires an authorized approver and a reason.

The same plan/subject/session/class/arm assignment rules apply to assessment entry as to teaching assignments. If the teacher cannot see a plan or student, verify the teacher login is linked to the staff profile and the assignment matches the plan exactly.

## 8. Generate and publish report cards

Report-card generation and final publication are managed by an owner, school administrator, manager, or principal. Teachers can work on drafts for their assigned classes but cannot generate, approve, or finalize the school's official report cards.

1. Finish attendance registers and finalize the registers that should count for the term.
2. Ensure all active subjects assigned to each class have one complete, approved result for each student.
3. Open **Report cards** and select the academic session, term, class, and arm.
4. Choose **Generate class report cards**. Each student succeeds or reports its own missing-data validation messages. Fix missing enrollments, subjects, approved results, or finalized attendance as appropriate, then regenerate the affected drafts.
5. Open each draft to enter teacher/head-teacher remarks, conduct/effort comments, and available psychomotor, behaviour, and affective ratings. Add the relevant staff display names. Save the draft and submit it for review.
6. An authorized school administrator reviews and approves the card, then finalizes it to publish the official report. Download or preview the PDF from the report-card record.

The PDF can include the school's logo, assessment components as separate score columns, approved totals and grades, finalized attendance, ratings, remarks, and sign-off names. The configured principal signature appears on finalized cards when the school has uploaded one and the report snapshot was generated with that signature. Regenerate a draft after changing the school logo/signature so the new draft uses the current school details. Draft/review PDFs are not official signed reports.

### Psychomotor and other student traits

In a selected draft, choose **Enter student traits**. Rate the items that the school actually assessed from **1 (Poor)** to **5 (Excellent)**, or leave an item as **Not rated**. Psychomotor items are handwriting, fluency, creativity, games, sports, drawing, and musical skills. The same form also has behaviour traits (such as punctuality and neatness) and affective traits (such as co-operation, responsibility, and self-confidence). Save the draft to preserve the ratings with that student's report-card revision. The PDF prints each trait and its numeric rating, along with the rating key. These are separate observations: they do not change a student's subject marks, total, percentage, or grade. Daily attendance records remain a separate feature; the behaviour form's “Attendance” item is only a trait rating.

## 9. Understanding statuses and messages

Common statuses describe where a record is in its workflow:

- A **draft** can still be completed or corrected by an authorized person.
- **Submitted** means it is waiting for the next review/finalization step; it is not yet official.
- **Approved** means it passed the approval step but may still need final publication (for report cards).
- **Finalized** means the attendance register or report card is official and protected from ordinary edits.
- **Pending enrollment** is not counted as an eligible active enrollment for attendance or assessment rosters.

The app displays request errors and confirmations as page feedback. On the main school workspace pages, this feedback stays pinned near the lower edge of the screen while scrolling so it can be read without jumping back to the top.

## Role summary

| Role | Typical responsibilities |
| --- | --- |
| School owner | Full school administration, invite staff, academic setup, review/approve/finalize records. |
| School administrator | School setup, invite staff, academics, attendance review, assessment approval, report-card publication. |
| Principal | Invite staff, manage school academics and staff assignments, generate/review reports; final approval/finalization depends on the action's permission. |
| School manager | Operational management, staff profiles/assignments, attendance finalization, assessment setup, report-card generation/review. Cannot invite school login accounts or approve results. |
| Teacher | Take assigned-class attendance, enter/submit results for assigned subjects, view assigned-class report cards, and complete allowed draft remarks/ratings. |
| Bursar / receptionist | Access only to the areas granted to their role; they do not receive teacher attendance/result permissions. |

For detailed rules, see [staff management](staff-management.md), [student attendance](student-attendance.md), [assessments and results](assessment-results.md), [report cards](report-cards.md), and [academic setup](academic-setup.md).

"""Rebuild output/pdf/EDUstacked-School-Owner-Guide.pdf from the guide content below."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "EDUstacked-School-Owner-Guide.pdf"

NAVY = colors.HexColor("#464b71")
TEAL = colors.HexColor("#168eaf")
MINT = colors.HexColor("#7cd6c3")
PAPER = colors.HexColor("#f2f2ed")
INK = colors.HexColor("#203c31")
MUTED = colors.HexColor("#5d7067")
LINE = colors.HexColor("#d9e3dc")
PALE_GREEN = colors.HexColor("#eef6f1")
PALE_BLUE = colors.HexColor("#eef5f8")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverKicker", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=9, leading=12, textColor=TEAL, spaceAfter=7,
))
styles.add(ParagraphStyle(
    name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=29, leading=33, textColor=INK, alignment=TA_LEFT, spaceAfter=9,
))
styles.add(ParagraphStyle(
    name="CoverSubtitle", parent=styles["BodyText"], fontSize=12,
    leading=17, textColor=MUTED, spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="SectionTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=20, leading=24, textColor=INK, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="SectionIntro", parent=styles["BodyText"], fontSize=9.2,
    leading=13, textColor=MUTED, spaceAfter=11,
))
styles.add(ParagraphStyle(
    name="Subhead", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=11.3, leading=14, textColor=NAVY, spaceBefore=6, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="BodyCopy", parent=styles["BodyText"], fontSize=8.6,
    leading=11.5, textColor=INK, spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="SmallCopy", parent=styles["BodyText"], fontSize=7.4,
    leading=9.5, textColor=MUTED, spaceAfter=2,
))
styles.add(ParagraphStyle(
    name="CardTitle", parent=styles["Heading3"], fontName="Helvetica-Bold",
    fontSize=9.5, leading=12, textColor=INK, spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="TableHead", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=7.5, leading=9, textColor=colors.white,
))
styles.add(ParagraphStyle(
    name="TableCell", parent=styles["BodyText"], fontSize=7.5,
    leading=9.5, textColor=INK,
))
styles.add(ParagraphStyle(
    name="TableCellBold", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=7.5, leading=9.5, textColor=INK,
))
styles.add(ParagraphStyle(
    name="Callout", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=8.4, leading=11.5, textColor=NAVY,
))


def p(text, style="BodyCopy"):
    return Paragraph(text, styles[style])


def points(items):
    return [p(f'<font color="{TEAL.hexval()}"><b>+</b></font> {item}') for item in items]


def card(title, body, width=84 * mm, fill=colors.white):
    content = [p(title, "CardTitle"), p(body, "BodyCopy")]
    table = Table([[content]], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def simple_table(rows, widths, header=True, row_backgrounds=True):
    formatted = []
    for row_index, row in enumerate(rows):
        cell_style = "TableHead" if header and row_index == 0 else "TableCell"
        formatted.append([cell if isinstance(cell, Paragraph) else p(str(cell), cell_style) for cell in row])
    table = Table(formatted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if row_backgrounds:
        for row_index in range(1 if header else 0, len(rows)):
            if row_index % 2 == (1 if header else 0):
                commands.append(("BACKGROUND", (0, row_index), (-1, row_index), PALE_GREEN))
    table.setStyle(TableStyle(commands))
    return table


def callout(text, fill=PALE_BLUE):
    table = Table([[p(text, "Callout")]], colWidths=[178 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def page_chrome(canvas, doc):
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, page_height - 5 * mm, page_width, 5 * mm, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(INK)
    canvas.drawString(16 * mm, page_height - 12 * mm, "EDUstacked")
    canvas.setFont("Helvetica", 7.3)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(page_width - 16 * mm, page_height - 12 * mm, "SCHOOL OWNER'S GUIDE")
    canvas.setStrokeColor(LINE)
    canvas.line(16 * mm, 13 * mm, page_width - 16 * mm, 13 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(16 * mm, 8 * mm, "A practical guide to setting up and using your school workspace")
    canvas.drawRightString(page_width - 16 * mm, 8 * mm, f"{doc.page}")
    canvas.restoreState()


story = []

# Page 1: overview and first steps.
story.append(Spacer(1, 15 * mm))
story.append(p("A PRACTICAL GUIDE FOR SCHOOL OWNERS AND ADMINISTRATORS", "CoverKicker"))
story.append(p("Run your school<br/>with more clarity.", "CoverTitle"))
story.append(p(
    "EDUstacked brings student records, staff responsibilities, attendance, assessment, report cards, "
    "parent access, fee tracking, and school messaging into one school workspace.",
    "CoverSubtitle",
))
story.append(Spacer(1, 7 * mm))
feature_cards = [[
    card("Organize", "Keep students, guardians, staff, classes, sessions, and subjects together.", 57 * mm, PALE_GREEN),
    card("Coordinate", "Give teachers access to the classes and subjects assigned to them.", 57 * mm, PALE_BLUE),
    card("Communicate", "Share parent updates, manage fee payments, and send tracked SMS.", 57 * mm, PAPER),
]]
features = Table(feature_cards, colWidths=[59 * mm, 59 * mm, 60 * mm])
features.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
story.append(features)
story.append(Spacer(1, 8 * mm))
story.append(p("Your first setup", "Subhead"))
setup_rows = [
    ["1", "Register", "Create the school workspace and verify the administrator's email."],
    ["2", "Set up academics", "Add sessions and terms, classes and arms, subjects, and the school's grading scale."],
    ["3", "Add people", "Enroll students, invite staff, link staff profiles, and invite guardians."],
    ["4", "Start daily work", "Assign teachers, take attendance, configure assessment plans, and enter results."],
    ["5", "Share outcomes", "Review and finalize report cards; activate parent fee access and school messaging."],
]
story.append(simple_table(setup_rows, [10 * mm, 34 * mm, 134 * mm], header=False))
story.append(Spacer(1, 7 * mm))
story.append(callout(
    "Use EDUstacked in a current web browser on desktop, tablet, or phone. It can be installed from the browser as a web app. "
    "Offline attendance is available for a register prepared on that device; internet is still needed to sync, submit, or finalize it.",
    PALE_GREEN,
))

story.append(PageBreak())

# Page 2: school setup and role clarity.
story.append(p("01  |  PREPARE YOUR SCHOOL WORKSPACE", "CoverKicker"))
story.append(p("Set up the people and school year first.", "SectionTitle"))
story.append(p(
    "Start with the school structure. The selected school, academic session, term, class, arm, and subject must match "
    "when you create enrollments, teacher assignments, attendance registers, and assessment plans.",
    "SectionIntro",
))
story.append(p("Academic setup", "Subhead"))
story.extend(points([
    "Create an academic session and its term start and end dates.",
    "Create each class and arm, then add subjects and assign them to the classes that study them.",
    "Create a grading scale and enter the school's approved grade bands before activating it.",
    "Add students and enroll each student in the correct session, class, and arm.",
    "Add school details and optional branding, including a logo and principal signature for reports.",
]))
story.append(Spacer(1, 3 * mm))
story.append(p("Give each person the right access", "Subhead"))
roles = [
    ["Role", "What they can do"],
    ["School owner", "Manage the school workspace, invite staff, configure academics, oversee records and billing, and review official reports."],
    ["Administrator / principal", "Manage school setup and staff access, oversee academics, and perform permitted approval and publication actions."],
    ["School manager", "Manage day-to-day students and academic operations, staff profiles and assignments, attendance finalization, and report-card drafts. Cannot approve results or invite school login accounts."],
    ["Teacher", "Work with assigned classes: take attendance and enter or submit scores for assigned subjects. A teacher cannot approve their own result."],
    ["Accountant / bursar", "Use the finance areas granted to the role, including school fee records and payment tracking."],
    ["Parent / guardian", "See only the children linked to their account, including available fees, attendance, finalized report cards, and school announcements."],
]
story.append(simple_table(roles, [39 * mm, 139 * mm]))
story.append(Spacer(1, 5 * mm))
story.append(p("School access and staff profiles are different", "Subhead"))
story.append(p(
    "An invitation gives a person a school login and role. A staff profile stores their employment details. For a teacher, "
    "link the login to the staff profile, designate the teacher, then add a teaching assignment for each session, class, arm, "
    "subject, and date range. One teacher can have several assignments. The login alone does not assign classes or subjects.",
    "BodyCopy",
))
story.append(callout(
    "Email verification confirms the administrator's email address. EDUstacked school verification is a separate platform review; "
    "basic school setup can continue while that review is pending.",
))

story.append(PageBreak())

# Page 3: the term workflow and report cards.
story.append(p("02  |  TEACHING, ASSESSMENT, AND REPORTS", "CoverKicker"))
story.append(p("A clear path from class work to report card.", "SectionTitle"))
story.append(p(
    "Give staff responsibilities that match the work they should perform. EDUstacked checks each action against the user's "
    "school role and, for teachers, the active class and subject assignment.",
    "SectionIntro",
))
story.append(p("Attendance", "Subhead"))
story.extend(points([
    "A teacher opens Attendance, chooses a date within a term, session, class, and arm covered by an active assignment, then loads the eligible student list.",
    "Mark students present, absent, late, or excused and save the register. Submit it when all students are marked; an authorized school administrator or manager finalizes it.",
    "Only finalized registers count in official attendance summaries and report cards. Missing registers are not treated as absences.",
]))
story.append(p("Offline attendance", "Subhead"))
story.append(p(
    "While online, prepare a draft register on the device that will be used. If the internet drops, save marks on that device. "
    "Reconnect and sync the saved draft. The school workspace checks the user's access and register version before accepting it. "
    "Offline marks are not shared with the school until they sync; submission and finalization need internet.",
    "BodyCopy",
))
story.append(p("Assessments and grades", "Subhead"))
story.extend(points([
    "An owner, administrator, principal, or manager sets up reusable score components and a plan for the session, term, class, arm, subject, and grading scale.",
    "Plans can include separate components such as 1st CA, 2nd CA, and Examination. Choose raw-score addition or weighted components and make the configured totals valid before publishing.",
    "Assigned teachers enter complete component marks and submit each student's result. An authorized administrator approves it; a person cannot approve a result they entered.",
]))
story.append(p("Report cards", "Subhead"))
story.extend(points([
    "After the subject results are approved, an authorized school administrator or manager generates report-card drafts for the class and term.",
    "Add comments and student trait ratings, submit for review, approve, and finalize the report. The PDF can show CA columns, examination marks, grades, attendance, class positions, remarks, and sign-offs.",
]))
story.append(Spacer(1, 3 * mm))
story.append(callout(
    "Report-card positions are shown as an ordinal and the full class size, for example, 2nd of 34. A report-card credit is used "
    "only on a student's first successful finalization for that term. Drafts, review, approval, previews, downloads, and reprints are free.",
    PALE_GREEN,
))

story.append(PageBreak())

# Page 4: parents and fees.
story.append(p("03  |  PARENTS AND SCHOOL FEES", "CoverKicker"))
story.append(p("Connect families to the right information.", "SectionTitle"))
story.append(p(
    "The parent portal is linked to existing student records. A parent does not create an unlinked student record or receive staff access.",
    "SectionIntro",
))
story.append(p("How a parent gets access", "Subhead"))
story.extend(points([
    "A staff member adds the parent's contact details to the student's guardian record and sends an invitation to the guardian's email address.",
    "The parent opens the one-time activation link, sets a password (or verifies the existing account), and signs in through the EDUstacked login page.",
    "The parent sees only actively linked children. They can review available attendance, finalized report cards and PDFs, school announcements, notifications, and fee information.",
]))
story.append(p("Set up and collect school fees", "Subhead"))
fee_rows = [
    ["School office", "Create a fee schedule for the session, term, class (and optionally arm), category, amount, and due date. Issue charges to eligible student enrollments."],
    ["Parent / guardian", "Open School fees in the parent portal, select a linked child or linked siblings at one school, enter a partial or full amount, and continue to secure checkout."],
    ["Payment confirmation", "The configured Paystack or Flutterwave provider verifies the transaction before the school balance is updated. Parents can view payment history and download available receipts."],
    ["At-school payment", "Authorized staff can record a physical payment such as cash, POS, or bank transfer. Keep the payment record and receipt available to the family."],
]
story.append(simple_table([["Who", "How it works"], *fee_rows], [39 * mm, 139 * mm]))
story.append(Spacer(1, 5 * mm))
story.append(p("A few safeguards", "Subhead"))
story.extend(points([
    "A parent's fee checkout can include charges for linked students at the same school only.",
    "Parents cannot view draft or unfinalized report cards, and they cannot enter or change school records.",
    "Each school uses its own configured payment account. Provider availability and school setup must be completed before online collection can begin.",
]))
story.append(callout(
    "To add a family, first create or update the guardian record on the student profile, then send the parent portal invitation. "
    "An invitation is what connects the parent's login to the student.",
    PALE_BLUE,
))

story.append(PageBreak())

# Page 5: SMS, charges, requirements, onboarding.
story.append(p("04  |  SMS, COSTS, AND GETTING STARTED", "CoverKicker"))
story.append(p("Stay in touch and plan your launch.", "SectionTitle"))
story.append(p("School SMS wallet", "Subhead"))
story.extend(points([
    "Each school receives 50 free SMS segments per calendar month. The free allowance resets monthly; unused free segments expire at month end.",
    "The wallet uses the free allowance first, then purchased credits. Purchased credits do not expire. Longer or Unicode messages may use more than one segment.",
    "Messages are sent through Termii. The SMS page shows recent message status, delivery information, wallet activity, and remaining balances. Fee receipts and one-time verification codes also use the school SMS wallet.",
    "School owners and authorized administrators can buy available bundles in the SMS page. Checkout offers Flutterwave or Paystack where enabled; credits are added after payment verification.",
]))
story.append(p("Report-card credits", "Subhead"))
story.append(p(
    "EDUstacked uses pay-per-credit for report-card finalization, not a school workspace subscription. The current Billing page lists "
    "the available credit packages and total price. For reference, the seeded options are:",
    "BodyCopy",
))
credit_rows = [
    ["Package", "Credits", "Current total"],
    ["Starter", "100", "NGN 30,000"],
    ["Growth", "300", "NGN 45,000"],
    ["School", "500", "NGN 50,000"],
]
story.append(simple_table(credit_rows, [52 * mm, 40 * mm, 86 * mm]))
story.append(Spacer(1, 3 * mm))
story.append(p(
    "Only the first successful finalization of a student's report card for a session and term uses a credit. Correcting that same "
    "card does not use another credit. A manually adjusted testing balance is not a verified purchase receipt.",
    "SmallCopy",
))
story.append(p("One-time assisted onboarding", "Subhead"))
training_rows = [
    ["Remote training", "NGN 15,000 one-time fee. Includes guided setup and training for school staff."],
    ["On-site training", "NGN 30,000 one-time fee. The school also covers transport."],
]
story.append(simple_table([["Option", "What is included"], *training_rows], [42 * mm, 136 * mm]))
story.append(Spacer(1, 3 * mm))
story.append(p(
    "Training is optional and separate from report-card credits. Request assisted onboarding from the welcome page; EDUstacked will confirm "
    "availability and payment steps before booking. Offline CBT is a separate add-on license; contact EDUstacked for its current offer.",
    "SmallCopy",
))
story.append(p("Before your first term", "Subhead"))
story.extend(points([
    "Prepare student names, admission numbers, classes, arms, and guardian contact details.",
    "Agree on school sessions, term dates, subjects, grading rules, assessment components, and report-card wording.",
    "Give each staff member an individual email login and role; link teachers to their staff profiles and assignments.",
    "Set up the school's payment provider for online fees and confirm the Termii SMS setup before relying on SMS delivery.",
]))
story.append(Spacer(1, 3 * mm))
story.append(callout(
    "Start with Register Your School on the EDUstacked website. Use Request a demo or Request assisted onboarding on the welcome page "
    "if your team wants a walkthrough.",
    PALE_GREEN,
))

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
document = SimpleDocTemplate(
    str(OUTPUT), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
    topMargin=18 * mm, bottomMargin=18 * mm,
    title="EDUstacked School Owner Guide", author="EDUstacked",
    subject="School setup, staff access, report cards, parent payments, and SMS",
)
document.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
print(OUTPUT)

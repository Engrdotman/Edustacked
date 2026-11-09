import { useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { ApiError, cbtList, cbtRequest, getServiceEntitlements } from '../services/api.js'
import { useAuth } from '../auth/AuthContext.jsx'

const blankQuestion = () => ({
  subject: '', class_level: '', topic: '', text: '', question_type: 'single_choice',
  difficulty: 'medium', marks: '1', explanation: '', options: [
    { text: '', is_correct: true }, { text: '', is_correct: false },
  ], image: null,
})

function localDateTime(hoursFromNow = 1) {
  const date = new Date(Date.now() + hoursFromNow * 60 * 60 * 1000)
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset())
  return date.toISOString().slice(0, 16)
}

function localDateTimeFromValue(value) {
  const date = new Date(value)
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset())
  return date.toISOString().slice(0, 16)
}

function errorMessage(error) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

export default function CbtManagementPage({ navigate }) {
  const { selectedSchool, signOut } = useAuth()
  const canPublish = ['platform_superadmin', 'school_owner', 'school_admin', 'principal'].includes(selectedSchool?.role)
  const canAssign = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(selectedSchool?.role)
  const [tab, setTab] = useState('questions')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [licensed, setLicensed] = useState(false)
  const [setup, setSetup] = useState({ classes: [], subjects: [], sessions: [], terms: [], eligible_students: [] })
  const [questions, setQuestions] = useState([])
  const [examinations, setExaminations] = useState([])
  const [questionSearch, setQuestionSearch] = useState('')
  const [questionFilter, setQuestionFilter] = useState({ subject: '', class_level: '', status: '' })
  const [questionForm, setQuestionForm] = useState(blankQuestion)
  const [editingQuestion, setEditingQuestion] = useState('')
  const [editingExam, setEditingExam] = useState('')
  const [examForm, setExamForm] = useState({
    title: '', description: '', instructions: '', subject: '', class_level: '', academic_session: '', term: '',
    duration_minutes: 40, starts_at: localDateTime(1), ends_at: localDateTime(2), pass_mark: 0,
    randomize_question_order: false, randomize_answer_options: false, maximum_attempts: 1,
    selection_method: 'manual', random_question_count: 10, difficulty: '', topic: '', question_ids: [],
  })
  const [expandedAssignment, setExpandedAssignment] = useState('')
  const [selectedStudents, setSelectedStudents] = useState([])
  const [assignments, setAssignments] = useState([])

  async function loadRecords() {
    const [nextSetup, nextQuestions, nextExams] = await Promise.all([
      cbtRequest('setup/'), cbtList('questions/'), cbtList('examinations/'),
    ])
    setSetup(nextSetup)
    setQuestions(nextQuestions)
    setExaminations(nextExams)
  }

  useEffect(() => {
    let mounted = true
    async function initialize() {
      try {
        const entitlements = await getServiceEntitlements()
        const hasLicense = entitlements.some((item) => item.service_code === 'offline_cbt' && item.is_current)
        if (!mounted) return
        setLicensed(hasLicense)
        if (hasLicense) await loadRecords()
      } catch (requestError) {
        if (mounted) setError(errorMessage(requestError))
      } finally {
        if (mounted) setLoading(false)
      }
    }
    initialize()
    return () => { mounted = false }
  }, [])

  const visibleQuestions = useMemo(() => questions.filter((question) => {
    const matchesSearch = !questionSearch || `${question.text} ${question.topic}`.toLowerCase().includes(questionSearch.toLowerCase())
    return matchesSearch && (!questionFilter.subject || String(question.subject) === questionFilter.subject)
      && (!questionFilter.class_level || String(question.class_level) === questionFilter.class_level)
      && (!questionFilter.status || question.status === questionFilter.status)
  }), [questions, questionSearch, questionFilter])

  const examQuestionChoices = useMemo(() => questions.filter((question) => (
    question.status === 'published'
    && String(question.subject) === String(examForm.subject)
    && String(question.class_level) === String(examForm.class_level)
  )), [questions, examForm.subject, examForm.class_level])

  const availableTerms = setup.terms.filter((term) => !examForm.academic_session || String(term.academic_session) === String(examForm.academic_session))

  async function run(action, successMessage = '') {
    setWorking(true)
    setError('')
    setNotice('')
    try {
      await action()
      if (successMessage) setNotice(successMessage)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setWorking(false)
    }
  }

  function clearQuestionForm() {
    setQuestionForm(blankQuestion())
    setEditingQuestion('')
  }

  async function submitQuestion(event) {
    event.preventDefault()
    await run(async () => {
      const body = new FormData()
      for (const field of ['subject', 'class_level', 'topic', 'text', 'question_type', 'difficulty', 'marks', 'explanation']) {
        body.append(field, questionForm[field] ?? '')
      }
      body.append('options', JSON.stringify(questionForm.question_type === 'text' ? [] : questionForm.options))
      if (questionForm.image) body.append('image', questionForm.image)
      const url = editingQuestion ? `questions/${editingQuestion}/` : 'questions/'
      await cbtRequest(url, { method: editingQuestion ? 'PATCH' : 'POST', body })
      await loadRecords()
      clearQuestionForm()
    }, editingQuestion ? 'Question updated.' : 'Question saved as a draft. Publish it when it is ready for examinations.')
  }

  function editQuestion(question) {
    setEditingQuestion(question.id)
    setQuestionForm({
      subject: String(question.subject), class_level: String(question.class_level), topic: question.topic || '',
      text: question.text, question_type: question.question_type, difficulty: question.difficulty,
      marks: String(question.marks), explanation: question.explanation || '', image: null,
      options: question.options.map((option) => ({ text: option.text, is_correct: option.is_correct })),
    })
    setTab('questions')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function publishQuestion(question) {
    await run(async () => {
      await cbtRequest(`questions/${question.id}/publish/`, { method: 'POST', body: {} })
      await loadRecords()
    }, 'Question published.')
  }

  async function archiveQuestion(question) {
    if (!window.confirm('Archive this question? It will no longer be available for new exams.')) return
    await run(async () => {
      await cbtRequest(`questions/${question.id}/archive/`, { method: 'POST', body: {} })
      await loadRecords()
    }, 'Question archived.')
  }

  async function deleteQuestion(question) {
    if (!window.confirm('Delete this unused draft question? Questions referenced by exam history are protected.')) return
    await run(async () => {
      await cbtRequest(`questions/${question.id}/`, { method: 'DELETE' })
      await loadRecords()
    }, 'Draft question deleted.')
  }

  function updateQuestionOption(index, change) {
    setQuestionForm((previous) => ({
      ...previous,
      options: previous.options.map((option, optionIndex) => optionIndex === index ? { ...option, ...change } : option),
    }))
  }

  function chooseCorrectOption(index, checked) {
    if (questionForm.question_type === 'single_choice') {
      setQuestionForm((previous) => ({
        ...previous,
        options: previous.options.map((option, optionIndex) => ({ ...option, is_correct: optionIndex === index })),
      }))
      return
    }
    updateQuestionOption(index, { is_correct: checked })
  }

  async function submitExam(event) {
    event.preventDefault()
    await run(async () => {
      const body = {
        title: examForm.title,
        description: examForm.description,
        instructions: examForm.instructions,
        subject: Number(examForm.subject),
        class_level: Number(examForm.class_level),
        academic_session: Number(examForm.academic_session),
        term: examForm.term ? Number(examForm.term) : null,
        duration_minutes: Number(examForm.duration_minutes),
        starts_at: new Date(examForm.starts_at).toISOString(),
        ends_at: new Date(examForm.ends_at).toISOString(),
        pass_mark: Number(examForm.pass_mark),
        randomize_question_order: examForm.randomize_question_order,
        randomize_answer_options: examForm.randomize_answer_options,
        maximum_attempts: Number(examForm.maximum_attempts),
        selection_method: examForm.selection_method,
        question_ids: examForm.selection_method === 'manual' ? examForm.question_ids : [],
      }
      if (examForm.selection_method === 'random') {
        body.random_question_count = Number(examForm.random_question_count)
        body.question_criteria = {
          ...(examForm.difficulty ? { difficulty: examForm.difficulty } : {}),
          ...(examForm.topic ? { topic: examForm.topic } : {}),
        }
      }
      await cbtRequest(editingExam ? `examinations/${editingExam}/` : 'examinations/', { method: editingExam ? 'PATCH' : 'POST', body })
      await loadRecords()
      setExamForm((previous) => ({ ...previous, title: '', description: '', instructions: '', question_ids: [] }))
      setEditingExam('')
      setTab('examinations')
    }, editingExam ? 'Examination draft updated.' : 'Examination draft created. Review its schedule and question selection before publishing.')
  }

  function editExam(exam) {
    setEditingExam(exam.id)
    setExamForm({
      title: exam.title, description: exam.description || '', instructions: exam.instructions || '',
      subject: String(exam.subject), class_level: String(exam.class_level), academic_session: String(exam.academic_session),
      term: exam.term ? String(exam.term) : '', duration_minutes: exam.duration_minutes,
      starts_at: localDateTimeFromValue(exam.starts_at), ends_at: localDateTimeFromValue(exam.ends_at), pass_mark: exam.pass_mark,
      randomize_question_order: exam.randomize_question_order, randomize_answer_options: exam.randomize_answer_options,
      maximum_attempts: exam.maximum_attempts, selection_method: exam.selection_method,
      random_question_count: exam.random_question_count || 10,
      difficulty: exam.question_criteria?.difficulty || '', topic: exam.question_criteria?.topic || '',
      question_ids: exam.selection_method === 'manual' ? exam.selected_questions.map((item) => item.source_question_id) : [],
    })
    setTab('examinations')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function publishExam(exam) {
    await run(async () => {
      await cbtRequest(`examinations/${exam.id}/publish/`, { method: 'POST', body: {} })
      await loadRecords()
    }, 'Examination published and its question snapshot locked.')
  }

  async function transitionExam(exam, nextStatus) {
    await run(async () => {
      await cbtRequest(`examinations/${exam.id}/status/`, { method: 'POST', body: { status: nextStatus } })
      await loadRecords()
    }, `Examination status changed to ${nextStatus}.`)
  }

  async function deleteExam(exam) {
    if (!window.confirm('Delete this unassigned draft examination?')) return
    await run(async () => {
      await cbtRequest(`examinations/${exam.id}/`, { method: 'DELETE' })
      await loadRecords()
    }, 'Draft examination deleted.')
  }

  async function openAssignments(exam) {
    setExpandedAssignment(expandedAssignment === exam.id ? '' : exam.id)
    setSelectedStudents([])
    setAssignments([])
    if (expandedAssignment === exam.id) return
    try {
      const [roster, assigned] = await Promise.all([
        cbtRequest(`setup/?class_level=${exam.class_level}&academic_session=${exam.academic_session}`),
        cbtList(`examinations/${exam.id}/assignments/`),
      ])
      setSetup((previous) => ({ ...previous, eligible_students: roster.eligible_students }))
      setAssignments(assigned)
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  async function assignStudents(exam, allStudents) {
    await run(async () => {
      const result = await cbtRequest(`examinations/${exam.id}/assignments/`, {
        method: 'POST',
        body: allStudents ? { all_students: true } : { student_ids: selectedStudents.map(Number) },
      })
      const latest = await cbtList(`examinations/${exam.id}/assignments/`)
      setAssignments(latest)
      setSelectedStudents([])
      setNotice(`${result.assigned} new assignment(s); ${result.already_assigned} already existed. Total: ${result.total_assignments}.`)
    })
  }

  async function handleSignOut() {
    await signOut()
    navigate('/')
  }

  return (
    <main className="app-page">
      <header className="app-topbar">
        <BrandMark navigate={navigate} />
        <nav className="page-actions" aria-label="Page actions">
          <button className="text-button" type="button" onClick={() => navigate('/app')}>Dashboard</button>
          <button className="text-button" type="button" onClick={handleSignOut}>Sign out</button>
        </nav>
      </header>
      <section className="app-content cbt-content">
        <p className="eyebrow">{selectedSchool?.school_name} · OFFLINE CBT</p>
        <h1 className="app-heading">Question bank <em>&amp; exams</em></h1>
        <p className="intro">Prepare reusable questions, publish scheduled exams, and assign them to eligible students in this school.</p>

        {error && <p className="form-error" role="alert">{error}</p>}
        {notice && <p className="form-success" role="status">{notice}</p>}
        {loading ? <p className="loading-message" role="status">Checking the CBT license…</p> : !licensed ? (
          <section className="access-panel">
            <h2>CBT license required</h2>
            <p>This school does not have an active Offline CBT license. Core EDUstacked features remain available.</p>
            <button className="primary-button" type="button" onClick={() => navigate('/app/services')}>View service license</button>
          </section>
        ) : (
          <>
            <div className="cbt-tabs" role="tablist" aria-label="CBT management">
              <button type="button" role="tab" aria-selected={tab === 'questions'} className={tab === 'questions' ? 'active' : ''} onClick={() => setTab('questions')}>Question bank ({questions.length})</button>
              <button type="button" role="tab" aria-selected={tab === 'examinations'} className={tab === 'examinations' ? 'active' : ''} onClick={() => setTab('examinations')}>Examinations ({examinations.length})</button>
            </div>

            {tab === 'questions' ? (
              <>
                <section className="cbt-panel" aria-labelledby="question-form-title">
                  <p className="panel-kicker">{editingQuestion ? 'EDIT QUESTION' : 'QUESTION AUTHORING'}</p>
                  <h2 id="question-form-title">{editingQuestion ? 'Update question' : 'Create a question'}</h2>
                  <form className="cbt-form" onSubmit={submitQuestion}>
                    <label>Question text<textarea required rows="4" value={questionForm.text} onChange={(event) => setQuestionForm({ ...questionForm, text: event.target.value })} /></label>
                    <div className="cbt-form-grid">
                      <label>Subject<select required value={questionForm.subject} onChange={(event) => setQuestionForm({ ...questionForm, subject: event.target.value })}><option value="">Choose subject</option>{setup.subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                      <label>Class<select required value={questionForm.class_level} onChange={(event) => setQuestionForm({ ...questionForm, class_level: event.target.value })}><option value="">Choose class</option>{setup.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                      <label>Topic<input value={questionForm.topic} onChange={(event) => setQuestionForm({ ...questionForm, topic: event.target.value })} placeholder="e.g. Fractions" /></label>
                      <label>Question type<select value={questionForm.question_type} onChange={(event) => setQuestionForm({ ...questionForm, question_type: event.target.value, options: event.target.value === 'text' ? [] : questionForm.options.length >= 2 ? questionForm.options : blankQuestion().options })}><option value="single_choice">Single choice</option><option value="multiple_answer">Multiple answer</option><option value="text">Text response</option></select></label>
                      <label>Difficulty<select value={questionForm.difficulty} onChange={(event) => setQuestionForm({ ...questionForm, difficulty: event.target.value })}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
                      <label>Marks<input type="number" min="0.01" step="0.01" required value={questionForm.marks} onChange={(event) => setQuestionForm({ ...questionForm, marks: event.target.value })} /></label>
                    </div>
                    {questionForm.question_type !== 'text' && <fieldset className="cbt-options"><legend>Answer options and correct answer</legend>
                      {questionForm.options.map((option, index) => <div className="cbt-option-row" key={index}>
                        <input aria-label={`Answer option ${index + 1}`} required value={option.text} onChange={(event) => updateQuestionOption(index, { text: event.target.value })} placeholder={`Option ${index + 1}`} />
                        <label><input type={questionForm.question_type === 'single_choice' ? 'radio' : 'checkbox'} name="correct-answer" checked={option.is_correct} onChange={(event) => chooseCorrectOption(index, event.target.checked)} /> Correct</label>
                        <button className="text-button" type="button" aria-label={`Remove option ${index + 1}`} disabled={questionForm.options.length <= 2} onClick={() => setQuestionForm({ ...questionForm, options: questionForm.options.filter((_, optionIndex) => optionIndex !== index) })}>Remove</button>
                      </div>)}
                      <button className="secondary-button" type="button" onClick={() => setQuestionForm({ ...questionForm, options: [...questionForm.options, { text: '', is_correct: false }] })}>Add option</button>
                    </fieldset>}
                    <label>Explanation (optional)<textarea rows="2" value={questionForm.explanation} onChange={(event) => setQuestionForm({ ...questionForm, explanation: event.target.value })} /></label>
                    <label>Question image (optional)<input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setQuestionForm({ ...questionForm, image: event.target.files?.[0] || null })} /></label>
                    <div className="cbt-actions"><button className="primary-button" disabled={working}>{working ? 'Saving…' : editingQuestion ? 'Save changes' : 'Save draft question'}</button>{editingQuestion && <button className="secondary-button" type="button" onClick={clearQuestionForm}>Cancel edit</button>}</div>
                  </form>
                </section>

                <section className="cbt-panel" aria-labelledby="question-list-title">
                  <div className="cbt-section-heading"><div><p className="panel-kicker">SCHOOL QUESTION BANK</p><h2 id="question-list-title">Questions</h2></div></div>
                  <div className="cbt-filters">
                    <label>Search<input value={questionSearch} onChange={(event) => setQuestionSearch(event.target.value)} placeholder="Question text or topic" /></label>
                    <label>Subject<select value={questionFilter.subject} onChange={(event) => setQuestionFilter({ ...questionFilter, subject: event.target.value })}><option value="">All subjects</option>{setup.subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                    <label>Class<select value={questionFilter.class_level} onChange={(event) => setQuestionFilter({ ...questionFilter, class_level: event.target.value })}><option value="">All classes</option>{setup.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                    <label>Status<select value={questionFilter.status} onChange={(event) => setQuestionFilter({ ...questionFilter, status: event.target.value })}><option value="">All statuses</option><option value="draft">Draft</option><option value="published">Published</option><option value="archived">Archived</option></select></label>
                  </div>
                  <div className="cbt-card-list">{visibleQuestions.map((question) => <article className="cbt-record" key={question.id}>
                    <div><div className="cbt-record-meta"><span>{question.subject_name}</span><span>{question.class_name}</span><span>{question.difficulty}</span><span>{question.marks} marks</span><strong className={`cbt-status status-${question.status}`}>{question.status}</strong></div><h3>{question.text}</h3><p>{question.topic || 'No topic'} · {question.question_type.replaceAll('_', ' ')}</p>
                      {question.image && <img className="cbt-question-image" src={question.image} alt="Question attachment" />}
                    </div>
                    <div className="cbt-actions cbt-record-actions"><button className="text-button" type="button" onClick={() => editQuestion(question)}>Edit</button>{question.status !== 'published' && question.status !== 'archived' && <button className="text-button" type="button" disabled={working} onClick={() => publishQuestion(question)}>Publish</button>}{question.status !== 'archived' && <button className="text-button" type="button" disabled={working} onClick={() => archiveQuestion(question)}>Archive</button>}{question.status === 'draft' && <button className="text-button danger-text" type="button" disabled={working} onClick={() => deleteQuestion(question)}>Delete</button>}</div>
                  </article>)}{visibleQuestions.length === 0 && <p className="selection-note">No questions match these filters.</p>}</div>
                </section>
              </>
            ) : (
              <>
                <section className="cbt-panel" aria-labelledby="exam-form-title">
                  <p className="panel-kicker">EXAM SETUP</p><h2 id="exam-form-title">{editingExam ? 'Edit examination draft' : 'Create examination draft'}</h2>
                  <form className="cbt-form" onSubmit={submitExam}>
                    <label>Examination title<input required value={examForm.title} onChange={(event) => setExamForm({ ...examForm, title: event.target.value })} /></label>
                    <div className="cbt-form-grid">
                      <label>Subject<select required value={examForm.subject} onChange={(event) => setExamForm({ ...examForm, subject: event.target.value, question_ids: [] })}><option value="">Choose subject</option>{setup.subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                      <label>Class<select required value={examForm.class_level} onChange={(event) => setExamForm({ ...examForm, class_level: event.target.value, question_ids: [] })}><option value="">Choose class</option>{setup.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                      <label>Academic session<select required value={examForm.academic_session} onChange={(event) => setExamForm({ ...examForm, academic_session: event.target.value, term: '' })}><option value="">Choose session</option>{setup.sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                      <label>Term (optional)<select value={examForm.term} onChange={(event) => setExamForm({ ...examForm, term: event.target.value })}><option value="">No term</option>{availableTerms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                      <label>Duration (minutes)<input type="number" min="1" max="600" required value={examForm.duration_minutes} onChange={(event) => setExamForm({ ...examForm, duration_minutes: event.target.value })} /></label>
                      <label>Pass mark<input type="number" min="0" step="0.01" required value={examForm.pass_mark} onChange={(event) => setExamForm({ ...examForm, pass_mark: event.target.value })} /></label>
                      <label>Start date and time<input type="datetime-local" required value={examForm.starts_at} onChange={(event) => setExamForm({ ...examForm, starts_at: event.target.value })} /></label>
                      <label>End date and time<input type="datetime-local" required value={examForm.ends_at} onChange={(event) => setExamForm({ ...examForm, ends_at: event.target.value })} /></label>
                      <label>Maximum attempts<input type="number" min="1" max="10" required value={examForm.maximum_attempts} onChange={(event) => setExamForm({ ...examForm, maximum_attempts: event.target.value })} /></label>
                      <label>Question selection<select value={examForm.selection_method} onChange={(event) => setExamForm({ ...examForm, selection_method: event.target.value, question_ids: [] })}><option value="manual">Choose questions manually</option><option value="random">Random from question bank</option></select></label>
                    </div>
                    <label>Description<textarea rows="2" value={examForm.description} onChange={(event) => setExamForm({ ...examForm, description: event.target.value })} /></label>
                    <label>Student instructions<textarea rows="3" value={examForm.instructions} onChange={(event) => setExamForm({ ...examForm, instructions: event.target.value })} /></label>
                    <div className="cbt-checks"><label><input type="checkbox" checked={examForm.randomize_question_order} onChange={(event) => setExamForm({ ...examForm, randomize_question_order: event.target.checked })} /> Randomize question order</label><label><input type="checkbox" checked={examForm.randomize_answer_options} onChange={(event) => setExamForm({ ...examForm, randomize_answer_options: event.target.checked })} /> Randomize answer options</label></div>
                    {examForm.selection_method === 'manual' ? <fieldset className="cbt-options"><legend>Select published questions ({examForm.question_ids.length} selected)</legend>{examQuestionChoices.map((question) => <label className="cbt-question-choice" key={question.id}><input type="checkbox" checked={examForm.question_ids.includes(question.id)} onChange={(event) => setExamForm({ ...examForm, question_ids: event.target.checked ? [...examForm.question_ids, question.id] : examForm.question_ids.filter((id) => id !== question.id) })} /><span>{question.text}</span><small>{question.marks} marks · {question.difficulty}</small></label>)}{examQuestionChoices.length === 0 && <p className="selection-note">Publish questions for the selected subject and class first.</p>}</fieldset> : <div className="cbt-form-grid"><label>Number of questions<input type="number" min="1" max="100" value={examForm.random_question_count} onChange={(event) => setExamForm({ ...examForm, random_question_count: event.target.value })} /></label><label>Difficulty filter<select value={examForm.difficulty} onChange={(event) => setExamForm({ ...examForm, difficulty: event.target.value })}><option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label><label>Topic filter<input value={examForm.topic} onChange={(event) => setExamForm({ ...examForm, topic: event.target.value })} /></label></div>}
                    <div className="cbt-actions"><button className="primary-button" disabled={working}>{working ? 'Saving…' : editingExam ? 'Save draft changes' : 'Save examination draft'}</button>{editingExam && <button className="secondary-button" type="button" onClick={() => { setEditingExam(''); setExamForm((previous) => ({ ...previous, title: '', description: '', instructions: '', question_ids: [] })) }}>Cancel edit</button>}</div>
                  </form>
                </section>

                <section className="cbt-panel" aria-labelledby="exam-list-title">
                  <p className="panel-kicker">EXAM HISTORY</p><h2 id="exam-list-title">Examinations</h2>
                  <div className="cbt-card-list">{examinations.map((exam) => <article className="cbt-record cbt-exam-record" key={exam.id}>
                    <div><div className="cbt-record-meta"><span>{exam.subject_name}</span><span>{exam.class_name}</span><span>{exam.session_name}</span><strong className={`cbt-status status-${exam.status}`}>{exam.status}</strong></div><h3>{exam.title}</h3><p>{exam.starts_at ? new Date(exam.starts_at).toLocaleString() : ''} · {exam.duration_minutes} min · {exam.total_marks} marks · {exam.selected_questions.length} questions</p></div>
                    <div className="cbt-actions cbt-record-actions">{exam.status === 'draft' && <button className="text-button" type="button" onClick={() => editExam(exam)}>Edit draft</button>}{exam.status === 'draft' && canPublish && <button className="primary-button" type="button" disabled={working} onClick={() => publishExam(exam)}>Validate &amp; publish</button>}{exam.status === 'draft' && <button className="text-button danger-text" type="button" onClick={() => deleteExam(exam)}>Delete draft</button>}{canAssign && exam.status !== 'draft' && exam.status !== 'completed' && exam.status !== 'archived' && <button className="secondary-button" type="button" onClick={() => openAssignments(exam)}>Assignments</button>}{canPublish && ['published', 'scheduled'].includes(exam.status) && <button className="text-button" type="button" onClick={() => transitionExam(exam, 'active')}>Mark active</button>}{canPublish && exam.status === 'active' && <button className="text-button" type="button" onClick={() => transitionExam(exam, 'completed')}>Mark completed</button>}</div>
                    {expandedAssignment === exam.id && canAssign && <div className="cbt-assignment-box"><h4>Assign students</h4><p>Only active students enrolled in {exam.class_name} for {exam.session_name} are eligible.</p><div className="cbt-roster">{setup.eligible_students.map((student) => <label key={student.id}><input type="checkbox" checked={selectedStudents.includes(String(student.id))} onChange={(event) => setSelectedStudents((previous) => event.target.checked ? [...previous, String(student.id)] : previous.filter((id) => id !== String(student.id)))} /><span>{student.name}</span><small>{student.admission_number}</small></label>)}{setup.eligible_students.length === 0 && <p>No active eligible students are enrolled in this class and session.</p>}</div><div className="cbt-actions"><button className="primary-button" type="button" disabled={working || !setup.eligible_students.length} onClick={() => assignStudents(exam, true)}>Assign entire class</button><button className="secondary-button" type="button" disabled={working || selectedStudents.length === 0} onClick={() => assignStudents(exam, false)}>Assign selected ({selectedStudents.length})</button></div><h4>Already assigned ({assignments.length})</h4>{assignments.slice(0, 8).map((item) => <p key={item.id}>{item.student_name} · {item.admission_number} · {item.status}</p>)}</div>}
                  </article>)}{examinations.length === 0 && <p className="selection-note">No examinations have been created yet.</p>}</div>
                </section>
              </>
            )}
          </>
        )}
      </section>
    </main>
  )
}

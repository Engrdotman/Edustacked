import { useCallback, useEffect, useMemo, useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { academicList, apiRequest } from '../services/api.js'

const emptyPlan = { academic_session: '', term: '', class_level: '', class_arm: '', subject: '', grading_scale: '', name: '', calculation_method: 'raw' }
const arrayFrom = (payload) => Array.isArray(payload) ? payload : (payload?.results || [])
const messageFor = (error) => {
  if (error?.fields && typeof error.fields === 'object') return Object.values(error.fields).flat().filter((x) => typeof x === 'string').join(' ')
  return error?.message || 'The request could not be completed.'
}

export default function AssessmentResultsPage({ navigate }) {
  const { selectedSchool } = useAuth()
  const role = selectedSchool?.role
  const canConfigure = ['platform_superadmin', 'school_owner', 'school_admin', 'school_manager', 'principal'].includes(role)
  const canApprove = ['platform_superadmin', 'school_owner', 'school_admin'].includes(role)
  const [plans, setPlans] = useState([])
  const [templates, setTemplates] = useState([])
  const [sessions, setSessions] = useState([])
  const [terms, setTerms] = useState([])
  const [classes, setClasses] = useState([])
  const [arms, setArms] = useState([])
  const [subjects, setSubjects] = useState([])
  const [scales, setScales] = useState([])
  const [planForm, setPlanForm] = useState(emptyPlan)
  const [templateForm, setTemplateForm] = useState({ name: '', max_score: '100.00', default_weight: '' })
  const [templateEditId, setTemplateEditId] = useState('')
  const [componentForm, setComponentForm] = useState({ component: '', max_score: '', weight: '', position: '1' })
  const [selectedPlanId, setSelectedPlanId] = useState('')
  const [plan, setPlan] = useState(null)
  const [results, setResults] = useState([])
  const [scoreInputs, setScoreInputs] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const chosenClass = useMemo(() => classes.find((item) => String(item.id) === String(planForm.class_level)), [classes, planForm.class_level])

  const reloadPlans = useCallback(async () => {
    const data = await apiRequest('assessment-plans/?page_size=100')
    const rows = arrayFrom(data)
    setPlans(rows)
    setSelectedPlanId((current) => rows.some((item) => String(item.id) === String(current)) ? current : String(rows[0]?.id || ''))
  }, [])

  const reloadSelected = useCallback(async (id = selectedPlanId) => {
    if (!id) { setPlan(null); setResults([]); return }
    const [planData, resultsData] = await Promise.all([
      apiRequest(`assessment-plans/${id}/`),
      apiRequest(`assessment-plans/${id}/results/?page_size=100`),
    ])
    setPlan(planData)
    const rows = arrayFrom(resultsData)
    setResults(rows)
    setScoreInputs(Object.fromEntries(rows.map((row) => [row.student_id, Object.fromEntries((row.result?.scores || []).map((score) => [score.plan_component_id, score.score]))])))
  }, [selectedPlanId])

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      await reloadPlans()
      if (canConfigure) {
        const [componentData, sessionData, classData, subjectData, scaleData] = await Promise.all([
          apiRequest('assessment-components/?page_size=100'), academicList('academic-sessions/'), academicList('classes/'), academicList('subjects/'), academicList('grading-scales/'),
        ])
        setTemplates(arrayFrom(componentData)); setSessions(sessionData); setClasses(classData); setSubjects(subjectData); setScales(scaleData.filter((item) => item.is_active))
      }
    } catch (e) { setError(messageFor(e)) }
    finally { setLoading(false) }
  }, [canConfigure, reloadPlans])

  useEffect(() => { load() }, [load, selectedSchool?.school_id])
  useEffect(() => {
    if (!selectedPlanId) { setPlan(null); setResults([]); return }
    reloadSelected(selectedPlanId).catch((e) => setError(messageFor(e)))
  }, [selectedPlanId, reloadSelected])
  useEffect(() => {
    if (!canConfigure || !planForm.academic_session) { setTerms([]); return }
    academicList(`terms/?academic_session=${planForm.academic_session}`).then(setTerms).catch((e) => setError(messageFor(e)))
  }, [canConfigure, planForm.academic_session])
  useEffect(() => {
    if (!canConfigure || !planForm.class_level) { setArms([]); return }
    academicList(`classes/${planForm.class_level}/arms/`).then(setArms).catch((e) => setError(messageFor(e)))
  }, [canConfigure, planForm.class_level])

  async function run(action, message) {
    setSaving(true); setError(''); setSuccess('')
    try { await action(); if (message) setSuccess(message) }
    catch (e) { setError(messageFor(e)) }
    finally { setSaving(false) }
  }

  async function createTemplate(event) {
    event.preventDefault()
    await run(async () => {
      const body = { name: templateForm.name, max_score: templateForm.max_score }
      if (templateForm.default_weight) body.default_weight = templateForm.default_weight
      const saved = await apiRequest(templateEditId ? `assessment-components/${templateEditId}/` : 'assessment-components/', { method: templateEditId ? 'PATCH' : 'POST', body })
      setTemplates((current) => templateEditId ? current.map((item) => item.id === saved.id ? saved : item) : [...current, saved]); setTemplateForm({ name: '', max_score: '100.00', default_weight: '' }); setTemplateEditId('')
    }, templateEditId ? 'Assessment component updated.' : 'Assessment component created.')
  }

  async function toggleTemplate(item) {
    await run(async () => {
      const updated = await apiRequest(`assessment-components/${item.id}/`, { method: 'PATCH', body: { is_active: !item.is_active } })
      setTemplates((current) => current.map((entry) => entry.id === updated.id ? updated : entry))
    }, item.is_active ? 'Component deactivated.' : 'Component activated.')
  }

  async function createPlan(event) {
    event.preventDefault()
    await run(async () => {
      const created = await apiRequest('assessment-plans/', { method: 'POST', body: { ...planForm, academic_session: Number(planForm.academic_session), term: Number(planForm.term), class_level: Number(planForm.class_level), class_arm: Number(planForm.class_arm), subject: Number(planForm.subject), grading_scale: Number(planForm.grading_scale) } })
      await reloadPlans(); setSelectedPlanId(String(created.id)); setPlanForm(emptyPlan)
    }, 'Assessment plan created as a draft.')
  }

  async function addComponent(event) {
    event.preventDefault()
    if (!plan) return
    await run(async () => {
      await apiRequest(`assessment-plans/${plan.id}/components/`, { method: 'POST', body: { component: Number(componentForm.component), max_score: componentForm.max_score, weight: plan.calculation_method === 'weighted' ? componentForm.weight || null : null, position: Number(componentForm.position) } })
      await reloadSelected(plan.id); setComponentForm({ component: '', max_score: '', weight: '', position: String((plan.components?.length || 0) + 2) })
    }, 'Component added to plan.')
  }

  async function planAction(action) {
    const reason = action === 'reopen' ? window.prompt('Reason for reopening this assessment plan:') : ''
    if (action === 'reopen' && !reason?.trim()) return
    await run(async () => { await apiRequest(`assessment-plans/${plan.id}/${action}/`, { method: 'POST', body: { reason, version: plan.version } }); await reloadSelected(plan.id); await reloadPlans() }, `Plan ${action === 'publish' ? 'published' : action === 'close' ? 'closed' : 'reopened'}.`)
  }

  async function saveScores(row) {
    if (!plan || !row.result && plan.status !== 'published') return
    const scores = plan.components.map((component) => ({ plan_component_id: component.id, score: scoreInputs[row.student_id]?.[component.id] })).filter((item) => item.score !== '' && item.score !== undefined && item.score !== null)
    if (!scores.length) { setError('Enter at least one component score before saving.'); return }
    await run(async () => {
      await apiRequest(`assessment-plans/${plan.id}/results/`, { method: 'PATCH', body: { entries: [{ student_id: row.student_id, version: row.version, scores }] } })
      await reloadSelected(plan.id)
    }, 'Scores saved as a draft.')
  }

  async function resultAction(row, action) {
    const reason = action === 'reopen' ? window.prompt('Reason for correcting this approved result:') : ''
    if (action === 'reopen' && !reason?.trim()) return
    await run(async () => {
      await apiRequest(`assessment-plans/${plan.id}/results/${action}/`, { method: 'POST', body: { entries: [{ student_id: row.student_id, version: row.version }], reason } })
      await reloadSelected(plan.id)
    }, `Result ${action === 'submit' ? 'submitted' : action === 'approve' ? 'approved' : 'reopened'}.`)
  }

  return <main className="app-page"><header className="app-topbar"><BrandMark /><button className="text-button" onClick={() => navigate('/app')}>Back to home</button></header>
    <section className="app-content assessment-page"><p className="eyebrow">{selectedSchool?.school_name} · ASSESSMENTS</p><h1 className="app-heading">Assessment <em>&amp; results</em></h1><p className="intro">Set a school-specific assessment plan, enter scores, then submit and approve each student's result.</p>
      {error && <p className="form-error" role="alert">{error}</p>}{success && <p className="form-success" role="status">{success}</p>}{loading && <p className="loading-message" role="status">Loading assessments…</p>}
      <section className="assessment-panel"><div className="assessment-panel-heading"><div><p className="panel-kicker">RESULT WORKSPACE</p><h2>Choose an assessment plan</h2></div><button className="secondary-button" type="button" onClick={() => reloadSelected()} disabled={saving || !plan}>Refresh</button></div>
        <label className="assessment-field">Assessment plan<select value={selectedPlanId} onChange={(e) => setSelectedPlanId(e.target.value)}><option value="">Select a plan</option>{plans.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.class_name} {item.arm_name} · {item.subject_name} · {item.term_name}</option>)}</select></label>
        {plan && <><div className="assessment-plan-summary"><div><span>Session / term</span><strong>{plan.session_name} · {plan.term_name}</strong></div><div><span>Class / arm / subject</span><strong>{plan.class_name} {plan.arm_name} · {plan.subject_name}</strong></div><div><span>Calculation</span><strong>{plan.calculation_method === 'raw' ? 'Raw score addition' : 'Weighted components'}</strong></div><span className={`assessment-status assessment-status-${plan.status}`}>{plan.status === 'published' ? 'Published for entry' : plan.status}</span></div>
          {canConfigure && plan.status === 'draft' && <><form className="assessment-components-form" onSubmit={addComponent}><label className="assessment-field">Component<select required value={componentForm.component} onChange={(e) => { const template = templates.find((item) => String(item.id) === e.target.value); setComponentForm({ ...componentForm, component: e.target.value, max_score: template?.max_score || '', weight: template?.default_weight || componentForm.weight }) }}><option value="">Choose component</option>{templates.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name} (default {item.max_score})</option>)}</select></label><label className="assessment-field">Maximum score<input required min="0.01" step="0.01" type="number" value={componentForm.max_score} onChange={(e) => setComponentForm({ ...componentForm, max_score: e.target.value })} /></label>{plan.calculation_method === 'weighted' && <label className="assessment-field">Weight (%)<input required min="0.01" step="0.01" type="number" value={componentForm.weight} onChange={(e) => setComponentForm({ ...componentForm, weight: e.target.value })} /></label>}<label className="assessment-field">Order<input required min="1" step="1" type="number" value={componentForm.position} onChange={(e) => setComponentForm({ ...componentForm, position: e.target.value })} /></label><button className="secondary-button" disabled={saving}>Add component</button></form>
            {templates.length === 0 && <p className="assessment-help">Create a reusable component below before configuring this plan.</p>}</>}
          <div className="assessment-component-list">{(plan.components || []).map((item) => <div key={item.id}><strong>{item.component_name}</strong><span>{item.max_score} marks{item.weight ? ` · ${item.weight}% weight` : ''}</span></div>)}{!plan.components?.length && <p className="academic-empty">Add components to define the score structure.</p>}</div>
          <div className="assessment-actions">{canConfigure && plan.status === 'draft' && <button className="primary-button" onClick={() => planAction('publish')} disabled={saving || !plan.components?.length}>Publish for score entry</button>}{canConfigure && plan.status === 'published' && <button className="secondary-button" onClick={() => planAction('close')} disabled={saving}>Close plan</button>}{canConfigure && plan.status === 'closed' && <button className="secondary-button" onClick={() => planAction('reopen')} disabled={saving}>Reopen plan</button>}</div>
          {plan.status === 'published' && <div className="assessment-student-list">{results.map((row) => { const result = row.result; const editable = !result || result.status === 'draft'; const calc = result?.calculation; return <article className="assessment-student-card" key={row.student_id}><div className="assessment-student-heading"><div><strong>{row.student_name}</strong><span>{row.admission_number}</span></div><span className={`assessment-status assessment-status-${result?.status || 'not-started'}`}>{result?.status || 'Not started'}</span></div>
                <div className="assessment-score-grid">{plan.components.map((component) => <label className="assessment-field" key={component.id}>{component.component_name} / {component.max_score}<input type="number" min="0" max={component.max_score} step="0.01" disabled={!editable || saving} value={scoreInputs[row.student_id]?.[component.id] ?? ''} onChange={(e) => setScoreInputs((current) => ({ ...current, [row.student_id]: { ...(current[row.student_id] || {}), [component.id]: e.target.value } }))} /></label>)}</div>
                {calc && <div className="assessment-calculation"><span>{calc.complete ? `Total ${calc.calculated_total} / ${calc.calculated_maximum}` : `Partial ${calc.component_total} / ${calc.component_maximum}`}</span><span>{calc.percentage ? `${calc.percentage}% · Grade ${calc.grade}` : 'Complete all components for percentage and grade'}</span>{result?.status === 'approved' && <span>Approved snapshot: {result.approved_total}/{result.approved_maximum} · {result.approved_percentage}% · {result.approved_grade}</span>}</div>}
                <div className="assessment-actions">{editable && <button className="secondary-button" onClick={() => saveScores(row)} disabled={saving}>Save draft scores</button>}{result?.status === 'draft' && <button className="secondary-button" onClick={() => resultAction(row, 'submit')} disabled={saving || !calc?.complete}>Submit result</button>}{canApprove && result?.status === 'submitted' && <button className="primary-button" onClick={() => resultAction(row, 'approve')} disabled={saving}>Approve result</button>}{canApprove && result?.status === 'approved' && <button className="secondary-button" onClick={() => resultAction(row, 'reopen')} disabled={saving}>Reopen for correction</button>}</div>
                {result?.audit_events?.length > 0 && <details className="assessment-audit"><summary>Result history ({result.audit_events.length})</summary>{result.audit_events.map((event) => <p key={event.id}>{event.event_type.replaceAll('_', ' ')} · {event.actor_name}{event.reason ? ` · ${event.reason}` : ''}</p>)}</details>}</article> })}{!results.length && <p className="academic-empty">No eligible students are enrolled in this class and term.</p>}</div>}
        </>}
      </section>

      {canConfigure && <>
        <section className="assessment-panel"><div className="assessment-panel-heading"><div><p className="panel-kicker">ASSESSMENT CONFIGURATION</p><h2>Create a plan</h2></div></div><form className="assessment-form-grid" onSubmit={createPlan}><label className="assessment-field">Session<select required value={planForm.academic_session} onChange={(e) => setPlanForm({ ...planForm, academic_session: e.target.value, term: '' })}><option value="">Choose session</option>{sessions.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="assessment-field">Term<select required value={planForm.term} onChange={(e) => setPlanForm({ ...planForm, term: e.target.value })}><option value="">Choose term</option>{terms.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="assessment-field">Class<select required value={planForm.class_level} onChange={(e) => setPlanForm({ ...planForm, class_level: e.target.value, class_arm: '' })}><option value="">Choose class</option>{classes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="assessment-field">Arm<select required value={planForm.class_arm} onChange={(e) => setPlanForm({ ...planForm, class_arm: e.target.value })}><option value="">Choose arm</option>{arms.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="assessment-field">Subject<select required value={planForm.subject} onChange={(e) => setPlanForm({ ...planForm, subject: e.target.value })}><option value="">Choose subject</option>{subjects.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label className="assessment-field">Grading scale<select required value={planForm.grading_scale} onChange={(e) => setPlanForm({ ...planForm, grading_scale: e.target.value })}><option value="">Choose scale</option>{scales.map((item) => <option value={item.id} key={item.id}>{item.name} / {item.maximum_score}</option>)}</select></label><label className="assessment-field">Plan name<input required maxLength="120" placeholder="First Term Examination" value={planForm.name} onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })} /></label><label className="assessment-field">Calculation<select value={planForm.calculation_method} onChange={(e) => setPlanForm({ ...planForm, calculation_method: e.target.value })}><option value="raw">Raw score addition</option><option value="weighted">Weighted components</option></select></label><button className="primary-button" disabled={saving}>Create draft plan</button></form></section>
        <section className="assessment-panel"><div className="assessment-panel-heading"><div><p className="panel-kicker">SCHOOL COMPONENT LIBRARY</p><h2>{templateEditId ? 'Edit component template' : 'Add component template'}</h2></div></div><form className="assessment-form-grid" onSubmit={createTemplate}><label className="assessment-field">Name<input required maxLength="100" placeholder="Test, assignment, examination" value={templateForm.name} onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value })} /></label><label className="assessment-field">Default maximum score<input type="number" min="0.01" step="0.01" required value={templateForm.max_score} onChange={(e) => setTemplateForm({ ...templateForm, max_score: e.target.value })} /></label><label className="assessment-field">Default weight (optional)<input type="number" min="0.01" step="0.01" value={templateForm.default_weight} onChange={(e) => setTemplateForm({ ...templateForm, default_weight: e.target.value })} /></label><button className="secondary-button" disabled={saving}>{templateEditId ? 'Save component' : 'Create component'}</button>{templateEditId && <button className="text-button" type="button" onClick={() => { setTemplateEditId(''); setTemplateForm({ name: '', max_score: '100.00', default_weight: '' }) }}>Cancel edit</button>}</form><div className="assessment-component-list">{templates.map((item) => <div key={item.id}><strong>{item.name} {item.is_active ? '' : '(inactive)'}</strong><span>Suggested max {item.max_score}{item.default_weight ? ` · ${item.default_weight}% default weight` : ''}<span className="assessment-template-actions"><button className="text-button" type="button" onClick={() => { setTemplateEditId(String(item.id)); setTemplateForm({ name: item.name, max_score: item.max_score, default_weight: item.default_weight || '' }) }}>Edit</button><button className="text-button" type="button" onClick={() => toggleTemplate(item)}>{item.is_active ? 'Deactivate' : 'Activate'}</button></span></span></div>)}</div></section>
      </>}
    </section>
  </main>
}

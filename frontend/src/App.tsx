import { useEffect, useMemo, useState } from "react"
import siteOpsLogo from "./imports/siteops-logo.png"
import { useAuth, type Role } from "./auth/AuthProvider"

type Screen = "dashboard" | "report" | "incidents" | "queue" | "review" | "analytics" | "settings"
type Tone = "teal" | "coral" | "amber" | "green" | "danger" | "neutral"

const incidents = [
  {
    id: "INC-2026-0418",
    title: "Slip near water tank",
    location: "Level 2 — Water Tank Area",
    reporter: "Marcus Reed",
    time: "8 min ago",
    status: "Emergency",
    tone: "danger" as Tone,
  },
  {
    id: "INC-2026-0417",
    title: "Missing guardrail on east deck",
    location: "Level 4 — East Deck",
    reporter: "Elena Torres",
    time: "24 min ago",
    status: "Ready for review",
    tone: "teal" as Tone,
  },
  {
    id: "INC-2026-0416",
    title: "Unsecured material near lift",
    location: "Loading Bay B",
    reporter: "Noah Williams",
    time: "41 min ago",
    status: "Needs clarification",
    tone: "amber" as Tone,
  },
  {
    id: "INC-2026-0415",
    title: "Damaged power cable",
    location: "Level 1 — South Corridor",
    reporter: "Priya Shah",
    time: "1h ago",
    status: "Verified",
    tone: "green" as Tone,
  },
]

const iconPaths: Record<string, React.ReactNode> = {
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="3" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
    </>
  ),
  list: (
    <>
      <path d="M8 6h13M8 12h13M8 18h13" />
      <path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
    </>
  ),
  queue: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="M8 9h8M8 13h5M8 17h3" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.55V21h-4v-.08a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3v-4h.08a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63a1.7 1.7 0 0 0 1-1.55V3h4v.08a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9a1.7 1.7 0 0 0 1.55 1H21v4h-.08a1.7 1.7 0 0 0-1.52 1Z" />
    </>
  ),
  bell: (
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  warning: (
    <>
      <path d="M10.3 3.7 2.4 18a2 2 0 0 0 1.75 3h15.7a2 2 0 0 0 1.75-3L13.7 3.7a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </>
  ),
  arrow: <path d="m9 18 6-6-6-6" />,
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  shield: (
    <>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  edit: (
    <>
      <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />
    </>
  ),
  play: <path d="m8 5 11 7-11 7Z" />,
  chevron: <path d="m6 9 6 6 6-6" />,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  file: (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6M8 13h8M8 17h5" />
    </>
  ),
}

function Icon({ name, size = 18 }: { name: string size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="icon"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      {iconPaths[name]}
    </svg>
  )
}

function Button({
  children,
  kind = "primary",
  onClick,
  icon,
  disabled,
}: {
  children: React.ReactNode
  kind?: "primary" | "coral" | "danger" | "neutral" | "ghost"
  onClick?: () => void
  icon?: string
  disabled?: boolean
}) {
  return (
    <button
      className={`button button--${kind}`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  )
}

function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode
  tone?: Tone
}) {
  return <span className={`badge badge--${tone}`}>{children}</span>
}

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`logo ${compact ? "logo--compact" : ""}`}>
      <img
        alt="SiteOps Voice Intelligence"
        className="logo-image"
        src={siteOpsLogo}
      />
    </div>
  )
}

function Sidebar({
  screen,
  role,
  onNavigate,
  onLogout,
  mobileOpen,
  onClose,
}: {
  screen: Screen
  role: Role
  onNavigate: (screen: Screen) => void
  onLogout: () => void
  mobileOpen: boolean
  onClose: () => void
}) {
  const managerItems: { label: string screen: Screen icon: string }[] = [
    { label: "Command center", screen: "dashboard", icon: "grid" },
    { label: "Review queue", screen: "queue", icon: "queue" },
    { label: "All incidents", screen: "incidents", icon: "list" },
    { label: "Analytics", screen: "analytics", icon: "chart" },
  ]
  const workerItems: { label: string screen: Screen icon: string }[] = [
    { label: "Report incident", screen: "report", icon: "mic" },
    { label: "My incidents", screen: "incidents", icon: "list" },
  ]
  const items = role === "worker" ? workerItems : managerItems

  return (
    <>
      <div
        className={`sidebar-backdrop ${mobileOpen ? "is-open" : ""}`}
        onClick={onClose}
      />
      <aside className={`sidebar ${mobileOpen ? "is-open" : ""}`}>
        <div className="sidebar-logo">
          <Logo />
          <button
            aria-label="Close menu"
            className="mobile-close"
            onClick={onClose}
            type="button"
          >
            <Icon name="x" />
          </button>
        </div>
        <div className="workspace-identity">
          <span className="workspace-identity__icon">
            <Icon name={role === "worker" ? "user" : "shield"} />
          </span>
          <span>
            <small>Authenticated workspace</small>
            <strong>
              {role === "admin" ? "Admin access" : role === "manager" ? "Manager access" : "Worker access"}
            </strong>
          </span>
          <Icon name="check" size={14} />
        </div>
        <span className="nav-label">{role} workspace</span>
        <nav className="nav-list">
          {items.map((item) => (
            <button
              className={screen === item.screen ? "active" : ""}
              key={item.screen}
              onClick={() => {
                onNavigate(item.screen)
                onClose()
              }}
              type="button"
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className={screen === "settings" ? "active" : ""}
            onClick={() => onNavigate("settings")}
            type="button"
          >
            <Icon name="settings" />
            <span>Settings</span>
          </button>
          <button className="logout-button" onClick={onLogout} type="button">
            <Icon name="x" />
            <span>Sign out</span>
          </button>
          <div className="system-status">
            <span className="status-dot status-dot--green" />
            <div>
              <strong>All systems operational</strong>
              <small>4 agents connected</small>
            </div>
          </div>
          <div className="ltm-signature">
            <span>Developed within</span>
            <strong>LTM</strong>
          </div>
        </div>
      </aside>
    </>
  )
}

function Topbar({
  role,
  employeeId,
  onMenu,
  onReport,
}: {
  role: Role
  employeeId: string
  onMenu: () => void
  onReport: () => void
}) {
  return (
    <header className="topbar">
      <button
        aria-label="Open menu"
        className="menu-button"
        onClick={onMenu}
        type="button"
      >
        <span />
        <span />
        <span />
      </button>
      <div className="mobile-brand">
        <Logo compact />
      </div>
      <div className="topbar-context">
        <span className="live-chip">
          <span /> Live operations
        </span>
        <span className="site-name">LTM Riverside Development</span>
      </div>
      <div className="topbar-actions">
        {role === "worker" && (
          <Button kind="primary" icon="mic" onClick={onReport}>
            New report
          </Button>
        )}
        <button
          aria-label="Notifications"
          className="icon-button notification"
          type="button"
        >
          <Icon name="bell" />
          <span />
        </button>
        <button className="profile-button" type="button">
          <span className="avatar">{role === "worker" ? "WO" : role === "admin" ? "AD" : "MG"}</span>
          <span className="profile-copy">
            <strong>{employeeId}</strong>
            <small>{role === "worker" ? "Field operative" : role === "admin" ? "Administrator" : "Site manager"}</small>
          </span>
          <Icon name="chevron" size={14} />
        </button>
      </div>
    </header>
  )
}

function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <div className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  )
}

function MetricCard({
  label,
  value,
  note,
  tone,
  icon,
  onClick,
}: {
  label: string
  value: string
  note: string
  tone: Tone
  icon: string
  onClick?: () => void
}) {
  return (
    <button
      className={`metric-card metric-card--${tone}`}
      onClick={onClick}
      type="button"
    >
      <div className="metric-top">
        <span className={`metric-icon metric-icon--${tone}`}>
          <Icon name={icon} />
        </span>
        <span className="metric-trend">{note}</span>
      </div>
      <strong>{value}</strong>
      <span>{label}</span>
      <span className="metric-open">
        View details <Icon name="arrow" size={13} />
      </span>
    </button>
  )
}

function Dashboard({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  return (
    <>
      <PageHeader
        action={
          <Button icon="mic" onClick={() => onNavigate("report")}>
            Create report
          </Button>
        }
        description="Monitor site safety, triage incoming reports, and make informed decisions."
        eyebrow="Wednesday, 8 October"
        title="Operations command center"
      />
      <section className="metrics-grid">
        <MetricCard
          icon="file"
          label="Incidents today"
          note="+3 since 08:00"
          onClick={() => onNavigate("incidents")}
          tone="teal"
          value="12"
        />
        <MetricCard
          icon="queue"
          label="Needs review"
          note="2 high priority"
          onClick={() => onNavigate("queue")}
          tone="coral"
          value="4"
        />
        <MetricCard
          icon="warning"
          label="Pending clarification"
          note="Awaiting workers"
          onClick={() => onNavigate("queue")}
          tone="amber"
          value="3"
        />
        <MetricCard
          icon="shield"
          label="Verified"
          note="92% evidence rate"
          onClick={() => onNavigate("analytics")}
          tone="green"
          value="28"
        />
        <MetricCard
          icon="bell"
          label="Emergency"
          note="Immediate action"
          onClick={() => onNavigate("review")}
          tone="danger"
          value="1"
        />
      </section>

      <section className="section attention-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow eyebrow--coral">Priority triage</span>
            <h2>Requires your attention</h2>
          </div>
          <button
            className="text-action"
            onClick={() => onNavigate("queue")}
            type="button"
          >
            Open review queue <Icon name="arrow" size={15} />
          </button>
        </div>
        <div className="attention-grid">
          <article className="attention-card attention-card--danger">
            <div className="attention-card__top">
              <Badge tone="danger">
                <span className="status-dot status-dot--danger" /> Emergency
              </Badge>
              <span>8 min ago</span>
            </div>
            <div className="attention-icon">
              <Icon name="warning" />
            </div>
            <h3>Slip near water tank</h3>
            <p>
              Worker injury reported on Level 2. Immediate site response is
              recommended.
            </p>
            <div className="attention-meta">
              <span>INC-2026-0418</span>
              <span>Marcus Reed</span>
            </div>
            <Button kind="danger" onClick={() => onNavigate("review")}>
              Review incident <Icon name="arrow" />
            </Button>
          </article>
          <article className="attention-card attention-card--amber">
            <div className="attention-card__top">
              <Badge tone="amber">
                <Icon name="warning" size={13} /> Clarification
              </Badge>
              <span>41 min ago</span>
            </div>
            <div className="attention-icon">
              <Icon name="queue" />
            </div>
            <h3>Unsecured material near lift</h3>
            <p>
              The exact lift number and immediate risk status were not provided.
            </p>
            <div className="attention-meta">
              <span>INC-2026-0416</span>
              <span>Noah Williams</span>
            </div>
            <Button kind="coral" onClick={() => onNavigate("review")}>
              Request clarification <Icon name="arrow" />
            </Button>
          </article>
          <article className="attention-card attention-card--teal">
            <div className="attention-card__top">
              <Badge tone="teal">
                <Icon name="shield" size={13} /> Ready for review
              </Badge>
              <span>24 min ago</span>
            </div>
            <div className="attention-icon">
              <Icon name="check" />
            </div>
            <h3>Missing guardrail on east deck</h3>
            <p>
              Evidence is supported by the transcript and ready for a human
              decision.
            </p>
            <div className="attention-meta">
              <span>INC-2026-0417</span>
              <span>Elena Torres</span>
            </div>
            <Button onClick={() => onNavigate("review")}>
              Go to review <Icon name="arrow" />
            </Button>
          </article>
        </div>
      </section>

      <section className="dashboard-lower">
        <div className="panel activity-panel">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">Live feed</span>
              <h2>Recent activity</h2>
            </div>
            <button
              className="text-action"
              onClick={() => onNavigate("incidents")}
              type="button"
            >
              View all
            </button>
          </div>
          <div className="activity-list">
            {incidents.map((incident) => (
              <button
                className="activity-row"
                key={incident.id}
                onClick={() => onNavigate("review")}
                type="button"
              >
                <span
                  className={`activity-symbol activity-symbol--${incident.tone}`}
                >
                  <Icon
                    name={incident.tone === "danger" ? "warning" : "file"}
                  />
                </span>
                <span className="activity-main">
                  <strong>{incident.title}</strong>
                  <small>
                    {incident.location} · {incident.reporter}
                  </small>
                </span>
                <Badge tone={incident.tone}>{incident.status}</Badge>
                <span className="activity-time">{incident.time}</span>
                <Icon name="arrow" />
              </button>
            ))}
          </div>
        </div>
        <aside className="panel agent-panel">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">LangGraph</span>
              <h2>Agent status</h2>
            </div>
            <Badge tone="green">Operational</Badge>
          </div>
          {["Extractor", "Verifier", "Clarification", "Action / Router"].map(
            (agent, index) => (
              <div className="agent-row" key={agent}>
                <span className="agent-order">0{index + 1}</span>
                <div>
                  <strong>{agent}</strong>
                  <small>
                    {index === 1
                      ? "Evidence grounding"
                      : index === 2
                        ? "Missing field handling"
                        : index === 3
                          ? "Workflow routing"
                          : "Structured incident data"}
                  </small>
                </div>
                <span className="status-dot status-dot--green" />
              </div>
            ),
          )}
          <div className="agent-footer">
            <Icon name="shield" />
            <span>AI assists</span>
            <strong>Human decides</strong>
          </div>
        </aside>
      </section>
    </>
  )
}

function Waveform({ active }: { active: boolean }) {
  return (
    <div className={`waveform ${active ? "is-active" : ""}`} aria-hidden="true">
      {Array.from({ length: 34 }).map((_, index) => (
        <span
          key={index}
          style={{
            animationDelay: `${(index % 8) * 70}ms`,
            height: `${18 + ((index * 13) % 48)}%`,
          }}
        />
      ))}
    </div>
  )
}

function ReportScreen({ showToast }: { showToast: (message: string) => void }) {
  const [mode, setMode] = useState<"voice" | "text">("voice")
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [text, setText] = useState("")

  useEffect(() => {
    if (!recording) return
    const timer = window.setInterval(
      () => setSeconds((value) => value + 1),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [recording])

  const timer = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`

  return (
    <>
      <PageHeader
        description="Describe what happened naturally. SiteOps will structure the details for your review."
        eyebrow="Worker workspace"
        title="Report an incident"
      />
      <div className="report-layout">
        <section className="panel recorder-panel">
          <div className="input-tabs">
            <button
              className={mode === "voice" ? "active" : ""}
              onClick={() => setMode("voice")}
              type="button"
            >
              <Icon name="mic" /> Voice report
            </button>
            <button
              className={mode === "text" ? "active" : ""}
              onClick={() => setMode("text")}
              type="button"
            >
              <Icon name="edit" /> Type instead
            </button>
          </div>
          {mode === "voice" ? (
            <div className="voice-stage">
              <span className="voice-kicker">
                {recording ? "Listening now" : "Voice incident report"}
              </span>
              <button
                aria-label={recording ? "Stop recording" : "Start recording"}
                className={`mic-control ${recording ? "is-recording" : ""}`}
                onClick={() => setRecording((value) => !value)}
                type="button"
              >
                <span className="mic-ring" />
                <Icon name={recording ? "x" : "mic"} size={34} />
              </button>
              <h2>{recording ? timer : "Tap to start recording"}</h2>
              <p>
                {recording
                  ? "Speak clearly. You can pause at any time."
                  : "Report in your own words — SiteOps will identify the key details."}
              </p>
              <Waveform active={recording} />
              {recording && (
                <Button
                  kind="coral"
                  onClick={() => {
                    setRecording(false)
                    showToast("Recording captured and ready to review")
                  }}
                >
                  Finish recording
                </Button>
              )}
            </div>
          ) : (
            <div className="text-stage">
              <label htmlFor="incident-description">What happened?</label>
              <textarea
                id="incident-description"
                onChange={(event) => setText(event.target.value)}
                placeholder="Describe the incident, where it happened, who was involved, and whether anyone is in immediate danger..."
                value={text}
              />
              <div className="textarea-footer">
                <span>{text.length} / 1,500</span>
                <Badge tone="teal">AI-assisted extraction</Badge>
              </div>
              <Button
                disabled={!text.trim()}
                onClick={() =>
                  showToast("Report submitted to the SiteOps workflow")
                }
              >
                Submit report <Icon name="arrow" />
              </Button>
            </div>
          )}
          <div className="privacy-note">
            <Icon name="shield" />
            <span>
              Your report is encrypted and only visible to authorized site
              personnel.
            </span>
          </div>
        </section>
        <aside className="report-aside">
          <section className="panel guide-panel">
            <span className="eyebrow">A useful report includes</span>
            {[
              ["What happened", "Describe the event or hazard."],
              ["Where it happened", "Give a level, zone, or landmark."],
              ["Who was involved", "Names or roles, if known."],
              ["Immediate danger", "Tell us if urgent action is needed."],
            ].map(([title, copy], index) => (
              <div className="guide-row" key={title}>
                <span>0{index + 1}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{copy}</p>
                </div>
              </div>
            ))}
          </section>
          <section className="emergency-note">
            <Icon name="warning" />
            <div>
              <strong>Immediate danger?</strong>
              <p>
                Contact site emergency services first, then submit your report.
              </p>
            </div>
          </section>
        </aside>
      </div>
    </>
  )
}

function IncidentsScreen({ onReview }: { onReview: () => void }) {
  const [query, setQuery] = useState("")
  const filtered = incidents.filter((incident) =>
    `${incident.title} ${incident.location} ${incident.id}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  )
  return (
    <>
      <PageHeader
        description="Search, filter, and track all incident reports across the project."
        eyebrow="Incident register"
        title="All incidents"
      />
      <section className="panel table-panel">
        <div className="table-toolbar">
          <label className="search-field">
            <Icon name="search" />
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search incidents..."
              value={query}
            />
          </label>
          <div className="toolbar-actions">
            <Button kind="neutral">
              All statuses <Icon name="chevron" />
            </Button>
            <Button kind="neutral">
              Today <Icon name="chevron" />
            </Button>
          </div>
        </div>
        <div className="incident-table">
          <div className="incident-table__head">
            <span>Incident</span>
            <span>Location</span>
            <span>Reported by</span>
            <span>Status</span>
            <span>Time</span>
            <span />
          </div>
          {filtered.map((incident) => (
            <button
              className="incident-table__row"
              key={incident.id}
              onClick={onReview}
              type="button"
            >
              <span>
                <strong>{incident.title}</strong>
                <small>{incident.id}</small>
              </span>
              <span>{incident.location}</span>
              <span>{incident.reporter}</span>
              <span>
                <Badge tone={incident.tone}>{incident.status}</Badge>
              </span>
              <span>{incident.time}</span>
              <span>
                <Icon name="arrow" />
              </span>
            </button>
          ))}
        </div>
      </section>
    </>
  )
}

function ReviewQueue({ onReview }: { onReview: () => void }) {
  const columns = [
    {
      title: "Emergency",
      count: 1,
      tone: "danger" as Tone,
      copy: "Immediate response required",
      items: [incidents[0]],
    },
    {
      title: "Ready for review",
      count: 2,
      tone: "teal" as Tone,
      copy: "Evidence verified by SiteOps",
      items: [incidents[1], incidents[3]],
    },
    {
      title: "Needs clarification",
      count: 1,
      tone: "amber" as Tone,
      copy: "Missing report information",
      items: [incidents[2]],
    },
  ]
  return (
    <>
      <PageHeader
        description="Triage reports by urgency and evidence status. Every final decision remains yours."
        eyebrow="Human oversight"
        title="Review queue"
      />
      <div className="queue-grid">
        {columns.map((column) => (
          <section
            className={`queue-column queue-column--${column.tone}`}
            key={column.title}
          >
            <div className="queue-header">
              <div>
                <span className={`status-dot status-dot--${column.tone}`} />
                <h2>{column.title}</h2>
                <span className="queue-count">{column.count}</span>
              </div>
              <p>{column.copy}</p>
            </div>
            <div className="queue-stack">
              {column.items.map((incident) => (
                <article className="queue-card" key={incident.id}>
                  <div className="queue-card__meta">
                    <span>{incident.id}</span>
                    <span>{incident.time}</span>
                  </div>
                  <h3>{incident.title}</h3>
                  <p>
                    <Icon name="grid" size={14} /> {incident.location}
                  </p>
                  <div className="queue-reporter">
                    <span className="avatar avatar--small">
                      {incident.reporter
                        .split(" ")
                        .map((part) => part[0])
                        .join("")}
                    </span>
                    <span>
                      Reported by
                      <br />
                      <strong>{incident.reporter}</strong>
                    </span>
                  </div>
                  <div className="confidence">
                    <span>Evidence confidence</span>
                    <strong>
                      {column.tone === "amber"
                        ? "64%"
                        : column.tone === "danger"
                          ? "91%"
                          : "96%"}
                    </strong>
                    <div>
                      <span
                        style={{
                          width:
                            column.tone === "amber"
                              ? "64%"
                              : column.tone === "danger"
                                ? "91%"
                                : "96%",
                        }}
                      />
                    </div>
                  </div>
                  <Button
                    kind={
                      column.tone === "danger"
                        ? "danger"
                        : column.tone === "amber"
                          ? "coral"
                          : "primary"
                    }
                    onClick={onReview}
                  >
                    {column.tone === "amber"
                      ? "Clarify report"
                      : "Review incident"}{" "}
                    <Icon name="arrow" />
                  </Button>
                </article>
              ))}
              {column.items.length === 1 && (
                <div className="queue-empty">
                  No other incidents in this queue
                </div>
              )}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}

function ReviewScreen({ showToast }: { showToast: (message: string) => void }) {
  const [decision, setDecision] = useState<"open" | "approved" | "rejected">(
    "open",
  )
  return (
    <>
      <div className="review-topline">
        <div>
          <Badge tone="danger">
            <span className="status-dot status-dot--danger" /> Emergency
          </Badge>
          <span>INC-2026-0418</span>
          <span>Reported 8 minutes ago</span>
        </div>
        <Badge tone="teal">
          <Icon name="shield" size={13} /> AI analysis complete
        </Badge>
      </div>
      <PageHeader
        description="Review the original report, verify extracted details, and make the final decision."
        eyebrow="Human review required"
        title="Slip near water tank"
      />
      <div className="trust-banner">
        <span className="trust-icon">
          <Icon name="shield" />
        </span>
        <div>
          <strong>SiteOps has prepared this report for your review</strong>
          <p>
            AI-generated fields are linked to their source evidence. Confirm
            accuracy before approval.
          </p>
        </div>
        <span>
          AI assists <i /> Human decides
        </span>
      </div>
      <div className="review-layout">
        <div className="review-main">
          <section className="panel transcript-panel">
            <div className="panel-title">
              <span className="step-number">01</span>
              <div>
                <span className="eyebrow">Original report</span>
                <h2>Worker transcript</h2>
              </div>
              <Button kind="neutral" icon="play">
                Play audio · 0:18
              </Button>
            </div>
            <blockquote>
              “A worker slipped <mark>near the water tank on Level 2</mark>. The
              floor is wet and he’s hurt his ankle. He can’t stand up right now.
              We’ve blocked the area but need someone here quickly.”
            </blockquote>
            <div className="transcript-meta">
              <span>
                <Icon name="user" /> Marcus Reed
              </span>
              <span>English (UK)</span>
              <span>Voice report</span>
            </div>
          </section>
          <div className="evidence-connector">
            <span />
            <Icon name="arrow" />
            <strong>Evidence mapped by SiteOps</strong>
            <span />
          </div>
          <section className="panel evidence-panel">
            <div className="panel-title">
              <span className="step-number">02</span>
              <div>
                <span className="eyebrow">Extracted fields</span>
                <h2>Evidence verification</h2>
              </div>
              <Badge tone="green">
                <Icon name="check" size={13} /> 5 of 6 supported
              </Badge>
            </div>
            <div className="evidence-list">
              {[
                [
                  "Incident type",
                  "Slip / fall",
                  "“worker slipped”",
                  "Supported by transcript",
                  "teal",
                ],
                [
                  "Location",
                  "Level 2 — Water Tank Area",
                  "“near the water tank on Level 2”",
                  "Supported by transcript",
                  "teal",
                ],
                [
                  "Injury",
                  "Ankle injury — unable to stand",
                  "“hurt his ankle... can’t stand up”",
                  "Supported by transcript",
                  "teal",
                ],
                [
                  "Immediate controls",
                  "Area blocked",
                  "“We’ve blocked the area”",
                  "Supported by transcript",
                  "teal",
                ],
                [
                  "Urgency",
                  "Emergency response",
                  "“need someone here quickly”",
                  "Human review required",
                  "danger",
                ],
                [
                  "Worker ID",
                  "Not provided",
                  "No source evidence",
                  "Needs clarification",
                  "amber",
                ],
              ].map(([label, value, quote, status, tone]) => (
                <div
                  className={`evidence-row evidence-row--${tone}`}
                  key={label}
                >
                  <div className="field-cell">
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                  <div className="evidence-line">
                    <span />
                    <Icon name="arrow" size={14} />
                  </div>
                  <div className="quote-cell">
                    <span>Source evidence</span>
                    <q>{quote}</q>
                  </div>
                  <Badge tone={tone as Tone}>
                    {tone === "teal" && <Icon name="check" size={12} />}
                    {tone === "amber" && <Icon name="warning" size={12} />}
                    {status}
                  </Badge>
                </div>
              ))}
            </div>
          </section>
        </div>
        <aside className="decision-panel panel">
          <span className="eyebrow eyebrow--coral">Final decision</span>
          <h2>Manager review</h2>
          <p>
            Confirm the report is accurate and the correct response has been
            initiated.
          </p>
          <div className="risk-summary">
            <span>Recommended priority</span>
            <Badge tone="danger">P1 · Emergency</Badge>
            <div>
              <span>AI confidence</span>
              <strong>91%</strong>
            </div>
          </div>
          <label>
            Manager note <span>Optional</span>
            <textarea placeholder="Add context for the audit trail..." />
          </label>
          {decision === "open" ? (
            <div className="decision-actions">
              <Button
                onClick={() => {
                  setDecision("approved")
                  showToast("Incident approved and routed to response team")
                }}
              >
                <Icon name="check" /> Approve & route
              </Button>
              <Button
                kind="coral"
                onClick={() =>
                  showToast("Clarification request sent to Marcus Reed")
                }
              >
                Request clarification
              </Button>
              <Button
                kind="neutral"
                icon="edit"
                onClick={() =>
                  showToast("Incident fields unlocked for editing")
                }
              >
                Edit extracted fields
              </Button>
              <button
                className="reject-action"
                onClick={() => {
                  setDecision("rejected")
                  showToast("Incident rejected with audit record")
                }}
                type="button"
              >
                Reject report
              </button>
            </div>
          ) : (
            <div className={`decision-result decision-result--${decision}`}>
              <Icon name={decision === "approved" ? "check" : "x"} />
              <strong>Report {decision}</strong>
              <span>The decision has been recorded in the audit trail.</span>
            </div>
          )}
          <div className="audit-note">
            <Icon name="shield" />
            <span>
              Your decision, timestamp, and any edits are recorded for
              accountability.
            </span>
          </div>
        </aside>
      </div>
    </>
  )
}

function Analytics() {
  const bars = [38, 48, 42, 68, 55, 74, 62, 86, 72, 91, 78, 84]
  return (
    <>
      <PageHeader
        description="Operational trends and evidence quality across the project."
        eyebrow="Safety intelligence"
        title="Analytics"
      />
      <section className="metrics-grid metrics-grid--four">
        <MetricCard
          icon="file"
          label="Total incidents"
          note="+8.2% this month"
          tone="teal"
          value="146"
        />
        <MetricCard
          icon="shield"
          label="Verified first pass"
          note="+4.1% improvement"
          tone="green"
          value="92%"
        />
        <MetricCard
          icon="warning"
          label="Clarification rate"
          note="-2.4% this month"
          tone="amber"
          value="11%"
        />
        <MetricCard
          icon="chart"
          label="Avg. review time"
          note="18 min faster"
          tone="coral"
          value="42m"
        />
      </section>
      <div className="analytics-grid">
        <section className="panel chart-panel">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">12 week view</span>
              <h2>Incident volume</h2>
            </div>
            <Badge tone="teal">All sites</Badge>
          </div>
          <div className="bar-chart">
            {bars.map((bar, index) => (
              <div key={index}>
                <span style={{ height: `${bar}%` }} />
                <small>W{index + 1}</small>
              </div>
            ))}
          </div>
        </section>
        <section className="panel category-panel">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">Distribution</span>
              <h2>Top incident types</h2>
            </div>
          </div>
          {[
            ["Slip / fall", "34%", "teal"],
            ["Site hazard", "26%", "coral"],
            ["Equipment", "19%", "amber"],
            ["PPE", "13%", "green"],
            ["Other", "8%", "neutral"],
          ].map(([label, value, tone]) => (
            <div className="category-row" key={label}>
              <span className={`category-dot category-dot--${tone}`} />
              <strong>{label}</strong>
              <div>
                <span className={`fill--${tone}`} style={{ width: value }} />
              </div>
              <span>{value}</span>
            </div>
          ))}
        </section>
      </div>
    </>
  )
}

function Settings() {
  const [alerts, setAlerts] = useState(true)
  const [verification, setVerification] = useState(true)
  return (
    <>
      <PageHeader
        description="Manage workspace preferences, notifications, and AI-assisted workflow controls."
        eyebrow="Workspace"
        title="Settings"
      />
      <div className="settings-layout">
        <section className="panel settings-panel">
          <div className="settings-heading">
            <span className="metric-icon metric-icon--teal">
              <Icon name="bell" />
            </span>
            <div>
              <h2>Notifications</h2>
              <p>Choose which operational updates reach you.</p>
            </div>
          </div>
          <div className="setting-row">
            <div>
              <strong>Emergency alerts</strong>
              <span>Immediate alerts for P1 incidents.</span>
            </div>
            <button
              className={`toggle ${alerts ? "active" : ""}`}
              onClick={() => setAlerts(!alerts)}
              type="button"
            >
              <span />
            </button>
          </div>
          <div className="setting-row">
            <div>
              <strong>Review queue summary</strong>
              <span>Daily digest of incidents awaiting action.</span>
            </div>
            <button className="toggle active" type="button">
              <span />
            </button>
          </div>
        </section>
        <section className="panel settings-panel">
          <div className="settings-heading">
            <span className="metric-icon metric-icon--coral">
              <Icon name="shield" />
            </span>
            <div>
              <h2>AI assistance</h2>
              <p>Control how SiteOps supports human review.</p>
            </div>
          </div>
          <div className="setting-row">
            <div>
              <strong>Evidence verification</strong>
              <span>Map extracted fields to source transcripts.</span>
            </div>
            <button
              className={`toggle ${verification ? "active" : ""}`}
              onClick={() => setVerification(!verification)}
              type="button"
            >
              <span />
            </button>
          </div>
          <div className="setting-row">
            <div>
              <strong>Automatic clarification</strong>
              <span>Ask workers for essential missing details.</span>
            </div>
            <button className="toggle active" type="button">
              <span />
            </button>
          </div>
        </section>
      </div>
    </>
  )
}

function LoginScreen({
  onLogin,
  initialError = "",
}: {
  onLogin: (email: string, password: string) => Promise<void>
  initialError?: string
}) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(initialError)

  useEffect(() => {
    setError(initialError)
  }, [initialError])

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!username.trim() || !password) {
      setError("Enter your SiteOps email and password.")
      return
    }

    setError("")
    setSubmitting(true)
    try {
      await onLogin(username.trim(), password)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-screen">
      <div className="login-ambient login-ambient--one" />
      <div className="login-ambient login-ambient--two" />
      <section className="login-brand">
        <Logo />
        <div className="login-brand__content">
          <span className="login-kicker">
            <span /> LTM safety operations
          </span>
          <h1>
            Every report.
            <br />
            <span>Grounded in evidence.</span>
          </h1>
          <p>
            Voice-first incident intelligence for faster site response,
            accountable decisions, and safer teams.
          </p>
        </div>
        <div className="login-trust">
          <div>
            <Icon name="mic" />
            <span>
              <strong>Voice capture</strong>
              Natural, field-ready reporting
            </span>
          </div>
          <div>
            <Icon name="shield" />
            <span>
              <strong>Evidence verified</strong>
              Human-controlled decisions
            </span>
          </div>
        </div>
        <div className="login-brand__footer">
          Developed within <strong>LTM</strong>
        </div>
      </section>

      <section className="login-access">
        <div className="login-card">
          <div className="login-card__header">
            <span className="access-icon">
              <Icon name="user" />
            </span>
            <span className="eyebrow">Secure access</span>
            <h2>Welcome to SiteOps</h2>
            <p>Sign in with your assigned Firebase/SiteOps credentials.</p>
          </div>
          <form onSubmit={submit}>
            <label htmlFor="username">
              Email
              <span className="login-input">
                <Icon name="user" />
                <input
                  autoComplete="username"
                  id="username"
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="you@company.com"
                  type="email"
                  value={username}
                />
              </span>
            </label>
            <label htmlFor="password">
              Password
              <span className="login-input">
                <Icon name="shield" />
                <input
                  autoComplete="current-password"
                  id="password"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  type="password"
                  value={password}
                />
              </span>
            </label>
            {error && (
              <div className="login-error">
                <Icon name="warning" size={15} /> {error}
              </div>
            )}
            <button
              className={`login-submit ${submitting ? "is-submitting" : ""}`}
              disabled={submitting}
              type="submit"
            >
              <span>
                {submitting ? "Verifying access" : "Sign in to workspace"}
              </span>
              {submitting ? <i /> : <Icon name="arrow" />}
            </button>
          </form>
          <div className="login-routing">
            <Icon name="shield" />
            <span>
              <strong>Role-based access enabled</strong>
              Your Firebase account determines your SiteOps role. Workers and
              managers do not choose their role on this screen.
            </span>
          </div>
        </div>
        <p className="login-support">
          Access issues? Contact your project administrator.
        </p>
      </section>
    </main>
  )
}

export default function App() {
  const { user, profile, loading, error: authError, signIn, signOutUser } = useAuth()
  const [screen, setScreen] = useState<Screen>("dashboard")
  const [mobileOpen, setMobileOpen] = useState(false)
  const [toast, setToast] = useState("")

  const role = profile?.role ?? null

  useEffect(() => {
    if (!role) return
    setScreen(role === "worker" ? "report" : "dashboard")
  }, [role])

  const showToast = (message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(""), 3400)
  }

  const navigate = (next: Screen) => {
    if (!role) return

    if (
      role === "worker" &&
      ["dashboard", "queue", "review", "analytics"].includes(next)
    ) {
      setScreen("report")
      showToast("This area requires manager access")
      return
    }

    setScreen(next)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  const logout = async () => {
    await signOutUser()
    setScreen("dashboard")
    setMobileOpen(false)
  }

  const content = useMemo(() => {
    if (!role) return null
    if (screen === "dashboard") return <Dashboard onNavigate={navigate} />
    if (screen === "report") return <ReportScreen showToast={showToast} />
    if (screen === "incidents")
      return <IncidentsScreen onReview={() => navigate("review")} />
    if (screen === "queue")
      return <ReviewQueue onReview={() => navigate("review")} />
    if (screen === "review") return <ReviewScreen showToast={showToast} />
    if (screen === "analytics") return <Analytics />
    return <Settings />
  }, [screen, role])

  if (loading) {
    return (
      <main className="login-screen">
        <section className="login-access">
          <div className="login-card">
            <div className="login-card__header">
              <span className="access-icon"><Icon name="shield" /></span>
              <span className="eyebrow">Secure access</span>
              <h2>Loading SiteOps</h2>
              <p>Checking your Firebase account and SiteOps permissions.</p>
            </div>
          </div>
        </section>
      </main>
    )
  }

  if (!user || !profile) {
    return <LoginScreen onLogin={signIn} initialError={authError} />
  }

  return (
    <div className="app-shell">
      <Sidebar
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        onNavigate={navigate}
        onLogout={logout}
        role={role}
        screen={screen}
      />
      <div className="app-main">
        <Topbar
          employeeId={profile.employee_id}
          onMenu={() => setMobileOpen(true)}
          onReport={() => navigate("report")}
          role={role}
        />
        <main className="page-content">{content}</main>
      </div>
      {toast && (
        <div className="toast">
          <span>
            <Icon name="check" />
          </span>
          <div>
            <strong>Workflow updated</strong>
            <p>{toast}</p>
          </div>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
            type="button"
          >
            <Icon name="x" />
          </button>
        </div>
      )}
    </div>
  )
}


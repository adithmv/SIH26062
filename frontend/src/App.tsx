import { useEffect, useState } from "react";
import { get, utc } from "./api";
import type { Mission, MissionDetail, Person, Vehicle } from "./api";
import "./App.css";
const pages = ["Overview", "Missions", "Personnel", "Vehicles"] as const;
type Page = (typeof pages)[number];

export default function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [missions, setMissions] = useState<Mission[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<MissionDetail | null>(null);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      get<Mission[]>("missions", controller.signal),
      get<Person[]>("personnel", controller.signal),
      get<Vehicle[]>("vehicles", controller.signal),
    ])
      .then(([m, p, v]) => {
        setMissions(m);
        setPeople(p);
        setVehicles(v);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    get<MissionDetail>("missions/" + selected, controller.signal)
      .then(setDetail)
      .catch((e) => {
        if (!controller.signal.aborted) setDetailError(e.message);
      });
    return () => controller.abort();
  }, [selected]);
  return (
    <div className="shell">
      <aside>
        <a
          className="brand"
          href="#"
          onClick={() => {
            setPage("Overview");
            setSelected(null);
          }}
        >
          <span className="brand-mark">△</span>
          <span>
            POLARIS<small>EXPEDITION OPERATIONS</small>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {pages.map((p, i) => (
            <button
              key={p}
              className={page === p ? "active" : ""}
              aria-current={page === p ? "page" : undefined}
              onClick={() => {
                setPage(p);
                setSelected(null);
              }}
            >
              <span aria-hidden="true">{["◈", "↗", "◎", "▱"][i]}</span>
              {p}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          ● DEVELOPMENT BUILD<p>Phase 01 / Foundation</p>
          <small>
            Fictional expedition data.
            <br />
            No live tracking connected.
          </small>
        </div>
      </aside>
      <main>
        <header>
          <span>Maitri station / Operations workspace</span>
          <span className="badge">DEMO ENVIRONMENT</span>
        </header>
        <div className="page-heading">
          <div>
            <p className="eyebrow">ANTARCTIC FIELD OPERATIONS</p>
            <h1>
              {selected
                ? "Mission briefing"
                : page === "Overview"
                  ? "Expedition overview"
                  : page}
            </h1>
            <p className="muted">
              A shared picture of your people, missions and field resources.
            </p>
          </div>
          <span className="date">
            28 SEP 2026
            <br />
            <small>Fixed demonstration snapshot</small>
          </span>
        </div>
        <div className="notice">
          ⓘ All names, missions and positions are fictional. Statuses are
          seeded; overdue detection arrives in Phase 2.
        </div>
        {loading ? (
          <p role="status" className="panel">
            Loading expedition records…
          </p>
        ) : error ? (
          <div role="alert" className="panel error">
            {error}
            <button
              onClick={() => {
                setLoading(true);
                setError("");
                setRetry(retry + 1);
              }}
            >
              Try again
            </button>
          </div>
        ) : selected ? (
          <section className="panel">
            <button className="back" onClick={() => setSelected(null)}>
              ← Back to missions
            </button>
            {detailError ? (
              <p role="alert">{detailError}</p>
            ) : !detail ? (
              <p role="status">Loading mission…</p>
            ) : (
              <>
                <p className="eyebrow">
                  {detail.code} / {detail.station}
                </p>
                <h2>{detail.name}</h2>
                <div className="detail-grid">
                  <div>
                    <h3>Mission plan</h3>
                    <p>Destination: {detail.destination}</p>
                    <p>Departure: {utc(detail.departure)}</p>
                    <p>Check-in expected: {utc(detail.expected_check_in)}</p>
                    <p>Return expected: {utc(detail.expected_return)}</p>
                    <p>Vehicle: {detail.vehicle.code}</p>
                  </div>
                  <div>
                    <h3>Assigned personnel</h3>
                    {detail.personnel.map((p) => (
                      <p key={p.id}>
                        {p.name} <span className="muted">/ {p.role}</span>
                      </p>
                    ))}
                    <h3>Last confirmed position</h3>
                    {detail.last_position ? (
                      <>
                        <p>
                          {detail.last_position.latitude.toFixed(4)}°,{" "}
                          {detail.last_position.longitude.toFixed(4)}°
                        </p>
                        <p className="muted">
                          {utc(detail.last_position.observed_at)}
                          <br />
                          {detail.last_position.source}
                        </p>
                      </>
                    ) : (
                      <p className="muted">No position recorded</p>
                    )}
                  </div>
                </div>
                <h3>Recorded check-ins</h3>
                {detail.check_ins.length ? (
                  detail.check_ins.map((c) => (
                    <p key={c.id}>
                      {c.note}
                      <br />
                      <small className="muted">
                        {utc(c.observed_at)} / {c.source}
                      </small>
                    </p>
                  ))
                ) : (
                  <p>No check-ins recorded</p>
                )}
              </>
            )}
          </section>
        ) : (
          <>
            {page === "Overview" && (
              <div className="stats">
                {[
                  ["Personnel", people.length, "Assigned expedition members"],
                  [
                    "Field missions",
                    missions.filter((m) => m.status === "in_field").length,
                    "Seeded in-field status",
                  ],
                  [
                    "Planned missions",
                    missions.filter((m) => m.status === "planned").length,
                    "Preparing for departure",
                  ],
                  ["Vehicles", vehicles.length, "Registered field resources"],
                ].map(([label, value, description]) => (
                  <article className="stat" key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                    <small>{description}</small>
                  </article>
                ))}
              </div>
            )}
            {(page === "Overview" || page === "Missions") && (
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Field missions</h2>
                    <p className="muted">
                      Mission plans and last confirmed field information.
                    </p>
                  </div>
                  <span className="count">{missions.length} missions</span>
                </div>
                {missions.length === 0 ? (
                  <p>
                    No missions yet. Load the demonstration fixtures to get
                    started.
                  </p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>MISSION</th>
                          <th>DESTINATION</th>
                          <th>STATUS</th>
                          <th>EXPECTED RETURN</th>
                          <th>DETAILS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {missions.map((m) => (
                          <tr key={m.id}>
                            <td>
                              <strong>{m.name}</strong>
                              <small>
                                {m.code} · {m.station}
                              </small>
                            </td>
                            <td>{m.destination}</td>
                            <td>
                              <span className={"status " + m.status}>
                                {m.status.replaceAll("_", " ")}
                              </span>
                            </td>
                            <td>{utc(m.expected_return)}</td>
                            <td>
                              <button
                                aria-label={"View " + m.code}
                                onClick={() => {
                                  setDetail(null);
                                  setDetailError("");
                                  setSelected(m.id);
                                }}
                              >
                                View ↗
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
            {page === "Personnel" && (
              <section className="panel">
                <h2>Expedition personnel</h2>
                <div className="cards">
                  {people.map((p) => (
                    <article key={p.id}>
                      <span className="avatar">
                        {p.name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")}
                      </span>
                      <h3>{p.name}</h3>
                      <p>{p.role}</p>
                      <small className="muted">Home station: {p.station}</small>
                    </article>
                  ))}
                </div>
                {!people.length && <p>No personnel recorded.</p>}
              </section>
            )}
            {page === "Vehicles" && (
              <section className="panel">
                <h2>Field resources</h2>
                <div className="cards">
                  {vehicles.map((v) => (
                    <article key={v.id}>
                      <p className="eyebrow">VEHICLE</p>
                      <h3>{v.code}</h3>
                      <p>{v.kind}</p>
                    </article>
                  ))}
                </div>
                {!vehicles.length && <p>No vehicles recorded.</p>}
              </section>
            )}
            {page === "Overview" && (
              <section className="next-panel">
                <span>01 / FOUNDATION</span>
                <h2>Built for the journey ahead.</h2>
                <p>
                  Mission records are connected. Offline capture, priority
                  delivery and communication simulation will follow in the next
                  phases.
                </p>
              </section>
            )}
          </>
        )}
        <footer>
          SIH26062{" "}
          <span>
            Mission continuity starts with a reliable operational picture.
          </span>
        </footer>
      </main>
    </div>
  );
}

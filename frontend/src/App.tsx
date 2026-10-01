import { useEffect, useState } from "react";
import { get, statusLabel, utc } from "./api";
import type { Mission, MissionDetail, Person, Vehicle } from "./api";
import { useOnline } from "./useDeliveries";
import OfflinePanel from "./OfflinePanel";
import MissionForm from "./MissionForm";
import MissionWorkspace from "./MissionWorkspace";
import "./App.css";
const pages = ["Overview", "Missions", "Personnel", "Vehicles"] as const;
type Page = (typeof pages)[number];

export default function App() {
  const online = useOnline();
  const [page, setPage] = useState<Page>("Overview");
  const [missions, setMissions] = useState<Mission[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<MissionDetail | null>(null);
  const [form, setForm] = useState<"create" | "edit" | null>(null);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setRevision((v) => v + 1), 30000);
    return () => clearInterval(timer);
  }, []);
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
        setError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    get<MissionDetail>("missions/" + selected, controller.signal)
      .then((d) => {
        setDetail(d);
        setDetailError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setDetailError(e.message);
      });
    return () => controller.abort();
  }, [selected, revision]);
  function open(id: string) {
    setSelected(id);
    setDetail(null);
    setDetailError("");
    setForm(null);
  }
  function saved(m: MissionDetail) {
    setDetail(m);
    setSelected(m.id);
    setForm(null);
    setRevision((v) => v + 1);
  }
  function navigate(p: Page) {
    setPage(p);
    setSelected(null);
    setForm(null);
  }
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="#" onClick={() => navigate("Overview")}>
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
              onClick={() => navigate(p)}
            >
              <span aria-hidden="true">{["◈", "↗", "◎", "▱"][i]}</span>
              {p}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          ● DEVELOPMENT BUILD<p>Expedition operations</p>
          <small>
            Operator-entered records.
            <br />
            No live tracking connected.
          </small>
        </div>
      </aside>
      <main>
        <header>
          <span>Expedition / Operations workspace</span>
          <span className="badge">PROTOTYPE</span>
        </header>
        <div className="page-heading">
          <div>
            <p className="eyebrow">ANTARCTIC FIELD OPERATIONS</p>
            <h1>
              {form === "create"
                ? "Plan a field mission"
                : selected
                  ? "Mission briefing"
                  : page === "Overview"
                    ? "Expedition overview"
                    : page}
            </h1>
            <p className="muted">
              A shared picture of your people, missions and field resources.
            </p>
          </div>
          <button onClick={() => setRevision((v) => v + 1)}>
            Refresh records
          </button>
        </div>
        <div className="notice">
          ⓘ Contact status uses the server's current time. Positions show the
          last recorded observation. No live tracking or emergency dispatch is connected.
        </div>
        <OfflinePanel onRefresh={() => setRevision((v) => v + 1)} />
        {error && (
          <div role="alert" className="panel error">
            {error} Previously loaded records may be stale.
            <button onClick={() => setRevision((v) => v + 1)}>Try again</button>
          </div>
        )}
        {loading ? (
          <p role="status" className="panel">
            Loading expedition records…
          </p>
        ) : form ? (
          <MissionForm
            key={form + (detail?.id ?? "")}
            initial={form === "edit" && detail ? detail : undefined}
            people={people}
            vehicles={vehicles}
            onSaved={saved}
            onCancel={() => setForm(null)}
          />
        ) : selected ? (
          <>
            {detailError && (
              <p className="form-error" role="alert">
                {detailError} Displayed details may be stale.
              </p>
            )}
            {detail ? (
              <MissionWorkspace
                key={detail.id}
                mission={detail}
                onSaved={saved}
                onEdit={() => setForm("edit")}
                onBack={() => setSelected(null)}
              />
            ) : (
              <p role="status" className="panel">
                {detailError
                  ? "Use Refresh records to retry."
                  : "Loading mission…"}
              </p>
            )}
          </>
        ) : (
          <>
            {page === "Overview" && (
              <div className="stats">
                {[
                  [
                    "Personnel",
                    people.length,
                    people.filter((p) => p.active_mission_id).length +
                      " currently in the field",
                  ],
                  [
                    "Field missions",
                    missions.filter((m) => m.status === "in_field").length,
                    "Departed and not yet returned",
                  ],
                  [
                    "Needs attention",
                    missions.filter(
                      (m) =>
                        m.status === "in_field" &&
                        m.operational_status !== "normal",
                    ).length,
                    "Due, overdue or escalated",
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
                  <button
                    className="primary"
                    disabled={!online}
                    onClick={() => setForm("create")}
                  >
                    New mission
                  </button>
                </div>
                {!missions.length ? (
                  <p>No missions recorded.</p>
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
                              <span
                                className={"status " + m.operational_status}
                              >
                                {statusLabel(m.operational_status)}
                              </span>
                              {m.return_overdue &&
                                m.operational_status !== "return_overdue" && (
                                  <small>Return overdue</small>
                                )}
                            </td>
                            <td>{utc(m.expected_return)}</td>
                            <td>
                              <button
                                aria-label={"View " + m.code}
                                onClick={() => open(m.id)}
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
                      <p>
                        <span className={"status " + p.operational_status}>
                          {statusLabel(p.operational_status)}
                        </span>
                      </p>
                      {p.active_mission_id ? (
                        <button onClick={() => open(p.active_mission_id!)}>
                          Open {p.active_mission_code}
                        </button>
                      ) : (
                        <small className="muted">At station: {p.station}</small>
                      )}
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
                      {missions
                        .filter(
                          (m) =>
                            m.vehicle_id === v.id && m.status === "in_field",
                        )
                        .map((m) => (
                          <button key={m.id} onClick={() => open(m.id)}>
                            In field · {m.code}
                          </button>
                        ))}
                    </article>
                  ))}
                </div>
                {!vehicles.length && <p>No vehicles recorded.</p>}
              </section>
            )}
          </>
        )}
        <footer>
          SIH26062
          <span>
            Mission continuity starts with a reliable operational picture.
          </span>
        </footer>
      </main>
    </div>
  );
}

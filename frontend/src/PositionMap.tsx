import { lazy, Suspense, useState } from "react";
import type { Position } from "./api";
const OnlineMap = lazy(() => import("./OnlineMap"));
export default function PositionMap({ position }: { position: Position }) {
  const [onlineMap, setOnlineMap] = useState(false);
  const x = (position.longitude - 11) * 100;
  const y = ((-70.5 - position.latitude) / 0.6) * 100;
  const inside = x >= 0 && x <= 100 && y >= 0 && y <= 100;
  return (
    <section className="map-section">
      <h3>Local coordinate map</h3>
      <div className="offline-map" aria-label="Offline demo coordinate map">
        <img
          src="/maps/maitri-demo.svg"
          alt="Bounded schematic grid from 70.50 to 71.10 degrees south and 11 to 12 degrees east"
        />
        {inside && (
          <span
            className="map-point"
            aria-label="Last confirmed observation"
            style={{ left: x + "%", top: y + "%" }}
          />
        )}
      </div>
      {!inside && (
        <p className="muted">
          This position is outside the saved demo area. Use the recorded
          coordinates.
        </p>
      )}
      <p className="muted">
        Available offline. This schematic is not a navigation chart. Marker uses
        the last server-confirmed observation.
      </p>
      <button type="button" onClick={() => setOnlineMap((v) => !v)}>
        {onlineMap ? "Hide online map" : "Load online map"}
      </button>
      {onlineMap && (
        <Suspense fallback={<p>Loading online map...</p>}>
          <OnlineMap position={position} />
        </Suspense>
      )}
    </section>
  );
}

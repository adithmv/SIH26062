import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
maplibregl.setWorkerUrl(workerUrl);
import type { Position } from "./api";
import { utc } from "./api";

export default function PositionMap({ position }: { position: Position }) {
  const container = useRef<HTMLDivElement>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    let map: maplibregl.Map | undefined;
    try {
      map = new maplibregl.Map({
        container: container.current,
        center: [position.longitude, position.latitude],
        zoom: 9,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              maxzoom: 19,
              attribution:
                '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
            },
          },
          layers: [{ id: "base", type: "raster", source: "osm" }],
        },
      });
      map.addControl(new maplibregl.NavigationControl(), "top-right");
      new maplibregl.Marker({ color: "#267d77" })
        .setLngLat([position.longitude, position.latitude])
        .setPopup(
          new maplibregl.Popup().setText(
            "Last confirmed: " + utc(position.observed_at),
          ),
        )
        .addTo(map);
      map.on("error", () => setUnavailable(true));
      map.on("load", () => setLoaded(true));
    } catch {
      queueMicrotask(() => setUnavailable(true));
    }
    return () => map?.remove();
  }, [
    position.id,
    position.latitude,
    position.longitude,
    position.observed_at,
  ]);
  return (
    <div>
      <div
        ref={container}
        className="position-map"
        aria-label="Map of the last confirmed position"
        data-state={unavailable ? "unavailable" : loaded ? "ready" : "loading"}
      />
      {!loaded && !unavailable && (
        <p role="status" className="muted">
          Loading map imagery...
        </p>
      )}
      {unavailable && (
        <p role="status" className="muted">
          Map imagery is unavailable. The recorded coordinates and timestamp
          remain available above.
        </p>
      )}
      {Math.abs(position.latitude) > 85 && (
        <p className="muted">
          This map projection cannot accurately show locations near the pole.
          Use the recorded coordinates.
        </p>
      )}
      <p className="muted">
        Recorded observation, not a live position. Basemap requires internet; no
        route is inferred.
      </p>
    </div>
  );
}

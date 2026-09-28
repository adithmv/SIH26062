import { useEffect, useState } from "react";
import { liveQuery } from "dexie";
import { db, STORE_ERROR } from "./localStore";
import type { Delivery } from "./localStore";
export function useDeliveries(missionId?: string) {
  const [items, setItems] = useState<Delivery[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const subscription = liveQuery(() =>
      missionId
        ? db.outbox.where("missionId").equals(missionId).toArray()
        : db.outbox.toArray(),
    ).subscribe({
      next: (rows) => {
        setItems(rows.sort((a, b) => a.createdAt.localeCompare(b.createdAt)));
        setError("");
      },
      error: () => setError(STORE_ERROR),
    });
    return () => subscription.unsubscribe();
  }, [missionId]);
  return { items, error };
}

export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

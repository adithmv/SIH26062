// Set before mounting the dashboard; base sessions never read field-device caches.
export let baseMode = false;
export function setBaseMode(value: boolean) { baseMode = value; }
export let baseUser: { username: string; role: string } | null = null;
export function setBaseUser(value: typeof baseUser) { baseUser = value; }

# Base station setup

The base station stores expedition records and files. Its dashboard includes missions, personnel, vehicles, cargo, inventory and received alerts. No example records or default accounts are installed.

**Release status: deployment candidate, not yet approved for public operation.** Local automated checks do not replace testing HTTPS, backups, load and recovery on the actual server. The acceptance list below records what remains.

## 1. Prepare the server

Install Docker with Compose. On Windows, start Docker Desktop with Linux containers enabled. Use a server with reliable power and persistent storage.

File storage must support hard links (for example NTFS or ext4). FAT/exFAT storage is unsupported because uploads must publish complete files without overwriting an existing transfer.

In the project folder, copy `deploy/.env.example` to `.env.base`. Edit it:

```text
BASE_HOST=your-real-base-hostname
BASE_DB_PASSWORD=your-random-64-character-hexadecimal-password
```

Use a password generator for the database password. Keep `.env.base` private; do not commit it. The hexadecimal format avoids special characters changing the database URL.

## 2. Choose the network

**Internet:** point your DNS hostname at the server. Allow incoming ports 80 and 443 only. The web server obtains and renews HTTPS certificates. Start:

```powershell
docker compose --env-file .env.base -f compose.base.yaml up -d --build
```

**Private LAN:** set `BASE_HOST` to a name such as `polar-base.internal`, and configure local DNS to resolve it to the server. Start:

```powershell
docker compose --env-file .env.base -f compose.base.yaml -f compose.base.lan.yaml up -d --build
```

The LAN configuration issues certificates using its own local certificate authority. Export its root certificate with the command below and have your administrator install it as a trusted root on authorized client computers. Never copy the CA private key. Do not bypass certificate warnings.

```powershell
docker compose --env-file .env.base -f compose.base.yaml cp web:/data/caddy/pki/authorities/local/root.crt ./polar-base-root.crt
```

For one base serving both networks, use the Internet configuration and the same HTTPS hostname on both networks. Local DNS can point that hostname to the private server address. Browser sign-in accepts only the configured origin.

The database and API have no published ports. Access them through HTTPS. The existing development setup on localhost remains separate.

The private API trusts forwarded client addresses from its gateway so sign-in limits apply per client. Caddy overwrites incoming forwarding headers. Keep the API port private; do not reuse this forwarding setting on a directly exposed API server.

## 3. Create accounts

Create the first administrator from the server terminal. Password entry is hidden:

```powershell
docker compose --env-file .env.base -f compose.base.yaml exec api python -m app.accounts set station-admin --role admin
```

Use passwords of at least 14 characters. Open `https://YOUR_BASE_HOST` and sign in.

| Role | Access |
| --- | --- |
| Viewer | Read station records and download files |
| Operator | Read records, register resources, manage missions, files, stock and alerts |
| Administrator | Operator access plus device listing and access-history API |

Create another user by replacing `station-admin` and choosing a role. Running `set` again changes that account's password and role, and revokes existing sessions. Disable an account:

```powershell
docker compose --env-file .env.base -f compose.base.yaml exec api python -m app.accounts disable USERNAME
```

Sessions expire after eight hours. Five unsuccessful attempts lock an account for 15 minutes. The server also limits sign-in attempts to 30 per minute per client IP across accounts. Devices sharing one public IP share this limit. Passwords and session tokens are not stored in plaintext. Base mode does not save mission records in the browser's offline database or send old offline reports.

All roles currently share station-wide read access. A confidential label does **not** create a separate permission group. Original files remain plaintext on the server; use encrypted server disks and protected backups. Separate per-mission clearance and MFA are not implemented.

## 4. Register field devices

```powershell
docker compose --env-file .env.base -f compose.base.yaml exec api python -m app.devices issue FIELD_DEVICE_NAME
```

Save the one-time token securely on that device as `PMCE_BASE_TOKEN`, and set its `PMCE_CENTRAL_URL` to the base HTTPS address. Event `device_id` must exactly match the registered device name. The existing PMCE worker sends the token with deliveries. Issuing again rotates the credential. Use `disable` instead of `issue` to revoke it.

Device credentials can deliver events and files only; they cannot browse station records or administer the base. A health check alone does not establish device identity.

For file delivery, POST the raw file to `/api/files?name=FILENAME` with `Authorization: Bearer TOKEN`, a stable UUID in `X-Transfer-ID`, and the lowercase SHA-256 in `X-Content-SHA256`. URL-encode the filename. Retry with the same ID and unchanged bytes after a lost response. The response includes `id`, `sha256`, size and storage status; verify them before marking a transfer delivered. Maximum size is 20 MiB. The field-side file transfer interface is still outside this base-only implementation.

## 5. Check operation

Open **Data Management** for the real storage location, free space, file count and received-event timestamp. A received timestamp does not mean that a device is currently online. Register personnel and vehicles before planning missions; add cargo before departure. Inventory adjustments require a reason. Acknowledge alerts before resolving them.

Check server health:

```powershell
docker compose --env-file .env.base -f compose.base.yaml ps
docker compose --env-file .env.base -f compose.base.yaml logs --tail 100 api
docker compose --env-file .env.base -f compose.base.yaml exec api python -m app.storage_check
```

The storage check is read-only. It reports verified, missing, damaged, unreferenced and older files without checksums. Do not delete unreferenced files automatically: they may be recoverable interrupted uploads. New uploads are flushed to disk before metadata is committed. Files and database updates cannot form one filesystem transaction; interrupted commits therefore need this reconciliation check.

Administrators can read the latest 200 access entries at `/api/auth/audit`. `request.authorized` records permission to attempt a change, not proof that the operation succeeded. Mission and stock histories separately record committed changes. Access-history retention and external log collection require deployment configuration.

## 6. Backup and recovery

Run the maintenance backup from the repository root with Python 3.12 or newer:

```powershell
python deploy/backup.py D:\PolarBackups\2026-10-12
```

Use a new destination folder each time. The command briefly stops the web and API services, backs up PostgreSQL and files together, writes a checksum manifest, then restarts them. Keep `.env.base` and the certificate volumes backed up separately under administrator control. Backup contents are sensitive; encrypt and copy them to separate storage.

Before deployment, rehearse restoration into a **separate Docker project with empty volumes**, not the live base. Verify manifest checksums; restore `database.dump` using `pg_restore -U polar -d polar --exit-on-error` and extract `files.tar.gz` into the new API's `/app/data/files` volume as its owner. Start the restored API, run `app.storage_check`, then verify sign-in, record counts, mission history and file downloads. Do not run migrations newer than the backup until the matching application release has been restored and checked. No restore is performed automatically.

## Release acceptance still required

- Run and verify both Docker network configurations; Docker was not running during local development.
- Test actual certificates, firewall rules, device delivery and token revocation from another computer.
- Rehearse backup restoration and interrupted-upload recovery on the deployment hardware.
- Establish expected users, file volume and retention; load-test disk, database and sign-in limits against those requirements.
- Decide MFA, confidential-data clearance and audit retention requirements with the station owner. Arrange independent security review before Internet exposure.

Technical references: [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

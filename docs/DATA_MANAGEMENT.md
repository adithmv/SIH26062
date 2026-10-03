# Data management

Open **Data Management** in Polar Expedition Manager.

The file manager has two panes. **This device** lists the backend's Originals and Prepared copies folders. **Other device / Base** shows Not connected until remote browsing and file transfer are implemented; it does not display sample files. Select a local filename to see its full storage path and preparation controls below the panes.

1. **Add a file** (nonempty, up to 20 MiB). The page shows its actual location on the backend computer.
2. **Edit data level** to mark importance and confidentiality, then **Save data level**.
3. Drag the original into the preparation area or click **Use this file**. Choose compression and answer **Encrypt this file?**
4. **Create prepared copy** saves a separate file. Download it, or use **Restore and download** to recover its contents.

Originals remain unchanged and unencrypted. Confidentiality is a label, not access control. The current local prototype has no user permissions. Files are **stored locally, not sent to base**; PMCE file transfer is not connected yet.

Storage defaults to `backend/data/files/`: `originals/` holds uploaded files and `prepared/` holds copies, under unique IDs. Names, levels and copy details are in the database. Set `FILE_STORAGE_ROOT` to change the folder before uploading; moving existing storage requires copying its contents. Back up both the database and folder. Docker uses a persistent `expedition_files` volume.

Compression uses gzip before encryption. Passwords must contain 12–256 characters and are never saved. Keep them safely; there is no password recovery. An encrypted copy uses AES-256-GCM with a random salt and nonce and a scrypt-derived key (N=32768, r=8, p=1). Its authenticated header is `PEM1`, a one-byte compression flag, a 16-byte salt and a 12-byte nonce, followed by ciphertext and the 16-byte tag. `.pemenc` is this application's format, not a ZIP file. Restore uses the selected server-stored copy; it does not import external encrypted files.

Use this prototype on your own computer. Shared deployment needs authentication, permissions and HTTPS. [Encryption implementation reference](https://cryptography.io/en/stable/hazmat/primitives/aead/).

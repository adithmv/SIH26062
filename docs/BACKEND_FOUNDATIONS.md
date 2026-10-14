# Backend foundations

We keep FastAPI, SQLAlchemy and Alembic. A larger application framework would add migration work without solving the current reliability problems.

| Project / pattern | Where it helps |
| --- | --- |
| [Pydantic Settings](https://github.com/pydantic/pydantic-settings) | Validates server mode and the HTTPS origin before startup. Normalizes hostnames and default ports to match browser requests. No accidental `.env` loading from a different working directory. |
| [pwdlib](https://github.com/frankie567/pwdlib), recommended by [FastAPI](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/security/oauth2-jwt.md) | Argon2id password hashing. Existing scrypt credentials still verify and upgrade only after a successful sign-in. Malformed hashes fail safely. |
| [Atomic publication pattern](https://github.com/untitaker/python-atomicwrites) | Flush a temporary file, publish its complete contents without overwriting an existing transfer, then commit metadata. We use Python's standard library; the archived package is not installed. |

The application retains revocable server-side sessions rather than changing its authentication protocol just to match an example. Existing encryption formats and data remain compatible.

These are targeted improvements, not a claim that the deployment has passed an independent security review. Every dependency is pinned in `backend/requirements.txt`; source examples are adapted to our own permission and storage rules rather than copied as a complete application.

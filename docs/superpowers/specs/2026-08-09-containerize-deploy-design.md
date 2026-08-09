# Containerize & Deploy Murzik — Design

## Context

Murzik currently only runs as a foreground Python process on Igor's Mac — if the laptop is closed/off, the bot is down, and (worse) APScheduler's periodic save job can silently miss runs across sleep (already patched with `misfire_grace_time=None`, but the root cause — the whole machine going offline — remains). Igor wants it running 24/7 independent of his laptop.

Igor already owns a VPS (`root@37.27.32.169`) used for the LucAutoWebsite project (`~/Desktop/Work/LucAutoWebsite`), which already runs Docker (a `docker-compose.yml` there runs an API container + Redis) and is reachable via SSH with a deploy key. No new VPS needs to be provisioned.

The Obsidian vault (`OBSIDIAN_VAULT_PATH`) currently lives only on Igor's Mac, with no sync mechanism to any other device. Since Murzik itself writes to the vault (`Murzik Notes/`, periodic conversation saves) in addition to Igor editing it in Obsidian, whatever runs on the VPS needs read/write access to the same vault content, kept in sync in both directions.

## Decisions

- **Host**: reuse the existing LucAuto VPS (`37.27.32.169`), as an isolated second `docker-compose` stack — own directory, own container names, no port collisions with LucAuto's `8888`/`6379`/`8081`.
- **Vault sync: Syncthing.** Self-hosted, continuous, bidirectional. Runs as its own container on the VPS, pairs with a Syncthing instance on Igor's Mac. Chosen over a git-based sync because two independent, live writers (Igor in Obsidian, Murzik via `Murzik Notes/`) is exactly the case Syncthing is built for and git is not (no real-time propagation, real conflict risk with concurrent writers).
- **Deploy method: manual SSH**, no CI. `git pull && docker compose up -d --build` run by hand (or via a small `deploy.sh` wrapping that) when Igor wants to push an update. No new GitHub Actions workflow, no new deploy-key secret — matches how infrequently this needs to change, consistent with this project's existing "don't add machinery you don't need yet" pattern.

## Architecture

Two containers, defined in a new `docker-compose.yml` at the repo root:

- **`murzik`** — built from a new `Dockerfile` (python:3.10-slim base, installs `requirements.txt`, `CMD ["python", "-m", "second_brain", "telegram"]` — confirmed entrypoint via `second_brain/cli.py`'s `telegram` subcommand). `restart: unless-stopped`.
- **`syncthing`** — official `syncthing/syncthing` image. `restart: unless-stopped`.

Both share one Docker named volume, `vault`: `syncthing` mounts it as its synced folder; `murzik` mounts the same volume at `/vault` and gets `OBSIDIAN_VAULT_PATH=/vault` via `docker-compose`'s `environment:` (which overrides the Mac-specific path in the `.env` loaded via `env_file:`).

`murzik` also bind-mounts `./data:/app/data` from the VPS host, so the Chroma index / BM25 index / `save_buffer.json` survive container rebuilds (not baked into the image, not lost on redeploy).

## Networking

- `murzik` needs no public port — it's long-polling (outbound-only to Telegram), unchanged from today.
- `syncthing`'s web UI (`8384`) binds to `127.0.0.1` only on the VPS — reached via an SSH tunnel for the one-time device-pairing step, never exposed publicly.
- `syncthing`'s sync ports (`22000/tcp`, `22000/udp`, `21027/udp`) need to be open in the VPS firewall for direct peer connections (falls back to relay servers if blocked, just slower).

## Secrets

`.env` lives only on the VPS, created by hand in the deploy directory, never committed — same pattern as LucAuto's deployment. `docker-compose`'s `env_file:` loads it into the `murzik` container.

## Deploy workflow

**One-time setup:**
1. `git clone` this repo to `/opt/murzik` on the VPS.
2. Write `.env` on the VPS (secrets only — `OBSIDIAN_VAULT_PATH` gets overridden by compose regardless).
3. `docker compose up -d --build`.
4. Open Syncthing's web UI via SSH tunnel (`ssh -L 8384:127.0.0.1:8384 root@37.27.32.169`), pair with a Syncthing instance installed on Igor's Mac (add device by ID, share the vault folder both directions), accept on both ends.

**Future code updates:** `ssh root@37.27.32.169 'cd /opt/murzik && git pull && docker compose up -d --build'`.

## Testing plan

1. **Local first** (de-risks the container itself before touching the VPS): build and run the compose stack on Igor's Mac, bind-mounting the *real* vault path directly (bypassing Syncthing entirely) instead of the `vault` named volume. Confirms the Dockerfile/compose config, env handling, and the bot's behavior inside a container are all correct in isolation.
2. **Deploy for real** to the VPS with Syncthing wired in as designed.
3. **Live verification on the VPS deployment:**
   - Message the bot via Telegram, confirm a reply — proves it's actually running from the VPS now, not the laptop.
   - Let Murzik write a note (trigger a periodic save or `Murzik Notes/` write), confirm it shows up in Obsidian on the Mac once Syncthing propagates it.
   - Edit a note directly in Obsidian on the Mac, confirm it syncs to the VPS and gets picked up by the existing `VaultWatcher` re-index logic.

## Out of scope

- Provisioning a new VPS (reusing the existing one).
- CI/CD automation for deploys (manual SSH chosen explicitly).
- Any change to the bot's own logic/behavior — this is packaging + hosting only.

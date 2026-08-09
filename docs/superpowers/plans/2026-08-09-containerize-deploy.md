# Containerize & Deploy Murzik Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package Murzik as a Docker container and deploy it to Igor's existing VPS (`root@37.27.32.169`) so it runs 24/7 independent of his laptop, with the Obsidian vault kept in sync via Syncthing.

**Architecture:** Two `docker-compose` services — `murzik` (built from a new `Dockerfile`, runs `python -m second_brain telegram`) and `syncthing` (official image) — sharing a Docker named volume `vault` for the vault contents on the VPS. Locally, a `docker-compose.override.yml` swaps the named volume for a direct bind mount of Igor's real vault path, so the container can be verified in isolation before Syncthing enters the picture at all.

**Tech Stack:** Docker, Docker Compose (v2, `docker compose` subcommand), python:3.10-slim base image, syncthing/syncthing official image.

## Global Constraints

- Entrypoint is `python -m second_brain telegram` (confirmed in `second_brain/cli.py`).
- No pytest coverage applies here — "tests" in this plan are literal build/run verification commands with an expected observable outcome (container starts, bot replies on Telegram, file appears on disk), not unit tests.
- Deploys are manual SSH, no CI/CD, no new GitHub secrets — this is a deliberate choice from the design doc, don't add automation beyond what's asked.
- Secrets (`.env`) are never committed and never baked into the image.
- Every task must be verified live before being called done — a successful `docker build` alone is not sufficient evidence a task works.
- Commit after each task, small and focused (per `[[git-commits]]` preference — no co-author trailer).

---

### Task 1: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Produces: a buildable image tagged `murzik:local` that runs `python -m second_brain telegram` as its default command. Task 2 builds on this image via `docker-compose.yml`'s `build: .`.

- [ ] **Step 1: Write `.dockerignore`**

```
.venv/
venv/
__pycache__/
*.pyc
.git/
.pytest_cache/
data/
.env
docs/
tests/
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY second_brain ./second_brain

CMD ["python", "-m", "second_brain", "telegram"]
```

- [ ] **Step 3: Build the image and verify it succeeds**

Run: `docker build -t murzik:local .`
Expected: build completes with no errors, ends with `naming to docker.io/library/murzik:local`. This will take a few minutes the first time (torch/sentence-transformers/chromadb are large) — that's expected, not a failure.

- [ ] **Step 4: Sanity-check the entrypoint without real credentials**

Run: `docker run --rm murzik:local python -m second_brain --help`
Expected: argparse help text listing the `index`, `query`, `telegram` subcommands — confirms the image has a working Python environment and the package imports cleanly, without needing `.env` or a real vault yet.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "build: add Dockerfile for containerized deployment"
```

---

### Task 2: docker-compose.yml + local override, verified against the real vault

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.override.yml`

**Interfaces:**
- Consumes: the `Dockerfile` from Task 1 (referenced via `build: .`).
- Produces: `docker compose up` runs the bot locally on Igor's Mac against his real vault via bind mount (override file), and the same `docker-compose.yml` (without the override) is what Task 3 extends with the `syncthing` service and named volume for the VPS.

`docker-compose.override.yml` is picked up automatically by `docker compose` alongside `docker-compose.yml` whenever both files are present in the same directory — this is standard Compose behavior, not a custom mechanism. On the VPS, only `docker-compose.yml` will exist (the override file is local-only, listed in `.gitignore` is NOT needed since it should stay out of the VPS checkout by simply never being copied there — see Task 4).

- [ ] **Step 1: Write `docker-compose.yml` (base — this is what ships to the VPS)**

```yaml
services:
  murzik:
    build: .
    container_name: murzik_bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - OBSIDIAN_VAULT_PATH=/vault
    volumes:
      - ./data:/app/data
      - vault:/vault

volumes:
  vault:
```

- [ ] **Step 2: Write `docker-compose.override.yml` (local-only — bind-mounts the real vault, skipping Syncthing entirely for this verification pass)**

```yaml
services:
  murzik:
    volumes:
      - ./data:/app/data
      - /Users/igortacu/Desktop/TuzikVault/TuzikVault:/vault
```

Compose merges this over the base file: the named `vault` volume mount from `docker-compose.yml` is replaced by this bind mount for local runs, everything else (env_file, environment, restart policy) is inherited unchanged.

- [ ] **Step 3: Run it locally and verify the bot actually responds on Telegram**

Run: `docker compose up --build`
Expected in the logs: `Starting Telegram bot (long-polling)...` with no traceback, followed by `HTTP Request: POST .../getUpdates "HTTP/1.1 200 OK"` lines repeating.

Then, from Telegram, send the bot a real question about something in the vault (e.g. ask about a note you know exists). Expected: a correct, grounded reply — same behavior as running it natively, just from inside the container. This is the live-verification gate for this task; a clean build log is not enough on its own.

- [ ] **Step 4: Confirm the vault-write path works inside the container too**

Ask the bot something that would trigger a `Murzik Notes/` write (or wait for/trigger the periodic save). Then, on the host:

Run: `ls "/Users/igortacu/Desktop/TuzikVault/TuzikVault/Murzik Notes/"`
Expected: the new/updated file is present with a recent mtime — confirms the bind mount is genuinely shared (writes from inside the container land on the real host vault), not an isolated copy.

- [ ] **Step 5: Stop the stack**

Run: `docker compose down`

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml docker-compose.override.yml
git commit -m "build: add docker-compose for local and VPS deployment"
```

---

### Task 3: Add Syncthing service + vault named volume

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: the `vault` named volume already declared in Task 2's `docker-compose.yml`.
- Produces: a `syncthing` service in the same compose file that the VPS deployment (Task 4) brings up alongside `murzik`.

- [ ] **Step 1: Add the `syncthing` service to `docker-compose.yml`**

```yaml
services:
  murzik:
    build: .
    container_name: murzik_bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - OBSIDIAN_VAULT_PATH=/vault
    volumes:
      - ./data:/app/data
      - vault:/vault
    depends_on:
      - syncthing

  syncthing:
    image: syncthing/syncthing:latest
    container_name: murzik_syncthing
    restart: unless-stopped
    hostname: murzik-vps
    volumes:
      - syncthing-config:/var/syncthing
      - vault:/var/syncthing/vault
    ports:
      - "127.0.0.1:8384:8384"
      - "22000:22000/tcp"
      - "22000:22000/udp"
      - "21027:21027/udp"

volumes:
  vault:
  syncthing-config:
```

`murzik`'s `depends_on: [syncthing]` only orders container *startup* (doesn't wait for the vault to actually be synced-in) — on a fresh deploy the vault will be empty until pairing happens in Task 4, which is expected and handled there, not here.

- [ ] **Step 2: Verify the compose file is syntactically valid and the new service resolves**

Run: `docker compose config`
Expected: prints the fully-resolved merged config (base + override, since the override file still touches `murzik` and is picked up automatically) with both `murzik` and `syncthing` services listed, no errors.

- [ ] **Step 3: Verify `syncthing` starts cleanly on its own (local sanity check, not a real pairing test yet)**

Run: `docker compose up syncthing`
Expected: logs show `My ID: ...` (a device ID string) and no crash loop. Then:

Run: `docker compose down`

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "build: add syncthing service for vault sync"
```

---

### Task 4: VPS deploy runbook

**Files:**
- Create: `docs/deploy-runbook.md`

**Interfaces:**
- Consumes: `Dockerfile`, `docker-compose.yml` from Tasks 1-3.
- Produces: a documented, repeatable sequence Igor runs by hand over SSH — this task's deliverable is the doc plus actually executing it once against the real VPS (Task 5 covers verifying the result).

- [ ] **Step 1: Write `docs/deploy-runbook.md`**

```markdown
# Murzik VPS Deploy Runbook

Target: `root@37.27.32.169` (existing LucAuto VPS, Docker already installed).
Deploy directory on the VPS: `/opt/murzik`.

## One-time setup

1. SSH in and clone the repo:

   ssh root@37.27.32.169
   git clone https://github.com/igortacu/Project-Tuzik /opt/murzik
   cd /opt/murzik

2. Create `.env` in `/opt/murzik` with the real secrets (OPENROUTER_API_KEY,
   TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, BRAVE_SEARCH_API_KEY,
   HF_TOKEN). OBSIDIAN_VAULT_PATH does not need to be set here -- compose
   overrides it to /vault regardless. Do NOT copy docker-compose.override.yml
   to the VPS -- only docker-compose.yml should exist there, so the vault
   named volume (synced by Syncthing) is used instead of a local bind mount.

3. Bring the stack up:

   docker compose up -d --build

4. Open Syncthing's web UI via an SSH tunnel (it's bound to 127.0.0.1 on the
   VPS on purpose -- never exposed publicly):

   ssh -L 8384:127.0.0.1:8384 root@37.27.32.169

   Then visit http://localhost:8384 in a browser on your Mac.

5. Install Syncthing on your Mac (https://syncthing.net/downloads/), open its
   web UI (usually http://localhost:8384 there too -- if both are tunneled
   to the same local port at once, tunnel the VPS one to a different local
   port, e.g. -L 8385:127.0.0.1:8384).

6. In the Mac's Syncthing UI: Add Remote Device, using the device ID shown in
   the VPS Syncthing UI (Actions > Show ID). Accept the resulting pairing
   request on the VPS side (in its tunneled web UI).

7. On the Mac's Syncthing UI: share your actual Obsidian vault folder
   (/Users/igortacu/Desktop/TuzikVault/TuzikVault) to the newly-paired VPS
   device. Accept the incoming folder share on the VPS side, pointing it at
   the "vault" folder Syncthing already sees mounted (/var/syncthing/vault).

8. Wait for the initial sync to complete (progress bar in either UI). Once
   done, the VPS's `vault` named volume contains a full copy of the vault,
   and `murzik` (which mounts that same volume at /vault) can see it.

9. Firewall: confirm 22000/tcp, 22000/udp, and 21027/udp are reachable from
   the internet on the VPS (check whatever firewall/cloud security group is
   already in front of it, alongside the existing rule for LucAuto's 8888).

## Future code updates

   ssh root@37.27.32.169 'cd /opt/murzik && git pull && docker compose up -d --build'
```

- [ ] **Step 2: Execute the one-time setup against the real VPS**

Follow the runbook's steps 1-9 for real, against `root@37.27.32.169`. This step has no separate "expected output" beyond what each numbered step already states — Task 5 is the actual live-verification gate for the deployed result.

- [ ] **Step 3: Commit the runbook**

```bash
git add docs/deploy-runbook.md
git commit -m "docs: add VPS deploy runbook for Murzik"
```

---

### Task 5: Live verification on the VPS

**Files:** none (verification-only task, no code changes expected unless something surfaces a bug).

**Interfaces:**
- Consumes: the fully deployed stack from Task 4.

- [ ] **Step 1: Confirm the bot is actually serving from the VPS, not the laptop**

Stop any locally-running instance of Murzik (native or `docker compose` on the Mac) so there's no ambiguity about which process is answering. Then message the bot on Telegram with a real question about the vault.

Expected: a correct, grounded reply, arriving even with the Mac's process fully stopped -- proves it's the VPS container serving it.

- [ ] **Step 2: Confirm Murzik's vault writes propagate back to the Mac**

Trigger a vault write from the bot (ask something that leads to a `Murzik Notes/` entry, or wait for a periodic save to fire).

Run (on the Mac): `ls -la "/Users/igortacu/Desktop/TuzikVault/TuzikVault/Murzik Notes/"`
Expected: the new file appears with a recent mtime, once Syncthing has had time to propagate it (should be seconds to low minutes).

- [ ] **Step 3: Confirm edits on the Mac propagate to the VPS and get re-indexed**

Edit or create a note directly in Obsidian on the Mac. Then check the VPS container's logs.

Run: `ssh root@37.27.32.169 'cd /opt/murzik && docker compose logs murzik --tail 50'`
Expected: a `Re-indexed external vault change: ...` log line (from `VaultWatcher`/`_on_vault_change`, unchanged existing logic) referencing the file you just edited -- confirms the synced-in file was picked up and indexed on the VPS side, not just present on disk.

- [ ] **Step 4: Confirm restart resilience**

Run: `ssh root@37.27.32.169 'docker restart murzik_bot'`

Wait ~10 seconds, then message the bot on Telegram again.

Expected: a normal reply -- confirms `restart: unless-stopped` and the container's startup sequence (including `_start_vault_watcher()`, `_warn_if_model_unknown()`) all recover cleanly without manual intervention.

- [ ] **Step 5: No commit needed** -- this task is verification-only. If any step surfaces a real bug, fix it in the relevant file from an earlier task and commit that fix with a normal descriptive message (not folded into this task).

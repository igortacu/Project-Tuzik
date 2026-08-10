# Murzik VPS Deploy Runbook

Target: `root@37.27.32.169`
Deploy directory on the VPS: `/opt/murzik`

Murzik runs as two Docker Compose services:

- `murzik`: the Telegram bot, built from this repo.
- `syncthing`: vault sync service, sharing the `vault` Docker volume with `murzik`.

The VPS must use `docker-compose.yml` only. Do not copy
`docker-compose.override.yml` to the VPS; that file is for local Mac testing and
bind-mounts the Mac vault path.

## One-Time Setup

1. SSH into the VPS:

   ```bash
   ssh root@37.27.32.169
   ```

2. Clone the repo into `/opt/murzik`:

   ```bash
   git clone https://github.com/igortacu/Project-Tuzik /opt/murzik
   cd /opt/murzik
   ```

   `docker-compose.override.yml` is gitignored, so a fresh clone will never
   bring the local Mac bind-mount override onto the VPS. Compose will only
   see `docker-compose.yml`. See `docker-compose.override.yml.example` in
   the repo for what the local-only override looks like.

3. Create `/opt/murzik/.env` with the real production values:

   ```bash
   nano /opt/murzik/.env
   chmod 600 /opt/murzik/.env
   ```

   The `chmod` restricts the file to the owner only, since it holds live
   secrets.

   Required values:

   ```dotenv
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_ALLOWED_USER_IDS=...
   OPENROUTER_API_KEY=...
   BRAVE_SEARCH_API_KEY=...
   HF_TOKEN=...
   ```

   `OBSIDIAN_VAULT_PATH` does not need to be set for the VPS. Compose sets it
   to `/vault` for the `murzik` container. Compose also sets
   `TZ=Europe/Chisinau` so Murzik's saved note timestamps use Moldova local
   time, including daylight saving changes.

4. Prepare the persistent data directory for the non-root container user:

   ```bash
   mkdir -p /opt/murzik/data
   chown -R 1000:1000 /opt/murzik/data
   ```

   Both `murzik` and `syncthing` run as UID/GID 1000 (the `syncthing`
   service sets this explicitly via `PUID`/`PGID` in `docker-compose.yml`),
   so the shared `vault` named volume and this bind-mounted `data`
   directory stay consistently owned across both containers.

5. Start the stack:

   ```bash
   cd /opt/murzik
   docker compose up -d --build
   ```

6. Confirm both containers are running:

   ```bash
   docker compose ps
   docker compose logs murzik --tail 50
   docker compose logs syncthing --tail 50
   ```

   Expected:

   - `murzik_bot` is running and logs `Starting Telegram bot (long-polling)...`.
   - `murzik_syncthing` is running and logs a Syncthing device ID.

## Syncthing Pairing

1. Open the VPS Syncthing UI through an SSH tunnel from the Mac:

   ```bash
   ssh -L 8385:127.0.0.1:8384 root@37.27.32.169
   ```

   Then open `http://localhost:8385`.

2. Install and start Syncthing on the Mac if it is not already running:

   ```text
   https://syncthing.net/downloads/
   ```

   The Mac UI is usually at `http://localhost:8384`.

3. In the Mac Syncthing UI, add the VPS as a remote device using the VPS device
   ID from the tunneled VPS UI.

4. Accept the pairing request in the VPS Syncthing UI.

5. In the Mac Syncthing UI, share the actual Obsidian vault folder with the VPS:

   ```text
   /Users/igortacu/Desktop/TuzikVault/TuzikVault
   ```

6. Accept the incoming folder share in the VPS Syncthing UI and point it at:

   ```text
   /var/syncthing/vault
   ```

7. Wait for initial sync to complete in the Syncthing UI. Once complete, the
   Docker `vault` volume contains the vault, mounted into `murzik` at `/vault`.

8. Once the initial sync finishes, restart the bot so it indexes the
   now-populated vault:

   ```bash
   ssh root@37.27.32.169 'cd /opt/murzik && docker compose restart murzik'
   ```

   This one-time restart is only needed for the initial sync. Ongoing edits
   to the vault after this point are picked up live by the `VaultWatcher`
   already running inside the bot, which logs
   `Re-indexed external vault change: ...` per changed file -- no separate
   reindex command is needed for anything after the initial sync.

## Firewall

Keep Syncthing's web UI private. The compose file binds port `8384` to
`127.0.0.1`, so use the SSH tunnel above.

Confirm these sync ports are allowed on the VPS firewall or cloud firewall:

```text
22000/tcp
22000/udp
21027/udp
```

Syncthing can fall back to relays if direct ports are blocked, but direct
connections are faster and more reliable.

## Future Code Updates

Run:

```bash
ssh root@37.27.32.169 'cd /opt/murzik && git pull && docker compose up -d --build'
```

## Verification

After deploy and initial vault sync:

1. Stop any local native or Docker Murzik process on the Mac.
2. Send Murzik a Telegram message and confirm it replies.
3. Trigger a Murzik vault write and confirm it appears on the Mac under:

   ```text
   /Users/igortacu/Desktop/TuzikVault/TuzikVault/Murzik Notes/
   ```

4. Edit a note on the Mac and confirm the VPS bot logs a re-index event:

   ```bash
   ssh root@37.27.32.169 'cd /opt/murzik && docker compose logs murzik --tail 50'
   ```

5. Restart the bot and confirm it recovers:

   ```bash
   ssh root@37.27.32.169 'docker restart murzik_bot'
   ```

   "Recovers" means: wait about 10 seconds after the restart, then send
   Murzik a real Telegram message and confirm it sends back a normal reply,
   confirming the restart didn't break long-polling.

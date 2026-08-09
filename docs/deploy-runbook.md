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

   For future updates:

   ```bash
   git pull
   ```

3. Create `/opt/murzik/.env` with the real production values:

   ```bash
   nano /opt/murzik/.env
   ```

   Required values:

   ```dotenv
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_ALLOWED_USER_IDS=...
   OPENROUTER_API_KEY=...
   BRAVE_SEARCH_API_KEY=...
   HF_TOKEN=...
   ```

   `OBSIDIAN_VAULT_PATH` does not need to be set for the VPS. Compose sets it
   to `/vault` for the `murzik` container.

4. Prepare the persistent data directory for the non-root container user:

   ```bash
   mkdir -p /opt/murzik/data
   chown -R 1000:1000 /opt/murzik/data
   ```

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

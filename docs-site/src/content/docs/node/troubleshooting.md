---
title: "Troubleshooting"
description: "Common Astromesh Node issues, platform-specific diagnostics, and astromeshctl doctor"
---

## Quick Diagnostics

Start with the built-in health check:

```bash
astromeshctl doctor
```

This checks: daemon status, API responsiveness, all provider connections, memory backends, and configuration validity.

For a quick status overview:

```bash
astromeshctl status
```

---

## Common Issues (All Platforms)

### Daemon does not start

**Step 1:** Check the daemon logs for errors.

- Linux: `sudo journalctl -u astromeshd -n 50`
- macOS: `tail -n 50 /var/log/astromesh/astromeshd.log`
- Windows: `Get-Content "C:\ProgramData\Astromesh\logs\astromeshd.log" -Tail 50`

**Step 2:** Validate your configuration:

```bash
astromeshctl config validate
```

**Step 3:** Check for port conflicts. Another process may be using port 8000:

- Linux/macOS: `sudo ss -tlnp | grep 8000` or `lsof -i :8000`
- Windows: `netstat -ano | findstr 8000`

Change the port in `runtime.yaml` or stop the conflicting process.

### API returns 503 / connection refused

The daemon may still be starting. Wait 10–30 seconds, then:

```bash
astromeshctl status
curl http://localhost:8000/v1/health
```

If the daemon is running but the API is not responding, check if the `api` service is enabled in `runtime.yaml`:

```yaml
spec:
  services:
    api: true    # Must be true
```

### Configuration syntax error

```
ERROR: Failed to parse /etc/astromesh/runtime.yaml: expected ':', line 5
```

Fix YAML syntax issues, then validate:

```bash
astromeshctl config validate
sudo systemctl restart astromeshd  # Linux
```

### Provider connection failures

```
ERROR: Provider 'ollama' health check failed: Connection refused
```

Verify the provider is reachable:

```bash
# Ollama
curl http://localhost:11434/api/tags

# OpenAI
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

The model router circuit breaker opens after 3 consecutive failures (60-second cooldown). Check provider status:

```bash
astromeshctl providers list
astromeshctl providers health
```

### Agent not found

```json
{"detail": "Agent 'myagent' not found"}
```

Verify the agent YAML file exists and is valid:

```bash
ls /etc/astromesh/agents/           # Linux/macOS
ls "C:\ProgramData\Astromesh\config\agents\"  # Windows

astromeshctl agents list
astromeshctl config validate
```

Reload agents without restarting:

```bash
sudo astromeshctl reload
```

### Permission errors

```
PermissionError: [Errno 13] Permission denied: '/var/lib/astromesh/memory/conversations.db'
```

Fix ownership (Linux/macOS):

```bash
sudo chown -R astromesh:astromesh /var/lib/astromesh
sudo chown -R astromesh:astromesh /var/log/astromesh
```

### Stale PID file (Linux/macOS)

```
ERROR: PID file exists but process is not running
```

The daemon did not shut down cleanly. Remove the stale PID file:

```bash
sudo rm /var/lib/astromesh/data/astromeshd.pid
sudo systemctl restart astromeshd   # Linux
```

---

## Linux-Specific

### systemd service fails to start

```bash
sudo systemctl status astromeshd
sudo journalctl -u astromeshd -n 100 --no-pager
```

Common causes:

| Error | Fix |
|-------|-----|
| `Address already in use` | Change port in `runtime.yaml` or stop conflicting process |
| `Permission denied` | Check file ownership: `sudo chown -R astromesh:astromesh /var/lib/astromesh` |
| `No such file or directory` | Re-run `sudo astromeshctl init` |
| `Failed to parse config` | Run `astromeshctl config validate` and fix YAML |

### View systemd logs

```bash
# Follow live
sudo journalctl -u astromeshd -f

# Last 100 lines
sudo journalctl -u astromeshd -n 100

# Only errors
sudo journalctl -u astromeshd -p err

# Full output without pager
sudo journalctl -u astromeshd --no-pager
```

### SELinux denials (RHEL/Fedora)

```bash
# Check for SELinux denials
sudo ausearch -c astromeshd -m avc --ts recent

# Generate and apply local policy
sudo ausearch -c astromeshd -m avc | audit2allow -M astromesh_local
sudo semodule -i astromesh_local.pp
```

---

## macOS-Specific

### launchd service does not start

```bash
# Check launchd status
sudo launchctl list | grep astromesh

# View plist errors
sudo launchctl print system/com.astromesh.astromeshd

# Check logs
tail -n 100 /var/log/astromesh/astromeshd.log
```

### Gatekeeper blocks the binary

```bash
sudo xattr -d com.apple.quarantine /usr/local/bin/astromeshd
sudo xattr -d com.apple.quarantine /usr/local/bin/astromeshctl
```

Or: System Settings > Privacy & Security > click "Allow Anyway".

### Service not loading on boot

Verify the plist is in the system LaunchDaemons directory (not user LaunchAgents):

```bash
ls /Library/LaunchDaemons/com.astromesh.astromeshd.plist

# Reload
sudo launchctl unload /Library/LaunchDaemons/com.astromesh.astromeshd.plist
sudo launchctl load /Library/LaunchDaemons/com.astromesh.astromeshd.plist
```

---

## Windows-Specific

### Service fails to start

```powershell
# Check service status
Get-Service AstromeshDaemon

# View Event Log
Get-EventLog -LogName Application -Source AstromeshDaemon -Newest 20

# View log file
Get-Content "C:\ProgramData\Astromesh\logs\astromeshd.log" -Tail 50
```

### PowerShell execution policy blocks install

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

### Port 8000 in use

```powershell
netstat -ano | findstr :8000
# Find the PID, then:
Stop-Process -Id <PID>
```

Or change the port in `C:\ProgramData\Astromesh\config\runtime.yaml`.

### astromeshctl not found after install

The installer adds `C:\Program Files\Astromesh\bin\` to the system PATH. Open a new terminal (the PATH update takes effect in new sessions):

```powershell
# Or add manually to current session:
$env:Path += ";C:\Program Files\Astromesh\bin"
```

---

## Log Locations

| Platform | Log Path |
|----------|----------|
| Linux | `/var/log/astromesh/astromeshd.log` + `journalctl -u astromeshd` |
| macOS | `/var/log/astromesh/astromeshd.log` |
| Windows | `C:\ProgramData\Astromesh\logs\astromeshd.log` + Windows Event Log |

---

## Getting More Help

- Run `astromeshctl doctor --json` and share the output
- Check [GitHub Issues](https://github.com/monaccode/astromesh/issues)
- Review the [Configuration reference](/astromesh/node/configuration/) for schema errors
- Check the [CLI Reference](/astromesh/node/cli-reference/) for command usage

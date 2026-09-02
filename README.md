# Daily team calendar summary

This project runs a 9:00 AM Asia/Singapore summary from the shared Google
Calendar **SW Leave & Events** to a single pinned WhatsApp group.

## Architecture

- Google's hosted Calendar MCP, restricted to calendar-list and event reads.
- `verygoodplugins/whatsapp-mcp` v0.6.0 for the linked-device bridge.
- `src/safe_whatsapp_mcp.py` as a destination-locked MCP facade. It exposes no
  inbox-reading or arbitrary-recipient tool and records one successful send per
  date and destination.
- The Codex scheduled task remains the orchestrator.

## Setup status

Run `python -m unittest discover -s tests -v` to verify the local safety layer.
Google OAuth and WhatsApp QR pairing are one-time interactive steps. After
pairing, pin the exact group JID with:

```powershell
python src/safe_whatsapp_mcp.py --config runtime/workflow.json --resolve-group --pin
```

Never commit `runtime/` or the WhatsApp bridge `store/`; both contain sensitive
identifiers, tokens, session keys, or delivery state.


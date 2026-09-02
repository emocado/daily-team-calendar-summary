# Calendar-to-WhatsApp MCP options

Research date: 2026-09-02 (Asia/Singapore)

## Recommendation

Use Google's hosted Calendar MCP for the calendar side, subject to a one-time compatibility test with the MCP host. For WhatsApp, use the maintained `verygoodplugins/whatsapp-mcp` fork only for a limited proof of concept with the **Me, Myself and I** group and preferably a secondary WhatsApp number. Do not treat the WhatsApp leg as production-safe: it uses the unofficial WhatsApp linked-device protocol and creates a real account-suspension risk.

Keep the existing scheduler as the orchestrator. MCP supplies tools; it does not schedule jobs. The daily run should:

1. Resolve and pin the exact ID of **Team Leave & Events** (the visible calendar name; confirm whether this is the calendar the user called **Team Leave & Events**).
2. Read events from today 00:00 through the day after tomorrow 00:00 in `Asia/Singapore`, yielding today and tomorrow.
3. Format a short deterministic summary.
4. Resolve **Me, Myself and I** to its WhatsApp group JID and send once, with an idempotency record keyed by run date, destination JID, and message hash.
5. Alert rather than retrying blindly when Calendar OAuth, WhatsApp pairing, group resolution, or delivery fails.

Before enabling unattended sending, run a reboot test, a token/session renewal test, and several manual test sends. Calendar event text is untrusted input: it must be quoted/summarized as data and never treated as instructions.

## Google Calendar

### 1. Google's hosted Calendar MCP — preferred

Google now provides a remote Calendar MCP endpoint at `https://calendarmcp.googleapis.com/mcp/v1`. It can list calendars and events as well as perform writes. Google's setup guide says the service inherits the authenticated user's permissions and data-governance controls, and currently labels it **Developer Preview**. Sources: [Google configuration guide](https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server), [MCP tool reference](https://developers.google.com/workspace/calendar/api/v3/reference/mcp).

Fit for this workflow:

- `list_calendars` returns calendars the signed-in user can access and is explicitly intended to resolve a human calendar name to a `calendar_id`. A shared calendar therefore works if it appears in that user's calendar list; visible details still depend on the user's sharing role. Source: [Google `list_calendars` MCP tool](https://developers.google.com/workspace/calendar/api/v3/reference/mcp/tools_list/list_calendars).
- Use only the read scopes needed here: `calendar.calendarlist.readonly` and `calendar.events.readonly`. The official setup page also lists a free/busy scope, but this summary does not need it.
- Setup requires a Google Cloud project, the Calendar API and Calendar MCP API enabled, an OAuth consent screen/client, and an interactive sign-in. The host must support remote HTTP MCP and OAuth 2.0.
- Predetermined-time/background access requires persistent OAuth refresh handling; Google describes offline access for applications that need to act when the user is absent. Source: [Google OAuth 2.0 for web server applications](https://developers.google.com/identity/protocols/oauth2/web-server#offline).

Why preferred: Google operates the service, so there is no community Calendar daemon or third-party hosted service to trust with team-calendar data. The tradeoff is preview status and the need to confirm the current MCP host's remote-OAuth compatibility.

### 2. `nspady/google-calendar-mcp` — focused open-source fallback

This MIT-licensed TypeScript server supports multiple accounts and calendars, date-filtered event listing, local OAuth tokens, stdio, and Docker/HTTP modes. It can restrict the exposed tools with `ENABLED_TOOLS`; for this job, expose only `list-calendars`, `list-events`, and optionally `get-current-time`. The repository warns that Google test-mode OAuth credentials can require reauthentication after seven days. Source: [`nspady/google-calendar-mcp`](https://github.com/nspady/google-calendar-mcp).

If chosen, pin an exact package version or audited commit, keep credential/token files outside the repository with restrictive permissions, and avoid floating `npx` updates in a scheduled task.

### 3. `googleworkspace/cli` MCP — broader fallback

The Google Workspace CLI can expose Calendar through `gws mcp -s calendar`, uses generic Workspace API shapes, and has a broader surface than this workflow needs. It lives under the Google Workspace GitHub organization and has Apache-2.0 licensing and frequent releases, but its own README says it is not an officially supported Google product. Sources: [`googleworkspace/cli`](https://github.com/googleworkspace/cli), [releases](https://github.com/googleworkspace/cli/releases), [changelog](https://github.com/googleworkspace/cli/blob/main/CHANGELOG.md).

Use this only if the hosted Calendar MCP cannot connect and a Google-org-maintained local binary is preferable to a focused community server.

## WhatsApp

### The important platform constraint

Meta's official WhatsApp Cloud API is the supported programmable business-messaging route and requires a Meta business portfolio, WhatsApp Business Account, business phone number, and access token. Source: [Meta's official WhatsApp Business Platform collection](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api).

Meta has published a Groups API reference, but it is a distinct Business Platform capability and should be validated against the exact account and group scenario before architecture is based on it: [Meta Groups Management API reference](https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-phone-number/groups-management-api). The requested destination is an already-existing ordinary personal group. The open-source MCPs below access that kind of group by pairing as a linked device, not through Cloud API.

WhatsApp says unauthorized automated or bulk messaging violates its terms and that it uses enforcement including bans. Its messaging guidelines also identify unofficial clients and harmful automation as adversarial behavior. Even a low-volume daily post is not guaranteed safe when it is sent through a reverse-engineered client. Sources: [WhatsApp Help Center on unauthorized automation](https://faq.whatsapp.com/general/security-and-privacy/unauthorized-use-of-automated-or-bulk-messaging-on-whatsapp/), [WhatsApp Messaging Guidelines](https://www.whatsapp.com/legal/messaging-guidelines).

### 1. `verygoodplugins/whatsapp-mcp` — best proof-of-concept candidate

This maintained MIT-licensed fork connects to a personal WhatsApp account through the reverse-engineered WhatsApp Web multi-device protocol using `whatsmeow`. It pairs once by QR code, stores the session and synced messages locally in SQLite, can list chats, and can send text to an individual or a **group JID**. Sources: [repository and setup](https://github.com/verygoodplugins/whatsapp-mcp), [tool documentation](https://github.com/verygoodplugins/whatsapp-mcp#send_message), [license](https://github.com/verygoodplugins/whatsapp-mcp/blob/main/LICENSE).

Why this candidate:

- Group sending is explicit: `send_message` accepts a group JID.
- It is actively maintained: the latest listed release is v0.6.0 dated 2026-08-11, and the repository documents CI, security scanning, automated releases, and a roughly monthly demand-driven target. Sources: [releases](https://github.com/verygoodplugins/whatsapp-mcp/releases), [roadmap](https://github.com/verygoodplugins/whatsapp-mcp/blob/main/ROADMAP.md), [CI](https://github.com/verygoodplugins/whatsapp-mcp/actions/workflows/ci.yml).
- The bridge API now uses a generated bearer token, host validation, and constrained outbound-media roots. A high-severity flaw affecting versions through 0.2.0 allowed unauthorized local sends and file exfiltration; it was fixed in 0.2.1. Therefore use a current pinned release, never an old tutorial snapshot. Source: [GHSA-7jj9-4qqq-4xc4](https://github.com/verygoodplugins/whatsapp-mcp/security/advisories/GHSA-7jj9-4qqq-4xc4).

Setup/operations: Go 1.25+, Python 3.11+, `uv`, the Go bridge kept running, and one QR pairing. The MCP server defaults to stdio; HTTP/SSE is optional and binds to localhost by default. The HTTP MCP layer has no built-in authentication, so it must not be exposed beyond loopback without an authenticated proxy. Session databases, message content, and bridge tokens are sensitive local files.

### Other open-source candidates

| Project | Group support and authentication | Maintenance / license | Assessment |
|---|---|---|---|
| [`lharries/whatsapp-mcp`](https://github.com/lharries/whatsapp-mcp) | Sends to individuals or groups; QR-paired `whatsmeow`; local SQLite | MIT; original popular project, but its maintained fork says upstream has not been updated since April 2025 | Do not start here; prefer the maintained fork. |
| [`pnizer/wweb-mcp`](https://github.com/pnizer/wweb-mcp) | Explicit search-groups and send-group-message tools; QR-paired `whatsapp-web.js`/Puppeteer; persistent local auth; API-key option | MIT; 16 commits; last visible commit 2025-07-18; README calls it testing-only | Clear group API but older, browser-heavier, and explicitly not production-ready. |
| [`panghy/whatsapp-mcp-server`](https://github.com/panghy/whatsapp-mcp-server) | Electron/Baileys, QR pairing, send by chat JID, multi-account and group visibility controls | MIT; cross-platform installers and auto-update; repository explicitly warns of bans and recommends a secondary number | Friendlier desktop packaging, but a larger trusted surface and the same unofficial-client risk. |
| [`ericporres/whatsapp-mcp-server`](https://github.com/ericporres/whatsapp-mcp-server) | Group-focused Baileys server; fuzzy group names; send/reply; QR credentials | MIT; small/new repository (15 commits and no releases visible at research time) | Attractive group ergonomics, but too young to outrank the maintained fork for unattended sending. |

## Proposed architecture

```text
Daily scheduler (08:00 Asia/Singapore)
  -> Google hosted Calendar MCP (read-only OAuth)
     -> pinned calendar ID for Team Leave & Events
     -> events for today + tomorrow
  -> deterministic formatter
  -> policy/idempotency gate
  -> local verygoodplugins WhatsApp bridge
     -> pinned JID for Me, Myself and I
```

Operational guardrails:

- Pin both destination IDs after one human-reviewed discovery step; fail closed if the display name resolves ambiguously or the ID changes.
- Run the WhatsApp bridge under a dedicated OS account or tightly scoped service context, on loopback only.
- Keep Calendar write tools disabled/unused. A calendar summary never needs create, update, or delete permissions.
- Avoid feeding WhatsApp inbox history to the model; this workflow only needs an outbound send tool. Less data access reduces prompt-injection and privacy exposure.
- Store the last successful `(date, calendar_id, group_jid, message_hash)` and do not resend automatically after an uncertain delivery result.
- Add a kill switch and report failures outside WhatsApp so a broken pairing does not fail silently.

## Decision gate

Proceed with a proof of concept only if the user accepts the unofficial WhatsApp-client/account risk. The safest long-term route is to move the destination to a channel with a supported bot/API, or to use an officially eligible WhatsApp Business Groups API setup after confirming that it can serve the exact group model. If the user keeps an ordinary personal WhatsApp group, browser automation and the open-source linked-device MCPs share essentially the same policy risk; the MCP mainly improves structure and reliability, not platform authorization.

# GL.iNet Router for Home Assistant

A privacy-conscious Home Assistant custom integration for GL.iNet firmware 4.x routers. The integration is developed and API-tested against a **GL-X3000 running firmware 4.8.3** with a Quectel RM520N-GL modem.

> This is an independent community integration and is not affiliated with GL.iNet or Home Assistant.
>
> **AI-generated project disclaimer:** This project was generated and is maintained with substantial AI assistance under human direction and review. It is provided **as is**, without warranty of any kind. Review the source and test it in your own environment before relying on it, especially for SMS, network configuration, or other state-changing operations. See the [MIT License](LICENSE) for the full warranty and liability terms.

## Highlights

- Firmware 4.x challenge negotiation with MD5-, SHA-256-, and SHA-512-crypt support
- In-memory SID handling, renewal, and one retry after session expiry
- Async local polling through Home Assistant's shared HTTP session
- Immediate normalization of router responses into a privacy-safe allowlist
- Router, cellular, Multi-WAN, VPN, Tailscale, repeater, tethering, and service entities
- UniFi-style, MAC-stable client device trackers with stale-client handling
- Constrained Cellular/Ethernet 1 failover-priority control
- Optional, disabled-by-default bounded controls
- Capability-gated status-LED switch with write verification
- SMS sending, inbox events, and bounded read/delete controls without retaining message contents in coordinator state or diagnostics
- Companion GNSS setup through Home Assistant's built-in GPSD integration

## Compatibility

| Device | Firmware | Status |
| --- | --- | --- |
| GL-X3000 | 4.8.3 | API-tested, including deliberately bounded SMS actions |
| Other GL.iNet firmware 4.x routers | Unknown | May work, but endpoint availability and response schemas differ |
| Firmware 3.x | Unsupported/untested | Use an integration designed for the older API |

## Versioning

Starting with `2026.8.0`, releases use Home Assistant-style calendar versions: `YYYY.M.patch`. The year and month identify the release line, and the patch number starts at `0` and increments for follow-up releases in that month. This does not imply a release every month.

Authentication is based on the algorithm advertised by the router challenge. The password is stored only in Home Assistant's config-entry storage. The temporary SID exists only in memory.

## Installation

### HACS custom repository

1. Open HACS.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/n8detar/glinet-home-assistant` as an **Integration**.
4. Install **GL.iNet Router**.
5. Restart Home Assistant.

> HACS owns the `update.gl_inet_router_update` entity. If it shows Home Assistant's unavailable-logo placeholder instead of this integration's bundled icon, that is the upstream [HACS brands-proxy limitation](https://github.com/hacs/integration/issues/5179), not a missing repository asset. The HACS fix is being tracked in [hacs/integration#5339](https://github.com/hacs/integration/pull/5339); new custom-integration logos are no longer accepted into the legacy Home Assistant brands repository.

### Manual installation

1. Copy `custom_components/glinet_router` into Home Assistant's `custom_components` directory.
2. The resulting path must be:

   ```text
   /config/custom_components/glinet_router/manifest.json
   ```

3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration**.
5. Search for **GL.iNet Router**.

## Configuration

The config flow requests:

- Router host, IP address, or full URL
- Router administrator username
- Router administrator password
- Whether to use HTTPS
- Whether to verify the HTTPS certificate

The default endpoint is `http://192.168.8.1/rpc`. The integration does not persist the SID.

Using HTTPS is recommended when supported by the router. With HTTP, the administrator password-derived login exchange and SID travel over the local network without transport encryption.

## GPS through gpsd

GL-X3000 owners with an RM520N-GL modem should consider enabling the modem's GNSS receiver and connecting it to Home Assistant through the built-in [GPSD integration](https://www.home-assistant.io/integrations/gpsd/). This keeps location handling separate from the router integration and uses gpsd's standard local interface.

See [GL-X3000 GNSS and Home Assistant through gpsd](docs/gpsd-home-assistant.md) for the verified firmware 4.8.3 setup, Home Assistant configuration, troubleshooting, and the security precautions for unauthenticated TCP port `2947`.

## Entities

Entities are created only when their normalized source value or capability is present. Firmware-specific entities may therefore be absent.

### Router and system

- Uptime
- CPU temperature
- 1-, 5-, and 15-minute load averages
- Memory and flash utilization, with MB defaults for memory size and GB defaults for flash size
- Router mode
- Time synchronization, IPv6, QoS, SQM, LED, and USB 3 states when available
- Fan speed and running state

### Internet and Multi-WAN

- Internet connectivity
- Active Internet path
- Multi-WAN mode and sensitivity
- Repeater, Ethernet 1, Cellular, Tethering, and Ethernet 2 health
- Separate normalized failover priority

### Cellular

- Connection state
- Active SIM slot, without SIM identifiers
- Operator and network type
- LTE/NR bands and downlink bandwidth
- RSRP, RSRQ, SINR, and RSSI as disabled-by-default diagnostic sensors
- Cellular traffic total, displayed in GB by default
- Unread SMS count
- Modem model and bus diagnostic values

Cell IDs, IMEI, IMSI, ICCID, APN credentials, SIM phone numbers, and exact location are never placed in coordinator data or diagnostics.

### Services and networking

- Aggregate wired, wireless, and online client counts
- Repeater and tethering states
- Tailscale state, access flags, and numeric status
- VPN client state and tunnel count
- WireGuard/OpenVPN server state
- AdGuard Home state
- DDNS and ZeroTier state
- Firewall-rule and port-forward counts

### Client device trackers

Connected clients are exposed as default-enabled `device_tracker` entities using stable, normalized MAC addresses. Trackers report normal local-network metadata when the router supplies it:

- MAC and IP address
- Client name/hostname
- Router interface (`2.4G`, `5G`, or `cable`)
- Normalized connection type (`wireless`, `wired`, `remote`, or `unknown`)
- Blocked and remote-client status

The platform polls the local `clients.get_list` RPC because GL.iNet firmware does not provide UniFi-style push events. A client that briefly disappears or reports offline remains `home` for the configured detection period (five minutes by default), then changes to `not_home`. Clients that are already historical/offline on the first poll do not create entities. The integration does not independently create a separate device-registry device for every client; Home Assistant may associate a tracker with an existing MAC-identified device.

Under **Settings → Devices & services → GL.iNet Router → Configure**, you can disable all client tracking, exclude wired clients, ignore randomized/locally administered wireless MAC addresses, or change the detection period. Client tracker states and attributes may be retained by Home Assistant Recorder; disable client tracking if you do not want those local identities stored. Existing entity-registry enable/disable choices are preserved across upgrades.

## Controls

Network-service configuration switches are disabled by default in the entity registry. The reversible status-LED switch is enabled by default when its firmware capability is confirmed.

### Internet priority

The `Internet priority` select is available only when:

- Multi-WAN is in failover mode; and
- the expected five interfaces are present in a recognized order.

Options:

- **Ethernet before Cellular**
- **Cellular before Ethernet**

The integration reads the current configuration, changes only the Ethernet 1 and Cellular positions, sends the complete five-interface ordering, reads it back, and verifies every metric. It does not switch load balancing to failover and does not rewrite unknown/custom orders.

### Status LEDs

The `Status LEDs` switch is created only when `led.get_config` returns a boolean `led_enable` value. Turning it on or off reads the current LED configuration, sends only the verified `led_enable` field, reads the configuration back, and reports an error if the router did not apply the requested state.

Router-local LED schedules are not exposed. Use a Home Assistant automation with this switch when scheduled control is needed.

### Bounded service controls

Disabled-by-default switches may be exposed for supported firmware:

- Tailscale enablement
- Tailscale remote LAN access
- Tailscale remote WAN access
- AdGuard Home enablement
- AdGuard Home DNS protection

Mutations are serialized and followed by a coordinator refresh.

### Disruptive buttons

These capability-gated buttons are created **disabled by default**:

- **Reboot router** — requests a router reboot and does not immediately poll the rebooting device.
- **Reconnect cellular** — disconnects the detected modem, waits two seconds, reconnects it, and refreshes coordinator state.

Enable them explicitly from the Home Assistant entity registry. Cellular reconnect can leave the modem offline if disconnect succeeds but the subsequent reconnect fails; the error is surfaced to Home Assistant.

### Deliberately excluded from v1

The following unrestricted controls are **not exposed**:

- Persistent cellular connect/disconnect switch
- Generic modem AT commands
- Repeater connection or scanning
- Generic Multi-WAN configuration
- WAN disablement
- Firewall, DMZ, or port-forward mutation
- Firmware updates

## SMS actions and events

Send an SMS:

```yaml
action: glinet_router.send_sms
data:
  config_entry_id: "CONFIG_ENTRY_ID"
  phone_number: "+1XXXXXXXXXX"
  message: "Home Assistant test"
```

Use E.164 international format: `+`, the country code, and digits only. For a US or Canadian destination, use `+1` immediately followed by the 10-digit number (`+1XXXXXXXXXX`). The integration sends the value to the router unchanged and does not remove spaces, parentheses, or hyphens.

Messages are limited to 160 characters, matching the GL.iNet WebUI limit. The action rejects longer bodies before sending them to the router.

The integration also provides:

- `glinet_router.mark_sms_read`, which marks one message read using the event's `message_id`.
- `glinet_router.delete_sms`, which permanently deletes one explicitly identified message and cannot be undone.
- A disabled-by-default **Mark all SMS read** button, which updates only unread received messages.
- A disabled-by-default **Delete all read SMS** button, which permanently deletes every message the router marks read.

When inbox support is available, each normal coordinator poll checks `modem.get_sms_list`. After establishing an initial baseline, a newly observed received message fires `glinet_router_sms_received` once per integration runtime. Existing messages do not replay at setup or reload. The event data is:

| Field | Description |
| --- | --- |
| `config_entry_id` | Router config-entry ID for multi-router routing |
| `message_id` | Router message identifier accepted by the mark-read and delete actions |
| `from` | Sender number, when reported |
| `message` | Full SMS body |
| `date` | Router-provided date, when reported |

Inbox records are processed transiently and are not added to coordinator data, entity states, diagnostics, or integration logs. The integration retains only observed message IDs in memory for event deduplication. **Home Assistant events, automation traces, logbook entries, YAML, and downstream notifications may retain sender numbers, message bodies, and action inputs.** Configure Recorder and trace retention appropriately before using SMS automations.

### Example: forward received SMS to a fixed number

This automation forwards newly received messages to one configured destination, marks each exact source message read, and then permanently deletes it. Replace the placeholder with your destination in E.164 format. The event-provided `config_entry_id` routes every action to the same router that received the message. The explicit slice keeps the sender prefix and body within the router's 160-character limit.

Keep the actions in this order and do not enable `continue_on_error`: if forwarding fails, Home Assistant stops the sequence before the source is marked or deleted. A successful `send_sms` action means the router accepted the request; it does **not** prove carrier delivery. This example can therefore delete the source even when the forwarded SMS never reaches the destination—omit `delete_sms` if retaining the source is more important. **`glinet_router.delete_sms` is permanent and irreversible.** Marking the message read immediately before deleting it is redundant for the final inbox state, but both actions are included to demonstrate specific-message control with the event-provided `message_id`. Queued mode allows up to ten active or queued runs; Home Assistant rejects additional triggers while that bound is full, leaving their source messages untouched on the router.

**Forwarding exports potentially sensitive SMS content—including one-time codes and account alerts—to the destination handset, carrier, notification surfaces, and any associated backups.**

```yaml
alias: Forward and remove received GL.iNet SMS
triggers:
  - trigger: event
    event_type: glinet_router_sms_received
conditions: []
actions:
  - action: glinet_router.send_sms
    data:
      config_entry_id: "{{ trigger.event.data.config_entry_id }}"
      phone_number: "+1XXXXXXXXXX"
      message: >-
        {{ ((trigger.event.data.from | default('Unknown sender', true)) ~ ': ' ~ trigger.event.data.message)[:160] }}
  - action: glinet_router.mark_sms_read
    data:
      config_entry_id: "{{ trigger.event.data.config_entry_id }}"
      message_id: "{{ trigger.event.data.message_id }}"
  - action: glinet_router.delete_sms
    data:
      config_entry_id: "{{ trigger.event.data.config_entry_id }}"
      message_id: "{{ trigger.event.data.message_id }}"
mode: queued
max: 10
```

Another option is an AI-assisted autoresponder: pass `trigger.event.data.message` to `conversation.process`, capture its `response_variable`, and send the response to the originating number. If you build that workflow, verify the event has a usable sender, normalize it to valid E.164, allowlist trusted senders, use an Assist agent without Home Assistant control capabilities, handle empty responses, and enforce the 160-character limit in the automation rather than relying only on the prompt. Incoming SMS is untrusted input, and both automation traces and the conversation provider may retain its contents.

## Privacy and diagnostics

Raw JSON-RPC response trees are discarded after every poll. Diagnostics are generated only from normalized allowlisted data and exclude:

- Passwords, challenge hashes, and SIDs
- Router host/IP and Wi-Fi credentials
- Client names, hostnames, MAC addresses, and IP addresses
- SMS destinations, senders, and message content
- IMEI, IMSI, ICCID, SIM identifiers, and APN credentials
- Cell IDs and exact location
- Tailscale account identity
- VPN profiles, keys, certificates, peers, and logs
- Firewall and port-forward contents

Unknown numeric enums are kept numeric until verified rather than assigned speculative labels.

## Polling and failure handling

Core system calls determine coordinator health. Optional subsystem RPC failures are isolated so an unsupported VPN, DDNS, firewall, or modem endpoint does not make unrelated router entities unavailable. Authentication failures trigger Home Assistant's config-entry reauthentication handling.

The routine cellular poll uses `modem.get_status`. SMS-capable routers also poll `modem.get_sms_list` for received-message events; inbox contents are handled transiently rather than stored in coordinator data. Other historical/heavy modem calls are not polled.

## Development

```bash
uv run --with pytest-homeassistant-custom-component --with passlib pytest -q
uv run --with ruff ruff check .
uv run --with ruff ruff format --check .
python3 -m compileall -q custom_components
```

Development and live verification do not require installing the integration into the production Home Assistant instance. No live SMS read or delete mutation was executed while developing the inbox controls; mutation payloads were implemented from the sanitized firmware audit.

## License

MIT — see [LICENSE](LICENSE).

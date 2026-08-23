# GL.iNet Router for Home Assistant

A privacy-conscious Home Assistant custom integration for GL.iNet firmware 4.x routers. The initial release is developed and read-only tested against a **GL-X3000 running firmware 4.8.3** with a Quectel RM520N-GL modem.

> This is an independent community integration and is not affiliated with GL.iNet or Home Assistant.

## Highlights

- Firmware 4.x challenge negotiation with MD5-, SHA-256-, and SHA-512-crypt support
- In-memory SID handling, renewal, and one retry after session expiry
- Async local polling through Home Assistant's shared HTTP session
- Immediate normalization of router responses into a privacy-safe allowlist
- Router, cellular, Multi-WAN, VPN, Tailscale, repeater, tethering, service, and aggregate-client entities
- Constrained Cellular/Ethernet 1 failover-priority control
- Optional, disabled-by-default bounded controls
- SMS sending without retaining recipient or body in coordinator state or diagnostics

## Compatibility

| Device | Firmware | Status |
| --- | --- | --- |
| GL-X3000 | 4.8.3 | Read-only API and authentication verified |
| Other GL.iNet firmware 4.x routers | Unknown | May work, but endpoint availability and response schemas differ |
| Firmware 3.x | Unsupported/untested | Use an integration designed for the older API |

Authentication is based on the algorithm advertised by the router challenge. The password is stored only in Home Assistant's config-entry storage. The temporary SID exists only in memory.

## Installation

### HACS custom repository

1. Open HACS.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/n8detar/glinet-home-assistant` as an **Integration**.
4. Install **GL.iNet Router**.
5. Restart Home Assistant.

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

## Entities

Entities are created only when their normalized source value or capability is present. Firmware-specific entities may therefore be absent.

### Router and system

- Uptime
- CPU temperature
- 1-, 5-, and 15-minute load averages
- Memory and flash utilization
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
- RSRP, RSRQ, SINR, and RSSI
- Cellular traffic total
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

Individual client entities are deliberately excluded from v1. Client names, hostnames, MAC addresses, and IP addresses are not retained.

## Controls

All configuration switches are disabled by default in the entity registry.

### Internet priority

The `Internet priority` select is available only when:

- Multi-WAN is in failover mode; and
- the expected five interfaces are present in a recognized order.

Options:

- **Ethernet before Cellular**
- **Cellular before Ethernet**

The integration reads the current configuration, changes only the Ethernet 1 and Cellular positions, sends the complete five-interface ordering, reads it back, and verifies every metric. It does not switch load balancing to failover and does not rewrite unknown/custom orders.

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

## SMS action

Action:

```yaml
action: glinet_router.send_sms
data:
  config_entry_id: "CONFIG_ENTRY_ID"
  phone_number: "+15551234567"
  message: "Home Assistant test"
```

The destination and body are passed directly to `modem.send_sms`. They are not added to coordinator data, entity states, diagnostics, or integration logs. Home Assistant automation traces and YAML are outside the integration's control and may retain action inputs; use trace retention appropriate for sensitive messages.

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

The routine cellular poll uses `modem.get_status`; historical/heavy modem calls are not polled.

## Development

```bash
uv run --with pytest-homeassistant-custom-component --with passlib pytest -q
uv run --with ruff ruff check .
uv run --with ruff ruff format --check .
python3 -m compileall -q custom_components
```

Development and live verification do not require installing the integration into the production Home Assistant instance. Live tests used read-only RPCs only.

## License

MIT — see [LICENSE](LICENSE).

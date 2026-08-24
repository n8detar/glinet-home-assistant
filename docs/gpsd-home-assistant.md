# GL-X3000 GNSS and Home Assistant through gpsd

The Quectel RM520N-GL modem in the GL.iNet GL-X3000 includes a GNSS receiver. On firmware 4.8.3, the router can expose the modem's NMEA stream to `gpsd`, and Home Assistant can consume it through the built-in [GPSD integration](https://www.home-assistant.io/integrations/gpsd/).

This is separate from the GL.iNet Router custom integration. Keeping location in the dedicated GPSD integration avoids adding raw coordinates to the router coordinator or its diagnostics.

## Scope and prerequisites

This procedure was verified with:

- GL.iNet GL-X3000 running firmware 4.8.3
- Quectel RM520N-GL modem
- GNSS NMEA device `/dev/mhi_LOOPBACK`
- Home Assistant and the router connected through a trusted network

Other firmware releases or modem variants may expose a different device. Confirm the device before changing the configuration.

## 1. Enable GNSS on the modem

In the GL.iNet admin interface, open the modem's manual AT-command page and send:

```text
AT+QGPSCFG="autogps",1
AT+QGPS=1
```

`AT+QGPSCFG="autogps",1` enables GNSS autostart in the modem's persistent configuration. `AT+QGPS=1` starts acquisition immediately. On the tested RM520N-GL, NMEA sentences are then available at `/dev/mhi_LOOPBACK`.

After autostart has taken effect, `AT+QGPS=1` may return `+CME ERROR: 504` because GNSS is already running. Check for NMEA data before treating that response as a failure. To deliberately restart GNSS, send `AT+QGPSEND`, wait for it to stop, and then send `AT+QGPS=1` again.

A cold start may take several minutes. Place the antenna where it has a clear view of the sky before troubleshooting acquisition.

## 2. Install and configure gpsd

Install the **gpsd** package from **Applications → Plugins** in the GL.iNet admin interface. Then connect to the router over SSH and configure gpsd:

```bash
uci set gpsd.core.device='/dev/mhi_LOOPBACK'
uci set gpsd.core.listen_globally='1'
uci set gpsd.core.enabled='1'
uci commit gpsd

/etc/init.d/gpsd enable
/etc/init.d/gpsd restart
```

The standard gpsd TCP port is `2947`.

> **Security:** gpsd does not provide application-level authentication. `listen_globally='1'` exposes live location data to network clients. Use it only on a trusted LAN, do not forward TCP port `2947` from the Internet, and use firewall rules if gpsd should not be reachable from every router interface.

## 3. Verify gpsd

On the router, confirm that the service is running:

```bash
/etc/init.d/gpsd status
netstat -lnt | grep 2947
```

From a trusted client, verify that TCP port `2947` is reachable. If a gpsd client such as `gpspipe` is installed, it can also confirm that gpsd is publishing data without requiring you to copy coordinates into a bug report.

The router's generic `system.get_info` response may report `hardware_feature.gps: false` even while the modem GNSS receiver and gpsd are functioning. Treat the live NMEA/gpsd result as authoritative for this modem.

## 4. Add GPSD to Home Assistant

1. In Home Assistant, open **Settings → Devices & services**.
2. Select **Add integration** and search for **GPSD**.
3. Enter the router's trusted-LAN address as the host.
4. Leave the port at `2947` unless you deliberately changed it.
5. Complete setup and wait for the receiver to obtain a fix.

The Home Assistant GPSD integration uses local polling and can expose position, elevation, speed, and satellite information provided by gpsd.

## Troubleshooting

### Home Assistant cannot connect

- Confirm `/etc/init.d/gpsd status` reports a running service.
- Confirm gpsd is listening on TCP port `2947`.
- Confirm `listen_globally='1'` is set and committed.
- Check that the router firewall permits Home Assistant to reach port `2947` from the trusted LAN.
- Use the router's LAN address, not its public/WAN address.

### Connected, but no position fix

- Allow several minutes for a cold start.
- Move the GNSS antenna to a location with a clear view of the sky.
- Confirm the modem accepted `AT+QGPS=1`.
- Confirm NMEA data is arriving from `/dev/mhi_LOOPBACK`.
- Do not publish raw coordinates, SIM identifiers, APN credentials, or cell IDs when requesting support.

## References

- [Home Assistant GPSD integration](https://www.home-assistant.io/integrations/gpsd/)
- [gpsd documentation](https://gpsd.io/)
- [GL.iNet forum: GL-X3000 GPS configuration guide](https://forum.gl-inet.com/t/howto-gl-x3000-gps-configuration-guide/30260)

# Local Stream IP Uptime Net Monitor

Desktop monitor for checking the availability of local streams and network endpoints. It checks each configured URL, uses ping only when the URL check fails, and records availability statistics during the current session.

The application is built with Python and PyQt6 and is designed for Windows.

## Features

- Loads endpoints from `IP_FILE_LIST.xlsx`.
- Checks each URL with a lightweight HTTP request.
- Skips ping when the URL is available: a reachable URL is shown as `ONLINE`.
- Pings the configured IP only when its URL check fails.
- Shows URL and IP uptime percentages, check count, current online state, and session uptime.
- Displays `ONLINE` in green and `OFFLINE` in grey.
- Highlights the table row currently being checked, including whether it is checking the URL or ping.
- Displays the endpoint description from the Excel file.
- Lets you resize and reorder table columns.
- Supports manual scans and automatic monitoring at a configurable interval.
- Exports the current results to `REPORTE_ACTUAL.xlsx`.
- Writes an hourly global-uptime entry to `uptimelog.txt`.
- Starts maximized.

## Excel input file

Place `IP_FILE_LIST.xlsx` in the same directory as the executable. The workbook must contain these columns:

| Column | Required | Description |
| --- | --- | --- |
| `IP` | Yes | IP address used for ping when the URL is unavailable. |
| `URL` | Yes | HTTP or HTTPS endpoint to monitor. |
| `DESCRIPTION` | No | Friendly name or description displayed in the table. |

Example:

| IP | URL | DESCRIPTION |
| --- | --- | --- |
| 192.168.1.50 | http://192.168.1.50:8080/stream | Main lobby camera |
| 192.168.1.51 | https://example.local/live | Backup audio stream |

## Usage

1. Put `IP_FILE_LIST.xlsx` next to the application executable.
2. Start `LocalStreamIPUptimeNetMonitorV0.14.exe`.
3. Select **CARGAR XLSX**.
4. Use **SCAN MANUAL** for one scan, or set an interval and choose **INICIAR MONITOR**.
5. Use **EXPORTAR REPORTE** to save the current session as `REPORTE_ACTUAL.xlsx`.

## Status behavior

| Result | Displayed status | Ping behavior |
| --- | --- | --- |
| URL responds with HTTP 200 or 206 | `ONLINE` (green) | Not run |
| URL check fails, ping succeeds | `OFFLINE` (grey) | Run and recorded as successful |
| URL check fails, ping fails | `OFFLINE` (grey) | Run and recorded as failed |

`ONLINE` represents URL availability because the stream endpoint itself is the monitored service. A successful ping alone does not make the endpoint online.

## Running from source

Install Python 3.10+ and the dependencies:

```powershell
pip install pandas requests openpyxl PyQt6
python .\LocalStreamIPUptimeNetMonitorV0.14.py
```

## Building the executable

Install the build dependencies:

```powershell
pip install pandas requests openpyxl PyQt6 pyinstaller
```

Build a single Windows executable:

```powershell
pyinstaller --noconfirm --clean --name LocalStreamIPUptimeNetMonitorV0.14 --onefile --windowed --icon=LOGO.ico .\LocalStreamIPUptimeNetMonitorV0.14.py
```

The executable will be created at `dist\LocalStreamIPUptimeNetMonitorV0.14.exe`.

## Output files

- `REPORTE_ACTUAL.xlsx` — exported table snapshot.
- `uptimelog.txt` — hourly global uptime history.

## Notes

- URL checks use a five-second connection/read timeout.
- Ping is limited to one request and, on Windows, a one-second timeout.
- Some devices or firewalls block ICMP ping. This does not affect an `ONLINE` result when the URL itself is available.

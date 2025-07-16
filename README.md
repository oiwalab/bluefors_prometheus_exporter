# Bluefors Prometheus Exporter

A Prometheus exporter for Bluefors Control Software API that dynamically discovers and exports all available metrics.

## Overview

This tool monitors Bluefors dilution refrigerator systems by connecting to their API and exposing metrics in Prometheus format. It automatically discovers available metrics and exports them for monitoring and alerting.

## Requirements

- Python 3.12+
- uv (Python package manager)
- Access to Bluefors Control Software API
- Valid SSL certificate (if using SSL verification)

## Installation

1. Clone the repository:
```cmd
git clone <repository-url>
cd bluefors_prometheus_exporter
```

2. Install dependencies using uv:
```cmd
uv sync
```

3. Configure the application by editing `config.yaml`

4. Put an ssl certificate `cert.pem` in the project root directory

5. Install as a Windows service (run as Administrator):
```cmd
install_service_win.bat
```

The install script will:
- Validate all required files are present
- Install Python dependencies including pywin32
- Register the service with Windows Service Manager
- Start the service immediately

## Configuration

Edit `config.yaml` to configure the exporter:

```yaml
api:
  url: "https://your-bluefors-ip:port"
  key: "your-api-key"
  cert: "cert.pem"
  verify_ssl: true

prometheus:
  port: 9091
  bind_address: "0.0.0.0"

collection:
  interval: 30  # seconds
  timeout: 10   # seconds

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## Usage

### Manual Execution

```cmd
uv run bluefors_prometheus_exporter.py
```

### Service Management
Use Windows Service Manager or standard Windows service commands to manage the service after installation.

## Metrics

The exporter automatically discovers and exports all available metrics from the Bluefors API. Metrics are available at:

```
http://localhost:{port}/metrics
```


### Service Uninstallation
```cmd
# Uninstall service (run as Administrator)
uninstall_service_win.bat
```


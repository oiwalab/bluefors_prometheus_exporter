#!/usr/bin/env python3
"""
Universal Prometheus exporter for Bluefors Control Software API

This exporter dynamically discovers and exports all available metrics
from the Bluefors Control Software API.
"""

import re
import sys
import time
import logging
import argparse
import requests
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from prometheus_client import start_http_server, Gauge, Info, Counter
import urllib3
from dataclasses import dataclass
from enum import Enum

# Disable SSL warnings if needed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class Config:
    """Configuration data class"""
    api_url: str
    api_key: Optional[str]
    cert_path: Optional[str]
    verify_ssl: bool
    prometheus_port: int
    bind_address: str
    collection_interval: int
    timeout: int
    log_level: str
    log_format: str


class BlueforsExporter:
    """Prometheus exporter for Bluefors API metrics"""
    
    def __init__(self, config: Config):
        """
        Initialize the exporter
        
        Args:
            config: Configuration object
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.base_url = config.api_url.rstrip('/')
        
        # Create session
        self.session = requests.Session()
        if config.api_key:
            self.session.params = {'key': config.api_key}
        self.session.timeout = config.timeout
        
        # Initialize metrics
        self.system_info = Info('bluefors_system', 'Bluefors system information')
        self.collection_duration = Gauge('bluefors_collection_duration_seconds', 'Duration of metrics collection')
        self.collection_errors = Counter('bluefors_collection_errors_total', 'Total number of collection errors')
        self.metrics: Dict[str, Gauge] = {}
        
        # Update system info
        self._update_system_info()
    
    def _get_cert_verify(self) -> bool | str:
        """Get certificate verification setting"""
        if not self.config.verify_ssl:
            return False
        return self.config.cert_path if self.config.cert_path else True
    
    def _update_system_info(self):
        """Update system information metric"""
        try:
            response = self.session.get(f"{self.base_url}/system/", verify=self._get_cert_verify())
            if response.status_code == 200:
                data = response.json()
                system_data = data.get('data', {})
                self.system_info.info({
                    'system_name': system_data.get('system_name', 'Unknown'),
                    'system_version': system_data.get('system_version', 'Unknown'),
                    'product_type': system_data.get('product_type', 'Unknown'),
                    'api_version': system_data.get('api_version', 'Unknown')
                })
                self.logger.info(f"Connected to Bluefors system: {system_data.get('system_name')}")
        except Exception as e:
            self.logger.error(f"Failed to get system info: {e}")
            self.collection_errors.inc()
    
    def _normalize_metric_name(self, path: str) -> str:
        """Convert API path to Prometheus metric name"""
        # Replace dots with underscores and remove driver prefix
        metric_name = path.replace('.', '_')
        metric_name = metric_name.replace('driver_', '')
        
        # Ensure valid Prometheus metric name (alphanumeric and underscores)
        metric_name = re.sub(r'[^a-zA-Z0-9_]', '_', metric_name)
        
        # Add bluefors prefix
        return f"bluefors_{metric_name}"
    
    def _extract_labels_from_path(self, path: str) -> Dict[str, str]:
        """Extract labels from API path"""
        labels = {}
        
        # Extract channel number if present
        channel_match = re.search(r'channel_(\d+)', path)
        if channel_match:
            labels['channel'] = channel_match.group(1)
        
        # Extract calibration curve number if present
        curve_match = re.search(r'calibration_curve_(\d+)', path)
        if curve_match:
            labels['curve'] = curve_match.group(1)
        
        # Extract heater number if present
        heater_match = re.search(r'heater(\d+)', path)
        if heater_match:
            labels['heater'] = heater_match.group(1)
        
        # Add the full path as a label for debugging
        labels['path'] = path
        
        return labels
    
    def _extract_unit_from_type(self, value_type: str) -> Optional[str]:
        """Extract unit from type field"""
        if not value_type:
            return None
        
        # Look for common unit patterns in type strings
        # Examples: Value.Number.Float.Unit.temperature, Value.Number.Float.Unit.pressure
        if '.Unit.' in value_type:
            parts = value_type.split('.Unit.')
            if len(parts) > 1:
                unit = parts[1].split('.')[0]  # Get first part after Unit
                return unit
        
        return None
    
    def _parse_value(self, value: Any) -> Optional[float]:
        """Parse value to float if possible"""
        if value is None or value == '':
            return None
        
        try:
            # Handle string values that might be numeric
            if isinstance(value, str):
                # Handle special status values
                if value in ['VALID', 'OK', 'ACTIVE', 'ON']:
                    return 1.0
                elif value in ['INVALID', 'ERROR', 'INACTIVE', 'OFF']:
                    return 0.0
                # Try to parse as float
                return float(value)
            else:
                return float(value)
        except (ValueError, TypeError):
            # Cannot convert to float
            return None
    
    def _get_or_create_metric(self, path: str, labels: Dict[str, str], unit: Optional[str] = None) -> Optional[Gauge]:
        """Get existing metric or create new one"""
        metric_name = self._normalize_metric_name(path)
        
        # Create unique key for this metric/label combination
        label_str = '_'.join(f"{k}={v}" for k, v in sorted(labels.items()) if k != 'path')
        metric_key = f"{metric_name}_{label_str}"
        
        if metric_key not in self.metrics:
            # Determine metric description based on path and unit
            description = f"Value from {path}"
            if unit:
                description = f"Value in {unit}"
            elif 'temperature' in path:
                description = "Temperature in Kelvin"
            elif 'resistance' in path:
                description = "Resistance in Ohms"
            elif 'reactance' in path:
                description = "Reactance in Ohms"
            elif 'pressure' in path:
                description = "Pressure value"
            elif 'flow' in path:
                description = "Flow value"
            elif 'power' in path:
                description = "Power in Watts"
            elif 'status' in path:
                description = "Status (1=VALID/OK, 0=INVALID/ERROR)"
            
            # Create new gauge metric
            try:
                self.metrics[metric_key] = Gauge(
                    metric_name,
                    description,
                    list(labels.keys())
                )
            except Exception as e:
                self.logger.error(f"Failed to create metric {metric_name}: {e}")
                return None
        
        return self.metrics[metric_key]
    
    def collect_metrics(self):
        """Collect all metrics from the API"""
        start_time = time.time()
        
        try:
            # Query the entire value tree with all available fields
            response = self.session.get(
                f"{self.base_url}/values/driver",
                verify=self._get_cert_verify()
            )
            
            if response.status_code != 200:
                self.logger.error(f"Failed to get values: HTTP {response.status_code}")
                self.collection_errors.inc()
                return
            
            data = response.json()
            values_data = data.get('data', {})
            
            # Debug: Log entries with units to see all available unit types
            debug_count = 0
            unit_types = set()
            for path, value_info in values_data.items():
                if isinstance(value_info, dict) and 'content' in value_info:
                    value_type = value_info.get('type', '')
                    unit = self._extract_unit_from_type(value_type)
                    if unit and unit not in unit_types:
                        unit_types.add(unit)
                        self.logger.debug(f"Unit found - Path: {path}, Type: {value_type}, Unit: {unit}")
                        debug_count += 1
                        if debug_count >= 15:  # Show more unit types
                            break
            
            # Process each value
            processed_count = 0
            for path, value_info in values_data.items():
                try:
                    # Skip non-value entries
                    if not isinstance(value_info, dict) or 'content' not in value_info:
                        continue
                    
                    content = value_info.get('content', {})
                    latest_value = content.get('latest_valid_value', content.get('latest_value', {}))
                    
                    if not latest_value:
                        continue
                    
                    raw_value = latest_value.get('value')
                    parsed_value = self._parse_value(raw_value)
                    
                    if parsed_value is None:
                        continue
                    
                    # Extract unit from type field
                    value_type = value_info.get('type', '')
                    unit = self._extract_unit_from_type(value_type)
                    
                    # Extract labels and create/update metric
                    labels = self._extract_labels_from_path(path)
                    metric = self._get_or_create_metric(path, labels, unit)
                    
                    if metric:
                        metric.labels(**labels).set(parsed_value)
                        processed_count += 1
                    
                except Exception as e:
                    self.logger.debug(f"Failed to process value {path}: {e}")
            
            self.logger.info(f"Processed {processed_count} metrics")
            
            # Record collection duration
            duration = time.time() - start_time
            self.collection_duration.set(duration)
            
        except Exception as e:
            self.logger.error(f"Unexpected error during collection: {e}")
            self.collection_errors.inc()
    
    def run(self):
        """Run the Prometheus exporter"""
        # Start HTTP server
        start_http_server(self.config.prometheus_port, addr=self.config.bind_address)
        self.logger.info(f"Prometheus exporter started on {self.config.bind_address}:{self.config.prometheus_port}")
        self.logger.info(f"Metrics available at http://localhost:{self.config.prometheus_port}/metrics")
        
        # Main collection loop
        while True:
            try:
                self.collect_metrics()
            except KeyboardInterrupt:
                self.logger.info("Exporter stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                self.collection_errors.inc()
            
            time.sleep(self.config.collection_interval)


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file"""
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file {config_path} not found")
    
    with open(config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    
    return Config(
        api_url=config_data['api']['url'],
        api_key=config_data['api']['key'],
        cert_path=config_data['api']['cert'],
        verify_ssl=config_data['api']['verify_ssl'],
        prometheus_port=config_data['prometheus']['port'],
        bind_address=config_data['prometheus']['bind_address'],
        collection_interval=config_data['collection']['interval'],
        timeout=config_data['collection']['timeout'],
        log_level=config_data['logging']['level'],
        log_format=config_data['logging']['format']
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Prometheus exporter for Bluefors Control Software API'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--url',
        help='Override API URL from config'
    )
    parser.add_argument(
        '--api-key',
        help='Override API key from config'
    )
    parser.add_argument(
        '--port',
        type=int,
        help='Override Prometheus port from config'
    )
    parser.add_argument(
        '--interval',
        type=int,
        help='Override collection interval from config'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Override log level from config'
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = load_config(args.config)
        
        # Override with command line arguments if provided
        if args.url:
            config.api_url = args.url
        if args.api_key:
            config.api_key = args.api_key
        if args.port:
            config.prometheus_port = args.port
        if args.interval:
            config.collection_interval = args.interval
        if args.log_level:
            config.log_level = args.log_level
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, config.log_level),
            format=config.log_format
        )
        
        # Create and run exporter
        exporter = BlueforsExporter(config)
        
        print(f"\nBluefors Prometheus Exporter")
        print(f"============================")
        print(f"Config file: {args.config}")
        print(f"API URL: {config.api_url}")
        print(f"Metrics Port: {config.prometheus_port}")
        print(f"Collection Interval: {config.collection_interval}s")
        print(f"\nExporting metrics from Bluefors API")
        print(f"Metrics available at: http://localhost:{config.prometheus_port}/metrics")
        print("\nPress Ctrl+C to stop\n")
        
        exporter.run()
        
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Missing configuration key {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
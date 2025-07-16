#!/usr/bin/env python3
"""
Windows Service wrapper for Bluefors Prometheus Exporter
"""

import sys
import time
import logging
import threading
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import os
from pathlib import Path

# Add the script directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from bluefors_prometheus_exporter import BlueforsExporter, load_config


class BlueforsExporterService(win32serviceutil.ServiceFramework):
    _svc_name_ = "BlueforsPrometheusExporter"
    _svc_display_name_ = "Bluefors Prometheus Exporter"
    _svc_description_ = "Prometheus exporter for Bluefors Control Software API"
    
    # Set the correct python executable path for virtual environment
    _exe_name_ = sys.executable
    _exe_args_ = f'"{__file__}"'

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_running = True

    def SvcStop(self):
        """Stop the service"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False

    def SvcDoRun(self):
        """Main service method"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        # Report service as running IMMEDIATELY - this is critical for Windows
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        
        # Now start the actual work
        self.main_loop()

    def main_loop(self):
        """Service main loop"""
        try:
            # Add virtual environment path to sys.path for module imports
            script_dir = Path(__file__).parent
            venv_path = script_dir / ".venv"
            if venv_path.exists():
                site_packages = venv_path / "Lib" / "site-packages"
                if site_packages.exists():
                    sys.path.insert(0, str(site_packages))
            
            # Determine config file path
            config_path = script_dir / "config.yaml"
            
            # Load configuration
            config = load_config(str(config_path))
            
            # Fix relative paths in config to absolute paths
            if hasattr(config, 'cert_path') and config.cert_path and not os.path.isabs(config.cert_path):
                config.cert_path = str(script_dir / config.cert_path)
            
            # Configure logging
            log_file = script_dir / "bluefors_exporter.log"
            logging.basicConfig(
                level=getattr(logging, config.log_level),
                format=config.log_format,
                handlers=[
                    logging.FileHandler(log_file, mode='a'),
                ]
            )
            
            logging.info("Starting Bluefors Prometheus Exporter Service...")
            
            # Create exporter instance
            exporter = BlueforsExporter(config)
            
            # Start HTTP server in a separate thread
            from prometheus_client import start_http_server
            
            def start_metrics_server():
                start_http_server(config.prometheus_port, addr=config.bind_address)
            
            server_thread = threading.Thread(target=start_metrics_server)
            server_thread.daemon = True
            server_thread.start()
            
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                0,
                f"Prometheus exporter started on {config.bind_address}:{config.prometheus_port}"
            )
            logging.info(f"Prometheus exporter started on {config.bind_address}:{config.prometheus_port}")
            
            # Main collection loop
            while self.is_running:
                try:
                    exporter.collect_metrics()
                    
                    # Check if we should stop
                    if win32event.WaitForSingleObject(self.hWaitStop, config.collection_interval * 1000) == win32event.WAIT_OBJECT_0:
                        break
                        
                except Exception as e:
                    logging.error(f"Error during metrics collection: {e}", exc_info=True)
                    if hasattr(exporter, 'collection_errors'):
                        exporter.collection_errors.inc()
                    
        except Exception as e:
            servicemanager.LogErrorMsg(f"Service error: {str(e)}")
            logging.error(f"Service error: {e}", exc_info=True)
        finally:
            logging.info("Service stopped")
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, '')
            )


def main():
    """Entry point for Windows service"""
    if len(sys.argv) == 1:
        # Service is being started by Windows
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(BlueforsExporterService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Command line arguments for install/remove
        win32serviceutil.HandleCommandLine(BlueforsExporterService)


if __name__ == '__main__':
    main()
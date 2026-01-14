#!/usr/bin/env python3
"""
Master Local Backend Orchestrator
Runs all three local backends simultaneously
User runs: python3 main.py
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path
from typing import List, Dict
import threading
import requests

# ANSI color codes for pretty output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

# Service configurations
SERVICES = [
    {
        "name": "PLIP Backend",
        "file": "plip.py",
        "port": 5008,
        "description": "Protein-Ligand Interaction Profiler"
    },
    {
        "name": "Docking Backend",
        "file": "Docking.py",
        "port": 5006,
        "description": "AutoDock Vina Molecular Docking"
    },
    {
        "name": "RFL-Score Backend",
        "file": "rfl.py",
        "port": 5007,
        "description": "RFL-Score Binding Affinity Prediction"
    }
]

# Global process tracking
processes: Dict[str, subprocess.Popen] = {}
shutdown_flag = False


def print_banner():
    """Print startup banner"""
    print(f"\n{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}🚀 Unified Local Backend Orchestrator{Colors.END}")
    print(f"{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.GREEN}Version: 1.0.0{Colors.END}")
    print(f"{Colors.YELLOW}Managing {len(SERVICES)} backend services{Colors.END}")
    print(f"{Colors.CYAN}{'='*80}{Colors.END}\n")


def check_port_available(port: int) -> bool:
    """Check if a port is available"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def check_service_health(port: int, max_retries: int = 30, delay: float = 1.0) -> bool:
    """Check if service is responding on the given port"""
    for attempt in range(max_retries):
        try:
            response = requests.get(f"http://127.0.0.1:{port}/", timeout=2)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(delay)
    return False


def start_service(service: Dict) -> bool:
    """Start a single backend service"""
    service_file = Path(service["file"])
    
    # Check if file exists
    if not service_file.exists():
        print(f"{Colors.RED}❌ Error: {service['file']} not found!{Colors.END}")
        return False
    
    # Check if port is available
    if not check_port_available(service["port"]):
        print(f"{Colors.RED}❌ Port {service['port']} is already in use!{Colors.END}")
        print(f"{Colors.YELLOW}   Please close any application using this port{Colors.END}")
        return False
    
    print(f"{Colors.BLUE}🔄 Starting {service['name']}...{Colors.END}")
    print(f"{Colors.CYAN}   File: {service['file']}{Colors.END}")
    print(f"{Colors.CYAN}   Port: {service['port']}{Colors.END}")
    print(f"{Colors.CYAN}   Description: {service['description']}{Colors.END}")
    
    try:
        # Get the directory containing the service file
        service_dir = service_file.parent if service_file.parent.exists() else Path.cwd()
        
        # Start the process directly with Python (not as a module)
        # This allows each mainX.py to run independently with its own uvicorn setup
        process = subprocess.Popen(
            [sys.executable, str(service_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(service_dir)
        )
        
        processes[service["name"]] = process
        
        # Wait a moment for startup
        time.sleep(3)
        
        # Check if process is still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            print(f"{Colors.RED}❌ {service['name']} failed to start!{Colors.END}")
            if stderr:
                # Show last few lines of error
                error_lines = stderr.strip().split('\n')[-5:]
                for line in error_lines:
                    print(f"{Colors.RED}   {line}{Colors.END}")
            return False
        
        # Check health endpoint
        print(f"{Colors.YELLOW}   ⏳ Waiting for service to respond...{Colors.END}")
        if check_service_health(service["port"], max_retries=20, delay=1.5):
            print(f"{Colors.GREEN}✅ {service['name']} started successfully!{Colors.END}")
            print(f"{Colors.GREEN}   🌐 Running at: http://127.0.0.1:{service['port']}{Colors.END}\n")
            return True
        else:
            print(f"{Colors.RED}❌ {service['name']} started but not responding{Colors.END}")
            print(f"{Colors.YELLOW}   Check if port {service['port']} is accessible{Colors.END}")
            # Try to get some output for debugging
            try:
                time.sleep(1)
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    if stderr:
                        print(f"{Colors.YELLOW}   Last error: {stderr.strip().split(chr(10))[-1]}{Colors.END}")
            except:
                pass
            print()
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Failed to start {service['name']}: {e}{Colors.END}\n")
        return False


def monitor_service(service: Dict):
    """Monitor a service's output in a separate thread"""
    process = processes.get(service["name"])
    if not process:
        return
    
    while not shutdown_flag:
        try:
            if process.poll() is not None:
                print(f"\n{Colors.RED}⚠️  {service['name']} has stopped unexpectedly!{Colors.END}")
                break
            time.sleep(5)
        except Exception:
            break


def print_status():
    """Print status of all services"""
    print(f"\n{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}📊 Service Status Dashboard{Colors.END}")
    print(f"{Colors.CYAN}{'='*80}{Colors.END}")
    
    for service in SERVICES:
        process = processes.get(service["name"])
        if process and process.poll() is None:
            status = f"{Colors.GREEN}✅ Running{Colors.END}"
            url = f"http://127.0.0.1:{service['port']}"
        else:
            status = f"{Colors.RED}❌ Stopped{Colors.END}"
            url = "N/A"
        
        print(f"{Colors.BOLD}{service['name']}{Colors.END}")
        print(f"  Status: {status}")
        print(f"  Port: {service['port']}")
        print(f"  URL: {Colors.CYAN}{url}{Colors.END}")
        print(f"  Description: {service['description']}\n")
    
    print(f"{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.YELLOW}💡 Press Ctrl+C to stop all services{Colors.END}")
    print(f"{Colors.CYAN}{'='*80}{Colors.END}\n")


def shutdown_services(signum=None, frame=None):
    """Gracefully shutdown all services"""
    global shutdown_flag
    shutdown_flag = True
    
    print(f"\n\n{Colors.YELLOW}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.YELLOW}🛑 Shutting down all services...{Colors.END}")
    print(f"{Colors.YELLOW}{'='*80}{Colors.END}\n")
    
    for service_name, process in processes.items():
        try:
            print(f"{Colors.BLUE}⏹️  Stopping {service_name}...{Colors.END}")
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=5)
                print(f"{Colors.GREEN}✅ {service_name} stopped gracefully{Colors.END}")
            except subprocess.TimeoutExpired:
                print(f"{Colors.YELLOW}⚠️  Force killing {service_name}...{Colors.END}")
                process.kill()
                process.wait()
                print(f"{Colors.GREEN}✅ {service_name} force stopped{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}❌ Error stopping {service_name}: {e}{Colors.END}")
    
    print(f"\n{Colors.GREEN}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}✅ All services stopped successfully!{Colors.END}")
    print(f"{Colors.GREEN}{'='*80}{Colors.END}\n")
    
    sys.exit(0)


def main():
    """Main orchestrator function"""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_services)
    signal.signal(signal.SIGTERM, shutdown_services)
    
    print_banner()
    
    # Check Python version
    if sys.version_info < (3, 8):
        print(f"{Colors.RED}❌ Python 3.8 or higher is required!{Colors.END}")
        print(f"{Colors.YELLOW}   Current version: {sys.version}{Colors.END}")
        sys.exit(1)
    
    print(f"{Colors.GREEN}✅ Python version: {sys.version.split()[0]}{Colors.END}\n")
    
    # Start all services
    started_count = 0
    for service in SERVICES:
        if start_service(service):
            started_count += 1
            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=monitor_service,
                args=(service,),
                daemon=True
            )
            monitor_thread.start()
        else:
            print(f"{Colors.RED}⚠️  Failed to start {service['name']}{Colors.END}")
            print(f"{Colors.YELLOW}   Continuing with other services...{Colors.END}\n")
    
    if started_count == 0:
        print(f"{Colors.RED}❌ No services started successfully!{Colors.END}")
        print(f"{Colors.YELLOW}Please check the error messages above{Colors.END}")
        sys.exit(1)
    
    # Print final status
    print(f"{Colors.GREEN}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}🎉 Successfully started {started_count}/{len(SERVICES)} services!{Colors.END}")
    print(f"{Colors.GREEN}{'='*80}{Colors.END}\n")
    
    print_status()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(10)
            
            # Check if any service has crashed
            for service in SERVICES:
                process = processes.get(service["name"])
                if process and process.poll() is not None:
                    print(f"\n{Colors.RED}⚠️  WARNING: {service['name']} is no longer running!{Colors.END}")
                    print(f"{Colors.YELLOW}Consider restarting the orchestrator{Colors.END}\n")
    except KeyboardInterrupt:
        shutdown_services()


if __name__ == "__main__":
    main()

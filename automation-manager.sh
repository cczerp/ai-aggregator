#!/bin/bash
# ArbiGirl Automation Manager
# Helps manage the background automation service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="arbigirl-automation.service"
SERVICE_NAME="arbigirl-automation"
SYSTEMD_DIR="/etc/systemd/system"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  ArbiGirl Automation Manager${NC}"
    echo -e "${CYAN}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

check_requirements() {
    print_info "Checking requirements..."

    # Check if running on Linux
    if [[ ! "$OSTYPE" =~ ^linux ]]; then
        print_error "This script is designed for Linux systems"
        exit 1
    fi

    # Check if logs directory exists
    if [ ! -d "$SCRIPT_DIR/logs" ]; then
        mkdir -p "$SCRIPT_DIR/logs"
        print_success "Created logs directory"
    fi

    # Check if .env file exists
    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        print_warning ".env file not found"
        print_info "Make sure to configure your .env file before starting"
    fi

    # Check if Python script exists
    if [ ! -f "$SCRIPT_DIR/run_graph_automation.py" ]; then
        print_error "run_graph_automation.py not found!"
        exit 1
    fi

    print_success "All requirements met"
}

install_service() {
    print_info "Installing systemd service..."

    check_requirements

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run with sudo to install systemd service"
        print_info "Usage: sudo $0 install"
        exit 1
    fi

    # Copy service file
    cp "$SCRIPT_DIR/$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_FILE"
    print_success "Service file copied to $SYSTEMD_DIR"

    # Reload systemd
    systemctl daemon-reload
    print_success "Systemd daemon reloaded"

    # Enable service
    systemctl enable "$SERVICE_NAME"
    print_success "Service enabled (will start on boot)"

    print_success "Installation complete!"
    print_info "Use '$0 start' to start the service"
}

uninstall_service() {
    print_info "Uninstalling systemd service..."

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run with sudo to uninstall systemd service"
        print_info "Usage: sudo $0 uninstall"
        exit 1
    fi

    # Stop service if running
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
        print_success "Service stopped"
    fi

    # Disable service
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl disable "$SERVICE_NAME"
        print_success "Service disabled"
    fi

    # Remove service file
    if [ -f "$SYSTEMD_DIR/$SERVICE_FILE" ]; then
        rm "$SYSTEMD_DIR/$SERVICE_FILE"
        print_success "Service file removed"
    fi

    # Reload systemd
    systemctl daemon-reload
    print_success "Systemd daemon reloaded"

    print_success "Uninstallation complete!"
}

start_service() {
    print_info "Starting automation service..."

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run with sudo to start systemd service"
        print_info "Usage: sudo $0 start"
        exit 1
    fi

    systemctl start "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service started successfully"
        print_info "Use '$0 status' to check status"
        print_info "Use '$0 logs' to view logs"
    else
        print_error "Failed to start service"
        print_info "Check logs with: sudo journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
}

stop_service() {
    print_info "Stopping automation service..."

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run with sudo to stop systemd service"
        print_info "Usage: sudo $0 stop"
        exit 1
    fi

    systemctl stop "$SERVICE_NAME"
    print_success "Service stopped"
}

restart_service() {
    print_info "Restarting automation service..."

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run with sudo to restart systemd service"
        print_info "Usage: sudo $0 restart"
        exit 1
    fi

    systemctl restart "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service restarted successfully"
    else
        print_error "Failed to restart service"
        exit 1
    fi
}

show_status() {
    print_info "Service status:"
    echo ""
    systemctl status "$SERVICE_NAME" --no-pager || true
}

show_logs() {
    print_info "Showing recent logs (last 100 lines)..."
    print_info "Press Ctrl+C to exit"
    echo ""

    # Try systemd logs first
    if command -v journalctl &> /dev/null; then
        sudo journalctl -u "$SERVICE_NAME" -n 100 -f
    else
        # Fall back to file logs
        tail -f "$SCRIPT_DIR/logs/automation.log" 2>/dev/null || \
        print_error "No logs available"
    fi
}

run_foreground() {
    print_info "Running automation in foreground..."
    check_requirements

    cd "$SCRIPT_DIR"
    python3 run_graph_automation.py
}

show_help() {
    print_header
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  install       Install systemd service (requires sudo)"
    echo "  uninstall     Uninstall systemd service (requires sudo)"
    echo "  start         Start the automation service (requires sudo)"
    echo "  stop          Stop the automation service (requires sudo)"
    echo "  restart       Restart the automation service (requires sudo)"
    echo "  status        Show service status"
    echo "  logs          Show and follow logs"
    echo "  run           Run automation in foreground (no systemd)"
    echo "  help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo $0 install    # Install and enable service"
    echo "  sudo $0 start      # Start the service"
    echo "  $0 status          # Check if running"
    echo "  $0 logs            # View logs"
    echo "  $0 run             # Run directly (for testing)"
    echo ""
}

# Main script
print_header
echo ""

case "${1:-}" in
    install)
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    run)
        run_foreground
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: ${1:-}"
        echo ""
        show_help
        exit 1
        ;;
esac

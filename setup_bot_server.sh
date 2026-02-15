#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Default: run all steps
RUN_SYSTEM_UPDATE=false
RUN_UV_INSTALL=false
RUN_PYTHON_DEPS=false
RUN_SYSTEMD_SERVICES=false
RUN_EXTRA_TOOLS=false
RUN_SWAP=false
RUN_DISABLE_SERVICES=false

# Show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --all                  Run all setup steps (default if no options specified)"
    echo "  --system-update        Update and upgrade the system"
    echo "  --uv-install           Install uv Python package manager"
    echo "  --python-deps          Install Python dependencies"
    echo "  --systemd-services     Configure systemd services (volume tracker + telegram bot)"
    echo "  --extra-tools          Install extra tools (byobu, zsh, oh-my-zsh)"
    echo "  --swap                 Configure swap space"
    echo "  --disable-services     Disable unnecessary services"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --all                                    # Run everything"
    echo "  $0 --systemd-services                       # Configure systemd services only"
    echo "  $0 --python-deps --systemd-services         # Install deps and configure services"
}

# Parse command line arguments
if [ $# -eq 0 ]; then
    # No arguments provided, run all
    RUN_SYSTEM_UPDATE=true
    RUN_UV_INSTALL=true
    RUN_PYTHON_DEPS=true
    RUN_SYSTEMD_SERVICES=true
    RUN_EXTRA_TOOLS=true
    RUN_SWAP=true
    RUN_DISABLE_SERVICES=true
else
    # Parse specific options
    while [ $# -gt 0 ]; do
        case $1 in
            --all)
                RUN_SYSTEM_UPDATE=true
                RUN_UV_INSTALL=true
                RUN_PYTHON_DEPS=true
                RUN_SYSTEMD_SERVICES=true
                RUN_EXTRA_TOOLS=true
                RUN_SWAP=true
                RUN_DISABLE_SERVICES=true
                shift
                ;;
            --system-update)
                RUN_SYSTEM_UPDATE=true
                shift
                ;;
            --uv-install)
                RUN_UV_INSTALL=true
                shift
                ;;
            --python-deps)
                RUN_PYTHON_DEPS=true
                shift
                ;;
            --systemd-services)
                RUN_SYSTEMD_SERVICES=true
                shift
                ;;
            --extra-tools)
                RUN_EXTRA_TOOLS=true
                shift
                ;;
            --swap)
                RUN_SWAP=true
                shift
                ;;
            --disable-services)
                RUN_DISABLE_SERVICES=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
fi

echo "Starting bot server setup..."
echo ""

# 0. Update and upgrade the system
if [ "$RUN_SYSTEM_UPDATE" = true ]; then
    echo "=== Updating and upgrading the system ==="
    apt update && apt upgrade -y
    echo "System update complete."
    echo ""
fi

# 2. Install uv (a fast Python package installer and resolver)
if [ "$RUN_UV_INSTALL" = true ]; then
    echo "=== Installing uv ==="
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for the current session and future sessions
    source $HOME/.local/bin/env
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
    echo "uv installation complete."
    echo ""
fi

# 3. Install Python dependencies using uv
if [ "$RUN_PYTHON_DEPS" = true ]; then
    echo "=== Installing Python dependencies with uv ==="
    uv venv
    source .venv/bin/activate
    echo "Virtual environment activated."
    uv python install
    echo "python version: $(python --version) installed."
    uv pip install -e .
    echo "Python dependencies installed."
    echo ""
fi

# 7. Configure systemd service for the Binance Volume Tracker
if [ "$RUN_SYSTEMD_SERVICES" = true ]; then
    echo "=== Configuring systemd services ==="
    
    # Configure volume tracker service
    echo "Creating binance-volume-tracker.service..."
    sudo bash -c 'cat <<EOF > /etc/systemd/system/binance-volume-tracker.service
[Unit]
Description=Binance Volume Tracker Script
After=network.target

[Service]
User=root
WorkingDirectory=/root/volume_tracker_binance
ExecStart=/root/volume_tracker_binance/.venv/bin/python /root/volume_tracker_binance/b_volume_alerts.py
Restart=always # This ensures the script restarts all the time after it finishes its run, it a continuous execution
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF'

    # Reload systemd to recognize the new service file
    echo "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    # Enable and start the new service
    echo "Enabling and starting binance-volume-tracker.service..."
    sudo systemctl enable binance-volume-tracker.service
    sudo systemctl start binance-volume-tracker.service

    echo "Binance Volume Tracker systemd service configured and started."
    echo ""

    # 8. Configure systemd service for the Telegram Bot Handler
    echo "Creating telegram-bot-handler.service..."
    sudo bash -c 'cat <<EOF > /etc/systemd/system/telegram-bot-handler.service
[Unit]
Description=Telegram Bot Handler Script
After=network.target

[Service]
User=root
WorkingDirectory=/root/volume_tracker_binance
ExecStart=/root/volume_tracker_binance/.venv/bin/python /root/volume_tracker_binance/telegram_bot_handler.py
Restart=always
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF'

    # Reload systemd to recognize the new service file
    echo "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    # Enable and start the new service
    echo "Enabling and starting telegram-bot-handler.service..."
    sudo systemctl enable telegram-bot-handler.service
    sudo systemctl start telegram-bot-handler.service

    echo "Telegram Bot Handler systemd service configured and started."
    echo ""
fi

# 9. additional tools
if [ "$RUN_EXTRA_TOOLS" = true ]; then
    echo "=== Installing extra tools ==="
    # byobu for better terminal management and running multiple sessions on the background
    echo "Installing byobu for terminal management..."
    apt install byobu -y

    apt install zsh -y
    # Install zsh and set it as the default shell
    # Check if Oh My Zsh is already installed to avoid re-installation prompts
    if [ ! -d "$HOME/.oh-my-zsh" ]; then
        sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
        echo "Oh My Zsh installed."
    else
        echo "Oh My Zsh is already installed."
    fi
    # Ensure .zshrc is sourced if it exists, or create a basic one if not
    if [ -f "$HOME/.zshrc" ]; then
        source ~/.zshrc
    else
        echo "Creating a basic .zshrc file."
        touch ~/.zshrc
        echo "source ~/.oh-my-zsh/ohmyzsh.sh" >> ~/.zshrc
        source ~/.zshrc
    fi
    echo "Extra tools installation complete."
    echo ""
fi

# mitigate memory issues by installing and configuring swap space and disabling unnecessary services

# 9. Install and configure swap space
if [ "$RUN_SWAP" = true ]; then
    echo "=== Configuring swap space ==="
    # Check if swapfile already exists
    if [ ! -f /swapfile ]; then
        sudo fallocate -l 2G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        # Add swap file to /etc/fstab for persistence across reboots
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
        echo "Swap space configured."
    else
        echo "Swapfile already exists. Skipping creation."
    fi

    # 10. Check system memory and swap space
    echo "Checking system memory and swap space..."
    free -h
    echo ""
fi

# 11. Disable unnecessary services
if [ "$RUN_DISABLE_SERVICES" = true ]; then
    echo "=== Disabling unnecessary services ==="
    # This ensures that nothing (not even fwupd-refresh.timer, or D-Bus) can start it again:
    sudo systemctl mask fwupd.service || true
    # also mask the timer if it exists:
    sudo systemctl mask fwupd-refresh.service || true
    sudo systemctl mask fwupd-refresh.timer || true
    echo "Unnecessary services disabled."
    echo ""
fi

echo "Bot server setup script finished."

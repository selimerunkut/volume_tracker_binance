#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting bot server setup..."

# Function to configure systemd service for the Binance Volume Tracker
configure_binance_volume_tracker_service() {
    echo "Configuring systemd service for the Binance Volume Tracker..."
    # Create the service file with correct paths and user
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
}

# Function to configure systemd service for the Telegram Bot Handler
configure_telegram_bot_handler_service() {
    echo "Configuring systemd service for the Telegram Bot Handler..."
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
}

# Function to configure systemd service for the Bot Monitor
configure_bot_monitor_service() {
    echo "Configuring systemd service for the Bot Monitor..."
    sudo bash -c 'cat <<EOF > /etc/systemd/system/bot-monitor.service
[Unit]
Description=Bot Monitor Script
After=network.target

[Service]
User=root
WorkingDirectory=/root/volume_tracker_binance
ExecStart=/root/volume_tracker_binance/.venv/bin/python /root/volume_tracker_binance/bot_monitor.py
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
    echo "Enabling and starting bot-monitor.service..."
    sudo systemctl enable bot-monitor.service
    sudo systemctl start bot-monitor.service

    echo "Bot Monitor systemd service configured and started."
}

# Function to display usage instructions
display_help() {
    echo "Usage: $0 [command]"
    echo "Commands:"
    echo "  all                         - Run the full setup script (default if no command is given)"
    echo "  configure_binance_service   - Configure and start Binance Volume Tracker systemd service"
    echo "  configure_telegram_service  - Configure and start Telegram Bot Handler systemd service"
    echo "  configure_bot_monitor_service - Configure and start Bot Monitor systemd service"
    echo "  help                        - Display this help message"
}

# Main script execution
if [ -z "$1" ]; then
    # If no arguments are provided, run the full setup
    echo "Running full bot server setup..."
    # 0. Update and upgrade the system
    echo "Updating and upgrading the system..."
    apt update && apt upgrade -y

    # 2. Install uv (a fast Python package installer and resolver)
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for the current session and future sessions
    source $HOME/.local/bin/env
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc

    # 3. Install Python dependencies using uv
    echo "Installing Python dependencies with uv..."
    uv venv
    source .venv/bin/activate
    echo "Virtual environment activated."
    uv python install
    echo "python version: $(python --version) installed."
    uv pip install -e .
    echo "Python dependencies installed."

    configure_binance_volume_tracker_service
    configure_telegram_bot_handler_service
    configure_bot_monitor_service

    # 9. additional tools
    # byobu for better terminal management and running multiple sessions on the background
    echo "Installing byobu for terminal management..."
    apt install byobu

    apt install zsh
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


    # mitigate memory issues by installing and configuring swap space and disabling unnecessary services

    # 9. Install and configure swap space
    echo "Configuring swap space..."
    # Check if swapfile already exists
    if [ ! -f /swapfile ]; then
        sudo fallocate -l 2G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        # Add swap file to /etc/fstab for persistence across reboots
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    else
        echo "Swapfile already exists. Skipping creation."
    fi

    # 10. Check system memory and swap space
    echo "Checking system memory and swap space..."
    free -h

    # 11. Disable unnecessary services
    # This ensures that nothing (not even fwupd-refresh.timer, or D-Bus) can start it again:
    echo "Disabling unnecessary services..."
    sudo systemctl mask fwupd.service || true
    # also mask the timer if it exists:
    sudo systemctl mask fwupd-refresh.service || true
    sudo systemctl mask fwupd-refresh.timer || true

    echo "Bot server setup script finished."
else
    case "$1" in
        configure_binance_service)
            configure_binance_volume_tracker_service
            ;;
        configure_telegram_service)
            configure_telegram_bot_handler_service
            ;;
        configure_bot_monitor_service)
            configure_bot_monitor_service
            ;;
        all)
            echo "Running full bot server setup..."
            # 0. Update and upgrade the system
            echo "Updating and upgrading the system..."
            apt update && apt upgrade -y

            # 2. Install uv (a fast Python package installer and resolver)
            echo "Installing uv..."
            curl -LsSf https://astral.sh/uv/install.sh | sh

            # Add uv to PATH for the current session and future sessions
            source $HOME/.local/bin/env
            echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc

            # 3. Install Python dependencies using uv
            echo "Installing Python dependencies with uv..."
            uv venv
            source .venv/bin/activate
            echo "Virtual environment activated."
            uv python install
            echo "python version: $(python --version) installed."
            uv pip install -e .
            echo "Python dependencies installed."

            configure_binance_volume_tracker_service
            configure_telegram_bot_handler_service
            configure_bot_monitor_service

            # 9. additional tools
            # byobu for better terminal management and running multiple sessions on the background
            echo "Installing byobu for terminal management..."
            apt install byobu

            apt install zsh
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


            # mitigate memory issues by installing and configuring swap space and disabling unnecessary services

            # 9. Install and configure swap space
            echo "Configuring swap space..."
            # Check if swapfile already exists
            if [ ! -f /swapfile ]; then
                sudo fallocate -l 2G /swapfile
                sudo chmod 600 /swapfile
                sudo mkswap /swapfile
                sudo swapon /swapfile
                # Add swap file to /etc/fstab for persistence across reboots
                echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
            else
                echo "Swapfile already exists. Skipping creation."
            fi

            # 10. Check system memory and swap space
            echo "Checking system memory and swap space..."
            free -h

            # 11. Disable unnecessary services
            # This ensures that nothing (not even fwupd-refresh.timer, or D-Bus) can start it again:
            echo "Disabling unnecessary services..."
            sudo systemctl mask fwupd.service || true
            # also mask the timer if it exists:
            sudo systemctl mask fwupd-refresh.service || true
            sudo systemctl mask fwupd-refresh.timer || true

            echo "Bot server setup script finished."
            ;;
        help)
            display_help
            ;;
        *)
            echo "Invalid command: $1"
            display_help
            exit 1
            ;;
    esac
fi

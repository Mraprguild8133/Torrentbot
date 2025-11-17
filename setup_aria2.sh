#!/bin/bash

# Install aria2
sudo apt update
sudo apt install aria2 -y

# Create aria2 configuration
mkdir -p ~/.config/aria2
cat > ~/.config/aria2/aria2.conf << EOL
dir=/path/to/your/downloads
input-file=/root/.config/aria2/aria2.session
save-session=/root/.config/aria2/aria2.session

enable-rpc=true
rpc-listen-all=true
rpc-secret=your_secret_here

continue=true
max-connection-per-server=16
min-split-size=1M
split=16
EOL

# Create session file
touch ~/.config/aria2/aria2.session

# Start aria2
aria2c --conf-path=/root/.config/aria2/aria2.conf -D

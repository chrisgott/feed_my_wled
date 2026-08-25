#!/bin/bash

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# 1. Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install numpy
else
    source venv/bin/activate
fi

echo "Starting feed_my_wled with PipeWire..."

# 2. Dynamically get the name of your default audio sink (output device)
DEFAULT_SINK=$(wpctl inspect @DEFAULT_AUDIO_SINK@ | awk -F '"' '/node.name/ {print $2}')
echo "Capturing audio from default output: $DEFAULT_SINK"

# 3. Run pw-record in raw mode (-a) and target the default sink
pw-record -a -P "stream.capture.sink=true" --target="$DEFAULT_SINK" --rate=44100 --channels=1 --format=s16 - | python feed_my_wled.py

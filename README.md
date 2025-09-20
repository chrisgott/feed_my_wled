# Feed My WLED
A Python script that transforms an audio stream to feed WLED over the air using its audio-reactive feature.

## Why?
Version 0.15 ("Kösen") of [WLED](https://github.com/Aircoookie/WLED.git) comes with a built-in audio-reactive feature, which was previously a fork. But how can you use it? At first glance, all I found was usage via analog/digital microphones or wired add-ons. Really? That was never an option for me because I don’t want background noise displayed on my LED strip, and I’m certainly not going to lay another cable around the room. After digging into the source code, it turns out WLED accepts specialized UDP packets (WARSL2 Protocol). On Windows, you may use this: [WledSRServer](https://github.com/Victoare/SR-WLED-audio-server-win). But what if you use Mac or Linux? That’s why I created this script, which can be fed with an audio stream and outputs the right data as a network UDP stream to your WLED strip.

## Working Principle on macOS
* Play some music (e.g., Apple Music) and share audio with your regular output AND Shairport-Sync.
* Configure Shairport-Sync to output audio as a FIFO stream — this can be done on the same Mac.
* Feed your stream to `feed_my_wled.py`.
* WLED receives your stream and reacts to audio by choosing sound-reactive effects.

## Working Principle on Linux
To be honest, I know it will work but haven’t tested it yet. Here are some hints that might help:
* Install Shairport-Sync (or a loopback device) and play audio through it.
* Create a FIFO stream and pipe it to `feed_my_wled`.

## How It Works
`feed_my_wled.py` processes any (raw) audio stream:
* Reads the audio stream from stdin.
* Buffers the audio stream. The buffer length can be set—this feature helps with syncing. On a Mac, the stream is often ahead of the music on your speakers. Buffering resolves this issue, even during play/pause or skipping tracks.
* Calculates raw level (4B float).
* Calculates peak level (1B int).
* Calculates FFT for 16 bands, normalizes, and converts it to 1B int.
* Determines the dominant frequency.
* Calculates the magnitude sum.
* Creates a UDP packet with calculated data and fixed values (WARSL2 Protocol).
* Sends it to any WLED device on the same network (ESP32 recommended as a receiver).

## Preferences
* `WLED_IP_ADDRESS`: IP address of your WLED device.
* `WLED_UDP_PORT`: Port (default is 11988).
* `sample_rate`: Sample rate of your audio stream. Shairport-Sync’s default is 88200 (it took me hours to figure this out!).
* `buffer_size`: Default is 163840, creating a delay of ~1.5 seconds. Adjust this variable for perfect synchronization. Higher values result in more delay.
* `chunk_size`: Bytes read by the script at once. Higher values improve mean calculations and reduce network bandwidth usage. The default is 8192, resulting in ~25 packets per second, which is sufficient for a fluid experience.

## Setup (on a Mac)
I recommend using Homebrew for all installations.

1. Install Python 3 and its dependencies (if not already installed):
   * numpy
   * pyaudio
2. Download and install Shairport-Sync ([Shairport-Sync](https://github.com/mikebrady/shairport-sync)) on your Mac.
3. Edit the Shairport-Sync config file (`/usr/local/etc/shairport-sync/shairport-sync.conf` on Mac) as follows:

```json
{
  "general": {
    "name": "Shairport",
    "output_backend": "pipe",
    "port": 6000,
    "ignore_volume_control": "no",
    "audio_backend_latency_offset_in_seconds": 0.0,
    "run_this_before_play_begins": "<path_to_your/feed_my_wled.py>"
  },
  "pipe": {
    "name": "/tmp/shairport-sync-audio"
  }
}
```

4. Start Shairport (`-d` as daemon, `-k` to kill it): `shairport-sync -d`
5. Clone or download `feed_my_wled` and save it somewhere on your Mac.
6. Pipe the stream to `feed_my_wled.py`: `cat /tmp/shairport-sync-audio | ./feed_my_wled.py`
7. Configure your WLED device:
   * Settings → WiFi: Disable WiFi sleep: OFF.
   * Settings → Sync → Realtime: Enable Receive UDP Realtime.
   * Settings → Usermod → AudioReactive: Enabled ON.
   * Settings → Usermod → AudioReactive → Sync: Port: 11988.
   * Settings → Usermod → AudioReactive → Sync: Mode: Receive.
   * Reboot WLED Device.
   * Main page: Select any audio-reactive effect, tweak the settings, and enjoy the show!

## Setup (on Linux)

`# pactl load-module module-pipe-sink sink_name=wled file=/tmp/wled format=s16le rate=44100 channels=1`
`# cat /tmp/wled | ./feed_my_wled.py`

### or alternatively

`# make install`

Copy `/etc/feed_my_wled.conf.example` to `/etc/feed_my_wled.conf` or `~/.feed_my_wled.conf`.

`$ systemctl --user enable --now feed-my-wled`

See `/etc/pipewire/pipewire.conf.d/90-fft-output.conf.example` for how to create a combine sink that will always output to the wled fft sink as well as your audio sink.

### About Me
This is my first project on GitHub and also my first "real" project written in Python, a language I’ve never used before. So, if you see something weird or unusual, please have mercy and let me know how I can improve. Regards, Chris

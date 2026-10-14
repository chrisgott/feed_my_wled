#!/usr/bin/env python3

import sys
import configparser
import socket
import struct
import argparse
import numpy as np
from collections import deque

# Parse only the config file first
config_parser = argparse.ArgumentParser(add_help=False)
config_parser.add_argument(
    "-c", "--config_file",
    default="feed_my_wled.conf",
    help="Configuration file"
)
config_args, remaining = config_parser.parse_known_args()

# load preferences file
config = configparser.ConfigParser()
#config.read("feed_my_wled.conf")
config.read(config_args.config_file)

#load preferences
WLED_IP_ADDRESS = config.get("WLED", "WLED_IP_ADDRESS")
# WLED_IPS = config.get("WLED", "WLED_IPS")
WLED_UDP_PORT = config.getint("WLED", "WLED_UDP_PORT")
sample_rate = config.getint("Audio", "sample_rate")
buffer_size = config.getint("Audio", "buffer_size")
chunk_size = config.getint("Audio", "chunk_size")

# Second-stage parser: full CLI, including the audio source selection.
# This reuses -c/--config_file (already consumed above) plus new options
# that control whether audio comes from a pipe (stdin) or is captured
# directly from a local input device (e.g. a mic or a loopback/monitor
# device) using PyAudio.
parser = argparse.ArgumentParser(
    description="Feed audio-reactive UDP data to WLED.",
    parents=[config_parser]
)
parser.add_argument(
    "-s", "--source",
    choices=["stdin", "mic"],
    default="stdin",
    help="Audio source: 'stdin' reads from a pipe (default, current behavior, "
         "e.g. 'arecord ... | ./feed_my_wled.py'), 'mic' captures audio "
         "directly from a local ALSA capture device, no external pipe needed."
)
parser.add_argument(
    "-D", "--alsa-device",
    default="default",
    help="ALSA PCM device string to capture from when --source mic is selected. "
         "Uses the exact same syntax as arecord's -D flag, "
         "e.g. 'default:CARD=Device'. Defaults to 'default'."
)
parser.add_argument(
    "--list-devices",
    action="store_true",
    help="List available ALSA capture device names (usable with -D/--alsa-device) and exit."
)
args = parser.parse_args(remaining)

if args.list_devices:
    import alsaaudio
    print("Available ALSA capture devices:")
    for name in alsaaudio.pcms(alsaaudio.PCM_CAPTURE):
        print(f"  {name}")
    print("\nUse one of these with: --source mic -D <name>")
    sys.exit(0)

# def vars
previous_smoothed_level = 0.0
ring_buffer = deque(maxlen=buffer_size // chunk_size) # Ringpuffer für Blöcke (standardmäßig leer)

# create socket
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

## functions

# calculating fft
def calculate_fft(audio_chunk, sample_rate):
    """
    Calc FFT for a Audioblock
    :param audio_chunk: Audiodata as Byte-Array.
    :param sample_rate: Samplerate of Audiodata.
    :return: Tuple (FFT-Ergebnisse for 16 Frequency bands, additional peaks).
    """
    try:
        # Convert to a numpy-Array
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)

        # Calc Peak (Raw Level and Peak Level)
        raw_level = np.mean(np.abs(audio_data))
        peak_level = int((np.max(np.abs(audio_data)) / 32767) * 255)

        # Calc FFT and Amplitudes
        fft_result = np.abs(np.fft.rfft(audio_data))

        # Normalize from 0 to 255
        fft_normalized = np.interp(fft_result, (0, np.max(fft_result)), (0, 255))

        # Select first 16 frequency bands
        fft_values = fft_normalized[:16].astype(np.uint8)

        # Find dominating frequency
        freq_index = np.argmax(fft_result)
        fft_peak_frequency = freq_index * (sample_rate / len(audio_data))

        # sum of fft magnitudes
        fft_magnitude_sum = np.sum(fft_result)

        # return calced values
        return fft_values, raw_level, peak_level, fft_magnitude_sum, fft_peak_frequency

    #error handling
    except Exception as e:
        print(f"Error at calcing FFT: {e}")
        return None, 0, 0, 0, 0, 0

# function for creating the udp package
def create_udp_packet(fft_values, raw_level, smoothed_level, peak_level, fft_magnitude_sum, fft_peak_frequency):
    """
    Creating udp-package in a wled compatible format
    :param fft_values: fft datas for 16 frequency bands
    :param raw_level: mean of audiosource
    :param smoothed_level: smoothed level of audiosource
    :param peak_level: mac peak of audiosource
    :param fft_magnitude_sum: sum of fft magnitudes
    :param fft_peak_frequency: dominant frequency of audiosignal
    :return: formated UDP-package
    """
    # Convert Values
    peak_level = int(peak_level)               # limit to uint8
    fft_values = [int(v) for v in fft_values]   # limit to uint8

    # Create package according to the WLED Protocol
    udp_packet = struct.pack('<6s2B2fBB16B2B2f',  # don't mess with that!
        b'00002',                     # Header (6 Bytes)
        0,0,                          # Gap (2 Bytes)
        float(raw_level),             # Raw Level (4 Bytes Float)
        float(smoothed_level),        # Smoothed Level (4 Bytes Float)
        peak_level,                   # Peak Level (1 Byte)
        0,                            # static 0 (1 Byte)
        *fft_values,                  # FFT Result (16 Bytes)
        0,0,                          # Gap (2 Bytes)
        float(fft_magnitude_sum),     # FFT Magnitude (4 Bytes Float)
        float(fft_peak_frequency))    # FFT Major Peak (4 Bytes Float)

    return udp_packet


def make_stdin_reader():
    """
    Returns a zero-arg callable that reads one chunk_size block of raw
    audio bytes from stdin (the original piped-input behavior).
    """
    def _read():
        return sys.stdin.buffer.read(chunk_size)
    return _read


def make_mic_reader(alsa_device):
    """
    Returns a zero-arg callable that reads one chunk_size block of raw
    audio bytes directly from an ALSA capture device (same device string
    syntax as `arecord -D ...`), replacing the external arecord pipe.
    """
    import alsaaudio

    # chunk_size is in bytes (mono, 16-bit = 2 bytes/frame)
    frames_per_period = max(1, chunk_size // 2)

    pcm = alsaaudio.PCM(
        type=alsaaudio.PCM_CAPTURE,
        mode=alsaaudio.PCM_NORMAL,
        device=alsa_device,
        channels=1,
        rate=sample_rate,
        format=alsaaudio.PCM_FORMAT_S16_LE,
        periodsize=frames_per_period,
    )

    buffer = bytearray()

    def _read():
        nonlocal buffer
        # Accumulate until we have a full chunk_size block, since ALSA
        # periods don't always land exactly on chunk_size boundaries.
        while len(buffer) < chunk_size:
            length, data = pcm.read()
            if length > 0:
                buffer.extend(data)
        chunk, remainder = bytes(buffer[:chunk_size]), buffer[chunk_size:]
        buffer = bytearray(remainder)
        return chunk

    _read.pcm = pcm
    return _read


# main function
def stream_audio_to_wled(read_chunk, source_label):
    """
    Reads audiodata from the given source and sends analyzed fft results to WLED
    :param read_chunk: zero-arg callable returning chunk_size bytes of raw audio
    :param source_label: human readable description of the source, for logging
    """
    global previous_smoothed_level, ring_buffer

    # init buffer with zeros
    for _ in range(ring_buffer.maxlen):
        ring_buffer.append(b"\x00" * chunk_size)

    try:
        print(f"Starting {source_label} to WLED at {WLED_IP_ADDRESS}:{WLED_UDP_PORT} ")

        # open stream from source
        while True:
            # read datas from source
            audio_data = read_chunk()
            if audio_data:
                ring_buffer.append(audio_data)  # push data to buffer

                # combine blocks for prozessing
                combined_data = b"".join(ring_buffer)

                # Calc FFT and Peaks with buffersize
                fft_result = calculate_fft(combined_data[:chunk_size], sample_rate)
                if fft_result[0] is None:
                    print("Unvalid FFT-Datas, skip actual block.")
                    continue

                # feed fft_result to its vars
                fft_data, raw_level, peak_level, fft_magnitude_sum, fft_peak_frequency = fft_result

                # Smooth the Peaks (Moving Average)
                smoothed_level = (0.8 * previous_smoothed_level) + (0.2 * raw_level)
                previous_smoothed_level = smoothed_level

                # Create UDP-Paket
                udp_packet = create_udp_packet(fft_data, raw_level, smoothed_level, peak_level, fft_magnitude_sum, fft_peak_frequency)

                # Send Package to WLED
                udp_socket.sendto(udp_packet, (WLED_IP_ADDRESS, WLED_UDP_PORT))

                # Send to multiple recievers
                #for ip in WLED_IPS:
                    #udp_socket.sendto(udp_packet, (ip, WLED_UDP_PORT))

    except KeyboardInterrupt:
        print("Audiostreaming closed.")
    finally:
        udp_socket.close()


# start
if args.source == "mic":
    reader = make_mic_reader(args.alsa_device)
    label = f"ALSA capture ({args.alsa_device})"
else:
    reader = make_stdin_reader()
    label = "Pipe"

try:
    stream_audio_to_wled(reader, label)
finally:
    # clean up the ALSA PCM handle if we opened a mic stream
    if args.source == "mic":
        reader.pcm.close()

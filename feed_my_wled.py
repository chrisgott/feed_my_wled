#!/usr/bin/env python3

import sys
import configparser
import socket
import struct
import numpy as np
from collections import deque

# load preferences file
config = configparser.ConfigParser()
config.read("feed_my_wled.conf")

#load preferences
WLED_IP_ADDRESS = config.get("WLED", "WLED_IP_ADDRESS")
WLED_UDP_PORT = config.getint("WLED", "WLED_UDP_PORT")
sample_rate = config.getint("Audio", "sample_rate")
buffer_size = config.getint("Audio", "buffer_size")
chunk_size = config.getint("Audio", "chunk_size")

# def vars
previous_smoothed_level = 0.0
ring_buffer = deque(maxlen=buffer_size // chunk_size)  # Ringpuffer für Blöcke (standardmäßig leer)

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
    peak_level = int(peak_level)  # limit to uint8
    fft_values = [int(v) for v in fft_values]  # limit to uint8

    # Create package according to the WLED Protocol
    udp_packet = struct.pack('<6s2B2fBB16B2B2f',        # don't mess with that!
        b'00002',                   # Header (6 Bytes)
        0,0,                        # Gap (2 Bytes)
        float(raw_level),           # Raw Level (4 Bytes Float)
        float(smoothed_level),      # Smoothed Level (4 Bytes Float)
        peak_level,                 # Peak Level (1 Byte)
        0,                          # static 0 (1 Byte)
        *fft_values,                # FFT Result (16 Bytes)
        0,0,                        # Gap (2 Bytes)
        float(fft_magnitude_sum),   # FFT Magnitude (4 Bytes Float)
        float(fft_peak_frequency))  # FFT Major Peak (4 Bytes Float)
    return udp_packet

# main function
def stream_audio_to_wled():
    """
    Reads audiodata from stream and send analyzed fft results to WLED
    """
    global previous_smoothed_level, ring_buffer

    # init buffer with zeros
    for _ in range(ring_buffer.maxlen):
        ring_buffer.append(b"\x00" * chunk_size)

    try:
        print(f"Start Pipe to WLED at ({WLED_IP_ADDRESS}:{WLED_UDP_PORT})...")

        # open stream from pipe
        while True:
            # read datas from pipe
            audio_data = sys.stdin.buffer.read(chunk_size)
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

    except KeyboardInterrupt:
        print("Audiostreaming closed.")
    finally:
        udp_socket.close()

# start 
stream_audio_to_wled()

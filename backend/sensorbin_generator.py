# backend/sensorbin_generator.py

import subprocess
import os
import shutil

def generate_instructions(generate_instructions_path, request_param_path, oval_file_path, timestamp):
    subprocess.run([generate_instructions_path, request_param_path, oval_file_path], check=True)

    output_file = f"cf.{timestamp}.bin.txt"
    shutil.copy("cf.bin", output_file)
    return output_file

def generate_sensor_cf(python_path, build_channel_file_path, instructions_file, timestamp, output_dir):
    cwd = os.getcwd()
    instructions_file_path = os.path.join(cwd, instructions_file)

    command = [
        python_path,
        build_channel_file_path,
        "--channel-id", "905",
        "--channel-format", "37",
        "--current-version", "1",
        "--current", instructions_file_path,
        "--channel-file", f"SensorCf.{timestamp}.bin"
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"BuildChannelFile.py failed. Output: {result.stdout}, Error: {result.stderr}")

    sensor_bin_path = os.path.join(output_dir, f"{timestamp}.bin")
    shutil.move(f"SensorCf.{timestamp}.bin", sensor_bin_path)
    return sensor_bin_path

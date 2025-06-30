# backend/vci_executor.py

import os
import paramiko
import base64
from backend.database import SessionLocal
from backend.models import Rule, VCIResult
from cryptography.fernet import Fernet
import winrm

# Load master key
master_key = os.getenv("MASTER_KEY").encode()
fernet = Fernet(master_key)


def decrypt_password(encrypted_pw: str) -> str:
    return fernet.decrypt(encrypted_pw.encode()).decode()


def run_vci_on_remote(rule_id_str, sensorbin_path,
                      remote_sensor_path="/tmp/sensor.bin",
                      remote_output_path="/tmp/output.json",
                      local_output_path=None):

    session = SessionLocal()

    # Fetch rule via ORM
    rule = session.query(Rule).filter_by(rule_id=rule_id_str).first()
    if not rule:
        session.close()
        raise Exception(f"No rule found for rule_id {rule_id_str}")

    # Find remote host for benchmark
    benchmark = rule.benchmark
    if not benchmark.remote_hosts:
        session.close()
        raise Exception(f"No remote host configured for benchmark {benchmark.name}")

    remote_host = benchmark.remote_hosts[0]

    ip_address = remote_host.ip_address
    username = remote_host.username
    encrypted_pw = remote_host.password_encrypted
    os_type = remote_host.os_type

    plaintext_pw = decrypt_password(encrypted_pw)

    if os_type.lower() == "linux":
        json_text = run_on_linux(
            ip_address, username, plaintext_pw,
            sensorbin_path, remote_sensor_path,
            remote_output_path, local_output_path
        )
    elif os_type.lower() == "windows":
        json_text = run_on_windows(
            ip_address, username, plaintext_pw,
            sensorbin_path, remote_sensor_path,
            remote_output_path, local_output_path
        )
    else:
        session.close()
        raise Exception(f"Unsupported OS type: {os_type}")

    # Save output to ORM
    vci_result = VCIResult(
        rule_id=rule.id,
        json_output=json_text
    )
    session.add(vci_result)
    session.commit()
    session.close()

    return json_text


def run_on_linux(ip, user, password,
                 sensorbin_path, remote_sensor_path,
                 remote_output_path, local_output_path):

    remote_home_dir = f"/home/{user}"
    remote_vci_dir = os.path.join(remote_home_dir, "vcidebug_testing")
    remote_vci_path = os.path.join(remote_vci_dir, "VCIDEBUGCLI")
    remote_sensor_path = os.path.join(remote_vci_dir, "sensor.bin")
    remote_output_path = os.path.join(remote_vci_dir, "output.json")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=user, password=password)

    sftp = ssh.open_sftp()

    # Create remote dir
    ssh.exec_command(f"mkdir -p {remote_vci_dir}")

    # Upload VCIDEBUGCLI binary
    local_vci_path = os.path.join(os.getcwd(), "VCIDEBUGCLI")
    sftp.put(local_vci_path, remote_vci_path)
    ssh.exec_command(f"chmod +x {remote_vci_path}")

    # Upload sensorbin
    sftp.put(sensorbin_path, remote_sensor_path)
    print(f"✅ Uploaded sensorbin to {remote_sensor_path}")

    # Run VCIDEBUGCLI
    cmd = f"{remote_vci_path} --hoststate --src {remote_sensor_path} --dest {remote_output_path}"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    exit_status = stdout.channel.recv_exit_status()

    if exit_status != 0:
        error_output = stderr.read().decode()
        ssh.close()
        raise Exception(f"VCIDEBUGCLI failed on remote Linux:\n{error_output}")

    if not local_output_path:
        local_output_path = os.path.join(os.getcwd(), f"{ip}_output.json")

    sftp.get(remote_output_path, local_output_path)
    print(f"✅ Downloaded output to {local_output_path}")

    sftp.close()
    ssh.close()

    with open(local_output_path, "r", encoding="utf-8") as f:
        json_text = f.read()

    return json_text

def run_on_windows(ip, user, password,
                   sensorbin_path, remote_sensor_path,
                   remote_output_path, local_output_path):

    remote_vci_dir = f"C:\\Users\\{user}\\vcidebug_testing"
    remote_vci_path = f"{remote_vci_dir}\\VCIDEBUGCLI.exe"
    remote_sensor_path = f"{remote_vci_dir}\\sensor.bin"
    remote_output_path = f"{remote_vci_dir}\\output.json"

    session = winrm.Session(target=ip,
                            auth=(user, password),
                            transport='ntlm')

    # Create remote folder
    ps_create = f"""
    New-Item -Path "{remote_vci_dir}" -ItemType Directory -Force
    """
    session.run_ps(ps_create)

    # Upload VCIDEBUGCLI.exe as base64
    with open("VCIDEBUGCLI.exe", "rb") as f:
        vci_data = f.read()
    vci_b64 = base64.b64encode(vci_data).decode()

    ps_vci = f"""
    $b64 = "{vci_b64}"
    $bytes = [System.Convert]::FromBase64String($b64)
    [System.IO.File]::WriteAllBytes("{remote_vci_path}", $bytes)
    """
    session.run_ps(ps_vci)

    # Upload sensor.bin as base64
    with open(sensorbin_path, "rb") as f:
        sensor_data = f.read()
    sensor_b64 = base64.b64encode(sensor_data).decode()

    ps_sensor = f"""
    $b64 = "{sensor_b64}"
    $bytes = [System.Convert]::FromBase64String($b64)
    [System.IO.File]::WriteAllBytes("{remote_sensor_path}", $bytes)
    """
    session.run_ps(ps_sensor)

    print(f"✅ Sensorbin written to Windows: {remote_sensor_path}")

    cmd = f'"{remote_vci_path}" --hoststate --src "{remote_sensor_path}" --dest "{remote_output_path}"'
    result = session.run_cmd(cmd)

    if result.status_code != 0:
        raise Exception(f"VCIDEBUGCLI failed on remote Windows:\n{result.std_err.decode()}")

    ps_read_json = f"""
    Get-Content "{remote_output_path}" | Out-String
    """
    result_json = session.run_ps(ps_read_json)

    if result_json.status_code != 0:
        raise Exception(f"Failed reading JSON output from Windows:\n{result_json.std_err.decode()}")

    json_text = result_json.std_out.decode()

    if not local_output_path:
        local_output_path = os.path.join(os.getcwd(), f"{ip}_output.json")

    with open(local_output_path, "w", encoding="utf-8") as f:
        f.write(json_text)

    print(f"✅ Downloaded Windows JSON output to {local_output_path}")

    return json_text

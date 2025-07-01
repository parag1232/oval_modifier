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


def run_vci_batch_on_linux(ip, user, password, rule_sensor_map, benchmark_dir):
    """
    Executes VCIDEBUGCLI for multiple rules over a single SSH session.

    rule_sensor_map:
        dict { rule_id -> sensorbin_path }

    benchmark_dir:
        benchmark data dir under /data

    Returns:
        dict { rule_id -> local_output_path }
    """

    remote_home_dir = f"/home/{user}"
    remote_vci_dir = os.path.join(remote_home_dir, "vcidebug_testing")
    remote_vci_path = os.path.join(remote_vci_dir, "VCIDEBUGCLI")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=user, password=password)

    sftp = ssh.open_sftp()

    # Create remote dir
    ssh.exec_command(f"mkdir -p {remote_vci_dir}")

    # Check if VCIDEBUGCLI already exists
    stdin, stdout, stderr = ssh.exec_command(f"test -f {remote_vci_path}")
    exit_status = stdout.channel.recv_exit_status()

    if exit_status != 0:
        # Upload VCIDEBUGCLI binary
        local_vci_path = os.path.join(os.getcwd(), "VCIDEBUGCLI")
        sftp.put(local_vci_path, remote_vci_path)
        ssh.exec_command(f"chmod +x {remote_vci_path}")
        print(f"✅ Uploaded VCIDEBUGCLI to remote host.")
    else:
        print(f"ℹ️ VCIDEBUGCLI already exists on remote host. Skipping upload.")

    vci_output_dir = os.path.join(benchmark_dir, "vci_output")
    os.makedirs(vci_output_dir, exist_ok=True)

    result_paths = {}

    for rule_id, sensorbin_path in rule_sensor_map.items():
        remote_sensor_path = os.path.join(remote_vci_dir, "sensor.bin")
        remote_output_path = os.path.join(remote_vci_dir, "output.json")

        # Upload sensor.bin
        sftp.put(sensorbin_path, remote_sensor_path)
        print(f"✅ Uploaded sensorbin for rule {rule_id}")

        # Run VCIDEBUGCLI
        cmd = f"{remote_vci_path} --hoststate --src {remote_sensor_path} --dest {remote_output_path}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            error_output = stderr.read().decode()
            print(f"❌ VCIDEBUGCLI failed for rule {rule_id}:\n{error_output}")
            continue

        local_output_path = os.path.join(vci_output_dir, f"{rule_id}.json")
        sftp.get(remote_output_path, local_output_path)
        print(f"✅ Downloaded VCI output for rule {rule_id} to {local_output_path}")

        result_paths[rule_id] = local_output_path

    sftp.close()
    ssh.close()

    return result_paths


def run_vci_batch_on_windows(ip, user, password, rule_sensor_map, benchmark_dir):
    """
    Batch execution on Windows is trickier due to WinRM session limits.
    This function re-establishes session for each rule but skips repeated VCIDEBUGCLI upload.
    """

    remote_vci_dir = f"C:\\Users\\{user}\\vcidebug_testing"
    remote_vci_path = f"{remote_vci_dir}\\VCIDEBUGCLI.exe"

    # Check if VCIDEBUGCLI already exists
    session = winrm.Session(target=ip,
                            auth=(user, password),
                            transport='ntlm')

    ps_create = f"""
    New-Item -Path "{remote_vci_dir}" -ItemType Directory -Force
    """
    session.run_ps(ps_create)

    ps_test_vci = f"""
    Test-Path "{remote_vci_path}"
    """
    result_test = session.run_ps(ps_test_vci)

    needs_upload = True
    if result_test.status_code == 0 and result_test.std_out.decode().strip() == "True":
        needs_upload = False

    if needs_upload:
        with open("VCIDEBUGCLI.exe", "rb") as f:
            vci_data = f.read()
        vci_b64 = base64.b64encode(vci_data).decode()

        ps_vci = f"""
        $b64 = "{vci_b64}"
        $bytes = [System.Convert]::FromBase64String($b64)
        [System.IO.File]::WriteAllBytes("{remote_vci_path}", $bytes)
        """
        session.run_ps(ps_vci)
        print(f"✅ Uploaded VCIDEBUGCLI.exe to remote host.")
    else:
        print(f"ℹ️ VCIDEBUGCLI.exe already exists on remote host. Skipping upload.")

    session.close()

    vci_output_dir = os.path.join(benchmark_dir, "vci_output")
    os.makedirs(vci_output_dir, exist_ok=True)

    result_paths = {}

    for rule_id, sensorbin_path in rule_sensor_map.items():
        session = winrm.Session(target=ip,
                                auth=(user, password),
                                transport='ntlm')

        remote_sensor_path = f"{remote_vci_dir}\\sensor.bin"
        remote_output_path = f"{remote_vci_dir}\\output.json"

        # Upload sensor.bin
        with open(sensorbin_path, "rb") as f:
            sensor_data = f.read()
        sensor_b64 = base64.b64encode(sensor_data).decode()

        ps_sensor = f"""
        $b64 = "{sensor_b64}"
        $bytes = [System.Convert]::FromBase64String($b64)
        [System.IO.File]::WriteAllBytes("{remote_sensor_path}", $bytes)
        """
        session.run_ps(ps_sensor)

        print(f"✅ Sensorbin written for rule {rule_id} to Windows: {remote_sensor_path}")

        cmd = f'"{remote_vci_path}" --hoststate --src "{remote_sensor_path}" --dest "{remote_output_path}"'
        result = session.run_cmd(cmd)

        if result.status_code != 0:
            print(f"❌ VCIDEBUGCLI failed for rule {rule_id}:\n{result.std_err.decode()}")
            session.close()
            continue

        ps_read_json = f"""
        Get-Content "{remote_output_path}" | Out-String
        """
        result_json = session.run_ps(ps_read_json)

        if result_json.status_code != 0:
            print(f"❌ Failed reading JSON for rule {rule_id}:\n{result_json.std_err.decode()}")
            session.close()
            continue

        json_text = result_json.std_out.decode()

        local_output_path = os.path.join(vci_output_dir, f"{rule_id}.json")
        with open(local_output_path, "w", encoding="utf-8") as f:
            f.write(json_text)

        print(f"✅ Downloaded Windows JSON output for rule {rule_id} to {local_output_path}")

        result_paths[rule_id] = local_output_path

        session.close()

    return result_paths


def save_batch_results_to_db(benchmark_name, result_paths):
    """
    After running a batch VCI job, call this to save results to the DB.
    """

    session = SessionLocal()

    benchmark_obj = session.query(Rule.benchmark).filter_by(name=benchmark_name).first()
    if not benchmark_obj:
        session.close()
        raise Exception(f"Benchmark {benchmark_name} not found.")

    for rule_id, json_path in result_paths.items():
        rule_obj = session.query(Rule).filter_by(
            benchmark_id=benchmark_obj.id,
            rule_id=rule_id
        ).first()

        if not rule_obj:
            print(f"⚠️ Rule {rule_id} not found in DB. Skipping.")
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            json_text = f.read()

        vci_result = VCIResult(
            rule_id=rule_obj.id,
            json_output=json_text
        )
        session.add(vci_result)
        session.commit()
        print(f"✅ Saved VCI result to DB for rule {rule_id}")

    session.close()

# backend/main.py

from fastapi import (
    FastAPI,
    UploadFile,
    BackgroundTasks,
    Form,
    HTTPException,
    Request,
    Depends,
    Query,
)
from fastapi.responses import (
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
    FileResponse,
)
from backend.utils import *
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from collections import defaultdict
from lxml import etree as ET
from cryptography.fernet import Fernet
import os
import re
import shutil
import json
import io
from backend.oval_parser import OvalDSA
from backend.xccdf_parser import XccdfDSA
from backend.oval_analyzer import OvalAnalyzer
from backend.disa_stig import parse_stig, generate_sensor_for_rule, parse_cis_stig
from backend.database import init_db, SessionLocal
from backend.models import Benchmark, Rule, UnsupportedRegex, RemoteHost, VCIResult
from backend.vci_executor import *
from backend.genai_regex_replacer import call_genai_api

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

master_key = os.getenv("MASTER_KEY").encode()
fernet = Fernet(master_key)

init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/benchmarks/{benchmark}/generate-full-oval")
async def generate_full_benchmark_oval(benchmark: str):
    benchmark_dir = f"data/{benchmark}"

    oval_path = os.path.join(benchmark_dir, "oval.xml")
    with open(oval_path, "rb") as f:
        oval_bytes = f.read()

    with open(os.path.join(benchmark_dir, "xccdf_to_oval_definition_map.json"), "r") as f:
        xccdf_to_oval_def = json.load(f)

    dsa = OvalDSA(oval_bytes)

    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()

    if not benchmark_obj:
        raise HTTPException(status_code=404, detail=f"Benchmark {benchmark} not found")

    rules = session.query(Rule).filter(
        Rule.benchmark_id == benchmark_obj.id,
        Rule.excluded == 0
    ).all()

    keep_definitions = []
    for rule in rules:
        def_id = xccdf_to_oval_def.get(rule.rule_id)
        if def_id:
            keep_definitions.append(def_id)

    dsa.keep_only_definitions(keep_definitions)
    output_bytes = dsa.to_xml_bytes()

    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={benchmark}_full_oval.xml"}
    )

@app.get("/api/benchmarks/{benchmark}/rules/{rule_id}/oval")
async def serve_existing_rule_oval(benchmark: str, rule_id: str):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()

    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    rule = session.query(Rule).filter_by(
        benchmark_id=benchmark_obj.id,
        rule_id=rule_id,
        excluded=0
    ).first()

    if not rule or not rule.oval_path:
        raise HTTPException(status_code=404, detail="Oval file not found in DB")

    oval_path = rule.oval_path
    if not os.path.exists(oval_path):
        raise HTTPException(status_code=404, detail="Oval file not found on disk")

    return FileResponse(oval_path, media_type="application/xml", filename=os.path.basename(oval_path))

class DeleteRulesRequest(BaseModel):
    rule_ids: list[str]

@app.delete("/api/benchmarks/{benchmark}/rules")
async def delete_rules(benchmark: str, request: DeleteRulesRequest):
    rule_ids = request.rule_ids
    if not rule_ids:
        raise HTTPException(status_code=400, detail="No rule IDs provided")

    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    rules = session.query(Rule).filter(
        Rule.benchmark_id == benchmark_obj.id,
        Rule.rule_id.in_(rule_ids)
    ).all()

    for rule in rules:
        rule.excluded = 1

    session.commit()

    return {"message": f"Excluded {len(rules)} rules"}

def process_stig_file(file_path: str, benchmark_dir: str, benchmark_name: str, benchmark_type: str = "DISA", background_tasks: BackgroundTasks = None):
    rules = parse_stig(file_path, benchmark_dir, benchmark_name, benchmark_type)
    if background_tasks:
        for rule in rules:
            background_tasks.add_task(
                generate_sensor_for_rule,
                benchmark_name,
                benchmark_dir,
                rule["rule_id"],
                rule["definition_id"],
                rule["oval_path"]
            )

def process_cis_file(xccdf_path: str, oval_path: str, benchmark_dir: str, benchmark_name: str, benchmark_type: str = "CIS",background_tasks: BackgroundTasks = None):
    rules = parse_cis_stig(xccdf_path, oval_path, benchmark_dir, benchmark_name, benchmark_type)
    if background_tasks:
        for rule in rules:
            background_tasks.add_task(
                generate_sensor_for_rule,
                benchmark_name,
                benchmark_dir,
                rule["rule_id"],
                rule["definition_id"],
                rule["oval_path"]
            )

@app.post("/api/stig/upload")
async def upload_stig_file(
    benchmark_name: str = Form(...),
    benchmark_type: str = Form(...),
    stig_file: UploadFile = None,
    xccdf_file: UploadFile = None,
    oval_file: UploadFile = None,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    try:
        benchmark_dir = os.path.join(DATA_DIR, benchmark_name)
        os.makedirs(benchmark_dir, exist_ok=True)

        session = SessionLocal()
        benchmark = Benchmark(name=benchmark_name, benchmark_type=benchmark_type)
        session.add(benchmark)
        session.commit()

        if benchmark_type == "DISA":
            file_path = os.path.join(benchmark_dir, stig_file.filename)
            with open(file_path, "wb") as f:
                f.write(await stig_file.read())

            background_tasks.add_task(process_stig_file, file_path, benchmark_dir, benchmark_name, "DISA", background_tasks)

        elif benchmark_type == "CIS":
            xccdf_path = os.path.join(benchmark_dir, "xccdf.xml")
            with open(xccdf_path, "wb") as f:
                f.write(await xccdf_file.read())

            oval_path = os.path.join(benchmark_dir, "oval.xml")
            with open(oval_path, "wb") as f:
                f.write(await oval_file.read())

            background_tasks.add_task(process_cis_file, xccdf_path, oval_path, benchmark_dir, benchmark_name, "CIS",background_tasks)

        else:
            raise HTTPException(status_code=400, detail="Unsupported benchmark type")

        return JSONResponse({"message": f"Benchmark '{benchmark_name}' uploaded successfully."})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/benchmarks")
async def list_benchmarks():
    session = SessionLocal()
    benchmarks = session.query(Benchmark).all()

    result = []
    for b in benchmarks:
        total = len(b.rules)
        automated = sum(1 for r in b.rules if not r.manual)
        unsupported = sum(1 for r in b.rules if not r.manual and not r.supported)
        coverage = ((automated - unsupported) / total * 100) if total else 0

        result.append({
            "benchmark": b.name,
            "type": b.benchmark_type,
            "total_rules": total,
            "automated_rules": automated,
            "unsupported_rules": unsupported,
            "coverage": round(coverage, 2)
        })

    return result

class GenerateOvalsRequest(BaseModel):
    rule_ids: list[str]

def build_merged_oval_from_files(oval_paths):
    NS_OVAL = "http://oval.mitre.org/XMLSchema/oval-definitions-5"
    nsmap = {None: NS_OVAL}

    root = ET.Element("{%s}oval_definitions" % NS_OVAL, nsmap=nsmap)

    generator_added = False
    id_map = defaultdict(dict)

    for path in oval_paths:
        tree = ET.parse(path)
        oval_root = tree.getroot()

        if not generator_added:
            generator_elem = oval_root.find(".//{*}generator")
            if generator_elem is not None:
                root.append(generator_elem)
                generator_added = True

        for section_name in ["definitions", "tests", "objects", "states", "variables"]:
            section = oval_root.find(f".//{{*}}{section_name}")
            if section is None:
                continue

            for el in section:
                el_id = el.attrib.get("id")
                if el_id:
                    if el_id not in id_map[section_name]:
                        id_map[section_name][el_id] = el

    for section_name in ["definitions", "tests", "objects", "states", "variables"]:
        if id_map[section_name]:
            sec_elem = ET.SubElement(root, f"{{{NS_OVAL}}}{section_name}")
            for el in id_map[section_name].values():
                sec_elem.append(el)

    return root

@app.post("/api/benchmarks/{benchmark}/generate-ovals")
async def generate_and_download_oval(benchmark: str, request: GenerateOvalsRequest):
    rule_ids = request.rule_ids
    if not rule_ids:
        raise HTTPException(status_code=400, detail="No rule IDs provided")

    benchmark_dir = f"data/{benchmark}"
    ovals_dir = os.path.join(benchmark_dir, "ovals")

    oval_files = []
    for rule_id in rule_ids:
        oval_path = get_hashed_path(rule_id, ovals_dir, "oval_rule_filename_map.json")
        if os.path.exists(oval_path):
            oval_files.append(oval_path)

    if not oval_files:
        raise HTTPException(status_code=404, detail="No edited OVAL files found for the requested rules.")

    merged_root = build_merged_oval_from_files(oval_files)
    output_bytes = ET.tostring(merged_root, pretty_print=True, encoding="UTF-8", xml_declaration=True)

    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={benchmark}_merged_oval.xml"
        }
    )

@app.get("/api/benchmarks/{benchmark}/rules")
async def list_rules(benchmark: str):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    rules = session.query(Rule).filter(
        Rule.benchmark_id == benchmark_obj.id,
        Rule.excluded == 0
    ).all()

    return [
        {
            "rule_id": r.rule_id,
            "supported": bool(r.supported) if r.supported is not None else False,
            "sensor_file_generated": bool(r.sensor_file_generated) if r.sensor_file_generated is not None else False
        }
        for r in rules
    ]

@app.delete("/api/benchmarks/{benchmark}")
async def delete_benchmark(benchmark: str):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()

    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    session.delete(benchmark_obj)
    session.commit()

    folder_path = os.path.join("data", benchmark)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

    return {"message": f"Benchmark '{benchmark}' deleted successfully"}

@app.get("/api/benchmarks/{benchmark}/rules/{rule_id}")
async def get_rule_oval(benchmark: str, rule_id: str):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
    if not benchmark_obj:
        return PlainTextResponse("Benchmark not found", status_code=404)

    rule = session.query(Rule).filter_by(
        benchmark_id=benchmark_obj.id,
        rule_id=rule_id
    ).first()

    if not rule:
        return PlainTextResponse("Rule not found", status_code=404)

    oval_path = rule.oval_path
    with open(oval_path, "r", encoding="utf-8") as f:
        content = f.read()
    return JSONResponse({"rule_id": rule_id, "oval": content})

@app.get("/api/benchmarks/{benchmark}/regex-issues")
async def get_regex_issues(benchmark: str):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
    if not benchmark_obj:
        return PlainTextResponse("Benchmark not found", status_code=404)

    patterns = []
    for rule in benchmark_obj.rules:
        for issue in rule.unsupported_regex:
            patterns.append(issue.pattern)

    patterns = list(set(patterns))
    response_text = "\n".join(patterns)

    return PlainTextResponse(response_text, media_type="text/plain")

@app.post("/api/benchmarks/{benchmark}/rules/{rule_id}")
async def save_rule_oval(benchmark: str, rule_id: str, request: Request):
    data = await request.json()
    oval_content = data.get("oval")

    if oval_content is None:
        raise HTTPException(status_code=400, detail="Missing oval content")

    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    rule = session.query(Rule).filter_by(
        benchmark_id=benchmark_obj.id,
        rule_id=rule_id
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    oval_path = rule.oval_path
    if not oval_path:
        raise HTTPException(status_code=404, detail="No oval path found for rule")

    with open(oval_path, "w", encoding="utf-8") as f:
        f.write(oval_content)

    return JSONResponse({"message": "Oval saved successfully"})



@app.post("/api/benchmarks/{benchmark}/rules/{rule_id}/xccdf")
async def save_rule_xccdf(benchmark: str, rule_id: str, request: Request):
    data = await request.json()
    xccdf_content = data.get("xccdf")

    if xccdf_content is None:
        raise HTTPException(status_code=400, detail="Missing xccdf content")

    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    rule = session.query(Rule).filter_by(
        benchmark_id=benchmark_obj.id,
        rule_id=rule_id
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Path for saving XCCDF
    rule_id = re.sub(r'_\d+$', '', rule_id)  # remove any suffix like _1, _2, etc.
    benchmark_dir = f"data/{benchmark}"
    xccdf_dir = os.path.join(benchmark_dir, "xccdf")
    os.makedirs(xccdf_dir, exist_ok=True)

    xccdf_path = get_hashed_path(rule_id, os.path.join(benchmark_dir, "xccdf"), "xccdf_rule_filename_map.json")

    with open(xccdf_path, "w", encoding="utf-8") as f:
        f.write(xccdf_content)

    return JSONResponse({"message": "XCCDF saved successfully"})





class RemoteHostRequest(BaseModel):
    benchmark_name: str
    ip_address: str
    username: str
    password: str
    os_type: str

@app.post("/api/remote-hosts")
async def add_remote_host(remote_host: RemoteHostRequest, db: Session = Depends(get_db)):
    # Check if benchmark exists
    benchmark = db.query(Benchmark).filter(Benchmark.name == remote_host.benchmark_name).first()
    if not benchmark:
        raise HTTPException(status_code=404, detail=f"Benchmark '{remote_host.benchmark_name}' not found")

    # Encrypt password
    encrypted_pw = fernet.encrypt(remote_host.password.encode()).decode()

    new_host = RemoteHost(
        benchmark_id=benchmark.id,
        ip_address=remote_host.ip_address,
        username=remote_host.username,
        password_encrypted=encrypted_pw,
        os_type=remote_host.os_type
    )

    db.add(new_host)
    db.commit()

    return {"message": "Remote host saved successfully."}


@app.get("/api/benchmarks/{benchmark_name}/remote-hosts")
async def list_remote_hosts(benchmark_name: str, db: Session = Depends(get_db)):
    benchmark = db.query(Benchmark).filter(Benchmark.name == benchmark_name).first()
    if not benchmark:
        raise HTTPException(status_code=404, detail=f"Benchmark '{benchmark_name}' not found")

    hosts = benchmark.remote_hosts

    result = []
    for host in hosts:
        result.append({
            "id": host.id,
            "ip_address": host.ip_address,
            "username": host.username,
            "os_type": host.os_type
            # we deliberately do NOT return password_encrypted
        })

    return result


@app.get("/api/rules/{rule_id}/hoststate")
async def get_hoststate(rule_id: str):
    session = SessionLocal()

    rule = session.query(Rule).filter_by(rule_id=rule_id).first()
    if not rule:
        session.close()
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    vci_result = session.query(VCIResult).filter_by(rule_id=rule.id).order_by(VCIResult.id.desc()).first()
    session.close()

    if not vci_result:
        raise HTTPException(status_code=404, detail=f"No hoststate JSON found for rule {rule_id}")

    return {"rule_id": rule_id, "hoststate_json": vci_result.json_output}





@app.post("/api/benchmarks/{benchmark}/run-vci-debug")
async def run_vci_debug_for_benchmark(benchmark: str):
    session = SessionLocal()
    benchmark_obj = session.query(Rule.benchmark).filter_by(name=benchmark).first()
    if not benchmark_obj:
        session.close()
        raise HTTPException(status_code=404, detail=f"Benchmark {benchmark} not found.")

    remote_host = benchmark_obj.remote_hosts[0]
    ip = remote_host.ip_address
    username = remote_host.username
    password = decrypt_password(remote_host.password_encrypted)
    os_type = remote_host.os_type.lower()

    rules = session.query(Rule).filter_by(
        benchmark_id=benchmark_obj.id,
        excluded=0,
        sensor_file_generated=1
    ).all()

    benchmark_dir = os.path.join("data", benchmark)

    rule_sensor_map = {}
    for rule in rules:
        sensorbin_path = os.path.join(benchmark_dir, "sensorbin", f"{rule.rule_id}.bin")
        if os.path.exists(sensorbin_path):
            rule_sensor_map[rule.rule_id] = sensorbin_path

    session.close()

    if os_type == "linux":
        result_paths = run_vci_batch_on_linux(ip, username, password, rule_sensor_map, benchmark_dir)
    elif os_type == "windows":
        result_paths = run_vci_batch_on_windows(ip, username, password, rule_sensor_map, benchmark_dir)
    else:
        raise HTTPException(status_code=400, detail="Batch VCI not implemented for this OS.")

    save_batch_results_to_db(benchmark, result_paths)

    return {"message": f"VCI executed for {len(result_paths)} rules for benchmark {benchmark}."}




def run_genai_conversion_for_benchmark(benchmark_name: str, model_name: str):
    session = SessionLocal()

    benchmark = session.query(Benchmark).filter_by(name=benchmark_name).first()
    if not benchmark:
        print(f"❌ Benchmark not found: {benchmark_name}")
        session.close()
        return

    total_converted = 0

    for rule in benchmark.rules:
        for regex_obj in rule.unsupported_regex:
            if regex_obj.processed_pattern:
                continue

            print(f"🔍 Processing regex: {regex_obj.pattern}")

            try:
                result = call_genai_api(model_name, regex_obj.pattern)

                regex_obj.processed_pattern = result["converted_regex"]
                regex_obj.tests_json = json.dumps(result.get("tests", []))

                total_converted += 1

            except Exception as e:
                print(f"❌ Error processing regex {regex_obj.pattern}: {e}")

    session.commit()
    session.close()

    print(f"✅ Converted {total_converted} regexes for benchmark {benchmark_name}")

@app.post("/api/benchmarks/{benchmark}/process-unsupported-regex-ai")
async def process_regexes_ai(benchmark: str, background_tasks: BackgroundTasks):
    model_name = "cloud35-sonnet-v2"    # or whichever you want as default
    background_tasks.add_task(run_genai_conversion_for_benchmark, benchmark, model_name)
    return {
        "message": f"Started GenAI regex conversion task for benchmark {benchmark}"
    }

@app.get("/api/benchmarks/{benchmark}/rules/test/{object_type}")
async def get_rules_by_object(benchmark: str,object_type: str):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
    print(benchmark_obj.name)

    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    # Filter rules where object_type contains the search string
    rules = session.query(Rule).filter(
        Rule.benchmark_id == benchmark_obj.id,
        Rule.excluded == 0,
        Rule.object_type.isnot(None),
        Rule.object_type.ilike(f"%{object_type}%")
    ).all()

    session.close()

    return [
        {
            "rule_id": r.rule_id,
            "definition_id": r.definition_id,
            "object_type": r.object_type,
            "supported": bool(r.supported) if r.supported is not None else False,
            "sensor_file_generated": bool(r.sensor_file_generated) if r.sensor_file_generated is not None else False,
        }
        for r in rules
    ]

@app.get("/api/benchmarks/{benchmark}/rules/{rule_id}/xccdf")
async def serve_existing_rule_xccdf(benchmark: str, rule_id: str):
    session = SessionLocal()
    # rule_id = re.sub(r'_\d+$', '', rule_id)  # remove any suffix like _1, _2, etc.
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()

    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    rule = session.query(Rule).filter_by(
        benchmark_id=benchmark_obj.id,
        rule_id=rule_id,
        excluded=0
    ).first()
    rule_id = re.sub(r'_\d+$', '', rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found in DB")

    # Path to edited XCCDF file (rule-specific)
    benchmark_dir = f"data/{benchmark}"
    xccdf_path = get_hashed_path(rule_id, os.path.join(benchmark_dir, "xccdf"), "xccdf_rule_filename_map.json")
    # xccdf_path = os.path.join(benchmark_dir, "xccdf", f"{rule_id}.xml")

    if not os.path.exists(xccdf_path):
        # fallback: extract on-the-fly from master XCCDF
        master_xccdf_path = os.path.join(benchmark_dir, "xccdf.xml")
        if not os.path.exists(master_xccdf_path):
            raise HTTPException(status_code=404, detail="Master XCCDF file not found")

        from backend.xccdf_parser import XccdfDSA

        with open(master_xccdf_path, "rb") as f:
            xccdf_bytes = f.read()

        dsa = XccdfDSA(xccdf_bytes)
        try:
            rule_xml_bytes = dsa.extract_rule(rule_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found in master XCCDF: {str(e)}")

        # save extracted rule for future access
        # os.makedirs(os.path.dirname(xccdf_path), exist_ok=True)
        # with open(xccdf_path, "wb") as f:
        #     f.write(rule_xml_bytes)

    return FileResponse(
        xccdf_path,
        media_type="application/xml",
        filename=os.path.basename(xccdf_path)
    )


from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import io
import os
from lxml import etree as ET
from backend.models import Benchmark, Rule
from backend.database import SessionLocal
from fastapi import Body

class GenerateXccdfRequest(BaseModel):
    rule_ids: list[str]

def merge_edited_xccdfs(master_path, edited_paths):
    parser = ET.XMLParser(remove_blank_text=True)
    master_tree = ET.parse(master_path, parser)
    master_root = master_tree.getroot()

    NAMESPACE_XCCDF = "http://checklists.nist.gov/xccdf/1.2"
    NAMESPACES = {"xccdf": NAMESPACE_XCCDF}

    master_rules = {
        el.attrib["id"]: el
        for el in master_root.xpath(".//xccdf:Rule", namespaces=NAMESPACES)
    }
    master_vars = {
        el.attrib["id"]: el
        for el in master_root.xpath(".//xccdf:Value", namespaces=NAMESPACES)
    }

    for path in edited_paths:
        edited_tree = ET.parse(path, parser)
        edited_root = edited_tree.getroot()

        # Merge variables
        for var_elem in edited_root.xpath(".//xccdf:Value", namespaces=NAMESPACES):
            var_id = var_elem.attrib.get("id")
            if not var_id:
                continue
            if var_id in master_vars:
                old_var = master_vars[var_id]
                parent = old_var.getparent()
                parent.replace(old_var, var_elem)
            else:
                master_root.append(var_elem)

        # Merge rules
        for rule_elem in edited_root.xpath(".//xccdf:Rule", namespaces=NAMESPACES):
            rule_id = rule_elem.attrib.get("id")
            if not rule_id:
                continue
            if rule_id in master_rules:
                old_rule = master_rules[rule_id]
                parent = old_rule.getparent()
                parent.replace(old_rule, rule_elem)
            else:
                master_root.append(rule_elem)

    return master_tree

@app.post("/api/benchmarks/{benchmark}/generate-xccdf")
async def generate_and_download_xccdf(benchmark: str, request: GenerateXccdfRequest):
    rule_ids = request.rule_ids
    if not rule_ids:
        raise HTTPException(status_code=400, detail="No rule IDs provided")

    benchmark_dir = f"data/{benchmark}"
    xccdf_dir = os.path.join(benchmark_dir, "xccdf")

    edited_files = []
    for rule_id in rule_ids:
        xccdf_path = os.path.join(xccdf_dir, f"{rule_id}.xml")
        if os.path.exists(xccdf_path):
            edited_files.append(xccdf_path)

    if not edited_files:
        raise HTTPException(status_code=404, detail="No edited XCCDF files found for the requested rules.")

    master_xccdf_path = os.path.join(benchmark_dir, "xccdf.xml")
    if not os.path.exists(master_xccdf_path):
        raise HTTPException(status_code=404, detail="Master XCCDF file not found.")

    merged_tree = merge_edited_xccdfs(master_xccdf_path, edited_files)

    output_bytes = ET.tostring(
        merged_tree.getroot(),
        pretty_print=True,
        encoding="UTF-8",
        xml_declaration=True
    )

    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={benchmark}_merged_xccdf.xml"
        }
    )


from backend.oval_transformer import transform_userright_oval

@app.get("/api/benchmarks/{benchmark}/rules/{rule_id}/transform-userright")
async def transform_userright(benchmark: str, rule_id: str):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()

    if not benchmark_obj:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    rule = session.query(Rule).filter_by(
        benchmark_id=benchmark_obj.id,
        rule_id=rule_id,
        excluded=0
    ).first()

    if not rule or not rule.oval_path:
        raise HTTPException(status_code=404, detail="Oval file not found in DB")

    oval_path = rule.oval_path
    if not os.path.exists(oval_path):
        raise HTTPException(status_code=404, detail="Oval file not found on disk")

    with open(oval_path, "rb") as f:
        oval_bytes = f.read()

    # Only transform if object_type includes userright_object
    if rule.object_type and "userright_object" not in rule.object_type:
        return JSONResponse({"message": "Rule does not use userright_object. No transformation needed."})

    transformed_bytes = transform_userright_oval(oval_bytes)
    if transformed_bytes is None:
        return JSONResponse({"message": "Rule does not use userright_states. No transformation needed."})

    return StreamingResponse(
        io.BytesIO(transformed_bytes),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={rule_id}_transformed.xml"}
    )

from fastapi import BackgroundTasks
from backend.userright_transformer import run_userright_transformation

@app.post("/api/benchmarks/{benchmark}/transform-userright")
async def transform_userright_all(benchmark: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_userright_transformation, benchmark)
    return {
        "message": f"Started userright transformation task for benchmark {benchmark}."
    }
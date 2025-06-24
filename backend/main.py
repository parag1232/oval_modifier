# backend/main.py

from fastapi import FastAPI, UploadFile, BackgroundTasks, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException
from pydantic import BaseModel
from fastapi import Body
import shutil
import os, json, sqlite3
from backend.oval_parser import OvalDSA
from backend.oval_analyzer import OvalAnalyzer
from backend.disa_stig import parse_stig, generate_sensor_for_rule
from backend.database import initialize_db
import json
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

initialize_db()
from fastapi.responses import FileResponse

@app.get("/api/benchmarks/{benchmark}/generate-full-oval")
async def generate_full_benchmark_oval(benchmark: str):
    benchmark_dir = f"data/{benchmark}"

    # Load oval.xml
    oval_path = os.path.join(benchmark_dir, "oval.xml")
    with open(oval_path, "rb") as f:
        oval_bytes = f.read()

    # Load mapping
    import json
    with open(os.path.join(benchmark_dir, "xccdf_to_oval_definition_map.json"), "r") as f:
        xccdf_to_oval_def = json.load(f)

    from backend.oval_parser import OvalDSA
    dsa = OvalDSA(oval_bytes)

    # Query all non-excluded rules from DB
    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()
    cursor.execute("SELECT rule_id FROM rules WHERE benchmark=? AND excluded=0", (benchmark,))
    rows = cursor.fetchall()
    conn.close()

    # Build list of valid definition_ids
    keep_definitions = []
    for row in rows:
        rule_id = row[0]
        def_id = xccdf_to_oval_def.get(rule_id)
        if def_id:
            keep_definitions.append(def_id)

    dsa.keep_only_definitions(keep_definitions)
    output_bytes = dsa.to_xml_bytes()

    return StreamingResponse(
        output_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={benchmark}_full_oval.xml"}
    )

@app.get("/api/benchmarks/{benchmark}/rules/{rule_id}/oval")
async def serve_existing_rule_oval(benchmark: str, rule_id: str):
    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()
    cursor.execute("SELECT oval_path FROM rules WHERE benchmark=? AND rule_id=? AND excluded=0", (benchmark, rule_id))
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Oval file not found in DB")

    oval_path = row[0]
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

    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()
    query = f"UPDATE rules SET excluded=1 WHERE benchmark=? AND rule_id IN ({','.join(['?'] * len(rule_ids))})"
    params = [benchmark] + rule_ids
    cursor.execute(query, params)
    conn.commit()
    conn.close()
    return {"message": f"Excluded {cursor.rowcount} rules"}
# Background ingestion
def process_stig_file(file_path: str, benchmark_dir: str, benchmark_name: str,benchmark_type: str = "DISA",background_tasks: BackgroundTasks = None):
    rules = parse_stig(file_path, benchmark_dir, benchmark_name,benchmark_type)
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

def process_cis_file(file_path: str, benchmark_dir: str, benchmark_name: str,benchmark_type: str = "CIS"):
    parse_stig(file_path, benchmark_dir, benchmark_name,benchmark_type)    

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

        if benchmark_type == "DISA":
            file_path = os.path.join(benchmark_dir, stig_file.filename)
            with open(file_path, "wb") as f:
                f.write(await stig_file.read())

            background_tasks.add_task(process_stig_file, file_path, benchmark_dir, benchmark_name,"DISA",background_tasks)

        elif benchmark_type == "CIS":
            xccdf_path = os.path.join(benchmark_dir, xccdf_file.filename)
            with open(xccdf_path, "wb") as f:
                f.write(await xccdf_file.read())

            oval_path = os.path.join(benchmark_dir, oval_file.filename)
            with open(oval_path, "wb") as f:
                f.write(await oval_file.read())

            background_tasks.add_task(process_cis_file, xccdf_path, oval_path, benchmark_dir, benchmark_name)

        else:
            raise HTTPException(status_code=400, detail="Unsupported benchmark type")

        return JSONResponse({"message": f"Benchmark '{benchmark_name}' uploaded successfully."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

# New API endpoints for frontend

@app.get("/api/benchmarks")
async def list_benchmarks():
    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            benchmark,
            benchmark_type, 
            COUNT(*) AS total_rules,
            SUM(CASE WHEN manual = 0 THEN 1 ELSE 0 END) AS automated_rules,
            SUM(CASE WHEN manual = 0 AND supported = 0 THEN 1 ELSE 0 END) AS unsupported_rules
        FROM rules
        WHERE excluded = 0
        GROUP BY benchmark
    """)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        benchmark, btype,total, automated, unsupported = row
        total = total or 0
        automated = automated or 0
        unsupported = unsupported or 0
        coverage = ((automated - unsupported) / total * 100) if total else 0

        result.append({
            "benchmark": benchmark,
            "type": btype,
            "total_rules": total,
            "automated_rules": automated,
            "unsupported_rules": unsupported,
            "coverage": round(coverage, 2)
        })
    return result

class GenerateOvalsRequest(BaseModel):
    rule_ids: list[str]

from fastapi.responses import StreamingResponse

@app.post("/api/benchmarks/{benchmark}/generate-ovals")
async def generate_and_download_oval(benchmark: str, request: GenerateOvalsRequest):
    rule_ids = request.rule_ids
    if not rule_ids:
        raise HTTPException(status_code=400, detail="No rule IDs provided")

    benchmark_dir = f"data/{benchmark}"
    oval_path = os.path.join(benchmark_dir, "oval.xml")
    with open(oval_path, "rb") as f:
        oval_bytes = f.read()

    
    with open(os.path.join(benchmark_dir, "xccdf_to_oval_definition_map.json"), "r") as f:
        xccdf_to_oval_def = json.load(f)

    dsa = OvalDSA(oval_bytes)

    keep_definitions = []
    for rule_id in rule_ids:
        def_id = xccdf_to_oval_def.get(rule_id)
        if def_id:
            keep_definitions.append(def_id)

    dsa.keep_only_definitions(keep_definitions)
    output_bytes = dsa.to_xml_bytes()

    return StreamingResponse(
        output_bytes,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={benchmark}_merged_oval.xml"
        }
    )




@app.get("/api/benchmarks/{benchmark}/rules")
async def list_rules(benchmark: str):
    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()
    cursor.execute("SELECT rule_id, supported, sensor_file_generated FROM rules WHERE benchmark=? AND excluded=0", (benchmark,))
    rows = cursor.fetchall()
    conn.close()
    return [{"rule_id": row[0], "supported": bool(row[1]) if row[1] is not None else False,"sensor_file_generated":bool(row[2]) if row[2] is not None else False} for row in rows]


@app.delete("/api/benchmarks/{benchmark}")
async def delete_benchmark(benchmark: str):
    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()

    # Check if benchmark exists
    cursor.execute("SELECT COUNT(*) FROM rules WHERE benchmark=?", (benchmark,))
    count = cursor.fetchone()[0]

    if count == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Benchmark not found")

    # Delete from DB
    cursor.execute("DELETE FROM rules WHERE benchmark=?", (benchmark,))
    conn.commit()
    conn.close()

    # Optional: delete benchmark folder from filesystem
    folder_path = os.path.join("data", benchmark)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

    return {"message": f"Benchmark '{benchmark}' deleted successfully"}

@app.get("/api/benchmarks/{benchmark}/rules/{rule_id}")
async def get_rule_oval(benchmark: str, rule_id: str):
    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()
    cursor.execute("SELECT oval_path FROM rules WHERE benchmark=? AND rule_id=?", (benchmark, rule_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return PlainTextResponse("Rule not found", status_code=404)
    oval_path = row[0]
    with open(oval_path, "r", encoding="utf-8") as f:
        content = f.read()
    return JSONResponse({"rule_id": rule_id, "oval": content})




@app.get("/api/benchmarks/{benchmark}/regex-issues")
async def get_regex_issues(benchmark: str):
    conn = sqlite3.connect("data/stig.db")
    cursor = conn.cursor()

    query = """
    SELECT ri.pattern
    FROM regex_issues ri
    JOIN rules r ON ri.rule_id = r.rule_id
    WHERE r.benchmark = ?
    ORDER BY r.rule_id, ri.id
    """
    cursor.execute(query, (benchmark,))
    rows = cursor.fetchall()
    conn.close()

    # Generate simple tab-separated output
    output_lines = []
    for pattern in rows:
        output_lines.append(f"{pattern[0]}")

    output_lines = (set(output_lines))    

    response_text = "\n".join(output_lines)

    return PlainTextResponse(response_text, media_type="text/plain")

# backend/userright_transformer.py

import requests
from lxml import etree as ET
import os
from backend.database import SessionLocal
from backend.models import *
import re
from backend.oval_transformer import transform_userright_oval

API_URL = "https://ccdodo.black.dodo.eyrie.cloud/apis/v1/crs/scacontentops/entities/script/oval/process_oval"
COOKIE = {"csrftoken": "asze0fJiOpyd8D6oXD620lsQhv28Ae8Q"}
HEADERS = {
    "accept": "*/*",
    "origin": "https://ccdodo.black.dodo.eyrie.cloud",
}

def process_oval_api(oval_path):
    with open(oval_path, "rb") as f:
        oval_xml = f.read()
    oval_xml = transform_userright_oval(oval_xml)
    if oval_xml is None:
        return    

    files = {
        "oval": ("blob", oval_xml.decode(), "text/xml"),
    }

    response = requests.post(API_URL, files=files, headers=HEADERS, cookies=COOKIE)
    response.raise_for_status()

    return response.content


def extract_ids_and_elements(oval_bytes):
    tree = ET.fromstring(oval_bytes)

    nsmap = tree.nsmap
    ns_oval = nsmap.get(None) or "http://oval.mitre.org/XMLSchema/oval-definitions-5"

    def_elem = tree.find(".//{%s}definition" % ns_oval)
    new_def_id = def_elem.attrib["id"] if def_elem is not None else None

    var_elems = tree.findall(".//{%s}external_variable" % ns_oval)
    var_ids = [v.attrib["id"] for v in var_elems]

    check_export_elem = tree.find(".//{%s}check-export" % ns_oval)
    value_elem = tree.find(".//Value")

    return new_def_id, var_ids, check_export_elem, value_elem


def update_xccdf(xccdf_path, old_def_id, new_def_id, check_export_elem, value_elem):
    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(xccdf_path, parser)
    root = tree.getroot()

    nsmap = {
        'xccdf': 'http://checklists.nist.gov/xccdf/1.2'
    }

    check_ref = root.find(".//xccdf:check/xccdf:check-content-ref", namespaces=nsmap)
    if check_ref is not None:
        if check_ref.attrib.get("name") == old_def_id:
            check_ref.attrib["name"] = new_def_id
            print(f"✅ Updated check-content-ref from {old_def_id} → {new_def_id}")
        else:
            print(f"⚠ check-content-ref name does not match {old_def_id}. Skipped replacement.")

    # Append check-export and Value at root
    if check_export_elem is not None:
        root.append(check_export_elem)
        print(f"✅ Added check-export element.")

    if value_elem is not None:
        root.append(value_elem)
        print(f"✅ Added Value element.")

    tree.write(xccdf_path, pretty_print=True, encoding="utf-8", xml_declaration=True)


def run_userright_transformation(benchmark_name: str):
    session = SessionLocal()
    benchmark = session.query(Benchmark).filter_by(name=benchmark_name).first()

    if not benchmark:
        print(f"❌ Benchmark {benchmark_name} not found.")
        session.close()
        return

    rules = session.query(Rule).filter(
        Rule.benchmark_id == benchmark.id,
        Rule.excluded == 0,
        Rule.object_type.isnot(None),
        Rule.object_type.ilike("%userright_object%")
    ).all()

    print(f"🔍 Found {len(rules)} userright_object rules to transform.")

    for rule in rules:
        try:
            oval_path = rule.oval_path
            xccdf_path = rule.xccdf_path

            if not oval_path or not os.path.exists(oval_path):
                print(f"⚠ OVAL file missing for rule {rule.rule_id}")
                continue
            if not xccdf_path or not os.path.exists(xccdf_path):
                print(f"⚠ XCCDF file missing for rule {rule.rule_id}")
                continue

            # Load old def id
            old_def_id = rule.definition_id
            old_def_id = re.sub(r'_\d+$', '', old_def_id)

            oval_bytes = process_oval_api(oval_path)
            if oval_bytes == None:
                continue

            new_def_id, var_ids, check_export_elem, value_elem = extract_ids_and_elements(oval_bytes)

            # Update XCCDF file
            update_xccdf(xccdf_path, old_def_id, new_def_id, check_export_elem, value_elem)

            # Optionally overwrite OVAL file with transformed XML
            with open(oval_path, "wb") as f:
                f.write(oval_bytes)

            print(f"✅ Finished transformation for rule {rule.rule_id}")

        except Exception as e:
            print(f"❌ Failed transforming rule {rule.rule_id}: {e}")

    session.close()
    print("✅ Userright transformation complete for benchmark.")

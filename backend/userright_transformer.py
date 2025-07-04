# backend/userright_transformer.py

import requests
from lxml import etree as ET
import os
from backend.database import SessionLocal
from backend.models import *
from backend.oval_transformer import transform_userright_oval
import re

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


def extract_ids_and_elements_and_clean(oval_bytes):
    """
    From transformed OVAL:
      - extract new definition id
      - extract variable ids
      - extract check-export and Value elements
      - REMOVE them from OVAL
      - return cleaned OVAL bytes
    """
    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.fromstring(oval_bytes, parser=parser)

    nsmap = tree.nsmap
    ns_oval = nsmap.get(None) or "http://oval.mitre.org/XMLSchema/oval-definitions-5"

    # new definition id
    def_elem = tree.find(".//{%s}definition" % ns_oval)
    new_def_id = def_elem.attrib["id"] if def_elem is not None else None

    # variable ids
    var_elems = tree.findall(".//{%s}external_variable" % ns_oval)
    var_ids = [v.attrib["id"] for v in var_elems]

    # extract and remove check-export
    check_export_elem = tree.find(".//{%s}check-export" % ns_oval)
    if check_export_elem is not None:
        parent = check_export_elem.getparent()
        parent.remove(check_export_elem)

    # extract and remove Value
    value_elem = tree.find(".//Value")
    if value_elem is not None:
        parent = value_elem.getparent()
        parent.remove(value_elem)

    cleaned_oval_bytes = ET.tostring(
        tree,
        pretty_print=True,
        encoding="utf-8",
        xml_declaration=True
    )

    return new_def_id, var_ids, check_export_elem, value_elem, cleaned_oval_bytes


def update_xccdf(xccdf_path, old_def_id, new_def_id, check_export_elem, value_elem):
    """
    Patches XCCDF:
      - replaces check-content-ref name with new def id
      - appends check-export and Value elements
    """
    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(xccdf_path, parser)
    root = tree.getroot()

    nsmap = {
        'xccdf': 'http://checklists.nist.gov/xccdf/1.2'
    }

    # Find check-content-ref
    check_ref = root.find(".//xccdf:check/xccdf:check-content-ref", namespaces=nsmap)
    if check_ref is not None:
        current_name = check_ref.attrib.get("name")
        if current_name == old_def_id:
            check_ref.attrib["name"] = new_def_id
            print(f"✅ Updated check-content-ref from {old_def_id} → {new_def_id}")
        else:
            print(f"⚠ check-content-ref name mismatch ({current_name} != {old_def_id}). Skipped replacement.")

    # Append check-export and Value if not already present
    existing_exports = root.findall(".//check-export")
    existing_values = root.findall(".//Value")

    if check_export_elem is not None:
        if not any(
            e.attrib.get("export-name") == check_export_elem.attrib.get("export-name")
            for e in existing_exports
        ):
            root.append(check_export_elem)
            print("✅ Added check-export to XCCDF.")

    if value_elem is not None:
        val_id = value_elem.attrib.get("id")
        if not any(
            e.attrib.get("id") == val_id
            for e in existing_values
        ):
            root.append(value_elem)
            print("✅ Added Value to XCCDF.")

    # Write back
    tree.write(xccdf_path, pretty_print=True, encoding="utf-8", xml_declaration=True)


def run_userright_transformation(benchmark_name: str):
    """
    Process all rules in a benchmark that use userright_object.
    - call remote oval transform api
    - extract new ids and elements
    - remove check-export and Value from oval
    - patch xccdf
    - overwrite oval with cleaned oval
    """
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

    print(f"🔍 Found {len(rules)} userright_object rules in benchmark {benchmark_name}.")

    for rule in rules:
        try:
            oval_path = rule.oval_path
            xccdf_path = rule.xccdf_path

            if not oval_path or not os.path.exists(oval_path):
                print(f"⚠ OVAL missing for rule {rule.rule_id}")
                continue
            if not xccdf_path or not os.path.exists(xccdf_path):
                print(f"⚠ XCCDF missing for rule {rule.rule_id}")
                continue

            old_def_id = rule.definition_id
            old_def_id = re.sub(r'_\d+$', '', old_def_id or "")

            # 1. Call remote API
            oval_bytes = process_oval_api(oval_path)
            if oval_bytes == None:
                continue

            # 2. Extract new ids and clean oval
            (
                new_def_id,
                var_ids,
                check_export_elem,
                value_elem,
                cleaned_oval_bytes
            ) = extract_ids_and_elements_and_clean(oval_bytes)

            # 3. Save cleaned oval
            with open(oval_path, "wb") as f:
                f.write(cleaned_oval_bytes)
            print(f"✅ Saved cleaned OVAL for rule {rule.rule_id}")

            # 4. Update XCCDF
            update_xccdf(
                xccdf_path,
                old_def_id,
                new_def_id,
                check_export_elem,
                value_elem
            )

            print(f"✅ Completed transformation for rule {rule.rule_id}")

        except Exception as e:
            print(f"❌ Error processing rule {rule.rule_id}: {e}")

    session.close()
    print("✅ Userright transformation finished.")

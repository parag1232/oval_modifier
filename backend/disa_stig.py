from lxml import etree
import json
import os
from backend.oval_analyzer import OvalAnalyzer
from backend.oval_parser import OvalDSA
from lxml import etree as lxml_etree
from backend.sensorbin_generator import *
from datetime import datetime
from backend.database import SessionLocal
from backend.models import Benchmark, Rule, UnsupportedRegex, RemoteHost, VCIResult
from backend.xccdf_parser import XccdfDSA
import re

PYTHON_PATH = os.getenv("PYTHON_PATH")
BUILD_CHANNEL_FILE = os.getenv("BUILD_CHANNEL_FILE")
GENERATE_INSTRUCTIONS = os.getenv("GENERATE_INSTRUCTIONS_LOCATION_PROJ")
REQUEST_PARAM = os.getenv("REQUEST_PARAM_FILE_LOCATION")

NAMESPACES = {
    'scap': 'http://scap.nist.gov/schema/scap/source/1.2',
    'xccdf': 'http://checklists.nist.gov/xccdf/1.2',
    'oval': 'http://oval.mitre.org/XMLSchema/oval-definitions-5',
    'cpe-dict': 'http://cpe.mitre.org/dictionary/2.0',
    'xlink': 'http://www.w3.org/1999/xlink'
}


def generate_sensor_for_rule(benchmark, benchmark_dir, rule_id, definition_id, oval_path):
    session = SessionLocal()
    try:
        cf_output = os.path.join(benchmark_dir, "cf_output")
        os.makedirs(cf_output, exist_ok=True)
        cf_output = os.path.abspath(cf_output)

        sensorbin_dir = os.path.join(benchmark_dir, "sensorbin")
        os.makedirs(sensorbin_dir, exist_ok=True)

        instructions_file = generate_instructions(
            GENERATE_INSTRUCTIONS,
            REQUEST_PARAM,
            oval_path,
            cf_output,
            rule_id
        )
        sensor_bin_path = generate_sensor_cf(
            PYTHON_PATH,
            BUILD_CHANNEL_FILE,
            instructions_file,
            rule_id,
            sensorbin_dir
        )
        benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
        if benchmark_obj:
            rule_obj = session.query(Rule).filter_by(
                benchmark_id=benchmark_obj.id,
                rule_id=rule_id
            ).first()
            if rule_obj:
                rule_obj.sensor_file_generated = 1
                session.commit()
        else:
            print(f"ℹ️ No remote host configured for benchmark {benchmark}. Skipping VCI debug.")        

        print(f"✅ Sensor generated for rule: {rule_id}")
    except Exception as e:
        benchmark_obj = session.query(Benchmark).filter_by(name=benchmark).first()
        if benchmark_obj:
            rule_obj = session.query(Rule).filter_by(
                benchmark_id=benchmark_obj.id,
                rule_id=rule_id
            ).first()
            if rule_obj:
                rule_obj.sensor_file_generated = 0
                session.commit()

        print(f"❌ Sensor generation failed for rule {rule_id}: {e}")
    finally:
        session.close()


def detect_benchmark_type_from_roots(xccdf_root, oval_root) -> str:
    platforms = []

    if xccdf_root is not None:
        for platform_elem in xccdf_root.findall(".//xccdf:platform", namespaces=NAMESPACES):
            platform_text = platform_elem.text
            if platform_text is not None:
                platforms.append(platform_text.lower())
            else:
                platform_text = platform_elem.attrib['idref']
                platforms.append(platform_text.lower())

    if oval_root is not None:
        for definition_elem in oval_root.findall(".//oval:definition", namespaces=NAMESPACES):
            affected_elem = definition_elem.find(".//oval:affected", namespaces=NAMESPACES)
            if affected_elem is not None:
                platform = affected_elem.find("oval:platform", namespaces=NAMESPACES)
                if platform is not None and platform.text:
                    platforms.append(platform.text.lower())

    full_platform_string = ' '.join(platforms)

    if 'windows' in full_platform_string:
        return 'Windows'
    elif 'linux' in full_platform_string or 'red hat' in full_platform_string or 'ubuntu' in full_platform_string:
        return 'Linux'
    elif 'mac' in full_platform_string or 'os x' in full_platform_string or 'macos' in full_platform_string:
        return 'Mac'
    else:
        return 'Unknown'


def extract_component(tree, comp_id):
    return tree.find(f".//scap:component[@id='{comp_id}']", namespaces=NAMESPACES)


def write_xml(root, filename, output_dir):
    if root is not None:
        out_path = os.path.join(output_dir, filename)
        etree.ElementTree(root).write(out_path, pretty_print=True, encoding='utf-8', xml_declaration=True)
        print(f"✅ Saved: {out_path}")
    else:
        print(f"⚠️ Skipped: {filename} not found")


def process_rules(
    oval_bytes,
    xccdf_to_oval_def,
    benchmark_name,
    benchmark_type,
    benchmark_dir,
    ben_platform,
    xccdf_bytes
):
    session = SessionLocal()
    benchmark_obj = session.query(Benchmark).filter_by(name=benchmark_name).first()

    ovals_dir = os.path.join(benchmark_dir, "ovals")
    xccdf_dir = os.path.join(benchmark_dir, "xccdf")
    os.makedirs(ovals_dir, exist_ok=True)
    os.makedirs(xccdf_dir, exist_ok=True)
    generated_rules = []

    for rule_id, definition_id in xccdf_to_oval_def.items():
        try:
            
            xccdf_dsa = XccdfDSA(xccdf_bytes)
            rule_id_try = rule_id
            rule_elem = xccdf_dsa.rules_by_id.get(rule_id_try)

            if rule_elem is None and re.search(r'_\d+$', rule_id):
                rule_id_try = re.sub(r'_\d+$', '', rule_id)
                rule_elem = xccdf_dsa.rules_by_id.get(rule_id_try)

            if rule_elem is None:
                raise Exception(f"Rule {rule_id} or {rule_id_try} not found in XCCDF.")
            xccdf_tree = lxml_etree.ElementTree(xccdf_dsa.extract_rule(rule_id_try))
            out_path_xccdf = os.path.join(xccdf_dir, f"{rule_id}.xml")
            xccdf_tree.write(out_path_xccdf, pretty_print=True, encoding="utf-8", xml_declaration=True)    
            if "sce/" in definition_id:
                print(f"⚠ Skipping SCE rule: {rule_id}")
                continue
            if "Manual Rule" in definition_id:
                continue

            temp_dsa = OvalDSA(oval_bytes)
            xccdf_dsa = XccdfDSA(xccdf_bytes)
            
            temp_dsa.keep_only_definition(definition_id)
            tree = lxml_etree.ElementTree(temp_dsa.to_lxml_element())
            
            
            
            out_path = os.path.join(ovals_dir, f"{rule_id}.xml")
            
            tree.write(out_path, pretty_print=True, encoding="utf-8", xml_declaration=True)
            

            analyzer = OvalAnalyzer(temp_dsa)
            object_types = analyzer._extract_object_types(definition_id)
            print(object_types)
            analysis_results = analyzer.analyze(ben_platform)
            regex_results = analyzer.analyze_regex()

            rule_supported = analysis_results[definition_id]['supported']
            unsupported_probes = analysis_results[definition_id]['unsupported_types']

            rule_obj = Rule(
                benchmark_id=benchmark_obj.id,
                rule_id=rule_id,
                definition_id=definition_id,
                oval_path=out_path,
                xccdf_path=out_path_xccdf,
                object_type = ",".join(object_types),
                supported=1 if rule_supported else 0,
                unsupported_probes=None if rule_supported else json.dumps(unsupported_probes),
                manual=False,
                benchmark_type=benchmark_type
            )
            session.add(rule_obj)
            session.commit()

            for regex_issue in regex_results:
                regex_obj = UnsupportedRegex(
                    rule_id=rule_obj.id,
                    definition_id=str(regex_issue['definition_id']),
                    object_id=regex_issue['node_id'],
                    pattern=regex_issue['regex'],
                    reason=regex_issue['reason']
                )
                session.add(regex_obj)
            session.commit()

            generated_rules.append({
                "rule_id": rule_id,
                "definition_id": definition_id,
                "oval_path": out_path
            })

        except Exception as e:
            print(f"⚠ Failed to extract OVAL for rule {rule_id}: {e}")
            continue

    session.close()
    return generated_rules

def parse_stig(file_path, benchmark_dir, benchmark_name, benchmark_type):
    print(f"🔍 Parsing: {file_path}")
    tree = etree.parse(file_path)
    root = tree.getroot()

    ids = {'xccdf': None, 'oval': None, 'cpe-oval': None, 'cpe-dict': None}

    for cref in root.findall(".//scap:component-ref", namespaces=NAMESPACES):
        cref_id = cref.get("id")
        href = cref.get("{http://www.w3.org/1999/xlink}href")
        if not href:
            continue
        ref = href.lstrip("#")

        if "-xccdf.xml" in cref_id:
            ids['xccdf'] = ref
        elif "-oval.xml" in cref_id and "-cpe-oval.xml" not in cref_id:
            ids['oval'] = ref
        elif "-cpe-oval.xml" in cref_id:
            ids['cpe-oval'] = ref
        elif "-cpe-dictionary.xml" in cref_id:
            ids['cpe-dict'] = ref

    components = {key: extract_component(tree, cid) for key, cid in ids.items()}

    xccdf_root = components['xccdf'].find(".//xccdf:Benchmark", namespaces=NAMESPACES) if components['xccdf'] else None
    oval_root = components['oval'].find(".//oval:oval_definitions", namespaces=NAMESPACES) if components['oval'] else None
    cpe_oval_root = components['cpe-oval'].find(".//oval:oval_definitions", namespaces=NAMESPACES) if components['cpe-oval'] else None
    cpe_dict_root = components['cpe-dict'].find(".//cpe-dict:cpe-list", namespaces=NAMESPACES) if components['cpe-dict'] else None

    write_xml(xccdf_root, "xccdf.xml", benchmark_dir)
    write_xml(oval_root, "oval.xml", benchmark_dir)
    write_xml(cpe_oval_root, "cpe-oval.xml", benchmark_dir)
    write_xml(cpe_dict_root, "cpe-dictionary.xml", benchmark_dir)
    # Create mapping
    xccdf_to_oval_def = {}
    if xccdf_root is not None:
        for rule in xccdf_root.findall(".//xccdf:Rule", namespaces=NAMESPACES):
            rule_id = rule.get("id")
            check_ref = rule.findall(".//xccdf:check/xccdf:check-content-ref", namespaces=NAMESPACES)
            if check_ref is not None:
                if len(check_ref) > 1:
                    for i,check in enumerate(check_ref):
                        href = check.get("name")
                        if href:
                            xccdf_to_oval_def[rule_id+"_"+str(i)] = href
                elif len(check_ref) == 0:
                      xccdf_to_oval_def[rule_id] = "Manual Rule"          
                else:            
                    href = check_ref[0].get("name")
                    if href is None:
                        href = check_ref[0].get("href")
                    xccdf_to_oval_def[rule_id] = href

    with open(os.path.join(benchmark_dir, "xccdf_to_oval_definition_map.json"), "w", encoding="utf-8") as f:
        json.dump(xccdf_to_oval_def, f, indent=2)
        print(f"✅ Saved: {benchmark_dir}/xccdf_to_oval_definition_map.json")

    oval_file_path = os.path.join(benchmark_dir, "oval.xml")
    if not os.path.exists(oval_file_path):
        print("⚠ OVAL file not found, skipping rule extraction.")
        return []

    with open(oval_file_path, "rb") as f:
        oval_bytes = f.read()

    xccdf_path = os.path.join(benchmark_dir, "xccdf.xml")
    with open(xccdf_path, "rb") as f:
        xccdf_bytes = f.read()    

    ben_platform = detect_benchmark_type_from_roots(xccdf_root, oval_root)

    return process_rules(
        oval_bytes,
        xccdf_to_oval_def,
        benchmark_name,
        benchmark_type,
        benchmark_dir,
        ben_platform,
        xccdf_bytes
    )

def parse_cis_stig(xccdf_path, oval_path, benchmark_dir, benchmark_name,benchmark_type):
    xccdf_root = etree.parse(xccdf_path)
    oval_root = etree.parse(oval_path)
    xccdf_to_oval_def = {}
    if xccdf_root is not None:
        for rule in xccdf_root.findall(".//xccdf:Rule", namespaces=NAMESPACES):
            rule_id = rule.get("id")
            check_ref = rule.findall(".//xccdf:check/xccdf:check-content-ref", namespaces=NAMESPACES)
            if check_ref is not None:
                if len(check_ref) > 1:
                    for i,check in enumerate(check_ref):
                        href = check.get("name")
                        if href:
                            xccdf_to_oval_def[rule_id+"_"+str(i)] = href
                elif len(check_ref) == 0:
                      xccdf_to_oval_def[rule_id] = "Manual Rule"          
                else:            
                    href = check_ref[0].get("name")
                    if href is None:
                        href = check_ref[0].get("href")
                    xccdf_to_oval_def[rule_id] = href

    with open(os.path.join(benchmark_dir, "xccdf_to_oval_definition_map.json"), "w", encoding="utf-8") as f:
        json.dump(xccdf_to_oval_def, f, indent=2)

    with open(oval_path, "rb") as f:
        oval_bytes = f.read()

    with open(xccdf_path, "rb") as f:
        xccdf_bytes = f.read()

    ben_platform = detect_benchmark_type_from_roots(xccdf_root, oval_root)

    return process_rules(
        oval_bytes,
        xccdf_to_oval_def,
        benchmark_name,
        benchmark_type,
        benchmark_dir,
        ben_platform,
        xccdf_bytes
    )
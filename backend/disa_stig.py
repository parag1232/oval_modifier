from lxml import etree
import json
import os
from backend.oval_analyzer import OvalAnalyzer
from backend.oval_parser import OvalDSA
from backend.database import insert_rule
from lxml import etree as lxml_etree

NAMESPACES = {
    'scap': 'http://scap.nist.gov/schema/scap/source/1.2',
    'xccdf': 'http://checklists.nist.gov/xccdf/1.2',
    'oval': 'http://oval.mitre.org/XMLSchema/oval-definitions-5',
    'cpe-dict': 'http://cpe.mitre.org/dictionary/2.0',
    'xlink': 'http://www.w3.org/1999/xlink'
}

def detect_benchmark_type_from_roots(xccdf_root, oval_root) -> str:
    platforms = []

    # Extract from XCCDF
    if xccdf_root is not None:
        for platform_elem in xccdf_root.findall(".//xccdf:platform", namespaces=NAMESPACES):
            platform_text = platform_elem.text
            if platform_text:
                platforms.append(platform_text.lower())

    # Extract from OVAL
    if oval_root is not None:
        for definition_elem in oval_root.findall(".//oval:definition", namespaces=NAMESPACES):
            affected_elem = definition_elem.find(".//oval:affected", namespaces=NAMESPACES)
            if affected_elem is not None:
                platform = affected_elem.find("oval:platform", namespaces=NAMESPACES)
                if platform is not None and platform.text:
                    platforms.append(platform.text.lower())

    # Simple rule-based mapping
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
        print(f"⚠️  Skipped: {filename} not found")

def parse_stig(file_path, benchmark_dir, benchmark_name,benchmark_type):
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

    xccdf_to_oval_def = {}

    if xccdf_root is not None:
        for rule in xccdf_root.findall(".//xccdf:Rule", namespaces=NAMESPACES):
            rule_id = rule.get("id")
            check_ref = rule.find(".//xccdf:check/xccdf:check-content-ref", namespaces=NAMESPACES)
            if check_ref is not None:
                href = check_ref.get("name")
                xccdf_to_oval_def[rule_id] = href

    with open(os.path.join(benchmark_dir, "xccdf_to_oval_definition_map.json"), "w", encoding="utf-8") as f:
        json.dump(xccdf_to_oval_def, f, indent=2)
        print(f"✅ Saved: {benchmark_dir}/xccdf_to_oval_definition_map.json")

    oval_file_path = os.path.join(benchmark_dir, "oval.xml")
    if not os.path.exists(oval_file_path):
        print("⚠ OVAL file not found, skipping rule extraction.")
        return

    with open(oval_file_path, "rb") as f:
        oval_bytes = f.read()

    ben_platform = detect_benchmark_type_from_roots(xccdf_root, oval_root)
    dsa = OvalDSA(oval_bytes)
    x = OvalAnalyzer(dsa)
    analysis_results = x.analyze(ben_platform)
    ovals_dir = os.path.join(benchmark_dir, "ovals")
    os.makedirs(ovals_dir, exist_ok=True)

    for rule_id, definition_id in xccdf_to_oval_def.items():
        try:

            # if rule_id != "xccdf_mil.disa.stig_rule_SV-238353r991562_rule":
            #     continue
            temp_dsa = OvalDSA(oval_bytes)
            temp_dsa.keep_only_definition(definition_id)
            output_bytes = temp_dsa.to_xml_bytes()

            # Format using lxml for pretty print
            
            lxml_tree = lxml_etree.parse(output_bytes)
            out_path = os.path.join(ovals_dir, f"{rule_id}.xml")
            lxml_tree.write(out_path, pretty_print=True, encoding="utf-8", xml_declaration=True)

            print(f"✅ Extracted OVAL for rule: {rule_id}")

            # Insert into DB
            if analysis_results[definition_id]['supported']:
                insert_rule(benchmark_name, rule_id, definition_id, out_path,supported=1, unsupported_probes=None, manual=False,benchmark_type=benchmark_type)
            else:
                unsupported_probes = analysis_results[definition_id]['unsupported_types']
                insert_rule(benchmark_name, rule_id, definition_id, out_path, supported=0, unsupported_probes=json.dumps(unsupported_probes), manual=False,benchmark_type=benchmark_type)       

        except Exception as e:
            print(f"⚠ Failed to extract OVAL for rule {rule_id}: {e}")

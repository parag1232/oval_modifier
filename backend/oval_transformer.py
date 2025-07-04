# backend/oval_transformer.py

import io
from lxml import etree as ET
import re

def transform_userright_oval(oval_bytes):
    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(io.BytesIO(oval_bytes), parser)
    root = tree.getroot()

    nsmap = root.nsmap
    ns_oval = nsmap.get(None) or "http://oval.mitre.org/XMLSchema/oval-definitions-5"

    id_changes = {}

    # === Rename definitions ===
    def_title_text = ""

    definitions = root.xpath(".//*[local-name()='definition']")
    for definition in definitions:
        title_elem = definition.find(f".//title",namespaces=nsmap)
        if title_elem is not None and title_elem.text:
            def_title_text = title_elem.text.strip()
            matches = re.findall(r"'([^']+)'", def_title_text)
            if len(matches) >= 2:
                raw_value = matches[1]
                parts = [p.strip() for p in raw_value.split(",")]
                regex_value = f"^({'|'.join(parts)})$"
            else:
                regex_value = None

        old_id = definition.attrib.get("id")
        if old_id:
            definition.attrib["id"] = "def1"
            id_changes[old_id] = "def1"

    # === Rename tests ===
    test_id_map = {}
    tests = root.xpath(".//*[substring(local-name(), string-length(local-name()) - 4) = '_test']")
    for idx, test in enumerate(tests, start=1):
        old_id = test.attrib.get("id")
        new_id = f"tst{idx}"
        if old_id:
            test.attrib["id"] = new_id
            test_id_map[old_id] = new_id
            id_changes[old_id] = new_id

    # === Rename states and transform trustee_sid → trustee_name ===
    states = root.xpath(".//*[substring(local-name(), string-length(local-name()) - 5) = '_state']")
    variable_ids = []
    for idx, state in enumerate(states, start=1):
        old_state_id = state.attrib.get("id")
        new_state_id = f"ste{idx}"
        if old_state_id:
            state.attrib["id"] = new_state_id
            id_changes[old_state_id] = new_state_id

        trustee_sid_elem = state.xpath(".//*[local-name()='trustee_sid']")
        if trustee_sid_elem:
            trustee_sid_elem = trustee_sid_elem[0]

            var_ref_id = f"var{idx}"
            variable_ids.append(var_ref_id)        
        if trustee_sid_elem:
            trustee_sid_elem = trustee_sid_elem[0]
            trustee_name_elem = ET.Element(f"trustee_name")
            trustee_name_elem.attrib["var_ref"] = var_ref_id
            trustee_name_elem.attrib["datatype"] = "string"
            trustee_name_elem.attrib["operation"] = "pattern match"
            parent = trustee_sid_elem.getparent()
            parent.replace(trustee_sid_elem, trustee_name_elem)

    # === Update references everywhere ===
    for elem in root.iter():
        for attr in elem.attrib:
            val = elem.attrib[attr]
            if val in id_changes:
                elem.attrib[attr] = id_changes[val]

    # === Update test_ref in criterion explicitly ===
    criteria = root.xpath(".//*[local-name()='criterion']")
    for crit in criteria:
        test_ref = crit.attrib.get("test_ref")
        if test_ref and test_ref in id_changes:
            crit.attrib["test_ref"] = id_changes[test_ref]
        elif test_ref and test_ref not in test_id_map:
            # replace unknown refs with first test ID
            crit.attrib["test_ref"] = "tst1"

    # === Ensure variables section exists ===
    variables_elem = root.xpath(".//*[local-name()='variables']")
    if variables_elem:
        variables_elem = variables_elem[0]
    else:
        variables_elem = ET.SubElement(root, f"{{{ns_oval}}}variables")

    # Check if var1 already exists
    existing_var = variables_elem.xpath(".//*[local-name()='external_variable'][@id='var1']")
    if not existing_var:
        for idx, var_id in enumerate(variable_ids, start=1):
            # Add external_variable
            ext_var_elem = ET.Element(f"{{{ns_oval}}}external_variable")
            ext_var_elem.attrib["id"] = var_id
            ext_var_elem.attrib["datatype"] = "string"
            ext_var_elem.attrib["comment"] = def_title_text or "Trustee name variable"
            ext_var_elem.attrib["version"] = "1"
            variables_elem.append(ext_var_elem)

            # Add check-export
            check_export_elem = ET.Element(f"{{{ns_oval}}}check-export")
            check_export_elem.attrib["export-name"] = f"oval:org.cisecurity.benchmarks:var:6400106{idx}"
            check_export_elem.attrib["value-id"] = f"xccdf_org.cisecurity.benchmarks_value_6400106_var{idx}"
            root.append(check_export_elem)

            # Extract regex value from title if possible
            regex_value = None
            matches = re.findall(r"'([^']+)'", def_title_text)
            if len(matches) >= 2:
                raw_value = matches[1]
                parts = [p.strip() for p in raw_value.split(",")]
                regex_value = f"^({'|'.join(parts)})"

            # Add Value element
            value_elem = ET.Element("Value")
            value_elem.attrib["id"] = f"xccdf_org.cisecurity.benchmarks_value_6220520_var{idx}"
            value_elem.attrib["type"] = "string"
            value_elem.attrib["operator"] = "pattern match"

            title_el = ET.Element("title")
            title_el.text = def_title_text
            value_elem.append(title_el)

            desc_el = ET.Element("description")
            desc_el.text = f"This value is used in Rule: {def_title_text}"
            value_elem.append(desc_el)

            val_el = ET.Element("value")
            val_el.text = regex_value or ""
            value_elem.append(val_el)

            root.append(value_elem)

        output_bytes = ET.tostring(root, pretty_print=True, encoding="UTF-8", xml_declaration=True)
        return output_bytes

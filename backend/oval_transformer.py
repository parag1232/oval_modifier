# backend/oval_transformer.py

import io
from lxml import etree as ET

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

        old_id = definition.attrib.get("id")
        if old_id:
            definition.attrib["id"] = "def1"
            id_changes[old_id] = "def1"

    # === Rename tests ===
    tests = root.xpath(".//*[substring(local-name(), string-length(local-name()) - 4) = '_test']")
    for test in tests:
        old_id = test.attrib.get("id")
        if old_id:
            test.attrib["id"] = "tst1"
            id_changes[old_id] = "tst1"

    # === Rename states and transform trustee_sid → trustee_name ===
    states = root.xpath(".//*[substring(local-name(), string-length(local-name()) - 5) = '_state']")
    for state in states:
        old_id = state.attrib.get("id")
        if old_id:
            state.attrib["id"] = "ste1"
            id_changes[old_id] = "ste1"

        trustee_sid_elem = state.xpath(".//*[local-name()='trustee_sid']")
        if trustee_sid_elem:
            trustee_sid_elem = trustee_sid_elem[0]
            trustee_name_elem = ET.Element(f"trustee_name")
            trustee_name_elem.attrib["var_ref"] = "var1"
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
        elif test_ref:
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
        ext_var_elem = ET.Element(f"{{{ns_oval}}}external_variable")
        ext_var_elem.attrib["id"] = "var1"
        ext_var_elem.attrib["datatype"] = "string"
        ext_var_elem.attrib["comment"] = def_title_text or "Trustee name variable"
        ext_var_elem.attrib["version"] = "1"
        variables_elem.append(ext_var_elem)

    output_bytes = ET.tostring(root, pretty_print=True, encoding="UTF-8", xml_declaration=True)
    return output_bytes

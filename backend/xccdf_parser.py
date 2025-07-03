# backend/xccdf_parser.py

from lxml import etree as ET
import io

class XccdfDSA:
    def __init__(self, xml_bytes):
        self.xml_bytes = xml_bytes
        self.parser = ET.XMLParser(remove_blank_text=True)
        self.tree = ET.parse(io.BytesIO(xml_bytes), self.parser)
        self.root = self.tree.getroot()
        self.nsmap = {'ds':'http://www.w3.org/2000/09/xmldsig#','xccdf': 'http://checklists.nist.gov/xccdf/1.2', 'ae': 'http://benchmarks.cisecurity.org/ae/0.5', 'cc6': 'http://cisecurity.org/20-cc/v6.1', 'cc7': 'http://cisecurity.org/20-cc/v7.0', 'cc8': 'http://cisecurity.org/20-cc/v8.0', 'ciscf': 'https://benchmarks.cisecurity.org/ciscf/1.0', 'notes': 'http://benchmarks.cisecurity.org/notes', 'xhtml': 'http://www.w3.org/1999/xhtml', 'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}

        self.rules_by_id = {}
        self.groups_by_id = {}
        self.variables_by_id = {}
        self.signatures = []

        self._index_tree()

    def _index_tree(self):
        # Preserve any digital signatures
        self.signatures = self.root.xpath(".//xccdf:signature", namespaces=self.nsmap)

        for group in self.root.xpath(".//xccdf:Group", namespaces=self.nsmap):
            gid = group.attrib.get("id")
            if gid:
                self.groups_by_id[gid] = group

        for rule in self.root.xpath(".//xccdf:Rule", namespaces=self.nsmap):
            rid = rule.attrib.get("id")
            if rid:
                self.rules_by_id[rid] = rule

        for var in self.root.xpath(".//xccdf:Value", namespaces=self.nsmap):
            var_id = var.attrib.get("id")
            if var_id:
                self.variables_by_id[var_id] = var

    def extract_rule(self, rule_id):
        rule_elem = self.rules_by_id.get(rule_id)
        if rule_elem is None:
            raise Exception(f"Rule {rule_id} not found.")

        # Find parent groups chain
        parent = rule_elem.getparent()
        parents_chain = []
        while parent is not None and parent.tag.endswith("Group"):
            parents_chain.insert(0, parent)
            parent = parent.getparent()

        # Create new minimal Benchmark root
        new_benchmark = ET.Element(
            self.root.tag,
            nsmap=self.nsmap,
            attrib=self.root.attrib
        )

        # Rebuild only the necessary group hierarchy
        last_parent = new_benchmark
        for group in parents_chain:
            new_group = ET.Element(group.tag, attrib=group.attrib)
            for child in group:
                if child.tag.endswith(("title", "description")):
                    new_group.append(child)
            last_parent.append(new_group)
            last_parent = new_group

        # Add the Rule
        last_parent.append(rule_elem)

        # Find variables used in the rule
        used_var_ids = self._find_variables_in_rule(rule_elem)

        for var_id in used_var_ids:
            var_elem = self.variables_by_id.get(var_id)
            if var_elem is not None:
                new_benchmark.append(var_elem)

        return new_benchmark


    def _find_variables_in_rule(self, rule_elem):
        used_vars = set()

        for el in rule_elem.xpath(".//*", namespaces=self.nsmap):
            for val in el.attrib.values():
                if val in self.variables_by_id:
                    used_vars.add(val)

        for el in rule_elem.xpath(".//*", namespaces=self.nsmap):
            if el.text:
                text = el.text.strip()
                if text in self.variables_by_id:
                    used_vars.add(text)

        return used_vars

    def merge_edited_xccdfs(self, edited_file_paths):
        """
        Merge edited Rules, Variables, Groups, and Profiles into the master XCCDF.
        """

        for edited_path in edited_file_paths:
            edited_tree = ET.parse(edited_path, self.parser)
            edited_root = edited_tree.getroot()

            # Merge variables
            edited_vars = edited_root.xpath(".//xccdf:Value", namespaces=edited_root.nsmap)
            for edited_var in edited_vars:
                var_id = edited_var.attrib.get("id")
                if not var_id:
                    continue
                if var_id in self.variables_by_id:
                    original_var = self.variables_by_id[var_id]
                    parent = original_var.getparent()
                    parent.replace(original_var, edited_var)
                    print(f"✅ Replaced variable {var_id}")
                else:
                    self.root.append(edited_var)
                    print(f"➕ Added new variable {var_id}")

            # Merge groups
            edited_groups = edited_root.xpath(".//xccdf:Group", namespaces=edited_root.nsmap)
            for edited_group in edited_groups:
                gid = edited_group.attrib.get("id")
                if not gid:
                    continue
                if gid in self.groups_by_id:
                    original_group = self.groups_by_id[gid]
                    parent = original_group.getparent()
                    parent.replace(original_group, edited_group)
                    print(f"✅ Replaced group {gid}")
                else:
                    self.root.append(edited_group)
                    print(f"➕ Added new group {gid}")

            # Merge rules
            edited_rules = edited_root.xpath(".//xccdf:Rule", namespaces=edited_root.nsmap)
            for edited_rule in edited_rules:
                rid = edited_rule.attrib.get("id")
                if not rid:
                    continue

                original_rule = self.rules_by_id.get(rid)
                if original_rule is not None:
                    parent = original_rule.getparent()
                    parent.replace(original_rule, edited_rule)
                    print(f"✅ Replaced rule {rid}")
                else:
                    self.root.append(edited_rule)
                    print(f"➕ Added new rule {rid}")

            # Merge profiles
            edited_profiles = edited_root.xpath(".//xccdf:Profile", namespaces=edited_root.nsmap)
            for edited_profile in edited_profiles:
                pid = edited_profile.attrib.get("id")
                if not pid:
                    continue

                existing_profiles = self.root.xpath(
                    f".//xccdf:Profile[@id='{pid}']",
                    namespaces=self.nsmap
                )
                if existing_profiles:
                    original_profile = existing_profiles[0]
                    parent = original_profile.getparent()
                    parent.replace(original_profile, edited_profile)
                    print(f"✅ Replaced profile {pid}")
                else:
                    self.root.append(edited_profile)
                    print(f"➕ Added new profile {pid}")

        # Re-index after merge
        self.rules_by_id.clear()
        self.groups_by_id.clear()
        self.variables_by_id.clear()
        self._index_tree()

    def to_xml_bytes(self):
        return ET.tostring(
            self.root,
            pretty_print=True,
            encoding="UTF-8",
            xml_declaration=True
        )

    def to_lxml_element(self):
        return self.root

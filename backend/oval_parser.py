from lxml import etree as ET
import io
from collections import defaultdict

class GraphNode:
    def __init__(self, node_id, node_type, element):
        self.id = node_id
        self.type = node_type
        self.element = element
        self.children = set()

class OvalDSA:
    def __init__(self, xml_bytes):
        self.xml_bytes = xml_bytes
        self.parser = ET.XMLParser(remove_blank_text=True)
        self.tree = ET.parse(io.BytesIO(xml_bytes), self.parser)
        self.root = self.tree.getroot()
        self.nsmap = self.root.nsmap
        self.nodes = {}
        self.reverse_refs = defaultdict(set)
        self.element_by_id = {}
        self._index_elements()
        self._build_graph()

    def _index_elements(self):
        for elem in self.root.iter():
            elem_id = elem.attrib.get("id")
            if elem_id:
                self.element_by_id[elem_id] = elem

    def _build_graph(self):
        for def_elem in self.root.findall(".//definitions/definition",namespaces=self.nsmap):
            self._process_definition(def_elem)

    def _process_definition(self, def_elem):
        def_id = def_elem.attrib["id"]
        if def_id in self.nodes:
            return
        def_node = GraphNode(def_id, "definition", def_elem)
        self.nodes[def_id] = def_node

        for ext in def_elem.findall(".//extend_definition", namespaces=self.nsmap):
            ref_id = ext.attrib.get("definition_ref")
            if ref_id and ref_id in self.element_by_id:
                def_node.children.add(ref_id)
                self.reverse_refs[ref_id].add(def_id)
                self._process_definition(self.element_by_id[ref_id])

        for criterion in def_elem.findall(".//criterion", namespaces=self.nsmap):
            test_ref = criterion.attrib.get("test_ref")
            if not test_ref:
                continue
            crit_id = f"criterion:{def_id}:{test_ref}"
            crit_node = GraphNode(crit_id, "criterion", criterion)
            self.nodes[crit_id] = crit_node
            def_node.children.add(crit_id)
            crit_node.children.add(test_ref)
            self.reverse_refs[crit_id].add(def_id)
            self.reverse_refs[test_ref].add(crit_id)

            test_elem = self.element_by_id.get(test_ref)
            if test_elem:
                if test_ref not in self.nodes:
                    self.nodes[test_ref] = GraphNode(test_ref, "test", test_elem)

                object_refs = [e.attrib["object_ref"] for e in test_elem.xpath(".//*[local-name()='object']") if "object_ref" in e.attrib]
                state_refs = [e.attrib["state_ref"] for e in test_elem.xpath(".//*[local-name()='state']") if "state_ref" in e.attrib]

                for obj_id in object_refs:
                    self.nodes[test_ref].children.add(obj_id)
                    self.reverse_refs[obj_id].add(test_ref)
                    self._process_object(obj_id)

                for state_id in state_refs:
                    self.nodes[test_ref].children.add(state_id)
                    self.reverse_refs[state_id].add(test_ref)
                    self._process_state(state_id)

    def _process_object(self, obj_id):
        obj_elem = self.element_by_id.get(obj_id)
        if not obj_elem:
            return
        if obj_id not in self.nodes:
            self.nodes[obj_id] = GraphNode(obj_id, "object", obj_elem)

        # Handle <set>
        set_elem = obj_elem.find(".//set", namespaces=self.nsmap)
        if set_elem is not None:
            for obj_ref_elem in set_elem.findall("oval:object_reference", namespaces=self.nsmap):
                child_obj_id = obj_ref_elem.text.strip()
                self.nodes[obj_id].children.add(child_obj_id)
                self.reverse_refs[child_obj_id].add(obj_id)
                self._process_object(child_obj_id)
            for filter_elem in set_elem.findall("oval:filter", namespaces=self.nsmap):
                state_id = filter_elem.text.strip()
                self.nodes[obj_id].children.add(state_id)
                self.reverse_refs[state_id].add(obj_id)
                self._process_state(state_id)

        # Also handle <filter> directly on object
        for filter_elem in obj_elem.xpath(".//*[local-name()='filter']"):
            state_id = filter_elem.text.strip()
            if state_id in self.element_by_id:
                self.nodes[obj_id].children.add(state_id)
                self.reverse_refs[state_id].add(obj_id)
                self._process_state(state_id)

    def _process_state(self, state_id):
        state_elem = self.element_by_id.get(state_id)
        if not state_elem:
            return
        if state_id not in self.nodes:
            self.nodes[state_id] = GraphNode(state_id, "state", state_elem)
        for var_elem in state_elem.xpath(".//*[@var_ref]"):
            var_id = var_elem.attrib.get("var_ref")
            if var_id and var_id in self.element_by_id:
                if var_id not in self.nodes:
                    self.nodes[var_id] = GraphNode(var_id, "variable", self.element_by_id[var_id])
                self.nodes[state_id].children.add(var_id)
                self.reverse_refs[var_id].add(state_id)

    def keep_only_definition(self, def_id):
        if def_id not in self.nodes:
            return
        keep_set = set()
        stack = [def_id]
        while stack:
            curr = stack.pop()
            if curr in keep_set:
                continue
            keep_set.add(curr)
            stack.extend(self.nodes[curr].children)

        for node_id in list(self.nodes):
            if node_id not in keep_set:
                del self.nodes[node_id]

    def keep_only_definitions(self, definition_ids):
        keep_set = set()
        stack = list(definition_ids)
        while stack:
            current_id = stack.pop()
            if current_id in keep_set:
                continue
            keep_set.add(current_id)
            node = self.nodes.get(current_id)
            if node:
                stack.extend(node.children)
        for node_id in list(self.nodes.keys()):
            if node_id not in keep_set:
                del self.nodes[node_id]            

    def to_xml_bytes(self):
        root_copy = ET.Element(self.root.tag, nsmap=self.root.nsmap)

        # Generator
        gen = self.root.find("oval:generator", namespaces=self.nsmap)
        if gen is not None:
            root_copy.append(gen)

        sections = defaultdict(list)
        for node in self.nodes.values():
            sections[node.type + "s"].append(node.element)

        for section in ["definitions", "tests", "objects", "states", "variables"]:
            if sections[section]:
                section_elem = ET.SubElement(root_copy, f"{{{self.nsmap[None]}}}{section}")
                for elem in sections[section]:
                    section_elem.append(elem)

        return ET.tostring(root_copy, pretty_print=True, encoding="utf-8", xml_declaration=True)
    

    def to_lxml_element(self):
        root_copy = ET.Element(self.root.tag, nsmap=self.root.nsmap)

        # Generator
        gen = self.root.find("oval:generator", namespaces=self.nsmap)
        if gen is not None:
            root_copy.append(gen)

        sections = defaultdict(list)
        for node in self.nodes.values():
            sections[node.type + "s"].append(node.element)

        for section in ["definitions", "tests", "objects", "states", "variables"]:
            if sections[section]:
                section_elem = ET.SubElement(root_copy, f"{{{self.nsmap[None]}}}{section}")
                for elem in sections[section]:
                    section_elem.append(elem)

        return root_copy
from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import xml.etree.ElementTree as ET
from collections import defaultdict
import io

# Register default known namespaces
ET.register_namespace('', "http://oval.mitre.org/XMLSchema/oval-definitions-5")
ET.register_namespace('oval', "http://oval.mitre.org/XMLSchema/oval-common-5")
ET.register_namespace('independent', "http://oval.mitre.org/XMLSchema/oval-definitions-5#independent")
ET.register_namespace('linux', "http://oval.mitre.org/XMLSchema/oval-definitions-5#linux")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def deepcopy_with_ns(elem):
    new_elem = ET.Element(elem.tag)
    for key, val in elem.attrib.items():
        new_elem.set(key, val)
    new_elem.text = elem.text
    new_elem.tail = elem.tail
    for child in elem:
        new_elem.append(deepcopy_with_ns(child))
    return new_elem

def normalize_namespaces_to_default(elem, target_ns):
    if "product_name" in elem.tag or "schema_version" in elem.tag or "timestamp" in elem.tag:
        return
    if elem.tag.startswith('{'):
        uri, tag = elem.tag[1:].split('}', 1)
        elem.tag = f'{{{target_ns}}}{tag}'
    for key in list(elem.attrib.keys()):
        if key.startswith('{'):
            uri, attr = key[1:].split('}', 1)
            new_key = attr
            elem.attrib[new_key] = elem.attrib.pop(key)
    for child in elem:
        normalize_namespaces_to_default(child, target_ns)

class GraphNode:
    def __init__(self, node_id, node_type, element):
        self.id = node_id
        self.type = node_type
        self.element = element
        self.children = set()

class OvalDSA:
    def __init__(self, xml_bytes):
        self.xml_bytes = xml_bytes
        self.ns = {'oval': 'http://oval.mitre.org/XMLSchema/oval-definitions-5'}
        self.nsmap = self._extract_nsmap()
        self.tree = ET.ElementTree(file=io.BytesIO(xml_bytes))
        self.root = self.tree.getroot()
        self.nodes = {}
        self.reverse_refs = defaultdict(set)
        self.element_by_id = {}
        self._index_elements()
        self._build_graph()

    def _extract_nsmap(self):
        nsmap = {}
        context = ET.iterparse(io.BytesIO(self.xml_bytes), events=("start-ns",))
        for event, elem in context:
            prefix, uri = elem
            nsmap[prefix] = uri
        return nsmap

    def _index_elements(self):
        for elem in self.root.iter():
            elem_id = elem.attrib.get("id")
            if elem_id:
                elem_copy = deepcopy_with_ns(elem)
                for prefix, uri in self.nsmap.items():
                    if prefix:
                        elem_copy.set(f"xmlns:{prefix}", uri)
                    else:
                        elem_copy.set("xmlns", uri)
                self.element_by_id[elem_id] = elem_copy

    def _build_graph(self):
        for def_elem in self.root.findall("oval:definitions/oval:definition", self.ns):
            self._process_definition(def_elem)

    def _process_definition(self, def_elem):
        def_id = def_elem.attrib["id"]
        if def_id in self.nodes:
            return
        def_node = GraphNode(def_id, "definition", def_elem)
        self.nodes[def_id] = def_node

        for ext in def_elem.findall(".//oval:extend_definition", self.ns):
            ref_id = ext.attrib.get("definition_ref")
            if ref_id and ref_id in self.element_by_id:
                def_node.children.add(ref_id)
                self.reverse_refs[ref_id].add(def_id)
                self._process_definition(self.element_by_id[ref_id])

        for criterion in def_elem.findall(".//oval:criterion", self.ns):
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
                object_refs = [ref.attrib["object_ref"] for ref in test_elem.findall(".//*") if ref.tag.endswith("object") and "object_ref" in ref.attrib]
                state_refs = [ref.attrib["state_ref"] for ref in test_elem.findall(".//*") if ref.tag.endswith("state") and "state_ref" in ref.attrib]

                for obj_id in object_refs:
                    if obj_id in self.element_by_id:
                        self.nodes[test_ref].children.add(obj_id)
                        self.reverse_refs[obj_id].add(test_ref)
                        self._process_object(obj_id)

                for state_id in state_refs:
                    if state_id in self.element_by_id:
                        self.nodes[test_ref].children.add(state_id)
                        self.reverse_refs[state_id].add(test_ref)
                        self._process_state(state_id)

    def _process_object(self, obj_id):
        if obj_id not in self.element_by_id:
            return
        obj_elem = self.element_by_id[obj_id]
        if obj_id not in self.nodes:
            self.nodes[obj_id] = GraphNode(obj_id, "object", obj_elem)

        set_elem = obj_elem.find(".//{http://oval.mitre.org/XMLSchema/oval-definitions-5}set")
        if set_elem is not None:
            for obj_ref_elem in set_elem.findall("{http://oval.mitre.org/XMLSchema/oval-definitions-5}object_reference"):
                child_obj_id = obj_ref_elem.text.strip()
                if child_obj_id:
                    self.nodes[obj_id].children.add(child_obj_id)
                    self.reverse_refs[child_obj_id].add(obj_id)
                    self._process_object(child_obj_id)

            for filter_elem in set_elem.findall("{http://oval.mitre.org/XMLSchema/oval-definitions-5}filter"):
                state_id = filter_elem.text.strip()
                if state_id:
                    self.nodes[obj_id].children.add(state_id)
                    self.reverse_refs[state_id].add(obj_id)
                    self._process_state(state_id)

    def _process_state(self, state_id):
        if state_id not in self.element_by_id:
            return
        state_elem = self.element_by_id[state_id]
        if state_id not in self.nodes:
            self.nodes[state_id] = GraphNode(state_id, "state", state_elem)
        for var_ref_elem in state_elem.findall(".//*"):
            var_ref = var_ref_elem.attrib.get("var_ref")
            if var_ref and var_ref in self.element_by_id:
                var_elem = self.element_by_id[var_ref]
                if var_ref not in self.nodes:
                    self.nodes[var_ref] = GraphNode(var_ref, "variable", var_elem)
                self.nodes[state_id].children.add(var_ref)
                self.reverse_refs[var_ref].add(state_id)

    def _delete_recursive(self, node_id, visited):
        if node_id in visited:
            return
        visited.add(node_id)
        node = self.nodes.get(node_id)
        if not node:
            return
        for child_id in node.children:
            self.reverse_refs[child_id].discard(node_id)
            if not self.reverse_refs[child_id]:
                self._delete_recursive(child_id, visited)
        del self.nodes[node_id]

    def delete_definition(self, def_id):
        if def_id in self.nodes and self.nodes[def_id].type == "definition":
            self._delete_recursive(def_id, set())

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
                self._delete_recursive(node_id, set())
        

    def keep_only_definition(self, def_id):
        if def_id not in self.nodes or self.nodes[def_id].type != "definition":
            raise ValueError("Invalid definition ID")
        keep_set = set()
        stack = [def_id]
        while stack:
            current_id = stack.pop()
            if current_id in keep_set:
                continue
            keep_set.add(current_id)

            node = self.nodes.get(current_id)
            if node:
                stack.extend(node.children)

            # 🔥 NEW LOGIC: include all definitions that reference this definition via extend_definition
            # for reverse_id in self.reverse_refs.get(current_id, []):
            #     if reverse_id in self.nodes and self.nodes[reverse_id].type == "definition":
            #         stack.append(reverse_id)

        for node_id in list(self.nodes.keys()):
            if node_id not in keep_set:
                del self.nodes[node_id]


    def to_xml_bytes(self):
        new_root = ET.Element(self.root.tag, self.root.attrib)
        generator = self.root.find("oval:generator", self.ns)
        if generator is not None:
            generator_cleaned = ET.Element("generator")
            for child in generator:
                tag_clean = child.tag.split("}")[-1]
                new_elem = ET.SubElement(generator_cleaned, f"{{http://oval.mitre.org/XMLSchema/oval-common-5}}{tag_clean}")
                new_elem.text = child.text
            new_root.append(generator_cleaned)

        sections = defaultdict(list)
        for node in self.nodes.values():
            sections[node.type + "s"].append(node.element)

        for section_name in ["definitions", "tests", "objects", "states","variables"]:
            if sections[section_name]:
                section = ET.SubElement(new_root, section_name)
                for elem in sections[section_name]:
                    section.append(deepcopy_with_ns(elem))

        # vars_section = ET.SubElement(new_root, "variables")
        # for elem in sections["variables"]:
        #     vars_section.append(deepcopy_with_ns(elem))

        normalize_namespaces_to_default(new_root, "http://oval.mitre.org/XMLSchema/oval-definitions-5")
        output = io.BytesIO()
        ET.ElementTree(new_root).write(output, encoding="utf-8", xml_declaration=True)
        output.seek(0)
        return output

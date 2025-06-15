WIN_SUPPORTED_PROBES = {
    "registry_object", "win-def:registry_object", "windows-def:registry_object",
    "file_object", "auditeventpolicysubcategories_object", "family_object",
    "lockoutpolicy_object", "passwordpolicy_object", "user_sid_object",
    "sid_sid_object", "user_sid55_object", "userright_object"
}

LINUX_SUPPORTED_PROBES = {
    "dpkginfo_object", "textfilecontent54_object", "systemdunitproperty_object",
    "rpminfo_object", "file_object", "partition_object", "uname_object",
    "sysctl_object", "sshd_object", "modprobe_object", "variable_object"
}

MAC_SUPPORTED_PROBES = {
    "plist511_object", "textfilecontent54_object", "account_pwpolicy_object",
    "authorizationdb_object", "open_directory_object", "launchctl_object",
    "pmset_object", "profiles_object", "sip_object", "systemsetup_v2_object",
    "userdefaults_object", "file_object"
}

class OvalAnalyzer:
    def __init__(self, oval_dsa):
        self.dsa = oval_dsa

    def analyze(self,benchmark_type=None):
        analysis_results = {}

        for node_id, node in self.dsa.nodes.items():
            if node.type != "definition":
                continue

            object_types = self._extract_object_types(node_id)
            if str.lower(benchmark_type) == "linux":
                unsupported = [obj for obj in object_types if obj not in LINUX_SUPPORTED_PROBES]
            elif str.lower(benchmark_type) == "macos":
                unsupported = [obj for obj in object_types if obj not in MAC_SUPPORTED_PROBES]
            else:
                unsupported = [obj for obj in object_types if obj not in WIN_SUPPORTED_PROBES]        
            supported = len(unsupported) == 0

            analysis_results[node_id] = {
                "supported": supported,
                "unsupported_types": unsupported,
                "all_object_types": object_types
            }

        return analysis_results

    def _extract_object_types(self, definition_id):
        object_types = set()
        visited = set()

        def traverse(node_id):
            if node_id in visited:
                return
            visited.add(node_id)

            node = self.dsa.nodes.get(node_id)
            if not node:
                return

            if node.type == "object":
                tag = node.element.tag.split("}")[-1]
                object_types.add(tag)

            for child in node.children:
                traverse(child)

        traverse(definition_id)
        return object_types

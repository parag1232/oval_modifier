import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getRules,
  deleteRules,
  downloadMergedOval,
  getOval,
  downloadSingleRuleOval,
  saveOval,
  getHostState,
  getRemoteHosts,
  evaluateRules,
  getXccdf,
  saveXccdf,
  getRulesByObject,
  transformUserRight,
} from "../api/api";

import CodeMirror from "@uiw/react-codemirror";
import { xml } from "@codemirror/lang-xml";
import { json } from "@codemirror/lang-json";
import beautify from "js-beautify";

function Modal({ open, onClose, title, children, onSave }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 bg-black/50 flex justify-center items-center z-50">
      <div className="bg-white rounded-xl w-full max-w-4xl p-6 max-h-[80vh] overflow-auto shadow-xl">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-800">{title}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-red-500 text-2xl font-bold"
          >
            ×
          </button>
        </div>
        <div className="overflow-y-auto">{children}</div>
        <div className="mt-6 flex justify-end gap-3">
          {onSave && (
            <button
              onClick={onSave}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md font-semibold"
            >
              Save
            </button>
          )}
          <button
            onClick={onClose}
            className="bg-gray-400 hover:bg-gray-500 text-white px-4 py-2 rounded-md font-semibold"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function RuleBrowserPage() {
  const { benchmark } = useParams();
  const [rules, setRules] = useState([]);
  const [search, setSearch] = useState("");
  const [objectSearch, setObjectSearch] = useState("");
  const [selectedRule, setSelectedRule] = useState("");
  const [oval, setOval] = useState("");
  const [xccdf, setXccdf] = useState("");
  const [selected, setSelected] = useState([]);
  const [sortAsc, setSortAsc] = useState(true);
  const [lastSelectedIndex, setLastSelectedIndex] = useState(null);
  const [saveStatus, setSaveStatus] = useState("");

  const [hostStateContent, setHostStateContent] = useState("");
  const [hostStateModalOpen, setHostStateModalOpen] = useState(false);
  const [selectedHostStateRule, setSelectedHostStateRule] = useState("");

  const [xccdfModalOpen, setXccdfModalOpen] = useState(false);
  const [xccdfSaveStatus, setXccdfSaveStatus] = useState("");

  const [remoteHostExists, setRemoteHostExists] = useState(false);

  const [transformModalOpen, setTransformModalOpen] = useState(false);
  const [transformedXml, setTransformedXml] = useState("");

  const navigate = useNavigate();

  const fetchRules = () => {
    getRules(benchmark).then(setRules);
  };

  const fetchRemoteHostStatus = async () => {
    try {
      const hosts = await getRemoteHosts(benchmark);
      setRemoteHostExists(hosts.length > 0);
    } catch (err) {
      console.error("Failed to fetch remote hosts:", err.message);
      setRemoteHostExists(false);
    }
  };

  useEffect(() => {
    fetchRules();
    fetchRemoteHostStatus();
  }, [benchmark]);

  const handleFilterByObject = async () => {
    if (!objectSearch.trim()) {
      fetchRules();
      return;
    }
    try {
      const result = await getRulesByObject(benchmark, objectSearch.trim());
      setRules(result);
    } catch (err) {
      alert("Failed to fetch rules by object: " + err.message);
    }
  };

  const handleOpenRule = async (ruleId) => {
    const res = await getOval(benchmark, ruleId);
    const formatted = beautify.html(res.oval, {
      indent_size: 2,
      wrap_line_length: 120,
      unformatted: [],
    });
    setSelectedRule(ruleId);
    setOval(formatted);
    setSaveStatus("");
  };

  const handleOpenXccdf = async (ruleId) => {
    try {
      const res = await getXccdf(benchmark, ruleId);
      const formatted = beautify.html(res.xccdf || "", {
        indent_size: 2,
        wrap_line_length: 120,
        unformatted: [],
      });
      setXccdf(formatted);
      setSelectedRule(ruleId);
      setXccdfModalOpen(true);
      setXccdfSaveStatus("");
    } catch (err) {
      alert("Failed to fetch XCCDF: " + err.message);
    }
  };

  const handleSaveOval = async () => {
    try {
      await saveOval(benchmark, selectedRule, oval);
      setSaveStatus("✅ OVAL saved successfully.");
      fetchRules();
      setTimeout(() => setSelectedRule(""), 1000);
    } catch (err) {
      setSaveStatus("❌ Failed to save OVAL: " + err.message);
    }
  };

  const handleSaveXccdf = async () => {
    try {
      await saveXccdf(benchmark, selectedRule, xccdf);
      setXccdfSaveStatus("✅ XCCDF saved successfully.");
      fetchRules();
      setTimeout(() => {
        setXccdfModalOpen(false);
        setSelectedRule("");
      }, 1000);
    } catch (err) {
      setXccdfSaveStatus("❌ Failed to save XCCDF: " + err.message);
    }
  };

  const handleDownloadRuleOval = async (ruleId) => {
    try {
      await downloadSingleRuleOval(benchmark, ruleId);
    } catch (err) {
      alert("Failed to download rule OVAL: " + err.message);
    }
  };

  const handleTransformUserRight = async (ruleId) => {
    try {
      const res = await transformUserRight(benchmark, ruleId);
      const formatted = beautify.html(res.transformed || "", {
        indent_size: 2,
        wrap_line_length: 120,
        unformatted: [],
      });
      setSelectedRule(ruleId);
      setTransformedXml(formatted);
      setTransformModalOpen(true);
    } catch (err) {
      alert("Failed to fetch transformed XML: " + err.message);
    }
  };

  const handleViewHostState = async (ruleId) => {
    try {
      const res = await getHostState(benchmark, ruleId);
      const formatted = JSON.stringify(res.hoststate_json, null, 2);
      setSelectedHostStateRule(ruleId);
      setHostStateContent(formatted);
      setHostStateModalOpen(true);
    } catch (err) {
      alert("Failed to fetch host state: " + err.message);
    }
  };

  const handleEvaluateRules = async () => {
    try {
      await evaluateRules(benchmark);
      alert("✅ Rules evaluated successfully!");
      fetchRules();
    } catch (err) {
      alert("❌ Failed to evaluate rules: " + err.message);
    }
  };

  const handleSelect = (ruleId, index, event) => {
    if (event.shiftKey && lastSelectedIndex !== null) {
      const start = Math.min(lastSelectedIndex, index);
      const end = Math.max(lastSelectedIndex, index);
      const idsToSelect = sortedRules
        .slice(start, end + 1)
        .map((rule) => rule.rule_id);
      const merged = Array.from(new Set([...selected, ...idsToSelect]));
      setSelected(merged);
    } else if (event.ctrlKey || event.metaKey) {
      setSelected((prev) =>
        prev.includes(ruleId)
          ? prev.filter((id) => id !== ruleId)
          : [...prev, ruleId]
      );
      setLastSelectedIndex(index);
    } else {
      setSelected((prev) =>
        prev.includes(ruleId)
          ? prev.filter((id) => id !== ruleId)
          : [...prev, ruleId]
      );
      setLastSelectedIndex(index);
    }
  };

  const filteredRules = rules.filter((rule) =>
    rule.rule_id.toLowerCase().includes(search.trim().toLowerCase())
  );

  const sortedRules = [...filteredRules].sort((a, b) => {
    if (sortAsc)
      return a.supported === b.supported ? 0 : a.supported ? 1 : -1;
    else return a.supported === b.supported ? 0 : a.supported ? -1 : 1;
  });

  const handleDeleteSelected = async () => {
    if (!selected.length) return;
    if (
      !window.confirm(
        `Are you sure you want to delete ${selected.length} rules?`
      )
    )
      return;

    try {
      await deleteRules(benchmark, selected);
      setSelected([]);
      fetchRules();
    } catch (err) {
      alert("Failed to delete: " + err.message);
    }
  };

  const handleGenerateOvals = async () => {
    if (!selected.length) return;
    try {
      await downloadMergedOval(benchmark, selected);
    } catch (err) {
      alert("Failed to generate merged OVAL: " + err.message);
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <h1 className="text-2xl font-bold text-gray-800">
          Rules for {benchmark}
        </h1>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleEvaluateRules}
            className="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-md font-semibold"
          >
            Evaluate Rules
          </button>
          {remoteHostExists && (
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-300">
              Remote Host Added
            </span>
          )}
        </div>
      </div>

      {/* Search and Object Filter */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div className="flex flex-col md:flex-row gap-2 w-full">
          <input
            type="text"
            placeholder="Search Rule ID"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border border-gray-300 rounded-md px-4 py-2 w-full md:w-80 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="flex gap-2 w-full md:w-auto">
            <input
              type="text"
              placeholder="Filter by Object name"
              value={objectSearch}
              onChange={(e) => setObjectSearch(e.target.value)}
              className="border border-gray-300 rounded-md px-4 py-2 w-full md:w-80 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleFilterByObject}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md font-semibold"
            >
              Filter
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md font-semibold disabled:opacity-50"
            disabled={selected.length === 0}
            onClick={handleDeleteSelected}
          >
            Delete Selected
          </button>
          <button
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md font-semibold disabled:opacity-50"
            disabled={selected.length === 0}
            onClick={handleGenerateOvals}
          >
            Download Merged OVAL
          </button>
          <button
            className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-md font-semibold"
            onClick={() => navigate(`/regex-issues/${benchmark}`)}
          >
            Unsupported Regex
          </button>
        </div>
      </div>

      <div className="overflow-auto rounded-lg border border-gray-200 shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th></th>
              <th className="px-40 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Rule ID
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider cursor-pointer"
                onClick={() => setSortAsc(!sortAsc)}
              >
                Supported {sortAsc ? "▲" : "▼"}
              </th>
              <th
                className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider cursor-pointer"
                onClick={() => setSortAsc(!sortAsc)}
              >
                Sensor File Status {sortAsc ? "▲" : "▼"}
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Rule Evaluation
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sortedRules.map((rule, index) => (
              <tr key={rule.rule_id} className="hover:bg-gray-50">
                <td className="px-4 py-3 whitespace-nowrap">
                  <input
                    type="checkbox"
                    checked={selected.includes(rule.rule_id)}
                    onChange={(e) =>
                      handleSelect(rule.rule_id, index, e.nativeEvent)
                    }
                    className="h-4 w-4 text-blue-600"
                  />
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-800 max-w-[200px] overflow-hidden truncate" title={rule.rule_id}>
                  {rule.rule_id}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm">
                  {rule.supported ? (
                    <span className="text-green-700 font-semibold">Supported ✅</span>
                  ) : (
                    <span className="text-red-600 font-semibold">Unsupported ❌</span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm">
                  {rule.sensor_file_generated ? (
                    <span className="text-green-700 font-semibold">Generated ✅</span>
                  ) : (
                    <span className="text-red-600 font-semibold">Not Generated ❌</span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm">
                  {rule.evaluation ? (
                    <span className={
                      rule.evaluation === "Passed"
                        ? "text-green-700 font-semibold"
                        : rule.evaluation === "Failed"
                        ? "text-red-600 font-semibold"
                        : "text-yellow-600 font-semibold"
                    }>
                      {rule.evaluation}
                    </span>
                  ) : (
                    <span className="text-gray-500 italic">N/A</span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap flex flex-wrap gap-2">
                  <button
                    className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                    onClick={() => handleOpenRule(rule.rule_id)}
                  >
                    View OVAL
                  </button>
                  <button
                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                    onClick={() => handleViewHostState(rule.rule_id)}
                  >
                    View HostState
                  </button>
                  <button
                    className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded-md text-sm font-semibold"
                    onClick={() => handleDownloadRuleOval(rule.rule_id)}
                  >
                    Download OVAL
                  </button>
                  <button
                    className="bg-pink-600 hover:bg-pink-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                    onClick={() => handleOpenXccdf(rule.rule_id)}
                  >
                    View XCCDF
                  </button>
                  <button
                    className="bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                    onClick={() => handleTransformUserRight(rule.rule_id)}
                  >
                    Process OVAL
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={!!selectedRule && !xccdfModalOpen}
        onClose={() => setSelectedRule("")}
        title={`OVAL for ${selectedRule}`}
        onSave={handleSaveOval}
      >
        <CodeMirror
          value={oval}
          height="500px"
          theme="dark"
          extensions={[xml()]}
          onChange={(value) => setOval(value)}
        />
        {saveStatus && (
          <p className="mt-2 text-blue-600 font-medium">{saveStatus}</p>
        )}
      </Modal>

      <Modal
        open={hostStateModalOpen}
        onClose={() => setHostStateModalOpen(false)}
        title={`HostState for ${selectedHostStateRule}`}
      >
        <CodeMirror
          value={hostStateContent || ""}
          height="500px"
          theme="dark"
          extensions={[json()]}
        />
      </Modal>

      <Modal
        open={xccdfModalOpen}
        onClose={() => {
          setXccdfModalOpen(false);
          setSelectedRule("");
        }}
        title={`XCCDF for ${selectedRule}`}
        onSave={handleSaveXccdf}
      >
        <CodeMirror
          value={xccdf}
          height="500px"
          theme="dark"
          extensions={[xml()]}
          onChange={(val) => setXccdf(val)}
        />
        {xccdfSaveStatus && (
          <p className="mt-2 text-blue-600 font-medium">{xccdfSaveStatus}</p>
        )}
      </Modal>

      <Modal
        open={transformModalOpen}
        onClose={() => {
          setTransformModalOpen(false);
          setSelectedRule("");
        }}
        title={`Transformed OVAL for ${selectedRule}`}
      >
        <CodeMirror
          value={transformedXml}
          height="500px"
          theme="dark"
          extensions={[xml()]}
          onChange={(val) => setTransformedXml(val)}
        />
      </Modal>
    </div>
  );
}

export default RuleBrowserPage;

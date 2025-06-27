import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getRules,
  deleteRules,
  downloadMergedOval,
  getOval,
  downloadSingleRuleOval,
  saveOval,
} from "../api/api";

import CodeMirror from "@uiw/react-codemirror";
import { xml } from "@codemirror/lang-xml";
import beautify from "js-beautify";

function Modal({ open, onClose, title, children, onSave }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center z-50">
      <div className="bg-white rounded-lg w-3/4 p-4 max-h-[80vh] overflow-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            onClick={onClose}
            className="text-red-600 font-bold text-xl"
          >
            ×
          </button>
        </div>
        <div className="overflow-y-auto">{children}</div>
        <div className="mt-4 flex justify-end space-x-2">
          {onSave && (
            <button
              onClick={onSave}
              className="bg-green-600 text-white px-4 py-2 rounded"
            >
              Save
            </button>
          )}
          <button
            onClick={onClose}
            className="bg-gray-500 text-white px-4 py-2 rounded"
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
  const [selectedRule, setSelectedRule] = useState("");
  const [oval, setOval] = useState("");
  const [selected, setSelected] = useState([]);
  const [sortAsc, setSortAsc] = useState(true);
  const [lastSelectedIndex, setLastSelectedIndex] = useState(null);
  const [saveStatus, setSaveStatus] = useState("");
  const navigate = useNavigate();

  const fetchRules = () => {
    getRules(benchmark).then(setRules);
  };

  useEffect(() => {
    fetchRules();
  }, [benchmark]);

  const handleOpenRule = async (ruleId) => {
    const res = await getOval(benchmark, ruleId);

    // Pretty-print the XML for better editing
    const formatted = beautify.html(res.oval, {
      indent_size: 2,
      wrap_line_length: 120,
      unformatted: [], // format all tags
    });

    setSelectedRule(ruleId);
    setOval(formatted);
    setSaveStatus("");
  };

  const handleDownloadRuleOval = async (ruleId) => {
    try {
      await downloadSingleRuleOval(benchmark, ruleId);
    } catch (err) {
      alert("Failed to download rule OVAL: " + err.message);
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
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-xl mb-4 font-semibold">Rules for {benchmark}</h1>

      <div className="flex mb-4 space-x-4">
        <input
          type="text"
          placeholder="Search Rule ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border p-2 w-80"
        />
        <button
          className="bg-red-600 text-white px-4 py-2 rounded"
          disabled={selected.length === 0}
          onClick={handleDeleteSelected}
        >
          Delete Selected
        </button>
        <button
          className="bg-green-600 text-white px-4 py-2 rounded"
          disabled={selected.length === 0}
          onClick={handleGenerateOvals}
        >
          Download Merged OVAL
        </button>
        <button
          className="bg-purple-600 text-white px-4 py-2 rounded"
          onClick={() => navigate(`/regex-issues/${benchmark}`)}
        >
          Unsupported Regex
        </button>
      </div>

      <table className="border border-gray-300 w-full">
        <thead className="bg-gray-200">
          <tr>
            <th className="px-4 py-2 border"></th>
            <th className="px-4 py-2 border">Rule ID</th>
            <th
              className="px-4 py-2 border cursor-pointer"
              onClick={() => setSortAsc(!sortAsc)}
            >
              Supported {sortAsc ? "▲" : "▼"}
            </th>
            <th
              className="px-4 py-2 border cursor-pointer"
              onClick={() => setSortAsc(!sortAsc)}
            >
              Sensor File Status {sortAsc ? "▲" : "▼"}
            </th>
            <th className="px-4 py-2 border">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sortedRules.map((rule, index) => (
            <tr key={rule.rule_id} className="border-b">
              <td className="px-4 py-2 border">
                <input
                  type="checkbox"
                  checked={selected.includes(rule.rule_id)}
                  onChange={(e) =>
                    handleSelect(rule.rule_id, index, e.nativeEvent)
                  }
                />
              </td>
              <td className="px-4 py-2 border">{rule.rule_id}</td>
              <td className="px-4 py-2 border">
                {rule.supported ? (
                  <span className="text-green-600 font-semibold">
                    Supported ✅
                  </span>
                ) : (
                  <span className="text-red-600 font-semibold">
                    Unsupported ❌
                  </span>
                )}
              </td>
              <td className="px-4 py-2 border">
                {rule.sensor_file_generated ? (
                  <span className="text-green-600 font-semibold">
                    Generated ✅
                  </span>
                ) : (
                  <span className="text-red-600 font-semibold">
                    Not Generated ❌
                  </span>
                )}
              </td>
              <td className="px-4 py-2 border">
                <button
                  className="bg-blue-500 text-white px-3 py-1 rounded mr-2"
                  onClick={() => handleOpenRule(rule.rule_id)}
                >
                  View OVAL
                </button>
                <button
                  className="bg-blue-500 text-white px-3 py-1 rounded"
                  onClick={() => handleDownloadRuleOval(rule.rule_id)}
                >
                  Download OVAL
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Modal
        open={!!selectedRule}
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
    </div>
  );
}

export default RuleBrowserPage;

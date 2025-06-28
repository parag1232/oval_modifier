import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getRegexIssues } from "../api/api";

export default function RegexIssuesPage() {
  const { benchmark } = useParams();
  const [regexText, setRegexText] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        const text = await getRegexIssues(benchmark);
        setRegexText(text);
      } catch (err) {
        setError("Failed to fetch regex issues: " + err.message);
      }
    }
    fetchData();
  }, [benchmark]);

  const handleCopy = () => {
    navigator.clipboard.writeText(regexText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6 text-gray-800">
        Unsupported Regex for {benchmark}
      </h1>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="relative bg-gray-900 text-green-200 p-4 rounded-lg shadow overflow-auto">
        <button
          className="absolute top-3 right-3 bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded-md text-sm font-semibold"
          onClick={handleCopy}
        >
          {copied ? "Copied!" : "Copy"}
        </button>
        <pre className="text-sm">
          <code>{regexText}</code>
        </pre>
      </div>
    </div>
  );
}

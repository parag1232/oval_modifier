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
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-xl mb-4 font-semibold">Unsupported Regex for {benchmark}</h1>
      {error && <p className="text-red-600">{error}</p>}
      
      <div className="relative bg-gray-900 text-green-200 p-4 rounded overflow-auto">
        <button
          className="absolute top-2 right-2 bg-gray-700 text-white px-3 py-1 rounded text-sm hover:bg-gray-600"
          onClick={handleCopy}
        >
          {copied ? "Copied!" : "Copy"}
        </button>
        <pre><code>{regexText}</code></pre>
      </div>
    </div>
  );
}

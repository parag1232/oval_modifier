import React, { useEffect, useState } from "react";
import { getBenchmarks } from "../api/api";
import { useNavigate } from "react-router-dom";
import { deleteBenchmark,downloadFullBenchmarkOval } from "../api/api";

export default function BenchmarkListPage() {
  const [benchmarks, setBenchmarks] = useState([]);
  const navigate = useNavigate();

  const fetchBenchmarks = () => {
    getBenchmarks().then(setBenchmarks);
  };
  const handleGenerateFullOval = async (benchmark) => {
  try {
    await downloadFullBenchmarkOval(benchmark);
  } catch (err) {
    alert("Failed to download: " + err.message);
  }
};

  useEffect(() => {
    fetchBenchmarks();
  }, []);

    const handleDelete = async (benchmark) => {
    if (window.confirm(`Are you sure you want to delete benchmark: ${benchmark}?`)) {
      try {
        await deleteBenchmark(benchmark);
        fetchBenchmarks();  // Refresh list after delete
      } catch (err) {
        alert("Failed to delete: " + err.message);
      }
    }
  };

   return (
    <div className="max-w-5xl mx-auto p-4">
      <h1 className="text-xl mb-4 font-semibold">Uploaded Benchmarks</h1>
      <table className="border border-gray-300">
        <thead className="bg-gray-200">
          <tr>
            <th className="px-4 py-2 border">Benchmark</th>
            <th className="px-4 py-2 border">Type</th>
            <th className="px-4 py-2 border">Total</th>
            <th className="px-4 py-2 border">Automated</th>
            <th className="px-4 py-2 border">Unsupported</th>
            <th className="px-4 py-2 border">Coverage %</th>
            <th className="px-4 py-2 border">Actions</th>
          </tr>
        </thead>
        <tbody>
          {benchmarks.map((b) => (
            <tr key={b.benchmark} className="hover:bg-gray-100">
              <td className="px-4 py-2 border">{b.benchmark}</td>
              <td className="px-4 py-2 border">{b.type}</td>
              <td className="px-4 py-2 border">{b.total_rules}</td>
              <td className="px-4 py-2 border">{b.automated_rules}</td>
              <td className="px-4 py-2 border">{b.unsupported_rules}</td>
              <td className="px-4 py-2 border">{b.coverage}%</td>
              <td className="px-4 py-2 border">
                <button className="bg-blue-500 text-white px-3 py-1 rounded mr-2" onClick={() => navigate(`/rules/${b.benchmark}`)}>
                  View
                </button>
                <button className="bg-red-500 text-white px-3 py-1 rounded mr-2" onClick={() => handleDelete(b.benchmark)}>
                  Delete
                </button>
                <button
                        className="bg-purple-500 text-white px-3 py-1 rounded"
                        onClick={() => handleGenerateFullOval(b.benchmark)}
                >
                  Generate OVAL
              </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

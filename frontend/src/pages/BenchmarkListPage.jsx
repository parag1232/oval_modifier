import React, { useEffect, useState } from "react";
import { getBenchmarks, deleteBenchmark, downloadFullBenchmarkOval } from "../api/api";
import { useNavigate } from "react-router-dom";

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
        fetchBenchmarks();
      } catch (err) {
        alert("Failed to delete: " + err.message);
      }
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6 text-gray-800">Uploaded Benchmarks</h1>

      <div className="overflow-auto border border-gray-200 rounded-lg shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">Benchmark</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">Type</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">Total</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">Automated</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">Unsupported</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">Coverage %</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {benchmarks.map((b) => (
              <tr key={b.benchmark} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm font-medium text-gray-800">{b.benchmark}</td>
                <td className="px-4 py-3 text-sm">{b.type}</td>
                <td className="px-4 py-3 text-sm">{b.total_rules}</td>
                <td className="px-4 py-3 text-sm">{b.automated_rules}</td>
                <td className="px-4 py-3 text-sm">{b.unsupported_rules}</td>
                <td className="px-4 py-3 text-sm">{b.coverage}%</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                      onClick={() => navigate(`/rules/${b.benchmark}`)}
                    >
                      View
                    </button>
                    <button
                      className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                      onClick={() => handleDelete(b.benchmark)}
                    >
                      Delete
                    </button>
                    <button
                      className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                      onClick={() => handleGenerateFullOval(b.benchmark)}
                    >
                      Generate OVAL
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

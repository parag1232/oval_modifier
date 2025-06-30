import React, { useEffect, useState } from "react";
import { getBenchmarks, deleteBenchmark, downloadFullBenchmarkOval } from "../api/api";
import { useNavigate } from "react-router-dom";

export default function BenchmarkListPage() {
  const [benchmarks, setBenchmarks] = useState([]);
  const navigate = useNavigate();

  // Modal state
  const [openModal, setOpenModal] = useState(false);
  const [remoteForm, setRemoteForm] = useState({
    benchmark_name: "",
    ip_address: "",
    username: "",
    password: "",
    os_type: "",
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const fetchBenchmarks = () => {
    getBenchmarks().then(setBenchmarks);
  };

  useEffect(() => {
    fetchBenchmarks();
  }, []);

  const handleGenerateFullOval = async (benchmark) => {
    try {
      await downloadFullBenchmarkOval(benchmark);
    } catch (err) {
      alert("Failed to download: " + err.message);
    }
  };

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

  const handleOpenRemoteModal = (benchmark) => {
    setRemoteForm({
      benchmark_name: benchmark,
      ip_address: "",
      username: "",
      password: "",
      os_type: "",
    });
    setMessage("");
    setOpenModal(true);
  };

  const handleRemoteSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    try {
      const res = await fetch("/api/remote-hosts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(remoteForm),
      });

      if (!res.ok) {
        throw new Error(await res.text());
      }

      const data = await res.json();
      setMessage(`✅ ${data.message || "Remote host added successfully."}`);
      setOpenModal(false);
    } catch (err) {
      setMessage(`❌ Failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6 text-gray-800">Uploaded Benchmarks</h1>

      <div className="overflow-auto border border-gray-200 rounded-lg shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Benchmark
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Type
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Total
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Automated
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Unsupported
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Coverage %
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {benchmarks.map((b) => (
              <tr key={b.benchmark} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm font-medium text-gray-800">
                  {b.benchmark}
                </td>
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
                    <button
                      className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded-md text-sm font-semibold"
                      onClick={() => handleOpenRemoteModal(b.benchmark)}
                    >
                      Add Remote Host
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {openModal && (
        <div className="fixed inset-0 bg-black/50 flex justify-center items-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-lg shadow-lg">
            <h2 className="text-xl font-bold mb-4 text-gray-800">
              Add Remote Host for {remoteForm.benchmark_name}
            </h2>

            <form onSubmit={handleRemoteSubmit} className="space-y-4">
              <div>
                <label className="block text-gray-700 font-medium mb-1">
                  IP Address
                </label>
                <input
                  type="text"
                  value={remoteForm.ip_address}
                  onChange={(e) =>
                    setRemoteForm({ ...remoteForm, ip_address: e.target.value })
                  }
                  className="border border-gray-300 rounded-md w-full px-3 py-2"
                  required
                />
              </div>

              <div>
                <label className="block text-gray-700 font-medium mb-1">
                  Username
                </label>
                <input
                  type="text"
                  value={remoteForm.username}
                  onChange={(e) =>
                    setRemoteForm({ ...remoteForm, username: e.target.value })
                  }
                  className="border border-gray-300 rounded-md w-full px-3 py-2"
                  required
                />
              </div>

              <div>
                <label className="block text-gray-700 font-medium mb-1">
                  Password
                </label>
                <input
                  type="password"
                  value={remoteForm.password}
                  onChange={(e) =>
                    setRemoteForm({ ...remoteForm, password: e.target.value })
                  }
                  className="border border-gray-300 rounded-md w-full px-3 py-2"
                  required
                />
              </div>

              <div>
                <label className="block text-gray-700 font-medium mb-1">
                  OS Type
                </label>
                <input
                  type="text"
                  value={remoteForm.os_type}
                  onChange={(e) =>
                    setRemoteForm({ ...remoteForm, os_type: e.target.value })
                  }
                  className="border border-gray-300 rounded-md w-full px-3 py-2"
                  placeholder="e.g. linux, windows"
                  required
                />
              </div>

              <div className="flex justify-end gap-3 mt-4">
                <button
                  type="button"
                  onClick={() => setOpenModal(false)}
                  className="bg-gray-400 hover:bg-gray-500 text-white px-4 py-2 rounded-md font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md font-semibold"
                >
                  {loading ? "Submitting..." : "Submit"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {message && (
        <p className="mt-6 text-center font-semibold text-green-700">{message}</p>
      )}
    </div>
  );
}

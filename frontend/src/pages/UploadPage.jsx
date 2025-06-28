import React, { useState } from "react";

export default function UploadPage() {
  const [benchmarkName, setBenchmarkName] = useState("");
  const [benchmarkType, setBenchmarkType] = useState("DISA");
  const [disaFile, setDisaFile] = useState(null);
  const [cisXccdfFile, setCisXccdfFile] = useState(null);
  const [cisOvalFile, setCisOvalFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    const formData = new FormData();

    formData.append("benchmark_name", benchmarkName);
    formData.append("benchmark_type", benchmarkType);

    if (benchmarkType === "DISA") {
      if (!disaFile) {
        alert("Please select DISA file");
        return;
      }
      formData.append("stig_file", disaFile);
    } else {
      if (!cisXccdfFile || !cisOvalFile) {
        alert("Please select both CIS files");
        return;
      }
      formData.append("xccdf_file", cisXccdfFile);
      formData.append("oval_file", cisOvalFile);
    }

    setUploading(true);

    try {
      const res = await fetch("/api/stig/upload", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMessage(data.message);
    } catch (err) {
      alert("Upload failed: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6 text-gray-800">Upload Benchmark</h1>

      <form
        onSubmit={handleSubmit}
        className="space-y-6 bg-white p-6 rounded-lg shadow border border-gray-200"
      >
        <div>
          <label className="block text-gray-700 font-medium mb-1">
            Benchmark Name
          </label>
          <input
            type="text"
            placeholder="e.g. RHEL9"
            value={benchmarkName}
            onChange={(e) => setBenchmarkName(e.target.value)}
            className="border border-gray-300 rounded-md w-full px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>

        <div>
          <label className="block text-gray-700 font-medium mb-1">
            Benchmark Type
          </label>
          <select
            value={benchmarkType}
            onChange={(e) => setBenchmarkType(e.target.value)}
            className="border border-gray-300 rounded-md w-full px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="DISA">DISA</option>
            <option value="CIS">CIS</option>
          </select>
        </div>

        {benchmarkType === "DISA" && (
          <div>
            <label className="block text-gray-700 font-medium mb-1">
              Upload DISA STIG XML
            </label>
            <input
              type="file"
              onChange={(e) => setDisaFile(e.target.files[0])}
              className="border border-gray-300 rounded-md w-full px-4 py-2 file:bg-gray-100 file:border file:border-gray-300 file:rounded file:px-3 file:py-1 hover:file:bg-gray-200"
            />
          </div>
        )}

        {benchmarkType === "CIS" && (
          <>
            <div>
              <label className="block text-gray-700 font-medium mb-1">
                Upload CIS XCCDF
              </label>
              <input
                type="file"
                onChange={(e) => setCisXccdfFile(e.target.files[0])}
                className="border border-gray-300 rounded-md w-full px-4 py-2 file:bg-gray-100 file:border file:border-gray-300 file:rounded file:px-3 file:py-1 hover:file:bg-gray-200"
              />
            </div>

            <div>
              <label className="block text-gray-700 font-medium mb-1">
                Upload CIS OVAL
              </label>
              <input
                type="file"
                onChange={(e) => setCisOvalFile(e.target.files[0])}
                className="border border-gray-300 rounded-md w-full px-4 py-2 file:bg-gray-100 file:border file:border-gray-300 file:rounded file:px-3 file:py-1 hover:file:bg-gray-200"
              />
            </div>
          </>
        )}

        <button
          type="submit"
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-md font-semibold disabled:opacity-50"
          disabled={uploading}
        >
          {uploading ? "Uploading..." : "Upload"}
        </button>
      </form>

      {message && (
        <p className="mt-4 text-green-600 font-medium">{message}</p>
      )}
    </div>
  );
}

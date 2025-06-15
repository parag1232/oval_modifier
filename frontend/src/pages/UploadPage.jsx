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
    <div className="max-w-md mx-auto p-4">
      <h1 className="text-xl font-semibold mb-4">Upload Benchmark</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="text"
          placeholder="Benchmark Name"
          value={benchmarkName}
          onChange={(e) => setBenchmarkName(e.target.value)}
          className="border w-full p-2"
          required
        />

        <select
          value={benchmarkType}
          onChange={(e) => setBenchmarkType(e.target.value)}
          className="border w-full p-2"
        >
          <option value="DISA">DISA</option>
          <option value="CIS">CIS</option>
        </select>

        {benchmarkType === "DISA" && (
          <div>
            <label>Upload DISA STIG XML:</label>
            <input
              type="file"
              onChange={(e) => setDisaFile(e.target.files[0])}
              className="border w-full p-2"
            />
          </div>
        )}

        {benchmarkType === "CIS" && (
          <>
            <div>
              <label>Upload CIS XCCDF:</label>
              <input
                type="file"
                onChange={(e) => setCisXccdfFile(e.target.files[0])}
                className="border w-full p-2"
              />
            </div>

            <div>
              <label>Upload CIS OVAL:</label>
              <input
                type="file"
                onChange={(e) => setCisOvalFile(e.target.files[0])}
                className="border w-full p-2"
              />
            </div>
          </>
        )}

        <button
          type="submit"
          className="bg-blue-600 text-white px-4 py-2 rounded"
          disabled={uploading}
        >
          {uploading ? "Uploading..." : "Upload"}
        </button>
      </form>

      {message && <p className="mt-4 text-green-600">{message}</p>}
    </div>
  );
}

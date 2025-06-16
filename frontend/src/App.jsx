import React from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import BenchmarkListPage from "./pages/BenchmarkListPage";
import RuleBrowserPage from "./pages/RuleBrowserPage";
import RegexIssuesPage from "./pages/RegexIssuesPage"; 

export default function App() {
  return (
    <BrowserRouter>
      <nav className="bg-gray-800 p-4 text-white flex space-x-4 mb-4">
        <Link to="/">Benchmarks</Link>
        <Link to="/upload">Upload</Link>
      </nav>
      <Routes>
        <Route path="/" element={<BenchmarkListPage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/rules/:benchmark" element={<RuleBrowserPage />} />
        <Route path="/regex-issues/:benchmark" element={<RegexIssuesPage />} />
      </Routes>
    </BrowserRouter>
  );
}

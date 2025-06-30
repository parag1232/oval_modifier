const BASE_URL = "http://localhost:8000/api"; // adjust if backend on diff port

export async function uploadBenchmark(formData) {
  const res = await fetch(`${BASE_URL}/stig/upload`, {
    method: "POST",
    body: formData,
  });
  return res.json();
}

export async function getBenchmarks() {
  const res = await fetch(`/api/benchmarks`);
  return res.json();
}

export async function getRules(benchmark) {
  const res = await fetch(`${BASE_URL}/benchmarks/${benchmark}/rules`);
  return res.json();
}

export async function getOval(benchmark, ruleId) {
  const res = await fetch(`${BASE_URL}/benchmarks/${benchmark}/rules/${ruleId}`);
  return res.json();
}

export async function deleteBenchmark(benchmark) {
  const res = await fetch(`/api/benchmarks/${benchmark}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

export async function deleteRules(benchmark, ruleIds) {
  const res = await fetch(`/api/benchmarks/${benchmark}/rules`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rule_ids: ruleIds }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function downloadMergedOval(benchmark, ruleIds) {
  const res = await fetch(`/api/benchmarks/${benchmark}/generate-ovals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rule_ids: ruleIds }),
  });
  if (!res.ok) throw new Error(await res.text());

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${benchmark}_merged_oval.xml`;
  link.click();
  window.URL.revokeObjectURL(url);
}

export async function downloadSingleRuleOval(benchmark, ruleId) {
  const res = await fetch(`/api/benchmarks/${benchmark}/rules/${ruleId}/oval`);
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${ruleId}.xml`;
  link.click();
  window.URL.revokeObjectURL(url);
}

export async function downloadFullBenchmarkOval(benchmark) {
  const res = await fetch(`/api/benchmarks/${benchmark}/generate-full-oval`);
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${benchmark}_full_oval.xml`;
  link.click();
  window.URL.revokeObjectURL(url);
}

export async function getRegexIssues(benchmark) {
  const res = await fetch(`${BASE_URL}/benchmarks/${benchmark}/regex-issues`);
  if (!res.ok) throw new Error(await res.text());
  const text = await res.text();
  return text;
}


export async function saveOval(benchmark, ruleId, ovalContent) {
  const res = await fetch(`${BASE_URL}/benchmarks/${benchmark}/rules/${ruleId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ oval: ovalContent }),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

export async function getHostState(benchmark, ruleId) {
  const res = await fetch(`${BASE_URL}/rules/${ruleId}/hoststate`);
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.text();
}


export async function addRemoteHost(payload) {
  const res = await fetch("/api/remote-hosts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getRemoteHosts(benchmark) {
  const res = await fetch(`/api/benchmarks/${benchmark}/remote-hosts`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
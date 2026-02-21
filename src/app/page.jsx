"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileCode2,
  FileText,
  FileType,
  Loader2,
  Upload,
  Zap,
} from "lucide-react";

const CONFIGURED_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "";
const API_BASE = CONFIGURED_API_BASE || (process.env.NODE_ENV !== "production" ? "http://127.0.0.1:8000" : "");

function renderMarkdown(md) {
  if (!md) return "";
  return md
    .replace(/^###\s(.+)$/gm, '<h3 class="text-base font-semibold text-slate-800 mt-5 mb-1">$1</h3>')
    .replace(/^##\s(.+)$/gm, '<h2 class="text-lg font-bold text-slate-900 mt-6 mb-2 border-b border-slate-200 pb-1">$1</h2>')
    .replace(/^#\s(.+)$/gm, '<h1 class="text-xl font-extrabold text-slate-900 mt-6 mb-3">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-slate-900">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em class="italic text-slate-700">$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-slate-100 text-indigo-700 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>')
    .replace(/^[-*]\s(.+)$/gm, '<li class="ml-4 list-disc text-slate-700 leading-relaxed">$1</li>')
    .replace(/^(\d+)\.\s(.+)$/gm, '<li class="ml-4 list-decimal text-slate-700 leading-relaxed">$2</li>')
    .replace(/---/g, '<hr class="border-slate-200 my-4" />')
    .replace(/^(?!<h|<l|<hr)(.+)$/gm, (m) =>
      m.trim() ? `<p class="text-slate-700 leading-relaxed mb-2">${m}</p>` : "",
    );
}

function normalizeApiError(err, apiBase) {
  const raw = err instanceof Error ? err.message : "Unknown error";
  if (!apiBase) {
    return "Backend URL is missing. Set NEXT_PUBLIC_API_BASE_URL in Vercel project settings and redeploy.";
  }
  if (raw.includes("Failed to fetch") || raw.includes("NetworkError") || raw.includes("Load failed")) {
    return `Cannot reach backend at ${apiBase}. Confirm backend is deployed and CORS/network access is allowed.`;
  }
  return raw;
}

function DropZone({ label, accept, file, onFile, onClear, icon: Icon }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) onFile(dropped);
    },
    [onFile],
  );

  return (
    <div
      onDrop={onDrop}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onClick={() => !file && inputRef.current?.click()}
      className={`relative border-2 border-dashed rounded-xl p-5 transition-all cursor-pointer ${
        dragging
          ? "border-indigo-500 bg-indigo-50"
          : file
            ? "border-indigo-300 bg-indigo-50/30"
            : "border-slate-300 hover:border-indigo-400"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => e.target.files[0] && onFile(e.target.files[0])}
      />

      {file ? (
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800 truncate">{file.name}</p>
            <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onClear();
            }}
            className="text-xs text-slate-500 hover:text-slate-700"
          >
            Clear
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <Icon className="w-5 h-5 text-indigo-500" />
          <div>
            <p className="text-sm font-semibold text-slate-700">{label}</p>
            <p className="text-xs text-slate-400">Drop file or click to browse ({accept})</p>
          </div>
        </div>
      )}
    </div>
  );
}

function PreviewPane({ title, content, isMarkdown, placeholder }) {
  return (
    <div className="flex-1 border border-slate-200 rounded-xl overflow-hidden bg-white shadow-sm min-h-[320px]">
      <div className="px-4 py-2.5 text-xs font-semibold uppercase tracking-widest text-slate-600 bg-slate-50 border-b border-slate-200">
        {title}
      </div>
      <div className="p-4 h-[320px] overflow-y-auto">
        {content ? (
          isMarkdown ? (
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
          ) : (
            <pre className="text-xs whitespace-pre-wrap text-slate-700 font-mono">{content}</pre>
          )
        ) : (
          <div className="h-full flex items-center justify-center text-sm text-slate-400">{placeholder}</div>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const [templateFile, setTemplateFile] = useState(null);
  const [sourceFile, setSourceFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [apiStatus, setApiStatus] = useState(API_BASE ? "checking" : "missing");

  const [sourceMarkdown, setSourceMarkdown] = useState("");
  const [reconstructedMarkdown, setReconstructedMarkdown] = useState("");
  const [extractedJson, setExtractedJson] = useState(null);

  useEffect(() => {
    if (!API_BASE) return;

    let cancelled = false;
    const checkHealth = async () => {
      setApiStatus("checking");
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        if (!cancelled) {
          setApiStatus(res.ok ? "ok" : "down");
        }
      } catch {
        if (!cancelled) {
          setApiStatus("down");
        }
      }
    };

    checkHealth();
    return () => {
      cancelled = true;
    };
  }, []);

  const canProcess =
    templateFile &&
    sourceFile &&
    status !== "uploading" &&
    status !== "processing" &&
    apiStatus === "ok";

  const processDocument = async () => {
    if (!canProcess) return;

    setStatus("uploading");
    setProgress(0);
    setErrorMessage("");
    setSourceMarkdown("");
    setReconstructedMarkdown("");
    setExtractedJson(null);

    try {
      for (let i = 0; i <= 25; i += 5) {
        await new Promise((r) => setTimeout(r, 60));
        setProgress(i);
      }

      setStatus("processing");
      setProgress(40);

      const formData = new FormData();
      formData.append("source_file", sourceFile);
      formData.append("template_file", templateFile);

      const res = await fetch(`${API_BASE}/api/format`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `Request failed with status ${res.status}`);
      }

      const data = await res.json();
      setProgress(100);
      setSourceMarkdown(data.source_markdown || "");
      setReconstructedMarkdown(data.reconstructed_markdown || "");
      setExtractedJson(data.extracted_json || null);
      setStatus("done");
    } catch (err) {
      setStatus("error");
      setErrorMessage(normalizeApiError(err, API_BASE));
    }
  };

  const downloadText = (filename, content, mime) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const exportMarkdown = () => {
    if (!reconstructedMarkdown) return;
    downloadText("reconstructed.md", reconstructedMarkdown, "text/markdown;charset=utf-8");
  };

  const exportJson = () => {
    if (!extractedJson) return;
    downloadText("result.json", JSON.stringify(extractedJson, null, 2), "application/json;charset=utf-8");
  };

  const exportWord = async () => {
    if (!reconstructedMarkdown) return;

    try {
      const res = await fetch(`${API_BASE}/api/export/word`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          markdown_text: reconstructedMarkdown,
          extracted_json: extractedJson,
        }),
      });

      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `Export failed with status ${res.status}`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "final.docx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setStatus("error");
      setErrorMessage(normalizeApiError(err, API_BASE));
    }
  };

  const statusLabel = {
    idle: "Ready",
    uploading: "Uploading...",
    processing: "Processing...",
    done: "Complete",
    error: "Error",
  }[status];

  const apiStatusLabel = {
    missing: "Backend URL not configured",
    checking: "Checking backend...",
    ok: "Backend reachable",
    down: "Backend unreachable",
  }[apiStatus];

  return (
    <div className="min-h-screen bg-slate-50 p-6 md:p-8 space-y-6">
      <header className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <h1 className="text-lg font-bold text-slate-900">Document Formatter Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Backend: {API_BASE || "[unset]"}</p>
        <p className={`text-xs mt-1 ${apiStatus === "ok" ? "text-emerald-600" : "text-amber-600"}`}>
          {apiStatusLabel}
        </p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DropZone
          label="Upload Template"
          accept=".pdf,.docx"
          file={templateFile}
          onFile={setTemplateFile}
          onClear={() => setTemplateFile(null)}
          icon={FileCode2}
        />
        <DropZone
          label="Upload Source"
          accept=".pdf,.docx,.txt"
          file={sourceFile}
          onFile={setSourceFile}
          onClear={() => setSourceFile(null)}
          icon={FileType}
        />
      </section>

      <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center gap-4">
          <button
            onClick={processDocument}
            disabled={!canProcess}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold ${
              canProcess
                ? "bg-indigo-600 text-white hover:bg-indigo-700"
                : "bg-slate-100 text-slate-400 cursor-not-allowed"
            }`}
          >
            {status === "uploading" || status === "processing" ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : status === "done" ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            Process Document
          </button>

          <div className="flex-1">
            <p className="text-sm text-slate-600">Status: {statusLabel}</p>
            <div className="w-full mt-1 h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>

        {status === "error" && (
          <div className="mt-3 text-sm text-red-600 inline-flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {errorMessage || "Processing failed."}
          </div>
        )}
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PreviewPane
          title="Source Markdown"
          content={sourceMarkdown}
          isMarkdown={false}
          placeholder="Source markdown will appear after processing"
        />
        <PreviewPane
          title="Reconstructed Markdown"
          content={reconstructedMarkdown}
          isMarkdown={true}
          placeholder="Reconstructed markdown will appear after processing"
        />
      </section>

      {status === "done" && (
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <p className="text-sm font-semibold text-slate-800 mb-3">Export</p>
          <div className="flex flex-wrap gap-2">
            <button onClick={exportMarkdown} className="px-3 py-2 text-sm rounded-lg border border-slate-300 hover:border-indigo-400">
              <FileText className="w-4 h-4 inline mr-1" /> Markdown
            </button>
            <button onClick={exportJson} className="px-3 py-2 text-sm rounded-lg border border-slate-300 hover:border-indigo-400">
              <Upload className="w-4 h-4 inline mr-1" /> JSON
            </button>
            <button onClick={exportWord} className="px-3 py-2 text-sm rounded-lg border border-slate-300 hover:border-indigo-400">
              <FileCode2 className="w-4 h-4 inline mr-1" /> Word (.docx)
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

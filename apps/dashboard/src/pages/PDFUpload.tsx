import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { privateAxios } from '../utils/axios';
import { ArrowLeft, UploadCloud, File, AlertCircle, CheckCircle } from 'lucide-react';

const PDFUpload = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const handleUpload = async () => {
    if (!file || !name.trim()) return;

    setUploading(true);
    setError('');
    setResult(null);

    const form = new FormData();
    form.append('file', file);
    form.append('name', name.trim());

    try {
      const res = await privateAxios.post('/dashboard/sources/pdf/upload', form, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setResult(res.data);
      setFile(null);
      setName('');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-8 text-slate-100 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button 
          onClick={() => navigate('/sources')}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800 transition-colors cursor-pointer"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Upload PDF Source</h2>
          <p className="text-slate-400 text-sm mt-1">Add indexable knowledge from local PDF documents.</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Upload Form Card */}
        <div className="md:col-span-2 bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg space-y-6">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
              Source Name
            </label>
            <input
              placeholder="e.g. Employee Handbook 2026"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-xl border border-slate-850 bg-slate-950 px-4 py-3 text-slate-200 placeholder-slate-600 focus:border-violet-600 focus:outline-none transition-all duration-200 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
              PDF Document File
            </label>
            
            {/* Custom drag-n-drop looking area */}
            <div className="relative border-2 border-dashed border-slate-800 hover:border-violet-500/60 rounded-2xl p-8 flex flex-col items-center justify-center bg-slate-950/40 hover:bg-slate-950/80 transition-colors">
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    setFile(e.target.files[0]);
                  }
                }}
                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              />
              <UploadCloud size={36} className="text-slate-600 mb-3" />
              <p className="text-sm font-semibold text-slate-300">Click to choose or drag a PDF here</p>
              <p className="text-xs text-slate-500 mt-1">Accepts text-based PDF files</p>
            </div>

            {file && (
              <div className="mt-3 flex items-center gap-2.5 bg-violet-950/40 px-4 py-3 rounded-xl border border-violet-900/30 text-violet-400">
                <File size={18} className="flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold truncate">{file.name}</p>
                  <p className="text-xxs text-violet-500 font-semibold uppercase mt-0.5">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={handleUpload}
            disabled={!file || !name.trim() || uploading}
            className="w-full rounded-xl bg-violet-600 py-3.5 text-sm font-semibold text-white shadow-md shadow-violet-900/30 hover:bg-violet-700 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? 'Processing & Indexing Document...' : 'Upload & Start Indexing'}
          </button>

          {error && (
            <div className="flex items-start gap-3 rounded-xl bg-rose-950/40 p-4 text-sm text-rose-350 border border-rose-900/60">
              <AlertCircle size={18} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="flex items-start gap-4 rounded-xl bg-teal-950/30 p-5 text-slate-300 border border-teal-900/30 animate-slideUp">
              <CheckCircle size={20} className="text-teal-400 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-white">PDF Uploaded Successfully</h4>
                <p className="text-xs text-slate-400">
                  Source name: <strong className="text-slate-300">{result.name}</strong> · Status: <span className="font-semibold text-teal-400">{result.status}</span>
                </p>
                <p className="text-xs text-slate-500">
                  We are now parsing and embedding the document in the background. Check back in a few minutes.
                </p>
                <button
                  onClick={() => navigate('/sources')}
                  className="mt-3 px-4 py-2 border border-slate-800 bg-slate-950 text-xs font-semibold text-slate-400 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
                >
                  Return to Sources
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Side Tip Info Card */}
        <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800/80 shadow-lg h-fit space-y-4">
          <h3 className="text-sm font-bold text-white">Upload Guidelines</h3>
          <ul className="text-xs text-slate-400 space-y-3 leading-relaxed">
            <li className="flex items-start gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-violet-500 mt-1.5 flex-shrink-0" />
              <span>Use text-based PDFs instead of scanned image PDFs to ensure optimal parsing and text extraction.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-violet-500 mt-1.5 flex-shrink-0" />
              <span>Ensure PDF contains structured headings and sections; this helps index the information in cohesive vector chunks.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-violet-500 mt-1.5 flex-shrink-0" />
              <span>Maximum file size limit is 10 MB per PDF document.</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default PDFUpload;

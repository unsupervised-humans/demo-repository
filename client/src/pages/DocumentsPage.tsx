import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useApp } from '../context';
import {
  DOC_HINTS,
  DOC_LABELS,
  MULTI_DOC_TYPES,
  type DocumentRecord,
  type DocumentType,
  type DocSuggestion,
} from '../types';

const STATUS_STYLE: Record<string, string> = {
  missing: 'bg-ink/5 text-ink/50',
  uploaded: 'bg-leaf/15 text-leaf',
  verified: 'bg-ok/15 text-ok',
  needs_attention: 'bg-amber/25 text-ink',
};

const SEVERITY_STYLE: Record<DocSuggestion['severity'], string> = {
  required: 'border-danger/30 bg-danger/5',
  recommended: 'border-amber/40 bg-amber/10',
  optional: 'border-forest/15 bg-white/70',
};

const DEFAULT_REQUIRED: DocumentType[] = [
  'aadhaar',
  'pan',
  'salary_slip',
  'bank_statement',
];
const DEFAULT_OPTIONAL: DocumentType[] = [
  'employment_letter',
  'form_16',
  'cancelled_cheque',
  'address_proof',
  'utility_bill',
];

export function DocumentsPage() {
  const { session, setDocuments, setProfile, refresh } = useApp();
  const [uploadingType, setUploadingType] = useState<DocumentType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<DocSuggestion[]>([]);
  const [required, setRequired] = useState<DocumentType[]>(DEFAULT_REQUIRED);
  const [optional, setOptional] = useState<DocumentType[]>(DEFAULT_OPTIONAL);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [dragOverType, setDragOverType] = useState<DocumentType | null>(null);
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const docs = session?.documents ?? [];

  const loadMeta = useCallback(async () => {
    try {
      const res = await api.getDocuments();
      setDocuments(res.documents);
      setRequired(res.requiredDocs?.length ? res.requiredDocs : DEFAULT_REQUIRED);
      setOptional(res.optionalDocs?.length ? res.optionalDocs : DEFAULT_OPTIONAL);
      setSuggestions(res.suggestions || []);
    } catch {
      /* session may still be enough */
    }
  }, [setDocuments]);

  useEffect(() => {
    void loadMeta();
  }, [loadMeta, session?.sessionId]);

  const progress = useMemo(() => {
    const done = required.filter((t) => docs.some((d) => d.type === t)).length;
    return { done, total: required.length };
  }, [required, docs]);

  const upload = useCallback(
    async (
      files: FileList | File[],
      opts: {
        expectedType: DocumentType;
        replaceId?: string;
        replaceType?: boolean;
      }
    ) => {
      const list = Array.from(files);
      if (!list.length) return;
      setUploadingType(opts.expectedType);
      setError(null);
      try {
        let lastSuggestions: DocSuggestion[] = [];
        for (const file of list) {
          const res = await api.uploadDocument(file, {
            expectedType: opts.expectedType,
            replaceId: opts.replaceId,
            replaceType: opts.replaceType ?? !MULTI_DOC_TYPES.includes(opts.expectedType),
          });
          setDocuments(res.documents);
          if (res.profile) setProfile(res.profile);
          lastSuggestions = res.suggestions || [];
        }
        setSuggestions(lastSuggestions);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setUploadingType(null);
      }
    },
    [setDocuments, setProfile]
  );

  const removeDoc = async (id: string) => {
    try {
      const res = await api.deleteDocument(id);
      setDocuments(res.documents);
      setSuggestions(res.suggestions || []);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const clearAll = async () => {
    try {
      const res = await api.clearDocuments();
      setDocuments(res.documents);
      setSuggestions(res.suggestions || []);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const triggerUpload = (key: string) => {
    fileRefs.current[key]?.click();
  };

  const docsFor = (type: DocumentType) => docs.filter((d) => d.type === type);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-forest">
            Your documents
          </h1>
          <p className="text-ink/60 mt-1 text-sm max-w-xl">
            Upload each document yourself — Aadhaar, PAN, salary slips, bank
            statement, and more. Nothing is locked to the demo; replace any file
            anytime.
          </p>
          <p className="text-sm text-forest mt-2 font-medium">
            Checklist progress: {progress.done}/{progress.total} required
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void clearAll()}
            className="border border-forest/25 text-forest px-3 py-2 rounded-lg text-sm hover:bg-foam"
          >
            Clear all docs
          </button>
          <Link
            to="/eligibility"
            className="bg-forest text-foam px-4 py-2 rounded-lg text-sm font-medium hover:bg-leaf transition-colors"
          >
            Run eligibility →
          </Link>
        </div>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {/* Info needed panel */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-forest">
          What we still need from you
        </h2>
        {suggestions.length === 0 ? (
          <p className="text-sm text-ok bg-ok/10 border border-ok/20 rounded-xl px-4 py-3">
            Looking good — required docs are in place. You can still add optional
            boosters below.
          </p>
        ) : (
          <ul className="space-y-2">
            {suggestions.slice(0, 8).map((s) => (
              <li
                key={s.id}
                className={`rounded-xl border px-4 py-3 flex flex-wrap gap-3 items-start justify-between ${SEVERITY_STYLE[s.severity]}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">
                    <span className="uppercase text-[10px] tracking-wide opacity-60 mr-2">
                      {s.severity}
                    </span>
                    {s.title}
                  </p>
                  <p className="text-sm text-ink/65 mt-0.5">{s.detail}</p>
                </div>
                {s.relatedDocType && (
                  <button
                    type="button"
                    onClick={() => triggerUpload(`req-${s.relatedDocType}`)}
                    className="shrink-0 text-xs font-medium bg-forest text-foam px-3 py-1.5 rounded-lg"
                  >
                    {s.action === 'add_more' ? 'Add file' : 'Upload'}
                  </button>
                )}
                {s.action === 'update_profile' && (
                  <Link
                    to="/"
                    className="shrink-0 text-xs font-medium border border-forest/30 px-3 py-1.5 rounded-lg"
                  >
                    Edit profile
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Required docs with per-type upload */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-forest">
          Required uploads
        </h2>
        <p className="text-sm text-ink/55">
          Use each row’s <strong>Upload</strong> button for that exact document
          type. Salary slips support multiple months.
        </p>
        <ul className="space-y-3">
          {required.map((type) => (
            <DocSlot
              key={type}
              type={type}
              required
              files={docsFor(type)}
              uploading={uploadingType === type}
              dragOver={dragOverType === type}
              expandedId={expandedId}
              inputRef={(el) => {
                fileRefs.current[`req-${type}`] = el;
              }}
              onExpand={setExpandedId}
              onDelete={(id) => void removeDoc(id)}
              onBrowse={() => triggerUpload(`req-${type}`)}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOverType(type);
              }}
              onDragLeave={() => setDragOverType(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOverType(null);
                if (e.dataTransfer.files.length) {
                  void upload(e.dataTransfer.files, {
                    expectedType: type,
                    replaceType: !MULTI_DOC_TYPES.includes(type),
                  });
                }
              }}
              onFileChange={(files) => {
                if (!files) return;
                void upload(files, {
                  expectedType: type,
                  replaceType: !MULTI_DOC_TYPES.includes(type),
                });
              }}
            />
          ))}
        </ul>
      </section>

      {/* Optional */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-forest">
          Optional — strengthens your file
        </h2>
        <ul className="space-y-3">
          {optional.map((type) => (
            <DocSlot
              key={type}
              type={type}
              files={docsFor(type)}
              uploading={uploadingType === type}
              dragOver={dragOverType === type}
              expandedId={expandedId}
              inputRef={(el) => {
                fileRefs.current[`opt-${type}`] = el;
              }}
              onExpand={setExpandedId}
              onDelete={(id) => void removeDoc(id)}
              onBrowse={() => triggerUpload(`opt-${type}`)}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOverType(type);
              }}
              onDragLeave={() => setDragOverType(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOverType(null);
                if (e.dataTransfer.files.length) {
                  void upload(e.dataTransfer.files, {
                    expectedType: type,
                    replaceType: true,
                  });
                }
              }}
              onFileChange={(files) => {
                if (!files) return;
                void upload(files, {
                  expectedType: type,
                  replaceType: true,
                });
              }}
            />
          ))}
        </ul>
      </section>

      <p className="text-xs text-ink/45">
        Sample PDFs for practice live in{' '}
        <code className="bg-foam px-1 rounded">server/sample-docs/</code> (salary
        slips, 6-month bank statement). Generate Aadhaar/PAN samples with the
        script if needed. Your real files stay on this machine’s upload folder —
        LoanReady never logs into your bank.
      </p>

      <button
        type="button"
        className="hidden"
        onClick={() => void refresh()}
        aria-hidden
      />
    </div>
  );
}

function DocSlot({
  type,
  required,
  files,
  uploading,
  dragOver,
  expandedId,
  inputRef,
  onExpand,
  onDelete,
  onBrowse,
  onDragOver,
  onDragLeave,
  onDrop,
  onFileChange,
}: {
  type: DocumentType;
  required?: boolean;
  files: DocumentRecord[];
  uploading: boolean;
  dragOver: boolean;
  expandedId: string | null;
  inputRef: (el: HTMLInputElement | null) => void;
  onExpand: (id: string | null) => void;
  onDelete: (id: string) => void;
  onBrowse: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent) => void;
  onFileChange: (files: FileList | null) => void;
}) {
  const status =
    files.length === 0
      ? 'missing'
      : files.some((f) => f.status === 'needs_attention')
        ? 'needs_attention'
        : files[0].status;
  const multi = MULTI_DOC_TYPES.includes(type);

  return (
    <li
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={`bg-white/80 border rounded-xl px-4 py-4 transition-colors ${
        dragOver ? 'border-leaf bg-foam/50' : 'border-forest/10'
      }`}
    >
      <div className="flex flex-wrap gap-3 items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{DOC_LABELS[type]}</p>
            {required && (
              <span className="text-[10px] uppercase tracking-wide text-clay">
                Required
              </span>
            )}
            {multi && (
              <span className="text-[10px] uppercase tracking-wide text-leaf">
                Multi-file OK
              </span>
            )}
          </div>
          <p className="text-xs text-ink/50 mt-1">{DOC_HINTS[type]}</p>

          {files.length === 0 ? (
            <p className="text-xs text-ink/40 mt-2">Not uploaded yet — drop a file here or click Upload</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {files.map((doc) => (
                <li key={doc.id} className="text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-ink/80">
                      {doc.originalName}
                    </span>
                    {doc.isDemo && (
                      <span className="text-[10px] bg-amber/20 px-1.5 py-0.5 rounded">
                        DEMO — replace me
                      </span>
                    )}
                    <button
                      type="button"
                      className="text-xs text-leaf underline"
                      onClick={() =>
                        onExpand(expandedId === doc.id ? null : doc.id)
                      }
                    >
                      {expandedId === doc.id ? 'Hide details' : 'View extracted'}
                    </button>
                    <button
                      type="button"
                      className="text-xs text-danger underline"
                      onClick={() => onDelete(doc.id)}
                    >
                      Remove
                    </button>
                  </div>
                  {doc.issues?.map((issue) => (
                    <p key={issue} className="text-sm text-clay mt-1">
                      ⚠ {issue}
                    </p>
                  ))}
                  {doc.infoRequests?.map((ask) => (
                    <p key={ask} className="text-sm text-forest/80 mt-1">
                      → {ask}
                    </p>
                  ))}
                  {expandedId === doc.id && (
                    <pre className="mt-2 text-xs bg-sand border border-forest/10 rounded-lg p-3 overflow-x-auto">
                      {JSON.stringify(doc.extractedFields, null, 2)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-col items-end gap-2">
          <span
            className={`text-xs font-medium px-2.5 py-1 rounded-full capitalize ${STATUS_STYLE[status]}`}
          >
            {status.replace('_', ' ')}
          </span>
          <button
            type="button"
            onClick={onBrowse}
            disabled={uploading}
            className="bg-leaf text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-forest disabled:opacity-50"
          >
            {uploading
              ? 'Processing…'
              : files.length
                ? multi
                  ? 'Add another'
                  : 'Replace'
                : 'Upload'}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,image/*,.txt"
            multiple={multi}
            className="hidden"
            onChange={(e) => {
              onFileChange(e.target.files);
              e.target.value = '';
            }}
          />
        </div>
      </div>
    </li>
  );
}

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { privateAxios } from '../utils/axios';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowLeft,
  Bus,
  ChevronRight,
  CircleDollarSign,
  GraduationCap,
  Loader2,
  Search,
  UserRound,
  WalletCards,
} from 'lucide-react';

interface StudentListItem {
  student_id: number;
  school_id: number;
  admission_no: string;
  student_name: string;
  class_id: number;
  section_id: number;
}

interface StudentRecord {
  student: Record<string, string | number>;
  school: { school_name?: string };
  class: { class_name?: string };
  section: { section_name?: string };
  fees: Array<Record<string, string | number>>;
  payments: Array<Record<string, string | number>>;
  transport: Record<string, any>;
  hostel: Record<string, string | number>;
  summary: {
    net_assigned: string;
    total_paid: string;
    agent_due: string;
    due_fee_records: number;
    calculation_basis: string;
    statuses: string[];
  };
}

const money = (value: string | number | undefined) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(value || 0));

const statusClass = (status: unknown) => {
  const value = String(status || '').toLowerCase();
  if (value === 'paid' || value === 'active') return 'bg-emerald-400/10 text-emerald-300 border-emerald-400/20';
  if (value === 'partial') return 'bg-amber-400/10 text-amber-300 border-amber-400/20';
  if (value === 'pending') return 'bg-rose-400/10 text-rose-300 border-rose-400/20';
  return 'bg-slate-800 text-slate-300 border-slate-700';
};

const Value = ({ label, value }: { label: string; value?: string | number }) => (
  <div className="flex items-start justify-between gap-4 border-b border-slate-800/80 py-2.5 last:border-0">
    <dt className="text-xs text-slate-500">{label}</dt>
    <dd className="max-w-[65%] break-words text-right text-sm font-medium text-slate-200">{value || 'Not recorded'}</dd>
  </div>
);

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="border border-slate-800 bg-slate-900">
    <h3 className="border-b border-slate-800 px-4 py-3 text-xs font-bold uppercase tracking-wider text-slate-400">{title}</h3>
    <div className="p-4">{children}</div>
  </section>
);

const SchoolRecords = () => {
  const [query, setQuery] = useState('');
  const [students, setStudents] = useState<StudentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingRecord, setLoadingRecord] = useState(false);
  const [record, setRecord] = useState<StudentRecord | null>(null);
  const [error, setError] = useState('');
  const [chatDue, setChatDue] = useState('');

  const search = useCallback(async (searchQuery: string) => {
    setLoadingList(true);
    setError('');
    try {
      const response = await privateAxios.get('/dashboard/school/students', { params: { query: searchQuery } });
      setStudents(response.data.items);
      setTotal(response.data.total_count);
    } catch {
      setError('Could not load student records. Please try again.');
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => { search(''); }, [search]);

  const selectStudent = async (studentId: number) => {
    setLoadingRecord(true);
    setError('');
    setChatDue('');
    try {
      const response = await privateAxios.get(`/dashboard/school/students/${studentId}`);
      setRecord(response.data);
    } catch {
      setError('Could not load this student record.');
    } finally {
      setLoadingRecord(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setRecord(null);
    search(query);
  };

  if (record) {
    const student = record.student;
    const initials = String(student.student_name || '?').split(' ').map(word => word[0]).slice(0, 2).join('');
    const enteredDue = Number(chatDue.replace(/[^0-9.]/g, ''));
    const dueMatches = chatDue.trim() !== '' && Number.isFinite(enteredDue) && Math.abs(enteredDue - Number(record.summary.agent_due)) < 0.005;
    return (
      <div className="space-y-6 text-slate-100 animate-fadeIn">
        <button onClick={() => setRecord(null)} className="inline-flex items-center gap-2 text-sm font-medium text-slate-400 transition-colors hover:text-violet-300">
          <ArrowLeft size={16} /> Back to student search
        </button>

        <div className="border border-slate-800 bg-slate-900 p-5 sm:flex sm:items-center sm:justify-between sm:gap-6">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center bg-violet-600 text-lg font-bold text-white">{initials}</div>
            <div>
              <p className="text-xl font-bold text-white">{String(student.student_name)}</p>
              <p className="mt-1 text-sm text-slate-400">Admission no. <span className="font-mono text-slate-200">{String(student.admission_no)}</span></p>
              <p className="mt-1 text-sm text-slate-400">{record.school.school_name || 'School'} · Class {record.class.class_name || student.class_id} · Section {record.section.section_name || student.section_id}</p>
            </div>
          </div>
          <div className="mt-4 border-l-2 border-rose-400 pl-4 sm:mt-0">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Chat-verifiable due</p>
            <p className="mt-1 font-mono text-2xl font-bold text-rose-300">{money(record.summary.agent_due)}</p>
            <p className="mt-1 text-xs text-slate-500">Pending + Partial fee records only</p>
          </div>
        </div>

        <div className="border border-slate-800 bg-slate-900 p-4 sm:flex sm:items-center sm:justify-between sm:gap-5">
          <div>
            <p className="text-sm font-semibold text-slate-200">Check a chat due-fee answer</p>
            <p className="mt-1 text-xs text-slate-500">Enter only the amount the chat stated for this student.</p>
          </div>
          <div className="mt-3 flex items-center gap-3 sm:mt-0">
            <input value={chatDue} onChange={event => setChatDue(event.target.value)} inputMode="decimal" placeholder="e.g. 9000" className="h-10 w-36 border border-slate-700 bg-slate-950 px-3 font-mono text-sm text-slate-100 outline-none focus:border-violet-500" />
            {chatDue.trim() !== '' && <span className={`border px-3 py-2 text-xs font-bold ${dueMatches ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-rose-400/30 bg-rose-400/10 text-rose-300'}`}>{dueMatches ? 'Matches report' : `Mismatch: ${money(record.summary.agent_due)}`}</span>}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          {([
            { label: 'Net assigned fees', value: money(record.summary.net_assigned), icon: CircleDollarSign, color: 'text-violet-300' },
            { label: 'Payments recorded', value: money(record.summary.total_paid), icon: WalletCards, color: 'text-emerald-300' },
            { label: 'Due fee records', value: String(record.summary.due_fee_records), icon: GraduationCap, color: 'text-amber-300' },
          ] as Array<{ label: string; value: string; icon: LucideIcon; color: string }>).map(({ label, value, icon: StatIcon, color }) => {
            return <div key={String(label)} className="border border-slate-800 bg-slate-900 p-4">
              <div className="flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p><StatIcon size={17} className={color} /></div>
              <p className="mt-3 font-mono text-xl font-bold text-slate-100">{value}</p>
            </div>;
          })}
        </div>

        <p className="border-l-2 border-violet-400 bg-violet-950/20 px-4 py-3 text-sm text-slate-300">The due figure above uses the same School Agent calculation: {record.summary.calculation_basis}</p>

        <div className="grid gap-4 lg:grid-cols-3">
          <Section title="Student details">
            <dl>
              <Value label="Father" value={student.father_name} /><Value label="Mother" value={student.mother_name} />
              <Value label="Gender" value={student.gender} /><Value label="Category" value={student.category} />
              <Value label="Blood group" value={student.blood_group} /><Value label="Address" value={student.address} />
            </dl>
          </Section>
          <Section title="Transport">
            {record.transport.transport_id ? <dl>
              <Value label="Route" value={record.transport.route?.route_name} /><Value label="Stop" value={record.transport.stop?.stop_name} />
              <Value label="Vehicle" value={record.transport.vehicle_no} /><Value label="Status" value={record.transport.transport_status} />
            </dl> : <p className="text-sm text-slate-500">No transport assignment.</p>}
          </Section>
          <Section title="Hostel">
            {record.hostel.hostel_id ? <dl>
              <Value label="Hostel" value={record.hostel.hostel_name} /><Value label="Room" value={record.hostel.room_no} />
              <Value label="Bed" value={record.hostel.bed_no} /><Value label="Status" value={record.hostel.hostel_status} />
            </dl> : <p className="text-sm text-slate-500">No hostel assignment.</p>}
          </Section>
        </div>

        <Section title="Applied fees">
          {record.fees.length ? <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="border-b border-slate-800 text-xs uppercase tracking-wider text-slate-500"><tr><th className="pb-3 font-semibold">Fee head</th><th className="pb-3 font-semibold">Assigned</th><th className="pb-3 font-semibold">Concession</th><th className="pb-3 font-semibold">Net</th><th className="pb-3 font-semibold">Due date</th><th className="pb-3 font-semibold">Status</th></tr></thead><tbody>{record.fees.map(fee => <tr key={String(fee.applied_fee_id)} className="border-b border-slate-800/70 last:border-0"><td className="py-3 text-slate-200">{String(fee.fee_head)}</td><td className="py-3 font-mono text-slate-300">{money(fee.amount)}</td><td className="py-3 font-mono text-slate-300">{money(fee.concession)}</td><td className="py-3 font-mono font-semibold text-white">{money(Number(fee.amount || 0) - Number(fee.concession || 0))}</td><td className="py-3 text-slate-400">{String(fee.due_date || '-')}</td><td className="py-3"><span className={`border px-2 py-1 text-xs font-semibold ${statusClass(fee.status)}`}>{String(fee.status)}</span></td></tr>)}</tbody></table></div> : <p className="text-sm text-slate-500">No applied fee records.</p>}
        </Section>

        <Section title="Payments">
          {record.payments.length ? <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><thead className="border-b border-slate-800 text-xs uppercase tracking-wider text-slate-500"><tr><th className="pb-3 font-semibold">Receipt</th><th className="pb-3 font-semibold">Paid amount</th><th className="pb-3 font-semibold">Mode</th><th className="pb-3 font-semibold">Payment date</th><th className="pb-3 font-semibold">Balance</th></tr></thead><tbody>{record.payments.map(payment => <tr key={String(payment.payment_id)} className="border-b border-slate-800/70 last:border-0"><td className="py-3 font-mono text-violet-300">{String(payment.receipt_no || '-')}</td><td className="py-3 font-mono text-slate-200">{money(payment.paid_amount)}</td><td className="py-3 text-slate-300">{String(payment.payment_mode || '-')}</td><td className="py-3 text-slate-400">{String(payment.payment_date || '-')}</td><td className="py-3 font-mono text-slate-300">{money(payment.balance)}</td></tr>)}</tbody></table></div> : <p className="text-sm text-slate-500">No payment records.</p>}
        </Section>
      </div>
    );
  }

  return (
    <div className="space-y-6 text-slate-100 animate-fadeIn">
      <div className="flex items-start gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center bg-violet-600 text-white"><UserRound size={20} /></div><div><h2 className="text-2xl font-bold text-white">School Records</h2><p className="mt-1 text-sm text-slate-400">Verify School Agent answers against your tenant’s live student, fee, payment, transport, and hostel records.</p></div></div>
      <form onSubmit={submit} className="flex gap-2 border border-slate-800 bg-slate-900 p-3"><div className="relative flex-1"><Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by student name or admission number" className="h-11 w-full border border-slate-700 bg-slate-950 pl-10 pr-3 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-violet-500" /></div><button type="submit" className="inline-flex h-11 items-center gap-2 bg-violet-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-violet-500"><Search size={16} /> Search</button></form>
      {error && <p className="border-l-2 border-rose-400 bg-rose-950/20 px-4 py-3 text-sm text-rose-200">{error}</p>}
      <section className="border border-slate-800 bg-slate-900"><div className="flex items-center justify-between border-b border-slate-800 px-4 py-3"><h3 className="text-sm font-bold text-white">Students</h3><span className="text-xs text-slate-500">{total} matching record{total === 1 ? '' : 's'}</span></div>{loadingList || loadingRecord ? <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-slate-400"><Loader2 size={18} className="animate-spin" /> Loading records</div> : students.length ? <div className="divide-y divide-slate-800">{students.map(student => <button key={student.student_id} onClick={() => selectStudent(student.student_id)} className="flex w-full items-center justify-between gap-4 px-4 py-4 text-left transition-colors hover:bg-slate-800/50"><div className="min-w-0"><p className="truncate font-semibold text-slate-100">{student.student_name}</p><p className="mt-1 text-xs text-slate-500">Admission no. <span className="font-mono text-slate-400">{student.admission_no}</span> · Class ID {student.class_id} · Section ID {student.section_id}</p></div><ChevronRight size={18} className="shrink-0 text-slate-500" /></button>)}</div> : <div className="flex min-h-56 flex-col items-center justify-center text-center"><Bus size={28} className="text-slate-700" /><p className="mt-3 text-sm text-slate-400">No matching students found.</p></div>}</section>
    </div>
  );
};

export default SchoolRecords;

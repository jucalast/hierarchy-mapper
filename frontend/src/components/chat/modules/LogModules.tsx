import React from 'react';
import { 
    User2, Mail, MessageSquare, Building2, Phone, Calendar, Check 
} from 'lucide-react';

export const ContactLogCard = ({ data, label }: { data: any, label?: string }) => (
    <div className="flex items-center gap-2 my-2 ml-4 p-2.5 bg-white/5 rounded-xl border border-white/10 w-fit backdrop-blur-sm shadow-lg hover:bg-white/10 transition-all duration-300 group">
        <div className="p-1.5 bg-purple-500/20 rounded-lg group-hover:bg-purple-500/30 transition-colors">
            <User2 size={14} className="text-purple-400" />
        </div>
        <div className="flex flex-col">
            <span className="text-xs font-semibold text-white/90">{data.name}</span>
            {data.source && <span className="text-[9px] text-gray-500 font-medium uppercase tracking-wider">{data.source}</span>}
        </div>
        {data.channels && (
            <div className="flex gap-1.5 ml-2 border-l border-white/10 pl-2">
                {data.channels.includes('WhatsApp') && <img src="/wppicon.png" width="14" height="14" alt="W" className="grayscale opacity-70 group-hover:grayscale-0 group-hover:opacity-100 transition-all" />}
                {data.channels.includes('Email') && <img src="/outlook.png" width="14" height="14" alt="E" className="grayscale opacity-70 group-hover:grayscale-0 group-hover:opacity-100 transition-all" />}
            </div>
        )}
        {label && <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded-full uppercase font-black ml-1 tracking-tighter border border-emerald-500/30">{label}</span>}
    </div>
);

export const EmailLogCard = ({ data }: { data: any }) => (
    <div className="flex flex-col gap-2 my-3 ml-4 p-3 bg-gradient-to-br from-white/10 to-transparent rounded-xl border border-white/10 max-w-[320px] backdrop-blur-md shadow-xl hover:border-blue-500/30 transition-all group">
        <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[10px] text-blue-400 uppercase font-black tracking-widest">
                <Mail size={12} className="group-hover:scale-110 transition-transform" /> E-mail Lido
            </div>
            <div className="text-[9px] text-gray-500 font-mono">{data.date?.split(' ')[0]}</div>
        </div>
        <div className="text-xs font-bold text-white/90 leading-tight group-hover:text-blue-200 transition-colors truncate">{data.subject}</div>
        <div className="text-[10px] text-gray-400 line-clamp-2 leading-relaxed italic">"{data.body}"</div>
    </div>
);

export const WhatsAppLogCard = ({ data }: { data: any }) => (
    <div className="flex flex-col gap-2 my-3 ml-4 p-3 bg-gradient-to-br from-[#25D366]/10 to-transparent rounded-xl border border-[#25D366]/20 max-w-[320px] backdrop-blur-md shadow-xl group">
        <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[10px] text-[#25D366] uppercase font-black tracking-widest">
                <MessageSquare size={12} /> WhatsApp
            </div>
        </div>
        <div className="text-[11px] text-white/90 leading-relaxed bg-white/5 p-2 rounded-lg border border-white/5">{data.body || data.text}</div>
        <div className="flex justify-between items-center text-[9px] text-gray-500">
            <span>{data.fromMe ? 'Enviado' : 'Recebido'}</span>
            <span>{data.time || data.date?.split(' ')[1]}</span>
        </div>
    </div>
);

export const DealLogCard = ({ data }: { data: any }) => (
    <div className="flex items-center gap-3 my-3 ml-4 p-3 bg-white/5 rounded-xl border border-white/10 w-fit backdrop-blur-sm group hover:bg-white/10 transition-all">
        <div className="p-2 bg-white/10 rounded-lg shadow-inner group-hover:bg-white/20 transition-colors">
            <Building2 size={16} className="text-white/70" />
        </div>
        <div className="flex flex-col">
            <div className="flex items-center gap-2">
                <span className="text-xs font-black text-white/90 uppercase tracking-tight">{data.title}</span>
                <span className="text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded font-bold uppercase tracking-tighter border border-blue-500/30">{data.stage_name}</span>
            </div>
            <div className="text-[11px] text-gray-400 font-medium">
                {data.formatted_value !== 'R$\xa00' ? data.formatted_value : 'Valor não definido'} • {data.status === 'open' ? 'Em aberto' : data.status}
            </div>
        </div>
    </div>
);

export const ActivityLogCard = ({ data }: { data: any }) => {
    const isDone = data.done === true || data.done === 1;
    return (
        <div className="flex items-center gap-3 my-2 ml-4 p-2.5 bg-white/5 rounded-xl border border-white/10 w-fit hover:bg-white/10 transition-all">
            <div className={`p-1.5 rounded-lg ${isDone ? 'bg-emerald-500/10' : 'bg-blue-500/10'}`}>
                {data.type === 'call' ? <Phone size={14} className={isDone ? 'text-emerald-400' : 'text-blue-400'} /> : 
                 data.type === 'email' ? <Mail size={14} className={isDone ? 'text-emerald-400' : 'text-blue-400'} /> :
                 <Calendar size={14} className={isDone ? 'text-emerald-400' : 'text-blue-400'} />}
            </div>
            <div className="flex flex-col">
                <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-bold ${isDone ? 'text-gray-400 line-through' : 'text-white/90'}`}>{data.subject}</span>
                    {isDone && <Check size={10} className="text-emerald-500" />}
                </div>
                <div className="text-[9px] text-gray-500 font-medium uppercase">{data.type_name || data.type} • {data.due_date}</div>
            </div>
        </div>
    );
};

export const NoteLogCard = ({ data }: { data: any }) => (
    <div className="flex flex-col gap-1.5 my-2 ml-4 p-3 bg-amber-500/5 rounded-xl border border-amber-500/10 max-w-[300px] border-l-4 border-l-amber-500/40">
        <div className="flex items-center gap-2 text-[10px] text-amber-400/80 uppercase font-black tracking-widest">
            <MessageSquare size={12} /> Nota Interna
        </div>
        <div className="text-[11px] text-gray-300 leading-relaxed line-clamp-3 italic">
            {data.content}
        </div>
    </div>
);

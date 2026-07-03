import { useState, useRef } from 'react';
import { CompanyResult } from '../ChatInterfaces';
import { communication } from '@/services/api';

interface UseChatAutocompleteProps {
    selectedCompanies: CompanyResult[];
    setSelectedCompanies: (companies: CompanyResult[] | ((prev: CompanyResult[]) => CompanyResult[])) => void;
    inputValue: string;
    setInputValue: (val: string) => void;
}

export const useChatAutocomplete = ({
    selectedCompanies,
    setSelectedCompanies,
    inputValue,
    setInputValue,
}: UseChatAutocompleteProps) => {
    const [showAutocomplete, setShowAutocomplete] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [companies, setCompanies] = useState<CompanyResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [searchingCategory, setSearchingCategory] = useState<string | null>(null);
    const lastSearchId = useRef(0);

    const searchUniversal = async (query: string, category: string | null = null) => {
        if (query.length < 1) { setCompanies([]); return; }
        const searchId = ++lastSearchId.current;
        setIsSearching(true);
        try {
            const data = await communication.universalSearch(query, category || undefined);
            if (searchId !== lastSearchId.current) return;
            let results = data.results || [];
            if (category) results = results.filter((item: any) =>
                category === 'whatsapp' ? item.type === 'whatsapp' :
                category === 'email'    ? item.type === 'email' : true
            );
            setCompanies(results as CompanyResult[]);
        } catch { /* ignore */ } finally {
            if (searchId === lastSearchId.current) setIsSearching(false);
        }
    };

    const handleInputChange = (val: string) => {
        setInputValue(val);
        const lastAt = val.lastIndexOf('@');
        if (lastAt !== -1) {
            const query = val.substring(lastAt + 1);
            const matched = selectedCompanies.find(c => query.toLowerCase().startsWith(c.name.toLowerCase()));
            if (matched && query.substring(matched.name.length).length > 0) { setShowAutocomplete(false); return; }
            const catMatch = query.match(/^(contato|email|empresa|cnpj|lead)\s+(.*)/i);
            if (catMatch) {
                let cat = catMatch[1].toLowerCase();
                if (cat === 'contato') cat = 'whatsapp';
                setSearchingCategory(cat);
                setSearchTerm(catMatch[2]);
                setShowAutocomplete(true);
                searchUniversal(catMatch[2], cat);
                return;
            }
            if (query.trim().length > 0 && query.length < 30) {
                setSearchTerm(query);
                setShowAutocomplete(true);
                setSearchingCategory(null);
                searchUniversal(query);
            } else {
                setShowAutocomplete(false);
            }
            return;
        }
        setShowAutocomplete(false);
    };

    return {
        showAutocomplete,
        setShowAutocomplete,
        searchTerm,
        setSearchTerm,
        companies,
        setCompanies,
        isSearching,
        searchingCategory,
        setSearchingCategory,
        handleInputChange,
    };
};

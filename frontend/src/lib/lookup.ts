import { api } from "./api";
import { onlyDigits } from "./format";

export type CompanyInfo = {
  cnpj: string;
  legal_name: string;
  trade_name: string;
  status: string;
  zip_code: string;
  street: string;
  number: string;
  complement: string;
  district: string;
  city: string;
  city_ibge: string;
  uf: string;
  phone: string;
};

export type AddressInfo = { zip_code: string; street: string; district: string; city: string; uf: string; city_ibge: string };

/** Dados públicos do CNPJ (null se não encontrado). */
export async function lookupCompany(cnpj: string): Promise<CompanyInfo | null> {
  const value = cnpj.replace(/[^0-9A-Za-z]/g, "").toUpperCase();
  if (value.length !== 14) return null;
  try {
    return await api<CompanyInfo>(`/lookup/cnpj/${value}`, { auth: false });
  } catch {
    return null;
  }
}

/** Endereço pelo CEP (null se não encontrado). */
export async function lookupAddress(cep: string): Promise<AddressInfo | null> {
  const value = onlyDigits(cep);
  if (value.length !== 8) return null;
  try {
    return await api<AddressInfo>(`/lookup/cep/${value}`, { auth: false });
  } catch {
    return null;
  }
}

export const maskCep = (v: string) => {
  const d = onlyDigits(v).slice(0, 8);
  return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
};

import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { VehicleForm } from '../src/pages/veiculos';
import { Pagamentos } from '../src/pages/vendas';
import { AvaliacaoPage } from '../src/pages/avaliacoes';

vi.mock('@/lib/auth', () => ({useAuth: () => ({organization: {id:'org'}, can: () => true})}));
vi.mock('@/lib/billing', () => ({useBilling: () => ({has: () => true})}));
vi.mock('wouter', async (original) => ({...await original<typeof import('wouter')>(), useParams: () => ({id:'evaluation'}), useLocation: () => ['/', vi.fn()], useSearch: () => ''}));
vi.mock('@/lib/api', () => ({api: vi.fn(async () => ({results:[], count:0})), download: vi.fn()}));
afterEach(cleanup);
function setup() {
  const client = new QueryClient({defaultOptions:{queries:{retry:false, staleTime:Infinity}}});
  const wrapper = ({children}:{children:ReactNode}) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return {client, wrapper};
}

describe('rascunhos permanecem ao atualizar dados do servidor', () => {
  it('cadastro de veículo mantém edição após novo objeto da mesma consulta', () => {
    const {wrapper} = setup();
    const vehicle = {id:'car', marca:'Fiat', modelo:'Uno', opcionais:[], ownership:'proprio', kind:'carro'} as any;
    const props = {open:true, onOpenChange:vi.fn(), vehicle};
    const view = render(<VehicleForm {...props}/>, {wrapper});
    fireEvent.change(screen.getByLabelText('Marca'), {target:{value:'Marca digitada'}});
    view.rerender(<VehicleForm {...props} vehicle={{...vehicle, km:2000}}/>);
    expect((screen.getByLabelText('Marca') as HTMLInputElement).value).toBe('Marca digitada');
  });
  it('pagamentos preservam a linha não salva após atualização da venda', () => {
    const {wrapper} = setup();
    const venda = {id:'sale', pagamentos:[], price_cents:6000000} as any;
    const view = render(<Pagamentos v={venda} editable onSaved={vi.fn()}/>, {wrapper});
    fireEvent.click(screen.getByRole('button', {name:/Adicionar/}));
    expect(screen.getAllByRole('button', {name:'Remover forma de pagamento'})).toHaveLength(1);
    view.rerender(<Pagamentos v={{...venda, status:'proposta'}} editable onSaved={vi.fn()}/>);
    expect(screen.getAllByRole('button', {name:'Remover forma de pagamento'})).toHaveLength(1);
  });
  it('avaliação mantém observações enquanto fotos e consulta se atualizam', async () => {
    const {wrapper, client} = setup();
    const evaluation = {id:'evaluation', marca:'Fiat', modelo:'Uno', kind:'carro', status:'aberta', checklist:{}, photos:[], notes:'Original'};
    client.setQueryData(['avaliacao','evaluation'], evaluation);
    render(<AvaliacaoPage/>, {wrapper});
    await waitFor(() => expect((screen.getByLabelText('Observações') as HTMLTextAreaElement).value).toBe('Original'));
    fireEvent.change(screen.getByLabelText('Observações'), {target:{value:'Não perder esta edição'}});
    act(() => client.setQueryData(['avaliacao','evaluation'], {...evaluation, notes:'Servidor', photos:[]}));
    expect((screen.getByLabelText('Observações') as HTMLTextAreaElement).value).toBe('Não perder esta edição');
  });
});

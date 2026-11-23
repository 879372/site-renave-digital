'use strict';

const menu = document.querySelector('#menu-toggle');
const nav = document.querySelector('#site-nav');
function closeMenu() {
  nav.classList.remove('is-open');
  menu.setAttribute('aria-expanded', 'false');
  menu.setAttribute('aria-label', 'Abrir menu');
}
menu.addEventListener('click', () => {
  const open = nav.classList.toggle('is-open');
  menu.setAttribute('aria-expanded', String(open));
  menu.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
});
nav.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && nav.classList.contains('is-open')) { closeMenu(); menu.focus(); }
});
document.addEventListener('click', event => { if (!event.target.closest('.header-inner')) closeMenu(); });

const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(tab, focus = false) {
  tabs.forEach(item => {
    const selected = item === tab;
    item.classList.toggle('active', selected);
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
    document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
  });
  if (focus) tab.focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', event => {
    let next;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); selectTab(tabs[next], true); }
  });
});

// O total anual equivale a dez mensalidades, conforme o catálogo de planos.
const plans = { essencial: { monthly: 9990, annual: 99900 }, profissional: { monthly: 15990, annual: 159900 }, premium: { monthly: 26990, annual: 269900 } };
const money = cents => (cents / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const billingButtons = [...document.querySelectorAll('[data-billing]')];
billingButtons.forEach(button => button.addEventListener('click', () => {
  const annual = button.dataset.billing === 'annual';
  billingButtons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  Object.entries(plans).forEach(([name, plan]) => {
    const amount = annual ? plan.annual / 12 : plan.monthly;
    const value = money(amount).split(',');
    const target = document.querySelector(`[data-price="${name}"]`);
    target.replaceChildren(document.createTextNode(value[0]));
    const decimals = document.createElement('span');
    decimals.textContent = ',' + value[1];
    target.append(decimals);
    document.querySelector(`[data-total="${name}"]`).textContent = annual ? `${money(plan.annual)} cobrados por ano.` : 'Cobrança mensal.';
  });
  document.querySelector('#annual-explanation').hidden = !annual;
}));
document.querySelector('#year').textContent = new Date().getFullYear();
if ('serviceWorker' in navigator && !['localhost', '127.0.0.1'].includes(location.hostname)) {
  addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

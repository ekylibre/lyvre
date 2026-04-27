// Live balance indicator on entry form
document.addEventListener('htmx:afterSettle', updateBalance);
document.addEventListener('input', updateBalance);

function updateBalance() {
  const indicator = document.getElementById('balance-indicator');
  if (!indicator) return;
  let debit = 0, credit = 0;
  document.querySelectorAll('input[name="debit[]"]').forEach(i => debit += parseFloat(i.value) || 0);
  document.querySelectorAll('input[name="credit[]"]').forEach(i => credit += parseFloat(i.value) || 0);
  const diff = Math.abs(debit - credit);
  if (diff < 0.001) {
    indicator.textContent = `✓ Équilibré (${debit.toFixed(2)} €)`;
    indicator.className = 'ms-auto text-success small';
  } else {
    indicator.textContent = `Déséquilibre : ${diff.toFixed(2)} €`;
    indicator.className = 'ms-auto text-danger small';
  }
}

// Auto-uppercase journal code inputs
document.addEventListener('input', e => {
  if (e.target.name === 'code' && e.target.closest('form')) {
    const pos = e.target.selectionStart;
    e.target.value = e.target.value.toUpperCase();
    e.target.setSelectionRange(pos, pos);
  }
});

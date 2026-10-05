const add = document.querySelector('#add-item');
if (add) add.addEventListener('click', () => {
  const total = document.querySelector('#id_items-TOTAL_FORMS');
  if (Number(total.value) >= 100) return;
  document.querySelector('#items').insertAdjacentHTML('beforeend', document.querySelector('#empty-item').innerHTML.replaceAll('__prefix__', total.value));
  total.value = Number(total.value) + 1;
});
const failed = document.querySelector('#failed-data');
if (failed) {
  const data = JSON.parse(failed.textContent);
  for (const form of document.querySelectorAll('.action-form, .approval-actions form')) {
    if (form.elements.action?.value !== data.action) continue;
    const key = ['item','purchase','lot','dispatch'].find(k => data[k]);
    if (key && form.elements[key]?.value !== data[key]) continue;
    for (const [name,value] of Object.entries(data)) {
      const field = form.elements.namedItem(name);
      if (field && name !== 'csrfmiddlewaretoken') field.value = value;
    }
    for (let p=form.parentElement; p; p=p.parentElement) if (p.tagName==='DETAILS') p.open=true;
  }
}
for (const form of document.querySelectorAll('form[method="post"]')) form.addEventListener('submit', () => {
  for (const b of form.querySelectorAll('button[type="submit"], button:not([type])')) {b.disabled=true;b.dataset.label=b.textContent;b.textContent='Salvando…';}
});
window.addEventListener('pageshow',()=>document.querySelectorAll('button[data-label]').forEach(b=>{b.disabled=false;b.textContent=b.dataset.label;}));

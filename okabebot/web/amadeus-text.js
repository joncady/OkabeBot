/* Private owner chat. Render untrusted text literally; never auto-retry a save. */
(() => {
  const form = document.querySelector('#amadeus-text-form');
  const input = document.querySelector('#amadeus-text-input');
  const log = document.querySelector('#amadeus-text-messages');
  const status = document.querySelector('#amadeus-text-status');
  const reset = document.querySelector('#amadeus-text-reset');
  let busy = false;
  const place = document.querySelector('#amadeus-chat-location');
  function locationContext() {
    return {location_id:place.value || undefined,
            surface_secret:localStorage.getItem('companion-device') || undefined};
  }
  async function refreshLocation() {
    try {
      const selected = localStorage.getItem('amadeus-dashboard-location') || '';
      const result = await api('/amadeus/text/location', {surface_secret:localStorage.getItem('companion-device') || undefined});
      place.replaceChildren(new Option('This browser (automatic)', ''));
      for(const p of result.locations) place.add(new Option(p.name,p.id));
      place.value = result.locations.some(p=>p.id===selected) ? selected : '';
      document.querySelector('#amadeus-chat-location-status').textContent = place.value
        ? `“Here” means ${place.selectedOptions[0].textContent}.`
        : result.location ? `This browser is paired to ${result.location.name}.` : 'Browser not paired to a screen. Select its location to use “come here”.';
    } catch(error) { status.textContent=error.message; }
  }
  place.onchange = () => {localStorage.setItem('amadeus-dashboard-location',place.value);refreshLocation();};
  refreshLocation();
  const auto = document.querySelector('#amadeus-auto-accept');
  const threshold = document.querySelector('#amadeus-confidence');
  async function policy(data) {
    try {
      const result = await api('/amadeus/text/policy', data);
      auto.checked = result.auto_accept;
      threshold.value = result.threshold;
    } catch(error) { status.textContent = error.message; }
  }
  auto.onchange = () => policy({auto_accept:auto.checked});
  threshold.onchange = () => policy({threshold:Number(threshold.value)});
  policy({});
  function message(who, text) {
    const row = document.createElement('p');
    row.textContent = `${who}: ${text}`;
    log.append(row);
    while (log.children.length > 40) log.firstElementChild.remove();
  }
  function working(value) {
    busy = value;
    form.querySelector('button[type="submit"]').disabled = value;
    reset.disabled = value;
    input.disabled = value;
  }
  form.onsubmit = async event => {
    event.preventDefault();
    if (busy || !input.value.trim()) return;
    const text = input.value.trim();
    working(true);
    status.textContent = 'Thinking…';
    message('You', text);
    try {
      const result = await api('/amadeus/text', {text,...locationContext()});
      message('Amadeus', result.reply);
      input.value = '';
      status.textContent = result.memory ? `Remembered ${result.memory.values.join(', ')} · confidence ${Math.round(result.memory.confidence*100)}%. Review or forget in Amadeus setup.` : result.pending ? `Please confirm · confidence ${Math.round(result.pending.confidence*100)}%.` : result.tools?.length ? `Used: ${result.tools.join(', ')}. Reply is text only.` : 'Text reply · ready for your next message.';
    } catch (error) {
      status.textContent = `${error.message}. Message was not retried; check saved preferences before repeating a confirmation.`;
    } finally { working(false); input.focus(); }
  };
  reset.onclick = async () => {
    if (busy) return;
    working(true);
    try {
      await api('/amadeus/text/reset', {});
      log.replaceChildren();
      status.textContent = 'New conversation. Previously confirmed preferences are unchanged.';
    } catch (error) { status.textContent = error.message; }
    finally { working(false); }
  };
  document.querySelector('#amadeus-text-feedback').onsubmit = async event => {
    event.preventDefault();
    const rating = event.submitter?.value;
    if (!rating) return;
    try {
      await api('/amadeus/text/feedback', {rating, note:document.querySelector('#amadeus-text-note').value});
      document.querySelector('#amadeus-text-note').value = '';
      status.textContent = 'Feedback saved privately on this controller.';
    } catch (error) { status.textContent = error.message; }
  };
})();

/* Self-contained frontend: no remote JS/CDN, all user data escaped before HTML insertion. */
const state={csrf:null,page:'dashboard',profiles:[],criteria:[],running:false};
const $=(s)=>document.querySelector(s);
const fmt=(n)=>n==null?'—':new Intl.NumberFormat('nl-NL').format(n);
const euro=(n)=>n==null?'—':new Intl.NumberFormat('nl-NL',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(n);
const dt=(s)=>s?new Date(s).toLocaleString('nl-NL',{timeZone:'Europe/Amsterdam',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'—';
const esc=(x)=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tag=(text,type)=>`<span class="pill ${type}">${esc(text)}</span>`;
const eligibility=(status)=>({MATCH:tag('Alle must-haves ✓','green'),REJECTED:tag('Must-have ontbreekt','red'),UNVERIFIED:tag('Nog onzeker','amber'),REVIEW:tag('Controle nodig','amber')}[status]||tag(status,'grey'));
const statusTag=(s)=>({COMPLETE:tag('Geslaagd','green'),PARTIAL:tag('Gedeeltelijk','amber'),FAILED:tag('Mislukt','red'),RUNNING:tag('Bezig','amber'),QUEUED:tag('In wachtrij','grey'),SUCCESS:tag('Gemini OK','green'),ERROR:tag('Gemini fout','red'),CACHE_HIT:tag('Cachehit','grey'),LOCAL_ONLY:tag('Lokaal','grey'),SKIPPED_NO_KEY:tag('Gemini uit','amber'),SKIPPED_BUDGET:tag('Budgetlimiet','amber')}[s]||tag(s||'—','grey'));
async function api(path,{method='GET',body,headers={}}={}){
 const opt={method,credentials:'same-origin',headers:{...headers}};
 if(body!==undefined){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
 if(!['GET','HEAD'].includes(method) && state.csrf)opt.headers['X-CSRF-Token']=state.csrf;
 const r=await fetch('/api/v1'+path,opt);let data;try{data=await r.json()}catch{data={detail:await r.text()}}
 if(!r.ok){const d=data.detail;throw Error(typeof d==='object'?(d.code||JSON.stringify(d)):(d||r.statusText))}
 return data;
}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.remove('hidden');setTimeout(()=>el.classList.add('hidden'),4800)}
function head(kicker,title,description,actions=''){return `<div class="page-heading"><div><p class="eyebrow">${kicker}</p><h1>${title}</h1><p class="subtitle">${description}</p></div><div class="inline-actions">${actions}</div></div>`}
function chart(points,{key='mean_asking',price=true}={}){
 if(!points?.length)return '<div class="chart-empty">Nog geen historische data. Voer een eerste refresh uit.</div>';
 const values=points.map(p=>Number(p[key]||0)),lo=Math.min(...values),hi=Math.max(...values),range=Math.max(hi-lo,1);
 const w=720,h=230,pad=40,usableW=w-pad*2,usableH=h-55;
 const xy=values.map((n,i)=>({x:pad+(points.length===1?usableW/2:i*usableW/(points.length-1)),y:20+(hi-n)/range*usableH}));
 const path=xy.map((p,i)=>`${i?'L':'M'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
 const grid=[0,.25,.5,.75,1].map(f=>{const y=20+usableH*f;return `<line x1="${pad}" x2="${w-pad}" y1="${y}" y2="${y}" stroke="#edf1f6"/><text x="${pad-6}" y="${y+3}" text-anchor="end">${price?fmt(Math.round(hi-(hi-lo)*f)) : fmt(Math.round(hi-(hi-lo)*f))}</text>`}).join('');
 const ticks=points.length>1?[0,Math.floor((points.length-1)/2),points.length-1]:[0];
 return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Historische prijsontwikkeling">${grid}
 <path d="${path}" fill="none" stroke="#21b5a4" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
 ${xy.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="3.3" fill="#fff" stroke="#21b5a4" stroke-width="2"/>`).join('')}
 ${ticks.map(i=>`<text x="${xy[i].x}" y="${h-8}" text-anchor="middle">${esc(points[i].date||dt(points[i].observed_at))}</text>`).join('')}</svg>`;
}
function table(headers,rows){return `<div class="table-wrap"><table><thead><tr>${headers.map(t=>`<th>${t}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${headers.length}" class="muted">Nog geen resultaten</td></tr>`}</tbody></table></div>`}
async function initialize(){const sess=await api('/session');if(!sess.authenticated){$('#login').classList.remove('hidden');return}state.csrf=sess.csrf;$('#login').classList.add('hidden');$('#shell').classList.remove('hidden');await showPage('dashboard')}
async function showPage(page){state.page=page;document.querySelectorAll('.nav-link').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$('.sidebar').classList.remove('show');const labels={dashboard:'Marktoverzicht',aanbod:'Autoaanbod',profielen:'Zoekprofielen',wensen:'Optieprofiel',runs:'Uitvoeringslog',gemini:'Gemini-integratie',instellingen:'Home Assistant'};$('#crumb-active').textContent=labels[page];$('#content').innerHTML='<div class="loading">Gegevens laden…</div>';
 try{const fn={dashboard:dashboardPage,aanbod:offersPage,profielen:profilesPage,wensen:criteriaPage,runs:runsPage,gemini:geminiPage,instellingen:settingsPage}[page];await fn()}
 catch(e){$('#content').innerHTML=`<div class="notice warn">Laden mislukt: ${esc(e.message)}</div>`}
}
async function dashboardPage(){const [d,l,r]=await Promise.all([api('/dashboard'),api('/listings'),api('/refresh-runs')]);const offers=l.items.slice(0,6);
 $('#content').innerHTML=head('MARKTINTELLIGENTIE','Marktoverzicht','Inzicht in de vraagprijzen, jouw matches en het prijsgedrag van gevolgde auto’s.',`<button class="btn btn-secondary" data-page="aanbod">Bekijk alle auto’s →</button>`)+
 `<div class="stats"><div class="stat"><div class="stat-head">Actieve advertenties <span class="stat-icon">▤</span></div><div class="stat-value">${fmt(d.active_listings)}</div><div class="stat-bottom">In jouw gemonitorde markt</div></div>
 <div class="stat"><div class="stat-head">Mediane vraagprijs <span class="stat-icon">€</span></div><div class="stat-value">${euro(d.median_asking)}</div><div class="stat-bottom">Geen gerealiseerde verkoopprijzen</div></div>
 <div class="stat"><div class="stat-head">Bevestigde must-have matches <span class="stat-icon">✓</span></div><div class="stat-value">${fmt(d.matches)}</div><div class="stat-bottom"><strong>Geschikt op verplichte opties</strong></div></div>
 <div class="stat"><div class="stat-head">Gem. uitrustingsmatch <span class="stat-icon">✦</span></div><div class="stat-value">${fmt(d.average_score)}%</div><div class="stat-bottom">70% must-have · 30% nice-to-have</div></div></div>
 <div class="notice warn">ⓘ&nbsp; <span>${esc(d.limitations[0])} Alle statistieken zijn gebaseerd op daadwerkelijk verwerkte gegevens.</span></div>
 <div class="grid-two"><section class="card"><div class="card-head"><h3>Ontwikkeling gemiddelde vraagprijs</h3><span class="micro">Per kalenderdag · niet gecorrigeerd voor wisselend aanbod</span></div>${chart(d.price_trend)}</section>
 <section class="card"><div class="card-head"><h3>Meest recente controles</h3><button class="btn btn-sm" data-page="runs">Alle logs</button></div>${r.items.length?r.items.slice(0,5).map(x=>`<div class="option-claim clickable" data-run="${esc(x.id)}"><div><strong>${dt(x.created_at)}</strong><p class="micro">${esc(x.trigger_source)} · ${x.summary.found||0} auto's</p></div>${statusTag(x.state)}</div>`).join(''):'<p class="muted">Nog geen refresh uitgevoerd.</p>'}</section></div>
 <section class="card"><div class="card-head"><h3>Interessante auto's</h3><span class="micro">Gerangschikt op matchscore en vraagprijs</span></div>${table(['Auto','Vraagprijs','Km-stand','Match','Geschiktheid'],offers.map(x=>`<tr class="clickable" data-car="${esc(x.id)}"><td class="table-link">${esc(x.title)}<br><span class="micro">${esc(x.seller||'Verkoper onbekend')}</span></td><td>${euro(x.price_eur)}</td><td>${fmt(x.kilometers)}</td><td><strong>${fmt(x.score_total)}%</strong></td><td>${eligibility(x.eligibility)}</td></tr>`))}</section>`;
}
async function profilesPage(){const data=await api('/profiles');state.profiles=data.items;
 $('#content').innerHTML=head('BRONBEHEER','Zoekprofielen','Plak de zoeklink van Gaspedaal. Experimentele directe uitlezing, een ingestelde JSON-API of handmatige JSON-import.')+
 `<section class="card"><div class="card-head"><h3>Nieuw zoekprofiel</h3>${tag(data.gaspedaal_site_available?'Directe URL-uitlezing ingeschakeld':'JSON-importmodus',data.gaspedaal_site_available?'green':'amber')}</div><form id="create-profile" class="form-grid"><div class="field"><label>Naam</label><input name="title" placeholder="XC90 Ultra 2025+" required minlength="2"></div><div class="field"><label>Gaspedaal-zoek-URL</label><input name="search_url" type="url" placeholder="https://www.gaspedaal.nl/…" required></div><button class="btn btn-primary">Opslaan</button></form></section>
 <section class="card"><div class="card-head"><h3>Opgeslagen zoekprofielen</h3><span class="micro">${data.items.length} profielen</span></div><div class="stack">${data.items.map(x=>`<div class="profile-card"><div class="profile-icon">⌕</div><div class="profile-info"><strong>${esc(x.title)}</strong><small>${esc(x.search_url)}</small></div>${tag(x.provider==='gaspedaal_site'?'Gaspedaal zoeklink':x.provider==='gaspedaal'?'JSON API':x.has_snapshot?'JSON snapshot':'Nog geen invoer',x.provider!=='fixture'||x.has_snapshot?'green':'amber')}<button class="btn btn-sm" data-import="${esc(x.id)}">JSON importeren</button><select data-source-select="${esc(x.id)}" aria-label="Gegevensbron"><option value="fixture" ${x.provider==='fixture'?'selected':''}>JSON import</option>${data.gaspedaal_site_available?`<option value="gaspedaal_site" ${x.provider==='gaspedaal_site'?'selected':''}>Gaspedaal zoeklink</option>`:''}${data.gaspedaal_api_configured?`<option value="gaspedaal" ${x.provider==='gaspedaal'?'selected':''}>JSON API</option>`:''}</select><button class="btn btn-secondary btn-sm" data-refresh-profile="${esc(x.id)}">↻</button></div>`).join('')||'<p class="muted">Nog geen profiel. Voeg eerst een zoeklink toe.</p>'}</div></section>`;
}
function photosOf(x){try{return JSON.parse(x.photos_json||'[]')}catch(e){return[]}}
function thumb(x){const p=photosOf(x)[0];return p?`<img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${esc(p)}" alt="">`:`<div class="thumb thumb-empty">Geen foto</div>`}
async function offersPage(){const data=await api('/listings');
 $('#content').innerHTML=head('SELECTIE','Autoaanbod',"Bekijk individuele auto's, optieherkenning en vraagprijshistorie.",`<a class="btn" href="/api/v1/export/observations.csv">↓ Exporteer prijshistorie</a>`)+
 `<section class="card"><div class="card-head"><h3>${fmt(data.items.length)} gevolgde auto's</h3><div class="inline-actions"><label class="micro"><input id="only-matches" type="checkbox"> Alleen bevestigde must-haves</label><label class="micro"><input id="only-favorites" type="checkbox"> Alleen favorieten</label></div></div><div id="offers-table"></div></section>`;
 const draw=()=>{const must=$('#only-matches').checked,favorites=$('#only-favorites').checked;let cars=data.items.filter(x=>(!must||x.eligibility==='MATCH')&&(!favorites||x.favorite));$('#offers-table').innerHTML=table(['Foto','Voertuig','Bouwjaar','Kilometers','Vraagprijs','Uitrustingsscore','Status'],cars.map(x=>`<tr class="clickable" data-car="${esc(x.id)}"><td>${thumb(x)}</td><td><strong>${esc(x.title)}</strong><br><span class="micro">${esc(x.seller||'—')} ${x.favorite?' ★':''}</span></td><td>${x.year||'—'}</td><td>${fmt(x.kilometers)}</td><td><strong>${euro(x.price_eur)}</strong></td><td>${fmt(x.score_total)}%<div class="two-bars"><b style="width:${x.score_must*.7}%"></b><b class="nice" style="width:${x.score_nice*.3}%"></b></div></td><td>${eligibility(x.eligibility)}</td></tr>`))};draw();$('#only-matches').addEventListener('change',draw);$('#only-favorites').addEventListener('change',draw);
}
async function criteriaPage(){const data=await api('/criteria');state.criteria=data.items;
 $('#content').innerHTML=head('UITRUSTING','Mijn opties','Bepaal welke accessoires verplicht zijn en welke extra punten opleveren. Wijzigingen worden bij de volgende refresh verwerkt.')+
 `<div class="notice">✦&nbsp; Een ontbrekende vermelding betekent <strong>onbekend</strong>, niet automatisch afwezig. De score is 70% must-haves en 30% nice-to-haves; een expliciet ontbrekende must-have leidt altijd tot afwijzing.</div>
 <section class="card"><div class="card-head"><h3>Optieprofiel</h3><span class="micro">Gewicht 1–5 per optie</span></div>${data.items.map(x=>`<div class="option-row"><div><strong>${esc(x.label)}</strong><small>${esc(x.description)}</small></div><select data-criterion-group="${esc(x.key)}"><option value="MUST_HAVE" ${x.group_name==='MUST_HAVE'?'selected':''}>Must-have</option><option value="NICE_TO_HAVE" ${x.group_name==='NICE_TO_HAVE'?'selected':''}>Nice-to-have</option></select><input type="number" min="1" max="5" value="${x.weight}" data-criterion-weight="${esc(x.key)}" aria-label="Gewicht"><button class="btn btn-sm btn-secondary" data-save-criterion="${esc(x.key)}">Opslaan</button></div>`).join('')}</section>`;
}
async function runsPage(){const data=await api('/refresh-runs');
 $('#content').innerHTML=head('AUDIT & UITVOERING','Uitvoeringslog','Iedere geplande of handmatige refresh, inclusief aantallen, processtappen en foutmeldingen.',`<button class="btn btn-secondary" data-refresh-all>↻ Handmatig starten</button>`)+
 `<section class="card"><div class="card-head"><h3>Alle refresh-runs</h3><span class="micro">Laatste 100 · klik voor tijdlijn</span></div>${table(['Gestart','Trigger','Uitkomst','Advertenties','Nieuw','Prijswijzigingen','Gemini','Actie'],data.items.map(x=>`<tr><td>${dt(x.created_at)}</td><td>${esc(x.trigger_source)}</td><td>${statusTag(x.state)}</td><td>${fmt(x.summary.found)}</td><td>${fmt(x.summary.new)}</td><td>${fmt(x.summary.price_changes)}</td><td>${fmt(x.summary.gemini_calls)}</td><td><button class="btn btn-sm" data-run="${esc(x.id)}">Details</button></td></tr>`))}</section>`;
}
async function geminiPage(){const data=await api('/integrations');
 $('#content').innerHTML=head('AI-VERANTWOORDING','Gemini-integratielog','Bekijk exact welke gesaniteerde advertentietekst is verzonden, het modelantwoord, tokenverbruik en fouten.')+
 `<div class="notice">ⓘ&nbsp; Alleen daadwerkelijke Gemini-verzoeken hebben een verzonden payload. Lokale classificaties en overgeslagen aanvragen worden apart geregistreerd.</div><section class="card"><div class="card-head"><h3>Classificaties en aanroepen</h3><span class="micro">Laatste 200</span></div>${table(['Tijdstip','Auto','Beslissing','Tokens in / uit','Model','Details'],data.items.map(x=>`<tr><td>${dt(x.created_at)}</td><td>${esc(x.title)}</td><td>${statusTag(x.decision)}${x.error?`<br><span class="micro error-text">${esc(x.error)}</span>`:''}</td><td>${fmt(x.tokens_in)} / ${fmt(x.tokens_out)}</td><td class="micro">${esc(x.model_id)}</td><td><button class="btn btn-sm" data-integration="${esc(x.id)}">Inspecteer</button></td></tr>`))}</section>`;
}
async function settingsPage(){
 $('#content').innerHTML=head('AUTOMATISERING','Home Assistant','Home Assistant bepaalt wanneer de applicatie een refresh uitvoert. De app bevat geen eigen planning.')+
 `<div class="grid-two"><section class="card"><div class="card-head"><h3>Trigger-endpoint</h3>${tag('POST · beveiligd','green')}</div><p class="subtitle">Gebruik dit endpoint in je Home Assistant <code>rest_command</code>. Stel de token in als secret in Home Assistant.</p><pre class="json">POST http://&lt;server-ip&gt;:8099/api/v1/refresh-runs\nAuthorization: Bearer &lt;HA_REFRESH_TOKEN&gt;\nContent-Type: application/json\n\n{"scope":"all","reason":"scheduled_ha"}</pre><p class="micro">Antwoord: HTTP 202 met run-ID. Bij een lopende run HTTP 409. De volledige runhistorie staat in het uitvoeringslog.</p></section>
 <section class="card"><div class="card-head"><h3>Installatie en beveiliging</h3></div><div class="stack"><p>① Beheer het schema in <strong>Instellingen → Automatiseringen</strong> van Home Assistant.</p><p>② Bewaar <code>HA_REFRESH_TOKEN</code> als geheim en gebruik dezelfde token in de app-container.</p><p>③ Gebruik voor toegang buiten je LAN HTTPS via een beveiligde reverse proxy of VPN.</p><p>④ Stel <code>GEMINI_API_KEY</code> in voor cloud-analyse. Zonder sleutel blijft lokale optieherkenning actief.</p><p>⑤ Controleer via <strong>Uitvoeringslog</strong> of iedere scan volledig is geslaagd.</p></div></section></div>
 <section class="card"><div class="card-head"><h3>Gegevensbronstatus</h3>${tag('Directe URL-adapter experimenteel','amber')}</div><p class="subtitle">De directe Gaspedaal-zoeklink wordt gelezen voor gestructureerde advertentiegegevens. Het parsergedrag moet met een echte live pagina worden gevalideerd. De aanbiederspop-up wordt als meerdere advertentiebronnen opgeslagen. Originele dealerpagina’s worden alleen opgehaald van expliciet toegestane domeinen; anders blijven deze als doorkliklink beschikbaar.</p></section>`;
}
function modal(html){$('#modal').innerHTML=html;$('#modal-backdrop').classList.remove('hidden')}
function closeModal(){$('#modal-backdrop').classList.add('hidden');$('#modal').innerHTML=''}
function modalHead(title,sub=''){return `<div class="modal-head"><div><h2>${esc(title)}</h2><p class="subtitle">${esc(sub)}</p></div><button class="modal-close" data-close aria-label="Sluiten">×</button></div>`}
function gallery(x){const ph=photosOf(x);if(!ph.length)return'<p class="micro">Geen foto’s beschikbaar in de bron.</p>';
 return `<section class="card gallery"><img id="gallery-main" class="gallery-main" referrerpolicy="no-referrer" src="${esc(ph[0])}" alt="">${ph.length>1?`<div class="gallery-strip">${ph.map((u,i)=>`<img class="gallery-thumb${i?'':' active'}" data-photo="${esc(u)}" loading="lazy" referrerpolicy="no-referrer" src="${esc(u)}" alt="Foto ${i+1}">`).join('')}</div>`:''}<p class="micro">${ph.length} foto${ph.length===1?'':'’s'}</p></section>`}
function sourceLinks(o){const l=[];if(o.source_url)l.push(`<a class="btn btn-sm" target="_blank" rel="noopener noreferrer" href="${esc(o.source_url)}">Advertentie bij ${esc(o.site)} ↗</a>`);
 if(o.click_url&&o.click_url!==o.source_url)l.push(`<a class="btn btn-sm" target="_blank" rel="noopener noreferrer" href="${esc(o.click_url)}">${o.source_url?'Via Gaspedaal':'Bekijk bij '+esc(o.site)} ↗</a>`);
 return l.join(' ')||'Onbekend'}
async function showCar(id){const x=await api('/listings/'+encodeURIComponent(id));const claims=x.claims||[];const neg=x.negotiation;
 modal(modalHead(x.title,`${x.year||'—'} · ${fmt(x.kilometers)} km · ${x.seller||'Onbekende verkoper'}`)+
 `<div class="inline-actions" style="margin-bottom:16px"><strong style="font:800 25px Manrope">${euro(x.price_eur)}</strong>${eligibility(x.eligibility)}<button class="btn btn-sm" data-favorite="${esc(id)}">${x.favorite?'★ Verwijder favoriet':'☆ Favoriet'}</button><a class="btn btn-sm" href="#aanbieders" data-goto="aanbieders">Bekijk advertentie bij ${(x.sources||[]).length||'alle'} aanbieders ↓</a></div>
 ${gallery(x)}
 <div class="detail-grid"><section class="card"><div class="card-head"><h3>Prijsgeschiedenis</h3><span class="micro">${x.history.length} metingen</span></div>${chart(x.history.map(o=>({...o,date:dt(o.observed_at),mean_asking:o.price_eur})))}</section>
 <section class="card"><div class="card-head"><h3>Onderhandelingsinformatie</h3>${tag(neg.sample_size+" vergelijkbare auto's",'grey')}</div><div class="stats" style="grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px"><div><div class="micro">Mediaan aanbod</div><h3>${euro(neg.median_asking)}</h3></div><div><div class="micro">Verschil mediaan</div><h3>${euro(neg.difference_vs_median_eur)}</h3></div><div><div class="micro">Indicatief openingsbod</div><h3>${euro(neg.illustrative_opening_offer)}</h3></div><div><div class="micro">Indicatieve streefprijs</div><h3>${euro(neg.illustrative_target)}</h3></div></div><p class="micro">${esc(neg.assessment)}</p></section></div>
 <section class="card" id="aanbieders"><div class="card-head"><h3>Alle aanbieders van deze auto</h3><span class="micro">${(x.sources||[]).length} aanbieders</span></div>
 ${(x.sources||[]).length?table(['Aanbieder','Vraagprijs','Links','Prijsmetingen'],x.sources.map(o=>`<tr><td><strong>${esc(o.site)}</strong><br><span class="micro">${esc(o.kind||'Aanbieder')}</span></td><td>${euro(o.price_eur)}</td><td>${sourceLinks(o)}</td><td>${fmt(o.history.length)}</td></tr>`)):'<p class="muted">Deze gegevensbron heeft geen individuele aanbieders meegegeven.</p>'}
 ${(x.detail_fetches||[]).length?`<details><summary class="micro">Log originele advertentietekst</summary>${x.detail_fetches.map(d=>`<p class="micro">${dt(d.created_at)} · ${esc(d.status)} · ${fmt(d.text_length)} tekens · ${esc(d.error||'')}</p>`).join('')}</details>`:''}</section>
 <section class="card"><div class="card-head"><h3>Uitrusting en AI-bewijs</h3><span class="micro">Matchscore: ${fmt(x.score_total)}%</span></div>${claims.map(c=>`<div class="option-claim"><div><strong>${esc(c.label)}</strong> <span class="micro">${c.group_name==='MUST_HAVE'?'VERPLICHT':'NICE-TO-HAVE'}</span><p class="micro">${esc(c.evidence||c.reason||'Geen expliciete vermelding')} · ${esc(c.source)}</p></div><div class="inline-actions">${tag({PRESENT:'Aanwezig',ABSENT:'Afwezig',UNKNOWN:'Onbekend',CONFLICT:'Tegenstrijdig'}[c.status],{PRESENT:'green',ABSENT:'red',UNKNOWN:'grey',CONFLICT:'amber'}[c.status])}<button class="btn btn-sm" data-review="${esc(id)}:${esc(c.criterion_key)}">Corrigeer</button></div></div>`).join('')||'<p class="muted">Nog niet beoordeeld.</p>'}</section>
 <section class="card"><div class="card-head"><h3>Onderhandelingsnotities</h3></div><form id="add-note" data-id="${esc(id)}" class="form-grid" style="grid-template-columns:160px 1fr auto"><div class="field"><label>Bod (€)</label><input name="offer_eur" type="number" min="0"></div><div class="field"><label>Notitie</label><input name="note" required placeholder="Dealer gesproken, voorwaarden, voorstel…"></div><button class="btn btn-primary">Opslaan</button></form>${x.notes.map(n=>`<p class="micro">${dt(n.created_at)} · ${euro(n.offer_eur)} · ${esc(n.note)}</p>`).join('')}</section>`);
}
async function showRun(id){const r=await api('/refresh-runs/'+encodeURIComponent(id));modal(modalHead('Run '+r.id,`${r.trigger_source} · ${dt(r.created_at)}`)+
 `<div class="inline-actions" style="margin-bottom:15px">${statusTag(r.state)}<strong>Gevonden: ${fmt(r.summary.found)}</strong><span>Nieuw: ${fmt(r.summary.new)}</span><span>Prijswijzigingen: ${fmt(r.summary.price_changes)}</span><span>Aanbieders: ${fmt(r.summary.portals)}</span><span>Portalprijswijzigingen: ${fmt(r.summary.portal_price_changes)}</span></div>
 ${r.error?`<div class="notice warn">${esc(r.error)}</div>`:''}<section class="card"><h3>Verwerkingstijdlijn</h3>${r.events.map(e=>`<div class="run-event ${esc(e.level)}"><strong>${dt(e.created_at)} · ${esc(e.stage)} · ${esc(e.level)}</strong><p style="margin:4px 0 0">${esc(e.message)}</p>${e.metrics_json && e.metrics_json!=='{}'?`<details><summary>Technische gegevens</summary><pre class="json">${esc(JSON.stringify(JSON.parse(e.metrics_json),null,2))}</pre></details>`:''}</div>`).join('')}</section>
 <section class="card"><h3>Gemini-integraties in deze run</h3>${r.gemini_requests.map(g=>`<div class="option-claim"><span>${dt(g.created_at)} · ${statusTag(g.decision)}</span><button class="btn btn-sm" data-integration="${esc(g.id)}">Bekijk</button></div>`).join('')||'<p class="muted">Geen integratieverzoeken in deze run</p>'}</section>`)}
async function showIntegration(id){const x=await api('/integrations/'+encodeURIComponent(id));modal(modalHead('Gemini-integratie',`${x.listing_id} · ${dt(x.created_at)}`)+
 `<div class="inline-actions" style="margin-bottom:15px">${statusTag(x.decision)}<span>Model: ${esc(x.model_id)}</span><span>Tokens: ${fmt(x.tokens_in)} / ${fmt(x.tokens_out)}</span><span>${fmt(x.duration_ms)} ms</span></div>
 ${x.error?`<div class="notice warn">${esc(x.error)}</div>`:''}
 <section class="card"><h3>Exact verzonden, gesanitiseerde payload</h3><pre class="json">${esc(x.request_json?JSON.stringify(x.request_json,null,2):'Geen Gemini-aanroep: lokaal afgehandeld of overgeslagen.')}</pre></section>
 <section class="card"><h3>Ruw modelantwoord</h3><pre class="json">${esc(x.response_json||'Geen antwoord')}</pre></section>
 <section class="card"><h3>Gevalideerde resultaten</h3><pre class="json">${esc(x.parsed_json?JSON.stringify(x.parsed_json,null,2):'Geen Gemini-resultaat')}</pre></section>`)}
function importModal(id){modal(modalHead('Importeer JSON-snapshot','Alle advertenties uit deze invoer worden bij de volgende refresh verwerkt.')+
 `<div class="notice warn">Een volledige snapshot met <code>complete:true</code> mag eerder aanwezige auto's als verdwenen markeren. Gebruik <code>complete:false</code> voor onvolledige imports.</div><form id="import-form" data-id="${esc(id)}"><div class="field"><label>JSON-bestand</label><input id="json-file" type="file" accept="application/json,.json"></div><div class="field" style="margin-top:12px"><label>JSON-inhoud</label><textarea id="json-text" rows="11" placeholder='{"complete":true,"listings":[{"external_id":"...","title":"...","price_eur":75000,"description":"..."}]}'></textarea></div><button class="btn btn-primary" style="margin-top:12px">Snapshot bewaren</button></form>`)}
async function startRefresh(scope='all'){
 try{const result=await api('/refresh-runs',{method:'POST',body:{scope,reason:'manual_ui'}});toast('Refresh geaccepteerd: '+result.run_id);const rid=result.run_id;
 setTimeout(async()=>{if(state.page==='runs'||state.page==='dashboard')await showPage(state.page)},1400);
 }catch(e){toast('Refresh niet gestart: '+e.message)}
}

document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-page],[data-car],[data-run],[data-integration],[data-close],[data-import],[data-favorite],[data-review],[data-refresh-profile],[data-save-criterion],[data-refresh-all],[data-source]');if(!b)return;
 try{
  if(b.hasAttribute('data-page'))return showPage(b.dataset.page);
  if(b.hasAttribute('data-close'))return closeModal();
  if(b.hasAttribute('data-car'))return showCar(b.dataset.car);
  if(b.hasAttribute('data-run'))return showRun(b.dataset.run);
  if(b.hasAttribute('data-integration'))return showIntegration(b.dataset.integration);
  if(b.hasAttribute('data-import'))return importModal(b.dataset.import);
  if(b.hasAttribute('data-source')){await api('/profiles/'+b.dataset.source+'/source',{method:'PUT',body:{provider:b.dataset.sourceValue}});toast('Gegevensbron aangepast');return showPage('profielen')}
  if(b.hasAttribute('data-refresh-profile'))return startRefresh({profile_ids:[b.dataset.refreshProfile]});
  if(b.hasAttribute('data-refresh-all'))return startRefresh();
  if(b.hasAttribute('data-favorite')){await api('/listings/'+b.dataset.favorite+'/favorite',{method:'POST'});return showCar(b.dataset.favorite)}
  if(b.hasAttribute('data-review')){const [id,key]=b.dataset.review.split(':');const status=prompt('Status (PRESENT, ABSENT, UNKNOWN, CONFLICT)');if(!status)return;const evidence=prompt('Bewijs / dealerbevestiging (optioneel)')||null;await api('/listings/'+id+'/review',{method:'POST',body:{criterion_key:key,status:status.toUpperCase(),evidence}});return showCar(id)}
  if(b.hasAttribute('data-save-criterion')){const c=state.criteria.find(x=>x.key===b.dataset.saveCriterion);const group=document.querySelector(`[data-criterion-group="${c.key}"]`).value,weight=Number(document.querySelector(`[data-criterion-weight="${c.key}"]`).value);await api('/criteria/'+c.key,{method:'PUT',body:{label:c.label,group_name:group,weight,description:c.description,synonyms:c.synonyms,enabled:!!c.enabled}});toast('Optie gewijzigd. Nieuwe beoordeling bij volgende refresh.');return showPage('wensen')}
 }catch(err){toast(err.message)}
});
document.addEventListener('submit',async e=>{
 const f=e.target;
 if(!['login-form','create-profile','import-form','add-note'].includes(f.id))return;e.preventDefault();
 try{
  if(f.id==='login-form'){const v=$('#password').value;const r=await api('/login',{method:'POST',body:{password:v}});state.csrf=r.csrf;$('#login-error').textContent='';$('#login').classList.add('hidden');$('#shell').classList.remove('hidden');return showPage('dashboard')}
  if(f.id==='create-profile'){const data=Object.fromEntries(new FormData(f));const r=await api('/profiles',{method:'POST',body:data});toast(r.provider==='gaspedaal_site'?'Zoeklink toegevoegd; controleer de eerste run op brondekking.':'Zoekprofiel toegevoegd. Importeer nu een snapshot.');return showPage('profielen')}
  if(f.id==='import-form'){const raw=$('#json-text').value;let obj;try{obj=JSON.parse(raw)}catch{throw Error('JSON is ongeldig')};const r=await api('/profiles/'+f.dataset.id+'/snapshot',{method:'POST',body:obj});toast(`${r.imported} advertenties geïmporteerd`);closeModal();return showPage('profielen')}
  if(f.id==='add-note'){const d=Object.fromEntries(new FormData(f));await api('/listings/'+f.dataset.id+'/notes',{method:'POST',body:{offer_eur:d.offer_eur?Number(d.offer_eur):null,note:d.note}});return showCar(f.dataset.id)}
 }catch(err){if(f.id==='login-form')$('#login-error').textContent=err.message;else toast(err.message)}
});
$('#modal-backdrop').addEventListener('click',e=>{if(e.target.id==='modal-backdrop')closeModal()});
$('#top-refresh').addEventListener('click',()=>startRefresh());
$('#logout').addEventListener('click',async()=>{try{await api('/logout',{method:'POST'})}finally{location.reload()}});
$('#menu-toggle').addEventListener('click',()=>$('.sidebar').classList.toggle('show'));
document.addEventListener('change',async e=>{if(e.target.matches('[data-source-select]')){try{await api('/profiles/'+e.target.dataset.sourceSelect+'/source',{method:'PUT',body:{provider:e.target.value}});toast('Gegevensbron aangepast');await showPage('profielen')}catch(err){toast(err.message)}return}if(e.target.id==='json-file' && e.target.files[0])$('#json-text').value=await e.target.files[0].text()});
initialize().catch(e=>{$('#login').classList.remove('hidden');$('#login-error').textContent='Kan server niet bereiken: '+e.message});
document.addEventListener('click',e=>{const t=e.target.closest&&e.target.closest('[data-photo],[data-goto]');if(!t)return;
 if(t.dataset.photo){const m=$('#gallery-main');if(m)m.src=t.dataset.photo;document.querySelectorAll('.gallery-thumb').forEach(i=>i.classList.toggle('active',i===t))}
 else if(t.dataset.goto){e.preventDefault();const el=document.getElementById(t.dataset.goto);if(el)el.scrollIntoView({behavior:'smooth',block:'start'})}});

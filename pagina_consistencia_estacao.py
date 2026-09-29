"""
Descricao: gera a aba "Consistencia por Estacao" (Hidrologia), com um
painel interativo (serie temporal de chuva e nivel, por estacao), a
partir do fato_consistencia_estacao que pipeline_consistencia.py ja
monta a cada rodada. Criado em 29/09/2026, adaptando a interface feita
por um colega da equipe (monitoramento_chuva_eixo_x.html) -- MESMA
interface e interacao (filtros, canvas, arrastar pra ampliar, desfazer
zoom), so trocando de onde os dados vem: em vez de embutir tudo (todas
as estacoes, todo o historico) num unico HTML, cada (variavel, estacao)
vira um arquivo .json proprio, buscado (fetch) so quando a pessoa
escolhe aquela estacao no filtro -- ver decisoes_e_progresso.md, "Painel
do colega Consistencia por Estacao". Mantem o historico completo desde
01/07 (nada e truncado) e nao precisa de nenhuma biblioteca nova.

O HTML original do colega nao tinha <head>/<body> explicitos (o
navegador infere); foram adicionados aqui porque nav_cg.injetar_subnav
exige um "</head>" literal para inserir a navegacao do site -- nenhuma
mudanca visual, so a estrutura.

O painel do colega tinha uma marca binaria de "aprovado" pra chuva vinda
de um arquivo antigo, com criterio nao documentado. Aqui a marca vem do
status_chuva/status_nivel_range/status_nivel_persist REAIS do pipeline
-- so "aprovado" conta como aprovado; suspeito/reprovado/nulo/"Teste nao
realizado" contam como nao aprovado (confirmado com a equipe em
29/09/2026). Isso resume as 3-4 categorias de cada teste num unico 0/1,
igual ao painel original -- mostrar a categoria exata no tooltip fica
para um passo seguinte, se um dia quiserem.

ATENCAO -- unidade do nivel: NAO confirmada (ver decisoes_e_progresso.md).
O rotulo do eixo fica generico ("unidade nao confirmada") ate alguem
confirmar -- nao inventar "cm" como o painel antigo fazia.

Conexoes do Pipeline:
- Entradas: fato_completo (DataFrame de
  fato_consistencia_estacao.montar_fato_completo -- normalmente
  resultados["fato_consistencia_estacao"], de
  pipeline_consistencia.rodar_para_todas_estacoes; ou lido do CSV salvo
  no Drive, fato_consistencia_estacao.NOME_ARQUIVO_FATO); dim_estacao
  (nomes das estacoes, para exibir no filtro em vez de so o codigo).
- Saidas: um HTML (caminho_saida) + uma pasta NOME_PASTA_DADOS ao lado
  dele, com um .json por (variavel, estacao) -- por exemplo
  dados_consistencia/chuva_40680001.json,
  dados_consistencia/nivel_40680001.json. As duas coisas (HTML e pasta)
  precisam ser publicadas juntas, no mesmo lugar (PASTA_SITE).
"""
import json
import os

import pandas as pd

import nav_cg
import nav_site

NOME_PASTA_DADOS = "dados_consistencia"
LIMIAR_CHUVA_MM = 1000  # mesmo limite de "valor impossivel" do 2.8 -- acima disso a barra some do grafico

CABECALHO_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Monitoramento hidrológico</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f2f5f8;color:#192e43;font:15px system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:30px}h1{margin:0 0 8px;font-size:29px}p{color:#5b6d7c;margin:8px 0 18px}.controls{display:flex;gap:20px;flex-wrap:wrap;align-items:end;margin:25px 0}label{display:flex;flex-direction:column;gap:7px;font-weight:600}select,input,button{font:inherit;padding:10px 14px;border:1px solid #b9c8d4;border-radius:7px;background:white;color:#192e43}button{cursor:pointer}select{min-width:200px}.cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px}.card{padding:14px 20px;background:white;border-radius:10px;min-width:180px}.card strong{display:block;font-size:24px;margin-top:3px}.panel{background:white;border:1px solid #dae2e9;border-radius:12px;padding:22px;margin:18px 0}h2{font-size:19px;margin:0 0 6px}.legend{display:flex;gap:24px;font-size:13px;margin:12px 0}.line{display:inline-block;width:13px;height:13px;background:#637991;vertical-align:middle;margin-right:6px}.dot{display:inline-block;width:13px;height:13px;background:#008f83;vertical-align:middle;margin-right:6px}.plot{height:330px;position:relative}canvas{width:100%;height:100%;display:block;touch-action:none;cursor:crosshair}.selection{position:absolute;top:27px;bottom:48px;background:#008f8326;border-left:1px solid #008f83;border-right:1px solid #008f83;pointer-events:none;display:none}.tip{position:absolute;pointer-events:none;background:#142b40;color:white;border-radius:7px;padding:10px;white-space:pre-line;font-size:12px;display:none;z-index:2}.note{font-size:12px;color:#627482;line-height:1.6}#empty{display:none;padding:15px;background:#fff1d7;border-radius:8px}@media(max-width:600px){main{padding:14px}.panel{padding:12px}.plot{height:300px}}
</style></head><body><main><h1>Monitoramento hidrológico</h1><p>Precipitação e nível · dados por estação</p>
<div class="controls"><label>Estação<select id="station"></select></label><label>Variável<select id="variable"><option value="chuva">Precipitação</option><option value="nivel">Nível</option></select></label><label>Data inicial<input id="start" type="date"></label><label>Data final<input id="end" type="date"></label><button id="reset">Período completo</button><button id="undozoom">Desfazer zoom</button></div>
<div class="cards"><div class="card">Registros brutos<strong id="total"></strong></div><div class="card"><span id="label1">Aprovados</span><strong id="approved"></strong></div><div class="card" id="card2"><span id="label2">Após persistência</span><strong id="approved2"></strong></div><div class="card">Valores ausentes<strong id="missing"></strong></div></div><div id="empty">Nenhum registro neste intervalo. Ajuste as datas.</div>
<section class="panel"><h2 id="title">Distribuição temporal</h2><p class="note">Arraste para ampliar o intervalo nos dois gráficos. Use “Desfazer zoom” para voltar. Consulte valores com o cursor.</p><div class="legend"></div><div class="plot"><canvas id="rain" aria-label="Gráfico temporal de chuva"></canvas><div class="tip"></div><div class="selection"></div></div><p id="zero" class="note"></p></section>
<section class="panel"><h2>Número de registros por dia</h2><p class="note">Contagem diária de registros com valor preenchido. As séries após os testes são contadas separadamente.</p><div class="legend"></div><div class="plot"><canvas id="counts" aria-label="Gráfico de registros por dia"></canvas><div class="tip"></div><div class="selection"></div></div></section>
</main>

"""

PAINEL_JS = """
const MANIFEST=JSON.parse(document.getElementById('manifesto').textContent), $=id=>document.getElementById(id), DAY=86400000;
const CACHE={chuva:{},nivel:{}};
async function carregar(modo,estacao){
  if(!estacao||CACHE[modo][estacao])return;
  $('title').textContent='Carregando...';
  try{const r=await fetch(MANIFEST.pasta_dados+modo+'_'+estacao+'.json');CACHE[modo][estacao]=r.ok?await r.json():[]}
  catch(e){CACHE[modo][estacao]=[]}
}
let zoomRange=null, zoomHistory=[];
const date=t=>new Date(t).toISOString().slice(0,10), fmt=t=>new Date(t).toLocaleDateString('pt-BR',{timeZone:'UTC'}), num=v=>v==null?'Ausente':v.toLocaleString('pt-BR',{maximumFractionDigits:4});
const colors=['#d32f2f','#008f83','#dd8a20'];
function seriesColor(i){return mode()==='nivel'&&i>0?colors[i===1?2:1]:colors[i]}
function mode(){return $('variable').value||'chuva'}
function names(){return mode()==='chuva'?['Bruto','Aprovado']:['Bruto','Após range','Após persistência']}
function source(){return (CACHE[mode()]||{})[$('station').value]||[]}
async function fillStations(){const prev=$('station').value;$('station').innerHTML='';const codigos=(MANIFEST[mode()]||[]).slice().sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));for(const code of codigos){const o=document.createElement('option');o.value=code;o.textContent=code+(MANIFEST.nomes[code]?(' — '+MANIFEST.nomes[code]):'');$('station').append(o)}$('station').value=codigos.includes(prev)?prev:(codigos[0]||'');await reset()}
async function reset(){zoomRange=null;zoomHistory=[];await carregar(mode(),$('station').value);const r=source();if(r.length){$('start').value=date(r[0][0]);$('end').value=date(r[r.length-1][0])}render()}
function render(){const level=mode()==='nivel';let lo=zoomRange?zoomRange[0]:Date.parse($('start').value),hi=zoomRange?zoomRange[1]:Date.parse($('end').value)+DAY-1;
const raw=source().filter(r=>r[0]>=lo&&r[0]<=hi), rows=raw.map(r=>[r[0],r[1],r[1]!=null&&r[2]?r[1]:null,...(level?[r[1]!=null&&r[3]?r[1]:null]:[])]);
const n=rows.filter(r=>r[1]!=null).length,a=rows.filter(r=>r[2]!=null).length,b=level?rows.filter(r=>r[3]!=null).length:0;
$('total').textContent=num(n);$('approved').textContent=(!level&&!MANIFEST.rain_status)?'Indisponível':num(a);$('approved2').textContent=num(b);$('label1').textContent=level?'Após range':'Aprovados';$('label2').textContent='Após persistência';$('card2').style.display=level?'block':'none';$('missing').textContent=num(raw.length-n);$('empty').style.display=n?'none':'block';$('empty').textContent='Sem valores preenchidos para esta variável no intervalo selecionado.';
$('title').textContent=level?'Distribuição temporal do nível':'Distribuição temporal da precipitação';
const labels=names();for(const legend of document.querySelectorAll('.legend'))legend.innerHTML=labels.map((v,i)=>'<span><i style="display:inline-block;width:12px;height:12px;background:'+seriesColor(i)+';margin-right:6px"></i>'+v+'</span>').join('');
const vals=rows.filter(r=>r[1]!=null&&(level||r[1]<=MANIFEST.rain_limit));$('zero').textContent=vals.length&&vals.every(r=>r[1]===0)?'Todos os valores disponíveis são zero; barras de altura zero não aparecem.':'';
// Contagem: o zoom não transforma um dia parcialmente visível em dia incompleto.
const days=new Map();if(Number.isFinite(lo)&&Number.isFinite(hi)&&lo<=hi)for(let t=Math.floor(lo/DAY)*DAY;t<=hi;t+=DAY)days.set(t,[t,0,0,...(level?[0]:[])]);
for(const r of source()){const t=Math.floor(r[0]/DAY)*DAY,b=days.get(t);if(b&&r[1]!=null){b[1]++;if(r[2])b[2]++;if(level&&r[3])b[3]++}}
const plotted=rows.map(r=>!level&&r[1]!=null&&r[1]>MANIFEST.rain_limit?[r[0],null,null]:r);
draw('rain',plotted,lo,hi,false);draw('counts',[...days.values()],Math.floor(lo/DAY)*DAY,Math.floor(hi/DAY)*DAY+DAY-1,true)}
// Escala recalculada com os dados visíveis em cada zoom/filtro.
function axisBounds(rows,count,lineChart){
    let low=Infinity,high=-Infinity;
    for(const r of rows)for(let j=1;j<r.length;j++){
        const v=r[j];if(v!=null&&Number.isFinite(v)){low=Math.min(low,v);high=Math.max(high,v)}
    }
    if(!Number.isFinite(low))return {mn:0,mx:1,step:count?1:.2};
    if(lineChart){
        const span=high-low;
        const margin=span>0?span*.08:Math.max(Math.abs(high)*.005,.1);
        low-=margin;high+=margin;
    }else{
        // Barras conservam a origem em zero para não distorcer as alturas.
        low=Math.min(0,low);high=Math.max(0,high);
        const span=(high-low)||1;high+=span*.08;if(low<0)low-=span*.08;
    }
    const target=(high-low)/5;
    const magnitude=10**Math.floor(Math.log10(target));
    const factor=[1,2,2.5,5,10].find(f=>f*magnitude>=target);
    let step=factor*magnitude;if(count)step=Math.max(1,Math.ceil(step));
    const mn=Math.floor(low/step)*step,mx=Math.ceil(high/step)*step;
    return {mn,mx:mx>mn?mx:mn+step,step};
}
function draw(id,rows,lo,hi,count){const c=$(id),tip=c.nextElementSibling,rect=c.getBoundingClientRect(),w=rect.width,h=rect.height,dpr=devicePixelRatio||1;c.width=w*dpr;c.height=h*dpr;const ctx=c.getContext('2d');ctx.scale(dpr,dpr);const bounds=axisBounds(rows,count,mode()==='nivel'&&!count);let {mn,mx,step}=bounds;const L=64,R=18,T=27,B=48,pw=w-L-R,ph=h-T-B;if(!Number.isFinite(lo)||!Number.isFinite(hi)||hi<=lo){lo=0;hi=1}const x=t=>L+(t-lo)/(hi-lo)*pw,y=v=>T+ph-(v-mn)/(mx-mn)*ph;ctx.font='12px system-ui';ctx.fillStyle='#526879';ctx.fillText(count?'Registros / dia':(mode()==='nivel'?MANIFEST.level_label:'Precipitação (mm)'),L,15);const ticks=Math.round((mx-mn)/step);for(let i=0;i<=ticks;i++){let v=mn+(mx-mn)*i/ticks;if(count)v=Math.round(v);const yy=y(v);ctx.strokeStyle='#e6edf2';ctx.beginPath();ctx.moveTo(L,yy);ctx.lineTo(w-R,yy);ctx.stroke();ctx.textAlign='right';ctx.fillText(num(v),L-9,yy+4)}const off=count?DAY/2:0,by=T+ph;ctx.strokeStyle='#c9d4dc';ctx.fillStyle='#526879';
// Eixo X: no gráfico diário, um rótulo único por dia, centralizado sob a barra; com muitos dias, pula rótulos para não sobrepor.
if(count){const nd=rows.length,slot=nd?pw/nd:pw,skip=Math.max(1,Math.ceil(80/slot));ctx.textAlign='center';for(let i=0;i<nd;i+=skip){const cx=x(rows[i][0]+off);ctx.beginPath();ctx.moveTo(cx,by);ctx.lineTo(cx,by+4);ctx.stroke();ctx.fillText(fmt(rows[i][0]),Math.max(L-20,Math.min(w-36,cx)),by+20)}}
else{const nt=w<650?3:6,short=hi-lo<=2*DAY,seen=new Set();for(let i=0;i<nt;i++){const t=lo+(hi-lo)*i/(nt-1),lab=fmt(t)+(short?' '+new Date(t).toISOString().slice(11,16):'');if(seen.has(lab))continue;seen.add(lab);ctx.textAlign=i===0?'left':(i===nt-1?'right':'center');ctx.fillText(lab,x(t),h-18)}}
ctx.save();ctx.beginPath();ctx.rect(L,T,pw,ph);ctx.clip();
// Barras sobrepostas: bruto largo ao fundo, aprovado estreito à frente.
const intervals=[];for(let i=1;i<rows.length;i++){const delta=rows[i][0]-rows[i-1][0];if(delta>0)intervals.push(delta)}intervals.sort((a,b)=>a-b);
const interval=count?DAY:(intervals.length?intervals[Math.floor(intervals.length/2)]:900000);
const barWidth=Math.max(0.8,Math.min(36,interval/(hi-lo)*pw*.8));
const base=y(0);
function bar(t,v,width,color){if(v==null)return;const top=y(v);ctx.fillStyle=color;ctx.fillRect(x(t+off)-width/2,Math.min(top,base),width,Math.abs(base-top))}
if(mode()==='nivel'&&!count){
    // Interrompe a linha nos valores ausentes, nos filtros e nas lacunas temporais.
    for(let series=1;series<=names().length;series++){
        ctx.strokeStyle=seriesColor(series-1);ctx.lineWidth=[2.6,1.9,1.2][series-1];
        ctx.beginPath();let previous=null;
        for(const r of rows){
            const v=r[series];if(v==null){previous=null;continue}
            if(previous&&r[0]-previous[0]<=interval*1.5){ctx.lineTo(x(r[0]),y(v))}
            else{ctx.moveTo(x(r[0]),y(v))}
            previous=r;
        }
        ctx.stroke();
        // Preserva observações isoladas entre lacunas, que não formam segmentos.
        ctx.fillStyle=seriesColor(series-1);
        for(let i=0;i<rows.length;i++){
            const r=rows[i];if(r[series]==null)continue;
            const prev=rows[i-1],next=rows[i+1];
            const left=prev&&prev[series]!=null&&r[0]-prev[0]<=interval*1.5;
            const right=next&&next[series]!=null&&next[0]-r[0]<=interval*1.5;
            if(!left&&!right){ctx.beginPath();ctx.arc(x(r[0]),y(r[series]),2,0,Math.PI*2);ctx.fill()}
        }
    }
}else{
    for(let series=1;series<=names().length;series++){const fraction=series===1?1:(series===2?.64:.30);for(const r of rows)bar(r[0],r[series],barWidth*fraction,seriesColor(series-1))}
}
ctx.restore();
c.onmousemove=e=>{if(dragStart!==null||!rows.length)return;const px=e.offsetX,t=lo+(px-L)/pw*(hi-lo)-off;let low=0,high=rows.length-1;while(low<high){const mid=(low+high)>>1;if(rows[mid][0]<t)low=mid+1;else high=mid}let idx=low;if(idx>0&&Math.abs(rows[idx-1][0]-t)<Math.abs(rows[idx][0]-t))idx--;const r=rows[idx];tip.textContent=(count?fmt(r[0]):fmt(r[0])+' '+new Date(r[0]).toISOString().slice(11,16))+'\\n'+names().map((label,i)=>label+': '+(r[i+1]==null?'Sem valor nesta série':num(r[i+1]))).join('\\n');tip.style.display='block';tip.style.left=Math.max(0,Math.min(px+12,w-205))+'px';tip.style.top=Math.max(0,e.offsetY-70)+'px'};c.onmouseleave=()=>tip.style.display='none';tip.style.display='none';
let dragStart=null;const selection=tip.nextElementSibling;
const localX=e=>Math.max(L,Math.min(w-R,e.clientX-c.getBoundingClientRect().left));
c.onpointerdown=e=>{if(e.button!==0||!rows.length)return;dragStart=localX(e);tip.style.display='none';c.setPointerCapture(e.pointerId);selection.style.left=dragStart+'px';selection.style.width='0px';selection.style.display='block'};
c.onpointermove=e=>{if(dragStart===null)return;const end=localX(e);selection.style.left=Math.min(dragStart,end)+'px';selection.style.width=Math.abs(end-dragStart)+'px'};
c.onpointerup=e=>{if(dragStart===null)return;const end=localX(e),begin=dragStart;dragStart=null;selection.style.display='none';c.releasePointerCapture(e.pointerId);if(Math.abs(end-begin)<8)return;zoomHistory.push(zoomRange?zoomRange.slice():null);zoomRange=[lo+(Math.min(begin,end)-L)/pw*(hi-lo),lo+(Math.max(begin,end)-L)/pw*(hi-lo)];render()};
c.onpointercancel=()=>{dragStart=null;selection.style.display='none'};
}
$('station').onchange=reset;$('variable').onchange=fillStations;const datesChanged=()=>{zoomRange=null;zoomHistory=[];render()};$('start').onchange=datesChanged;$('end').onchange=datesChanged;$('undozoom').onclick=()=>{zoomRange=zoomHistory.length?zoomHistory.pop():null;render()};$('reset').onclick=reset;let timer;window.onresize=()=>{clearTimeout(timer);timer=setTimeout(render,100)};fillStations();
"""


def _preparar_serie_chuva(fato_estacao):
    """[[timestamp_ms, chuva_mm, aprovado(0/1)], ...] -- so as leituras
    com chuva preenchida (mesmo criterio de "dado coletado" do 2.8)."""
    if "chuva" not in fato_estacao.columns:
        return []
    d = fato_estacao.dropna(subset=["chuva"])
    if d.empty:
        return []
    ts = pd.to_datetime(d["data_hora"]).astype("int64") // 10**6
    aprovado = (d["status_chuva"] == "aprovado").astype(int)
    return list(zip(ts.tolist(), d["chuva"].round(4).tolist(), aprovado.tolist()))


def _preparar_serie_nivel(fato_estacao):
    """[[timestamp_ms, nivel, range_aprovado(0/1), persist_aprovado(0/1)], ...]
    -- so as leituras com nivel preenchido."""
    if "nivel" not in fato_estacao.columns:
        return []
    d = fato_estacao.dropna(subset=["nivel"])
    if d.empty:
        return []
    ts = pd.to_datetime(d["data_hora"]).astype("int64") // 10**6
    range_ok = (d["status_nivel_range"] == "aprovado").astype(int)
    persist_ok = (d["status_nivel_persist"] == "aprovado").astype(int)
    return list(zip(ts.tolist(), d["nivel"].round(4).tolist(), range_ok.tolist(), persist_ok.tolist()))


def gerar_dados_json(fato_completo, pasta_dados):
    """Um arquivo por (variavel, estacao) -- so escreve o arquivo quando a
    estacao tem pelo menos uma leitura daquela variavel (uma estacao so-
    chuva nao ganha nivel_<codigo>.json, e vice-versa). Devolve
    (codigos_com_chuva, codigos_com_nivel), para o manifesto."""
    os.makedirs(pasta_dados, exist_ok=True)
    codigos_chuva, codigos_nivel = [], []
    for codigo, grupo in fato_completo.groupby("codigo_estacao"):
        serie_chuva = _preparar_serie_chuva(grupo)
        if serie_chuva:
            with open(os.path.join(pasta_dados, f"chuva_{codigo}.json"), "w", encoding="utf-8") as f:
                json.dump(serie_chuva, f, separators=(",", ":"))
            codigos_chuva.append(codigo)
        serie_nivel = _preparar_serie_nivel(grupo)
        if serie_nivel:
            with open(os.path.join(pasta_dados, f"nivel_{codigo}.json"), "w", encoding="utf-8") as f:
                json.dump(serie_nivel, f, separators=(",", ":"))
            codigos_nivel.append(codigo)
    return sorted(codigos_chuva), sorted(codigos_nivel)


def _nomes_estacao(dim_estacao):
    if dim_estacao is None or "nome_estacao" not in dim_estacao.columns:
        return {}
    d = dim_estacao.copy()
    d["codigo_estacao"] = d["codigo_estacao"].astype(str).str.zfill(8)
    return dict(zip(d["codigo_estacao"], d["nome_estacao"].astype(str)))


def gerar_pagina_consistencia(fato_completo, dim_estacao, caminho_saida):
    """Grava o HTML em caminho_saida e os .json de cada estacao numa
    pasta NOME_PASTA_DADOS ao lado dele (mesma pasta de caminho_saida).
    fato_completo pode vir vazio/None (nenhuma estacao ainda) -- a pagina
    e gerada mesmo assim, so com os filtros vazios."""
    pasta_saida = os.path.dirname(os.path.abspath(caminho_saida)) or "."
    pasta_dados = os.path.join(pasta_saida, NOME_PASTA_DADOS)

    if fato_completo is None or fato_completo.empty:
        codigos_chuva, codigos_nivel = [], []
    else:
        fato_completo = fato_completo.copy()
        fato_completo["codigo_estacao"] = fato_completo["codigo_estacao"].astype(str).str.zfill(8)
        codigos_chuva, codigos_nivel = gerar_dados_json(fato_completo, pasta_dados)

    manifesto = {
        "chuva": codigos_chuva,
        "nivel": codigos_nivel,
        "rain_status": True,
        "rain_limit": LIMIAR_CHUVA_MM,
        "level_label": "Nivel (unidade nao confirmada)",
        "pasta_dados": NOME_PASTA_DADOS + "/",
        "nomes": _nomes_estacao(dim_estacao),
    }
    cabecalho = (CABECALHO_HTML
                .replace("<title>Monitoramento hidrológico</title>",
                         "<title>Hidrologia — Consistência por estação</title>")
                .replace("<h1>Monitoramento hidrológico</h1><p>Precipitação e nível · dados por estação</p>",
                         "<h1>Hidrologia — Consistência por estação</h1>"
                         "<p>Precipitação e nível, por estação, desde 01/07/2026 · "
                         "aprovado = passou no teste de consistência do indicador 2.8</p>"))
    html = (cabecalho
           + '<script id="manifesto" type="application/json">'
           + json.dumps(manifesto, separators=(",", ":"))
           + "</script>"
           + f"<script>{PAINEL_JS}</script></body></html>")

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(html)
    nav_site.injetar_nav(caminho_saida, "hidrometria")
    nav_cg.injetar_subnav(caminho_saida, "hidrologia", "consistencia")
    print(f"Página gerada: {caminho_saida} "
          f"({len(codigos_chuva)} estação(ões) com chuva, {len(codigos_nivel)} com nível).")

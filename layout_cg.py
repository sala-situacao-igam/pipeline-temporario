"""
Descrição: NOVO layout (Fase 2) da página de Hidrologia -- leitura
HORIZONTAL em grade de cartões, no lugar da coluna única atual.

  ┌ faixa de KPIs: 2.1 | 2.2 Cota | 2.2 Chuva | 2.8 Chuva | 2.8 Nível ┐
  ├ 2.2 (2 colunas): filtros por faixa + ranking em janela  │ 2.1      ┤
  └ 2.8 (2 colunas): aprovado × reprovado por teste         │ MERGE    ┘

Este módulo SÓ desenha: recebe um dicionário `dados` já calculado (ver
montar_dados_exemplo() em prototipo_layout.py para o formato) e grava um
HTML autocontido (CSS/JS embutidos, sem bibliotecas externas). Não lê
Drive nem calcula indicador -- assim o mesmo desenho serve para o
protótipo (dados de teste) e para o pipeline (dados reais).

Formato de `dados`:
{
  "titulo": str, "periodo": str, "atualizado_em": str,
  "kpis": [ {"id","rotulo","nota","percentual","detalhe"} , ... ],
  "ind_2_1": {"periodo": str, "universos": [
        {"rotulo": str, "n": int, "sem_atraso": pct, "com_atraso": pct, "nao_recebido": pct, "nota": int}, ...]},
  "ind_2_2": {"cota": [ {"codigo","nome","percentual","pontuacao"}, ...],
              "chuva": [...], "nota_cota": num, "nota_chuva": num},
  "ind_2_8": {"barras": [ {"rotulo","aprovado","reprovado","base","nota"(opcional)}, ...],
              "notas": [str, ...]},
  "merge": {"convergencia": int, "divergencia": int, "periodo": str},
  "avisos": [str, ...]
}
"""
import html as _html
import json as _json

# Cores de status por pontuação -- as MESMAS de indicador_2_2_calculo.STATUS_POR_PONTUACAO
# (identidade visual do site), sempre acompanhadas de ícone + rótulo.
STATUS = {
    10: ("#0ca30c", "✓", "Ótima"),
    9: ("#52c90d", "✓", "Muito boa"),
    8: ("#fab219", "●", "Boa"),
    7: ("#ec835a", "▲", "Regular"),
    6: ("#ec835a", "▲", "Regular"),  # 4.x usa 6
    0: ("#d03b3b", "✕", "Reprovada"),
}
# Cores das marcas via variáveis CSS -- cada uma tem um passo para o modo
# claro e outro para o escuro (validados contra a superfície de cada modo).
COR_APROVADO = "var(--c-aprov)"     # claro #1c3f66 (mesmo azul do relatório) · escuro #9dc0e6
COR_REPROVADO = "var(--c-reprov)"   # claro #7ba3c9 · escuro #46698f
COR_NEUTRO = "var(--c-neutro)"      # claro #c9d6e3 · escuro #4b4b47


def _e(texto):
    return _html.escape(str(texto))


def _fmt_pct(valor, casas=1):
    return f"{valor:.{casas}f}".replace(".", ",") + "%"


def _fmt_int(valor):
    return f"{int(valor):,}".replace(",", ".")


def _chip_status(nota):
    cor, icone, rotulo = STATUS.get(int(nota), STATUS[0])
    return (f'<span class="chip"><span class="chip-icone" style="background:{cor}">{icone}</span>'
            f'{_e(rotulo)}</span>')


def _kpi_html(kpi):
    nota = kpi["nota"]
    nota_txt = f"{nota:.1f}".replace(".", ",").replace(",0", "") if isinstance(nota, float) else str(nota)
    chip = _chip_status(round(nota) if isinstance(nota, float) else nota) if kpi.get("mostrar_chip", True) else ""
    return f"""
      <div class="kpi" id="kpi-{_e(kpi['id'])}">
        <p class="kpi-rotulo">{_e(kpi['rotulo'])}</p>
        <p class="kpi-valor">{nota_txt}<small>/10</small></p>
        <p class="kpi-pct">{_fmt_pct(kpi['percentual'])} {_e(kpi.get('detalhe', ''))}</p>
        {chip}
      </div>"""


def _barras_2_1_html(universo):
    categorias = [
        ("Sem atraso", universo["sem_atraso"], COR_APROVADO),
        ("Com atraso", universo["com_atraso"], COR_REPROVADO),
        ("Não recebido", universo["nao_recebido"], COR_NEUTRO),
    ]
    colunas = "".join(
        f"""<div class="col-item" data-tip="{_e(rot)}: {_fmt_pct(val)} dos pacotes previstos">
              <span class="col-valor">{_fmt_pct(val)}</span>
              <span class="col-barra" style="height:{max(1, val) * 0.85:.1f}%;background:{cor}"></span>
            </div>"""
        for rot, val, cor in categorias
    )
    rotulos = "".join(f'<span class="col-rotulo">{_e(rot)}</span>' for rot, _v, _c in categorias)
    return f'<div class="colunas">{colunas}</div><div class="col-rotulos">{rotulos}</div>'


def _barra_100_html(item):
    base = item["base"] or 1
    pa = item["aprovado"] / base * 100
    pr = item["reprovado"] / base * 100
    nota_html = ""
    if item.get("nota") is not None:
        nota_html = f'<span class="barra100-nota">nota {item["nota"]}/10</span>'
    return f"""
        <div class="barra100">
          <div class="barra100-cab"><span class="barra100-rotulo">{_e(item['rotulo'])}</span>
            <span class="barra100-base">{_fmt_int(base)} leituras</span>{nota_html}</div>
          <div class="barra100-trilha">
            <span class="seg" style="width:{pa:.2f}%;background:{COR_APROVADO}"
                  data-tip="Aprovado: {_fmt_int(item['aprovado'])} leituras ({_fmt_pct(pa)})"></span>
            <span class="seg" style="width:{pr:.2f}%;background:{COR_REPROVADO}"
                  data-tip="Reprovado: {_fmt_int(item['reprovado'])} leituras ({_fmt_pct(pr)})"></span>
          </div>
          <div class="barra100-rotulos"><span>{_fmt_pct(pa)} aprovado</span><span>{_fmt_pct(pr)} reprovado</span></div>
        </div>"""


CSS = """
:root{
  --surface:#fcfcfb; --page:#f4f4f1; --ink:#0b0b0b; --ink-2:#52514e; --ink-3:#898781;
  --grid:#e1e0d9; --border:rgba(11,11,11,.10); --accent:#1c3f66;
  --c-aprov:#1c3f66; --c-reprov:#7ba3c9; --c-neutro:#c9d6e3;
  --aviso-bg:#fff4d6; --aviso-ink:#5a4300; color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --surface:#1a1a19; --page:#0d0d0d; --ink:#fff; --ink-2:#c3c2b7; --ink-3:#898781;
    --grid:#2c2c2a; --border:rgba(255,255,255,.10); --accent:#9dc0e6;
    --c-aprov:#9dc0e6; --c-reprov:#46698f; --c-neutro:#4b4b47;
    --aviso-bg:#3a3014; --aviso-ink:#f3dfa4; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --surface:#1a1a19; --page:#0d0d0d; --ink:#fff; --ink-2:#c3c2b7; --ink-3:#898781;
  --grid:#2c2c2a; --border:rgba(255,255,255,.10); --accent:#9dc0e6;
  --c-aprov:#9dc0e6; --c-reprov:#46698f; --c-neutro:#4b4b47;
  --aviso-bg:#3a3014; --aviso-ink:#f3dfa4; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
.pagina{max-width:1280px;margin:0 auto;padding:16px 20px 40px}
/* alinha a nav principal e as sub-abas (nav_site/nav_cg usam 920px) à largura da grade */
body .nav-site, body .subnav-site{max-width:1280px}
.cabecalho{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin:6px 0 14px}
.cabecalho h1{font-size:1.25rem;margin:0}
.cabecalho p{margin:0;color:var(--ink-2);font-size:.85rem}
.aviso{background:var(--aviso-bg);color:var(--aviso-ink);border-radius:8px;padding:8px 12px;font-size:.8rem;margin-bottom:12px}

/* faixa de KPIs */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:12px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.kpi-rotulo{margin:0;color:var(--ink-2);font-size:.78rem;font-weight:600}
.kpi-valor{margin:4px 0 0;font-size:2rem;font-weight:600;line-height:1.1}
.kpi-valor small{font-size:.9rem;color:var(--ink-3);font-weight:400;margin-left:2px}
.kpi-pct{margin:2px 0 8px;color:var(--ink-2);font-size:.78rem}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:.75rem;color:var(--ink-2)}
.chip-icone{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;color:#fff;font-size:.62rem}

/* grade principal */
.grade{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.cartao{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px;min-width:0}
.span2{grid-column:span 2}
.cartao h2{font-size:.95rem;margin:0}
.cartao .sub{margin:2px 0 12px;color:var(--ink-3);font-size:.75rem}
.cartao-topo{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap}

/* seletor segmentado */
.seg-ctrl{display:inline-flex;border:1px solid var(--grid);border-radius:7px;overflow:hidden}
.seg-ctrl button{border:0;background:transparent;color:var(--ink-2);font:inherit;font-size:.75rem;padding:4px 10px;cursor:pointer}
.seg-ctrl button[aria-pressed="true"]{background:var(--ink-2);color:var(--surface);font-weight:600}

/* 2.2: filtros + ranking em janela */
.dois-paineis{display:grid;grid-template-columns:200px minmax(0,1fr);gap:14px}
.faixas{display:flex;flex-direction:column;gap:6px}
.faixa{display:flex;align-items:center;gap:8px;border:1px solid var(--grid);background:transparent;
  border-radius:8px;padding:6px 10px;cursor:pointer;font:inherit;color:var(--ink);text-align:left}
.faixa[aria-pressed="true"]{border-color:var(--ink-2);box-shadow:inset 0 0 0 1px var(--ink-2)}
.faixa .qtd{margin-left:auto;font-weight:600;font-variant-numeric:tabular-nums}
.faixa .rot{font-size:.78rem;color:var(--ink-2)}
.resumo-faixas{font-size:.75rem;color:var(--ink-3);margin-top:6px}
.janela{border:1px solid var(--grid);border-radius:8px;max-height:272px;overflow:auto}
.janela table{width:100%;border-collapse:collapse;font-size:.78rem}
.janela thead th{position:sticky;top:0;background:var(--surface);text-align:left;color:var(--ink-2);
  font-weight:600;padding:7px 8px;border-bottom:1px solid var(--grid);cursor:pointer;white-space:nowrap}
.janela td{padding:5px 8px;border-bottom:1px solid var(--grid)}
.janela td.num{text-align:right;font-variant-numeric:tabular-nums}
.mini-barra{display:inline-block;height:6px;border-radius:0 3px 3px 0;background:var(--accent);vertical-align:middle;margin-right:6px}
.contador{font-size:.72rem;color:var(--ink-3);margin-top:6px}

/* 2.1 colunas */
.colunas{display:flex;align-items:flex-end;gap:14px;height:170px;padding:0 6px;border-bottom:1px solid var(--grid)}
.col-item{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
.col-barra{width:24px;border-radius:4px 4px 0 0;min-height:1px}
.col-valor{font-size:.8rem;font-weight:600;margin-bottom:4px}
.col-rotulos{display:flex;gap:14px;padding:6px 6px 0}
.col-rotulo{flex:1;font-size:.72rem;color:var(--ink-2);text-align:center}
.nota-rodape{font-size:.72rem;color:var(--ink-3);margin:8px 0 0}

/* 2.8 barras 100% */
.barra100{margin-bottom:14px}
.barra100-cab{display:flex;gap:10px;align-items:baseline;margin-bottom:5px;flex-wrap:wrap}
.barra100-rotulo{font-weight:600;font-size:.82rem}
.barra100-base{color:var(--ink-3);font-size:.72rem}
.barra100-nota{margin-left:auto;font-size:.75rem;color:var(--ink-2);font-weight:600}
.barra100-trilha{display:flex;gap:2px;height:22px}
.barra100-trilha .seg{display:block;height:100%}
.barra100-trilha .seg:first-child{border-radius:4px 0 0 4px}
.barra100-trilha .seg:last-child{border-radius:0 4px 4px 0}
.barra100-rotulos{display:flex;justify-content:space-between;font-size:.72rem;color:var(--ink-2);margin-top:3px}
.legenda{display:flex;flex-wrap:wrap;gap:14px;font-size:.72rem;color:var(--ink-2);margin:4px 0 12px}
.legenda i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}

.detalhes{margin-top:12px}
.detalhes summary{cursor:pointer;font-size:.78rem;color:var(--ink-2);padding:4px 0;list-style:none;display:flex;align-items:center;gap:6px}
.detalhes summary::-webkit-details-marker{display:none}
.detalhes summary::before{content:"▸";display:inline-block;transition:transform .15s}
.detalhes[open] summary::before{transform:rotate(90deg)}
.lista-janela{border:1px solid var(--grid);border-radius:8px;max-height:150px;overflow:auto;margin-top:6px}
.lista-janela table{width:100%;border-collapse:collapse;font-size:.74rem}
.lista-janela th{position:sticky;top:0;background:var(--surface);text-align:left;color:var(--ink-2);padding:5px 8px;border-bottom:1px solid var(--grid)}
.lista-janela td{padding:4px 8px;border-bottom:1px solid var(--grid)}
/* tooltip */
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);font-size:.72rem;
  padding:5px 8px;border-radius:6px;opacity:0;transition:opacity .08s;z-index:10;max-width:260px}

@media (max-width:900px){
  .grade{grid-template-columns:1fr}.span2{grid-column:auto}
  .dois-paineis{grid-template-columns:1fr}.faixas{flex-direction:row;flex-wrap:wrap}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
}
"""

JS = r"""
(function(){
  // ---------- tooltip ----------
  var tip=document.getElementById('tip');
  document.addEventListener('mousemove',function(ev){
    var alvo=ev.target.closest('[data-tip]');
    if(!alvo){tip.style.opacity=0;return;}
    tip.textContent=alvo.getAttribute('data-tip');
    tip.style.left=Math.min(ev.clientX+12,window.innerWidth-270)+'px';
    tip.style.top=(ev.clientY+14)+'px';tip.style.opacity=1;
  });

  // ---------- 2.1: troca de universo ----------
  document.querySelectorAll('[data-u21]').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('[data-u21]').forEach(function(x){x.setAttribute('aria-pressed',x===b)});
      document.querySelectorAll('.u21').forEach(function(p){p.hidden=p.dataset.u!==b.dataset.u21});
    });
  });

  // ---------- 2.2: variável, faixa, ordenação ----------
  var DADOS=JSON.parse(document.getElementById('dados-2-2').textContent);
  var ORDEM=[10,9,8,7,0], ROT={10:'Ótima',9:'Muito boa',8:'Boa',7:'Regular',0:'Reprovada'};
  var COR={10:'#0ca30c',9:'#52c90d',8:'#fab219',7:'#ec835a',0:'#d03b3b'};
  var ICO={10:'✓',9:'✓',8:'●',7:'▲',0:'✕'};
  var estado={variavel:'cota',faixa:null,col:'percentual',desc:true};

  function renderFaixas(){
    var lista=DADOS[estado.variavel], box=document.getElementById('faixas');
    box.innerHTML='';
    ORDEM.forEach(function(p){
      var n=lista.filter(function(e){return e.pontuacao===p}).length;
      var b=document.createElement('button');b.type='button';b.className='faixa';
      b.setAttribute('aria-pressed',estado.faixa===p);
      b.innerHTML='<span class="chip-icone" style="background:'+COR[p]+'">'+ICO[p]+'</span>'+
        '<span class="rot">'+ROT[p]+' ('+p+')</span><span class="qtd">'+n+'</span>';
      b.onclick=function(){estado.faixa=(estado.faixa===p?null:p);renderFaixas();renderTabela();};
      box.appendChild(b);
    });
    document.getElementById('resumo-faixas').textContent=
      estado.faixa===null?'Clique numa faixa para filtrar o ranking.':'Filtro ativo — clique de novo para limpar.';
  }
  function renderTabela(){
    var lista=DADOS[estado.variavel].slice();
    if(estado.faixa!==null) lista=lista.filter(function(e){return e.pontuacao===estado.faixa});
    lista.sort(function(a,b){var x=a[estado.col],y=b[estado.col];
      var r=(typeof x==='string')?x.localeCompare(y):x-y; return estado.desc?-r:r;});
    var corpo=document.getElementById('corpo-2-2');
    corpo.innerHTML=lista.map(function(e,i){
      return '<tr><td class="num">'+(i+1)+'</td><td>'+e.codigo+'</td><td>'+e.nome+'</td>'+
        '<td class="num"><span class="mini-barra" style="width:'+Math.max(1,e.percentual*0.6)+'px"></span>'+
        e.percentual.toFixed(1).replace('.',',')+'%</td>'+
        '<td><span class="chip"><span class="chip-icone" style="background:'+COR[e.pontuacao]+'">'+ICO[e.pontuacao]+'</span>'+e.pontuacao+'</span></td></tr>';
    }).join('');
    document.getElementById('contador-2-2').textContent=lista.length+' de '+DADOS[estado.variavel].length+' estações';
    renderSemDados();
  }
  function renderSemDados(){
    var sem=DADOS[estado.variavel].filter(function(e){return e.percentual===0});
    var box=document.getElementById('sem-dados');
    box.hidden=sem.length===0;
    document.getElementById('sem-dados-titulo').textContent=
      'Estações sem nenhum dado de '+estado.variavel+' no período ('+sem.length+')';
    document.getElementById('corpo-sem-dados').innerHTML=sem.map(function(e){
      return '<tr><td>'+e.codigo+'</td><td>'+e.nome+'</td></tr>';}).join('');
  }
  document.querySelectorAll('[data-v22]').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('[data-v22]').forEach(function(x){x.setAttribute('aria-pressed',x===b)});
      estado.variavel=b.dataset.v22;estado.faixa=null;renderFaixas();renderTabela();
    });
  });
  document.querySelectorAll('[data-ord]').forEach(function(th){
    th.addEventListener('click',function(){
      var c=th.dataset.ord; if(estado.col===c){estado.desc=!estado.desc}else{estado.col=c;estado.desc=(c!=='nome'&&c!=='codigo')}
      renderTabela();
    });
  });
  renderFaixas();renderTabela();
})();
"""


def _cartao_2_1(i21):
    universos = i21["universos"]
    seletor = ""
    if len(universos) > 1:
        botoes = "".join(
            f'<button type="button" data-u21="{i}" aria-pressed="{str(i == 0).lower()}">{_e(u["rotulo"])}</button>'
            for i, u in enumerate(universos)
        )
        seletor = f'<div class="seg-ctrl" role="group" aria-label="Universo">{botoes}</div>'
    paineis = "".join(
        f'<div class="u21" data-u="{i}" {"" if i == 0 else "hidden"}>{_barras_2_1_html(u)}'
        f'<p class="nota-rodape">{_e(u["rotulo"])} · nota {u["nota"]}/10 · base: pacotes previstos (24/dia por estação)</p></div>'
        for i, u in enumerate(universos)
    )
    return f"""
    <section class="cartao" aria-labelledby="t21">
      <div class="cartao-topo">
        <div><h2 id="t21">2.1 — Atraso na transmissão</h2><p class="sub">{_e(i21['periodo'])}</p></div>
        {seletor}
      </div>
      {paineis}
    </section>"""


def _cartao_2_2():
    return """
    <section class="cartao span2" aria-labelledby="t22">
      <div class="cartao-topo">
        <div><h2 id="t22">2.2 — Disponibilidade de dados (sem perda de registros)</h2>
          <p class="sub">Nota por estação conforme o Anexo II · clique numa faixa para filtrar</p></div>
        <div class="seg-ctrl" role="group" aria-label="Variável">
          <button type="button" data-v22="cota" aria-pressed="true">Cota</button>
          <button type="button" data-v22="chuva" aria-pressed="false">Chuva</button>
        </div>
      </div>
      <div class="dois-paineis">
        <div><div class="faixas" id="faixas"></div><p class="resumo-faixas" id="resumo-faixas"></p></div>
        <div>
          <div class="janela" tabindex="0" aria-label="Ranking de estações (role dentro da janela)">
            <table>
              <thead><tr><th data-ord="percentual">#</th><th data-ord="codigo">Código</th><th data-ord="nome">Estação</th>
                <th data-ord="percentual">Disponibilidade ▾</th><th data-ord="pontuacao">Nota</th></tr></thead>
              <tbody id="corpo-2-2"></tbody>
            </table>
          </div>
          <p class="contador" id="contador-2-2"></p>
          <details class="detalhes" id="sem-dados">
            <summary id="sem-dados-titulo"></summary>
            <div class="lista-janela" tabindex="0" aria-label="Estações sem nenhum dado no período">
              <table><thead><tr><th>Código</th><th>Estação</th></tr></thead><tbody id="corpo-sem-dados"></tbody></table>
            </div>
          </details>
        </div>
      </div>
    </section>"""


def _cartao_2_8(i28):
    barras = "".join(_barra_100_html(b) for b in i28["barras"])
    notas = "".join(f"<li>{_e(n)}</li>" for n in i28.get("notas", []))
    return f"""
    <section class="cartao span2" aria-labelledby="t28">
      <div class="cartao-topo">
        <div><h2 id="t28">2.8 — Consistência de dados</h2>
          <p class="sub">Leituras aprovadas ÷ leituras testadas, somando todas as estações (soma da rede)</p></div>
        <div class="legenda"><span><i style="background:{COR_APROVADO}"></i>Aprovado</span>
          <span><i style="background:{COR_REPROVADO}"></i>Reprovado (suspeito, nulo, não aprovado)</span></div>
      </div>
      {barras}
      <ul class="nota-rodape">{notas}</ul>
    </section>"""


def _cartao_merge(ch):
    total = (ch["convergencia"] + ch["divergencia"]) or 1
    barra = _barra_100_html({
        "rotulo": "Estação × satélite (por dia)", "aprovado": ch["convergencia"],
        "reprovado": ch["divergencia"], "base": total,
    }).replace("leituras", "estações-dia").replace("aprovado</span>", "convergência</span>").replace(
        "reprovado</span>", "divergência</span>").replace("Aprovado:", "Convergência:").replace("Reprovado:", "Divergência:")
    return f"""
    <section class="cartao" aria-labelledby="tch">
      <h2 id="tch">2.8 — Chuva: comparação com o MERGE (CPTEC/INPE)</h2>
      <p class="sub">{_e(ch['periodo'])} · informativo, não entra na nota</p>
      {barra}
      <p class="nota-rodape">Divergência = um lado registrou chuva (&gt; 1 mm na janela 12Z-12Z) e o outro não.</p>
    </section>"""


def gerar_pagina_hidro(dados, caminho_saida):
    """Grava o HTML completo (layout em grade) em caminho_saida.
    Ordem: KPIs → [2.1 | 2.2 (2 col)] → [2.8 (2 col) | MERGE].
    `ind_2_8` e `merge` são opcionais (a página de Série histórica não tem 2.8)."""
    kpis_html = "".join(_kpi_html(k) for k in dados["kpis"])
    avisos_html = "".join(f'<div class="aviso">{_e(a)}</div>' for a in dados.get("avisos", []))
    i22 = dados["ind_2_2"]
    dados_22 = _json.dumps({"cota": i22["cota"], "chuva": i22["chuva"]}, ensure_ascii=False).replace("</", "<\\/")

    cartoes = _cartao_2_1(dados["ind_2_1"]) + _cartao_2_2()
    if dados.get("ind_2_8"):
        cartoes += _cartao_2_8(dados["ind_2_8"])
    if dados.get("merge"):
        cartoes += _cartao_merge(dados["merge"])

    pagina = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{_e(dados['titulo'])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="pagina">
  <div class="cabecalho">
    <h1>{_e(dados['titulo'])}</h1>
    <p>{_e(dados['periodo'])} · atualizado em {_e(dados['atualizado_em'])}</p>
  </div>
  {avisos_html}
  <section class="kpis" aria-label="Resumo das notas">{kpis_html}
  </section>
  <div class="grade">{cartoes}
  </div>
</div>
<div id="tip" role="tooltip"></div>
<script type="application/json" id="dados-2-2">{dados_22}</script>
<script>{JS}</script>
</body>
</html>
"""
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(pagina)
    print(f"Layout gerado em: {caminho_saida}")


# =====================================================================
# Página de METEOROLOGIA (4.1, 4.2, 4.3) -- mesmo sistema visual
# =====================================================================
JS_TOOLTIP = r"""
(function(){
  var tip=document.getElementById('tip');
  document.addEventListener('mousemove',function(ev){
    var alvo=ev.target.closest('[data-tip]');
    if(!alvo){tip.style.opacity=0;return;}
    tip.textContent=alvo.getAttribute('data-tip');
    tip.style.left=Math.min(ev.clientX+12,window.innerWidth-270)+'px';
    tip.style.top=(ev.clientY+14)+'px';tip.style.opacity=1;
  });
})();
"""

CSS_METEO = """
.hbarras{display:flex;flex-direction:column;gap:5px}
.hbarra{display:grid;grid-template-columns:62px 1fr 34px;align-items:center;gap:8px;font-size:.72rem}
.hbarra .rot{color:var(--ink-2)}
.hbarra .trilha{height:12px}
.hbarra .fill{display:block;height:100%;border-radius:0 4px 4px 0;background:var(--c-aprov);min-width:1px}
.hbarra .val{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
.resumo-cd{font-size:.78rem;color:var(--ink-2);margin:0 0 12px}
.resumo-cd strong{color:var(--ink)}
.dois-graficos{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.dois-graficos h3{font-size:.75rem;color:var(--ink-2);font-weight:600;margin:0 0 6px}
@media (max-width:900px){.dois-graficos{grid-template-columns:1fr}}
"""


def _colunas_contagem_html(itens, sufixo_tip=""):
    """Colunas verticais para contagens (uma série só): itens = [(rótulo, valor)]."""
    maximo = max([v for _r, v in itens] + [1])
    colunas = "".join(
        f"""<div class="col-item" data-tip="{_e(rot)}: {v}{_e(sufixo_tip)}">
              <span class="col-valor">{v}</span>
              <span class="col-barra" style="height:{max(0.5, v / maximo * 85):.1f}%;background:{COR_APROVADO}"></span>
            </div>"""
        for rot, v in itens
    )
    rotulos = "".join(f'<span class="col-rotulo">{_e(rot)}</span>' for rot, _v in itens)
    return f'<div class="colunas" style="gap:8px">{colunas}</div><div class="col-rotulos" style="gap:8px">{rotulos}</div>'


def _hbarras_html(itens, sufixo_tip=""):
    maximo = max([v for _r, v in itens] + [1])
    linhas = "".join(
        f"""<div class="hbarra" data-tip="{_e(rot)}: {v}{_e(sufixo_tip)}"><span class="rot">{_e(rot)}</span>
              <span class="trilha"><span class="fill" style="width:{v / maximo * 100:.1f}%"></span></span>
              <span class="val">{v}</span></div>"""
        for rot, v in itens
    )
    return f'<div class="hbarras">{linhas}</div>'


def gerar_pagina_meteo(dados, caminho_saida):
    """Página de Meteorologia em grade. Formato de `dados`:
    {"titulo","periodo","atualizado_em","avisos":[...], "kpis":[...como na hidro...],
     "ind_4_1": {"por_dia_semana":[(dia,n)...], "resumo": str},
     "ind_4_2": {"por_mes_dias":[(mes,n)...], "por_mes_alertas":[(mes,n)...], "resumo": str},
     "ind_4_3": {"por_mes":[(mes,n)...], "boletins":[(data_str,titulo)...], "resumo": str}}"""
    kpis_html = "".join(_kpi_html(k) for k in dados["kpis"])
    avisos_html = "".join(f'<div class="aviso">{_e(a)}</div>' for a in dados.get("avisos", []))
    i41, i42, i43 = dados["ind_4_1"], dados["ind_4_2"], dados["ind_4_3"]
    linhas_bol = "".join(f"<tr><td>{_e(d)}</td><td>{_e(t)}</td></tr>" for d, t in i43["boletins"])

    cartoes = f"""
    <section class="cartao" aria-labelledby="t41">
      <h2 id="t41">4.1 — Previsões do tempo publicadas</h2>
      <p class="sub">Publicações por dia da semana</p>
      <p class="resumo-cd">{i41['resumo']}</p>
      {_colunas_contagem_html(i41['por_dia_semana'], ' previsões')}
    </section>
    <section class="cartao" aria-labelledby="t42">
      <h2 id="t42">4.2 — Monitoramento e alertas</h2>
      <p class="sub">Por mês</p>
      <p class="resumo-cd">{i42['resumo']}</p>
      <div class="dois-graficos">
        <div><h3>Dias com relatório/alerta</h3>{_hbarras_html(i42['por_mes_dias'], ' dias')}</div>
        <div><h3>Alertas individuais</h3>{_hbarras_html(i42['por_mes_alertas'], ' alertas')}</div>
      </div>
    </section>
    <section class="cartao" aria-labelledby="t43">
      <h2 id="t43">4.3 — Monitoramento climático</h2>
      <p class="sub">Boletins de tendência climática por mês</p>
      <p class="resumo-cd">{i43['resumo']}</p>
      {_colunas_contagem_html(i43['por_mes'], ' boletim(ns)')}
      <details class="detalhes">
        <summary>Ver boletins publicados ({len(i43['boletins'])})</summary>
        <div class="lista-janela" tabindex="0" aria-label="Boletins publicados">
          <table><thead><tr><th>Criado em</th><th>Boletim</th></tr></thead><tbody>{linhas_bol}</tbody></table>
        </div>
      </details>
    </section>"""

    pagina = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{_e(dados['titulo'])}</title>
<style>{CSS}{CSS_METEO}</style>
</head>
<body>
<div class="pagina">
  <div class="cabecalho">
    <h1>{_e(dados['titulo'])}</h1>
    <p>{_e(dados['periodo'])} · atualizado em {_e(dados['atualizado_em'])}</p>
  </div>
  {avisos_html}
  <section class="kpis" aria-label="Resumo das notas">{kpis_html}
  </section>
  <div class="grade">{cartoes}
  </div>
</div>
<div id="tip" role="tooltip"></div>
<script>{JS_TOOLTIP}</script>
</body>
</html>
"""
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write(pagina)
    print(f"Layout gerado em: {caminho_saida}")

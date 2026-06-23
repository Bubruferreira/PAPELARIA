"""
ARQUIVO: app.py
RESPONSABILIDADE: 
Este é o núcleo do sistema (Back-end). É responsável por:
1. Gerenciar a persistência de dados (leitura/escrita no database.json).
2. Controlar as sessões de usuário (PDV e Loja Online).
3. Definir as rotas (URLs) e as regras de negócio de cada fluxo.
4. Aplicar políticas de segurança (Login e Permissões de Gerência).
5. Intermediar a comunicação entre os dados salvos e a interface (Templates).
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from functools import wraps
import json
import os
import urllib.parse

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_sr_papel'

# ==========================================
# FUNÇÕES DE PERSISTÊNCIA (DATABASE)
# ==========================================
ARQUIVO_DB = 'database.json'

def carregar_banco():
    """Lê o arquivo JSON de banco de dados."""
    try:
        with open(ARQUIVO_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"usuarios": {}, "produtos": {}, "vendas": []}

def salvar_banco(dados):
    """Grava o dicionário atualizado no arquivo JSON."""
    with open(ARQUIVO_DB, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


# ==========================================
# DECORATORS DE CONTROLE DE ACESSO
# ==========================================
def login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def gerencia_obrigatoria(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('cargo') != 'gerencia':
            flash("Acesso restrito.")
            return redirect(url_for('pdv_caixa'))
        return f(*args, **kwargs)
    return decorated_function


# =================================================================
# FUNÇÕES GLOBAIS PARA O HTML (CONTEXT PROCESSOR)
# =================================================================
@app.context_processor
def injetar_funcoes_globais():
    def produto_esta_esgotado(sku):
        """Verifica no banco de dados se um produto zerou no estoque"""
        try:
            with open(ARQUIVO_DB, 'r', encoding='utf-8') as f:
                db = json.load(f)
            produto = db.get('produtos', {}).get(str(sku))
            if produto and int(produto.get('quantidade', 0)) <= 0:
                return True
            return False
        except Exception:
            return False
    return dict(produto_esta_esgotado=produto_esta_esgotado)


# ==========================================
# FLUXO DE LOGIN E PÚBLICO
# ==========================================
@app.route('/')
def catalogo():
    """Página principal de vendas online (Visão do Cliente)."""
    banco = carregar_banco()
    produtos = banco.get('produtos', {})
    busca = request.args.get('busca', '').lower()
    if busca:
        produtos = {sku: p for sku, p in produtos.items() if busca in p['nome'].lower()}
    return render_template('catalogo.html', produtos=produtos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, s = request.form.get('usuario'), request.form.get('senha')
        user = carregar_banco().get('usuarios', {}).get(u)
        if user and user['senha'] == s:
            session['usuario'], session['cargo'] = u, user['cargo']
            return redirect(url_for('admin' if user['cargo'] == 'gerencia' else 'pdv_caixa'))
        flash("Credenciais inválidas")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ==========================================
# FLUXO PDV (LOJA FÍSICA) - Usa 'carrinho'
# ==========================================

@app.route('/pdv')
@login_obrigatorio
def pdv_caixa():
    carrinho = session.get('carrinho', {})
    total = sum(i['preco'] * i['qtd'] for i in carrinho.values())
    
    # --- NOVA LÓGICA DE BUSCA POR NOME ---
    busca = request.args.get('busca', '').lower().strip()
    resultados_busca = {}
    
    if busca:
        banco = carregar_banco()
        produtos = banco.get('produtos', {})
        # Filtra os produtos que tem a palavra pesquisada no nome E que tem estoque > 0
        resultados_busca = {
            sku: p for sku, p in produtos.items() 
            if busca in p['nome'].lower() and p['quantidade'] > 0
        }
    # -------------------------------------
    
    # Agora enviamos os resultados da busca para a tela também!
    return render_template('caixa.html', carrinho=carrinho, total=total, resultados_busca=resultados_busca, busca=busca)

@app.route('/adicionar_carrinho', methods=['POST'])
@login_obrigatorio
def adicionar_carrinho():
    # 1. Pega o que a funcionária digitou ou bipou na barra única
    termo = request.form.get('termo', '').strip()
    
    # 2. Pega o clique do botão "+ Adicionar" caso ela tenha usado a lista de pesquisa
    sku_direto = request.form.get('sku')
    
    # Define quem o sistema vai usar
    codigo_final = sku_direto if sku_direto else termo
    
    banco = carregar_banco()
    produtos = banco.get('produtos', {})
    prod = produtos.get(codigo_final)
    
    if prod:
        # AÇÃO A: ACHOU O CÓDIGO! (Joga no carrinho na hora)
        if prod['quantidade'] > 0:
            carrinho_pdv = session.get('carrinho', {})
            
            if codigo_final in carrinho_pdv:
                if carrinho_pdv[codigo_final]['qtd'] < prod['quantidade']: 
                    carrinho_pdv[codigo_final]['qtd'] += 1
                else: 
                    flash("❌ Estoque insuficiente para este item!")
            else: 
                carrinho_pdv[codigo_final] = {'nome': prod['nome'], 'preco': prod['preco_varejo'], 'qtd': 1}
            
            session['carrinho'] = carrinho_pdv
            session.modified = True
        else:
            flash("❌ Produto esgotado no estoque!")
            
        return redirect(url_for('pdv_caixa'))
        
    else:
        # AÇÃO B: NÃO É UM CÓDIGO DE BARRAS! (Pesquisa pelo nome)
        # Se não tiver vazio, redireciona ativando a pesquisa
        if termo:
            return redirect(url_for('pdv_caixa', busca=termo))
        return redirect(url_for('pdv_caixa'))

@app.route('/atualizar_qtd_direto/<sku>', methods=['POST'])
@login_obrigatorio
def atualizar_qtd_direto(sku):
    carrinho = session.get('carrinho', {})
    
    try:
        nova_qtd = int(request.form.get('nova_qtd', 1))
    except ValueError:
        nova_qtd = 1
        
    banco = carregar_banco()
    produto = banco.get('produtos', {}).get(sku)
    
    if sku in carrinho and produto:
        if nova_qtd <= 0:
            del carrinho[sku]
        elif nova_qtd <= produto['quantidade']:
            carrinho[sku]['qtd'] = nova_qtd
        else:
            # Trava de segurança para digitação manual!
            carrinho[sku]['qtd'] = produto['quantidade']
            flash(f"❌ O estoque máximo deste item é {produto['quantidade']}!")
            
    session['carrinho'] = carrinho
    session.modified = True
    return redirect(url_for('pdv_caixa'))
    
    # 1. Carrega o banco para saber o limite de estoque real
    banco = carregar_banco()
    produto = banco.get('produtos', {}).get(sku)
    
    if sku in carrinho and produto:
        if acao == 'aumentar': 
            # 2. A trava de segurança do botão de MAIS (+)
            if carrinho[sku]['qtd'] < produto['quantidade']:
                carrinho[sku]['qtd'] += 1
            else:
                flash(f"❌ O estoque máximo deste item é {produto['quantidade']}!")
        else: 
            # Botão de MENOS (-)
            carrinho[sku]['qtd'] -= 1
            
        # 3. Se zerar, tira do carrinho
        if carrinho[sku]['qtd'] <= 0: 
            del carrinho[sku]
            
    session['carrinho'] = carrinho
    session.modified = True
    return redirect(url_for('pdv_caixa'))

@app.route('/remover_item/<sku>', methods=['POST'])
@login_obrigatorio
def remover_item(sku):
    carrinho = session.get('carrinho', {})
    if sku in carrinho:
        del carrinho[sku]
    session.modified = True
    return redirect(url_for('pdv_caixa'))

@app.route('/limpar_carrinho', methods=['POST'])
@login_obrigatorio
def limpar_carrinho():
    session.pop('carrinho', None)
    return redirect(url_for('pdv_caixa'))

@app.route('/finalizar_venda', methods=['POST'])
@login_obrigatorio
def finalizar_venda():
    carrinho = session.get('carrinho', {})
    if not carrinho: return redirect(url_for('pdv_caixa'))
    banco = carregar_banco()
    
    total_bruto = sum(item['preco'] * item['qtd'] for item in carrinho.values())
    desconto = float(request.form.get('desconto') or 0)
    valor_recebido = float(request.form.get('recebido') or 0)
    total_pagar = total_bruto - desconto
    
    recibo_dados = {
        'data': datetime.now().strftime("%d/%m/%Y %H:%M"),
        'operador': session.get('usuario', 'Caixa'),
        'itens': list(carrinho.values()),
        'total_bruto': total_bruto,
        'desconto': desconto,
        'total_pagar': total_pagar,
        'forma_pgto': request.form.get('pagamento'),
        'valor_recebido': valor_recebido,
        'troco': max(0, valor_recebido - total_pagar)
    }
    
    banco.setdefault('vendas', []).append(recibo_dados)
    for sku, item in carrinho.items():
        if sku in banco['produtos']: banco['produtos'][sku]['quantidade'] -= item['qtd']
    salvar_banco(banco)
    
    session['ultimo_recibo'] = recibo_dados
    session.pop('carrinho', None)
    return redirect(url_for('exibir_recibo'))

@app.route('/recibo')
@login_obrigatorio
def exibir_recibo():
    return render_template('recibo.html', recibo=session.get('ultimo_recibo'))


# ==========================================
# FLUXO CLIENTE ONLINE - Usa 'carrinho_cliente'
# ==========================================
# ==========================================
# FLUXO CLIENTE ONLINE - Usa 'carrinho_cliente'
# ==========================================
@app.route('/carrinho_cliente')
def ver_carrinho_cliente():
    # Agora a variável nasce com o nome certo:
    carrinho_cliente = session.get('carrinho_cliente', {})
    total = sum(item['preco'] * item['qtd'] for item in carrinho_cliente.values())
    return render_template('carrinho_cliente.html', carrinho=carrinho_cliente, total=total)

@app.route('/adicionar_carrinho_cliente/<sku>', methods=['POST', 'GET'])
def adicionar_carrinho_cliente(sku):
    if 'carrinho_cliente' not in session:
        session['carrinho_cliente'] = {}
        
    banco = carregar_banco()
    produto = banco.get('produtos', {}).get(str(sku))
    
    if produto:
        carrinho_cliente = session['carrinho_cliente']
        
        if str(sku) in carrinho_cliente:
            # Trava para não comprar mais do que tem no estoque
            if carrinho_cliente[str(sku)]['qtd'] < produto['quantidade']:
                carrinho_cliente[str(sku)]['qtd'] += 1
        else:
            carrinho_cliente[str(sku)] = {
                'nome': produto['nome'],
                'preco': float(produto['preco_varejo']),
                'qtd': 1
            }
            
        session['carrinho_cliente'] = carrinho_cliente
        session.modified = True
        
    return redirect(url_for('catalogo'))

@app.route('/alterar_qtd_cliente/<sku>', methods=['POST'])
def alterar_qtd_cliente(sku):
    carrinho_cliente = session.get('carrinho_cliente', {})
    acao = request.form.get('acao')
    
    if sku in carrinho_cliente:
        if acao == 'aumentar': 
            carrinho_cliente[sku]['qtd'] += 1
        else: 
            carrinho_cliente[sku]['qtd'] -= 1
        
        # Tiramos o "_cliente" extra que escorregou aqui rs
        if carrinho_cliente[sku]['qtd'] <= 0: 
            del carrinho_cliente[sku]
            
    session['carrinho_cliente'] = carrinho_cliente
    session.modified = True
    
    # Redireciona para o nome novo:
    return redirect(url_for('ver_carrinho_cliente'))

@app.route('/remover_carrinho_cliente/<sku>', methods=['POST'])
def remover_carrinho_cliente(sku):
    carrinho_cliente = session.get('carrinho_cliente', {})
    if sku in carrinho_cliente:
        del carrinho_cliente[sku]
        
    session['carrinho_cliente'] = carrinho_cliente
    session.modified = True
    
    # Redireciona para o nome novo:
    return redirect(url_for('ver_carrinho_cliente'))

@app.route('/limpar_carrinho_cliente', methods=['POST'])
def limpar_carrinho_cliente():
    session.pop('carrinho_cliente', None)
    return redirect(url_for('ver_carrinho_cliente'))

@app.route('/finalizar_pedido_whatsapp')
def finalizar_pedido_whatsapp():
    carrinho_cliente = session.get('carrinho_cliente', {})
    if not carrinho_cliente:
        return redirect(url_for('catalogo'))

    texto = "🛍️ *NOVO PEDIDO - SR. PAPEL* 🛍️\n\n"
    total = 0
    for sku, item in carrinho_cliente.items():
        subtotal = item['qtd'] * item['preco']
        texto += f"▪️ {item['qtd']}x {item['nome']} (R$ {subtotal:.2f})\n"
        total += subtotal
        
    texto += f"\n💰 *TOTAL A PAGAR: R$ {total:.2f}*"
    texto += "\n\nOlá! Gostaria de confirmar a disponibilidade e finalizar a compra destes itens."

    # O seu número já está no esquema!
    telefone_loja = "5521985726588"
    texto_codificado = urllib.parse.quote(texto)
    link_wpp = f"https://wa.me/{telefone_loja}?text={texto_codificado}"
    
    # Limpa o carrinho após gerar o pedido
    session.pop('carrinho_cliente', None)
    
    return redirect(link_wpp)


# ==========================================
# GERÊNCIA (ADMIN)
# ==========================================
@app.route('/admin')
@gerencia_obrigatoria
def admin():
    db = carregar_banco()
    produtos = db.get('produtos', {})
    vendas = db.get('vendas', [])
    
    total_hoje = 0.0
    total_mes = 0.0
    qtd_vendas = len(vendas)
    nome_top = "Nenhum Produto"
    
    for venda in vendas:
        valor = venda.get('total_pagar', 0)
        total_hoje += valor
        total_mes += valor
        
    return render_template('admin.html', produtos=produtos, total_hoje=total_hoje, 
                           total_mes=total_mes, nome_top=nome_top, qtd_vendas=qtd_vendas)

@app.route('/historico')
@gerencia_obrigatoria
def historico():
    db = carregar_banco()
    vendas = db.get('vendas', [])
    vendas_reversas = list(reversed(vendas))
    return render_template('historico.html', vendas=vendas_reversas)

@app.route('/adicionar_produto', methods=['POST'])
@gerencia_obrigatoria
def adicionar_produto():
    banco = carregar_banco()
    sku = request.form.get('sku')
    banco['produtos'][sku] = {
        "nome": request.form.get('nome'), 
        "preco_varejo": float(request.form.get('varejo')), 
        "preco_atacado": float(request.form.get('atacado')), 
        "quantidade": int(request.form.get('qtd'))
    }
    salvar_banco(banco)
    return redirect(url_for('admin'))

@app.route('/entrada_estoque', methods=['POST'])
@gerencia_obrigatoria
def entrada_estoque():
    banco = carregar_banco()
    sku, qtd = request.form.get('sku'), int(request.form.get('qtd'))
    if sku in banco['produtos']:
        banco['produtos'][sku]['quantidade'] += qtd
        salvar_banco(banco)
    return redirect(url_for('admin'))

@app.route('/excluir_produto/<sku>')
@gerencia_obrigatoria
def excluir_produto(sku):
    banco = carregar_banco()
    if sku in banco.get('produtos', {}):
        del banco['produtos'][sku]
        salvar_banco(banco)
    return redirect(url_for('admin'))

@app.route('/editar_produto/<sku>', methods=['GET', 'POST'])
@gerencia_obrigatoria
def editar_produto(sku):
    banco = carregar_banco()
    if request.method == 'POST':
        p = banco['produtos'][sku]
        p['nome'] = request.form['nome']
        p['preco_varejo'] = float(request.form['varejo'])
        p['preco_atacado'] = float(request.form['atacado'])
        p['quantidade'] = int(request.form['qtd'])
        salvar_banco(banco)
        return redirect(url_for('admin'))
    return render_template('editar_produto.html', sku=sku, produto=banco['produtos'][sku])


# =================================================================
# AUTO-GERADOR DE BANCO DE DADOS
# =================================================================
def inicializar_banco_de_dados():
    """Cria o arquivo JSON com usuários padrão se ele não existir."""
    if not os.path.exists(ARQUIVO_DB):
        banco_inicial = {
            "usuarios": {
                "gerente": {
                    "senha": "123",
                    "cargo": "gerencia",
                    "nome": "Gerente Principal"
                },
                "caixa": {
                    "senha": "123",
                    "cargo": "operador",
                    "nome": "Operador de Caixa"
                }
            },
            "produtos": {},
            "vendas": []
        }
        with open(ARQUIVO_DB, 'w', encoding='utf-8') as f:
            json.dump(banco_inicial, f, indent=4, ensure_ascii=False)
        print(f"✅ Banco de dados '{ARQUIVO_DB}' criado com usuários padrão!")

inicializar_banco_de_dados()

# =================================================================
if __name__ == '__main__':
    # Mantivemos a porta 5001 para não conflitar com a versão antiga!
    app.run(debug=True, port=5001)

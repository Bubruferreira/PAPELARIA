import json
import os

# Nome do seu ficheiro de base de dados (ajuste se o seu tiver outro nome, ex: 'dados.json')
ARQUIVO_DB = 'database.json'

def criar_usuarios_padrao():
    # Carrega a base de dados existente ou cria uma nova
    if os.path.exists(ARQUIVO_DB):
        with open(ARQUIVO_DB, 'r', encoding='utf-8') as f:
            db = json.load(f)
    else:
        db = {}

    # Garante que a secção de utilizadores existe
    if 'usuarios' not in db:
        db['usuarios'] = {}

    # Criação do acesso de GERÊNCIA (Tem acesso a tudo, incluindo o admin.html)
    db['usuarios']['gerente'] = {
        'senha': '123',
        'cargo': 'gerencia',
        'nome': 'Gerente Principal'
    }

    # Criação do acesso de CAIXA (Só tem acesso ao PDV)
    db['usuarios']['caixa'] = {
        'senha': '123',
        'cargo': 'operador',
        'nome': 'Operador de Caixa'
    }

    # Guarda as alterações no ficheiro
    with open(ARQUIVO_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=4, ensure_ascii=False)
        
    print("✅ Utilizadores padrão criados com sucesso!")

if __name__ == '__main__':
    criar_usuarios_padrao()
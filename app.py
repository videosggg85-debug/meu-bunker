from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuração de Pastas
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect('bunker.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Tabela de Usuários (Adicionado 'banido' e 'criado_em')
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios 
        (id INTEGER PRIMARY KEY, user TEXT UNIQUE, senha TEXT, cargo TEXT, ip TEXT, 
         online INTEGER DEFAULT 0, foto TEXT, criado_em DATETIME DEFAULT CURRENT_TIMESTAMP, banido INTEGER DEFAULT 0)''')
    
    # 2. Tabela de Posts (Adicionado 'status')
    cursor.execute('''CREATE TABLE IF NOT EXISTS posts 
        (id INTEGER PRIMARY KEY, autor TEXT, titulo TEXT, conteudo TEXT, cargo_autor TEXT, anexo TEXT, status TEXT DEFAULT 'aprovado')''')
    
    # 3. Tabela de Mensagens
    cursor.execute('''CREATE TABLE IF NOT EXISTS mensagens 
        (id INTEGER PRIMARY KEY, remetente TEXT, destinatario TEXT, texto TEXT, anexo TEXT, data DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 4. Tabela de Comentários
    cursor.execute('''CREATE TABLE IF NOT EXISTS comentarios 
        (id INTEGER PRIMARY KEY, post_id INTEGER, autor TEXT, texto TEXT, data DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # APENAS VOCÊ - A ENTIDADE ABSOLUTA (Sem outros arcanjos automáticos)
    cursor.execute("INSERT OR REPLACE INTO usuarios (id, user, senha, cargo, ip) VALUES (1, 'Padoca6i', 'tuquedeixamano007', 'ENTIDADE ABSOLUTA', '0.0.0.0')")
    
    conn.commit()
    conn.close()
    print(">>> SISTEMA DE MODERAÇÃO ATIVADO. APENAS ENTIDADE CRIADA.")

init_db()

# --- NOVAS ROTAS DE MODERAÇÃO ROBUSTA ---

@app.route('/api/admin/gerenciar_post', methods=['POST'])
def gerenciar_post():
    d = request.json # { post_id, acao: 'aceitar' ou 'recusar' }
    conn = get_db()
    if d['acao'] == 'aceitar':
        conn.execute("UPDATE posts SET status='aprovado' WHERE id=?", (d['post_id'],))
    else:
        conn.execute("DELETE FROM posts WHERE id=?", (d['post_id'],))
        conn.execute("DELETE FROM comentarios WHERE post_id=?", (d['post_id'],))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Ação executada com sucesso"}), 200

@app.route('/api/admin/espionar/<alvo>', methods=['GET'])
def espionar(alvo):
    # Rota para Staff ver conversas de um usuário específico
    conn = get_db()
    msgs = conn.execute("SELECT * FROM mensagens WHERE remetente=? OR destinatario=? ORDER BY data DESC", (alvo, alvo)).fetchall()
    conn.close()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/admin/banir', methods=['POST'])
def banir_usuario():
    d = request.json # { target_user }
    conn = get_db()
    conn.execute("UPDATE usuarios SET banido=1, online=0 WHERE user=?", (d['target_user'],))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Usuário banido do Bunker!"}), 200

# --- ROTAS ORIGINAIS ATUALIZADAS ---

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/cadastro', methods=['POST'])
def cadastro():
    d = request.json
    ip = request.remote_addr # Captura o IP real do usuário
    conn = get_db()
    cursor = conn.cursor()
    user_exists = cursor.execute("SELECT * FROM usuarios WHERE user = ?", (d['user'],)).fetchone()
    if user_exists:
        conn.close()
        return jsonify({"erro": "Este nome já está em uso!"}), 400
    try:
        # Todos os novos entram como 'Humano'
        cursor.execute("INSERT INTO usuarios (user, senha, cargo, ip) VALUES (?, ?, ?, ?)",
                       (d['user'], d['senha'], 'Humano', ip))
        conn.commit()
        return jsonify({"msg": "Registrado no Bunker!"}), 201
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE user=? AND senha=?", (d['user'], d['senha'])).fetchone()
    if user:
        if user['banido'] == 1:
            conn.close()
            return jsonify({"erro": "Você foi banido deste Bunker por IP!"}), 403
        
        conn.execute("UPDATE usuarios SET online=1 WHERE user=?", (user['user'],))
        conn.commit()
        userData = dict(user)
        conn.close()
        return jsonify(userData), 200
    conn.close()
    return jsonify({"erro": "Nome ou senha incorretos!"}), 401

@app.route('/api/comunidade', methods=['GET'])
def comunidade():
    conn = get_db()
    # Retorna usuários não banidos
    users = conn.execute("SELECT user, cargo, online, foto, criado_em, ip FROM usuarios WHERE banido=0").fetchall()
    # Pega todos os posts para filtrar no frontend (aprovados vs pendentes)
    posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
    coments = conn.execute("SELECT * FROM comentarios ORDER BY data ASC").fetchall()
    conn.close()
    return jsonify({
        "membros": [dict(u) for u in users], 
        "posts": [dict(p) for p in posts],
        "comentarios": [dict(c) for c in coments]
    })

@app.route('/api/postar', methods=['POST'])
def postar():
    try:
        autor = request.form.get('autor')
        titulo = request.form.get('titulo')
        conteudo = request.form.get('conteudo')
        cargo = request.form.get('cargo')
        file = request.files.get('file')
        
        # LÓGICA DE MODERAÇÃO: Se for Humano, o post fica 'pendente'
        status = 'pendente' if cargo == 'Humano' else 'aprovado'
        
        filename = None
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        conn = get_db()
        conn.execute("INSERT INTO posts (autor, titulo, conteudo, cargo_autor, anexo, status) VALUES (?, ?, ?, ?, ?, ?)", 
                     (autor, titulo, conteudo, cargo, filename, status))
        conn.commit()
        conn.close()
        return jsonify({"msg": "Enviado!", "status": status}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/api/alterar_cargo', methods=['POST'])
def alterar_cargo():
    d = request.json
    # Apenas cargos de Staff (Moderador, Admin, Entidade) podem mudar cargos
    staff_cargos = ["MODERADOR", "ADMIN", "ENTIDADE"]
    if any(x in d['admin_cargo'].upper() for x in staff_cargos):
        conn = get_db()
        conn.execute("UPDATE usuarios SET cargo=? WHERE user=?", (d['novo_cargo'], d['target_user']))
        conn.commit()
        conn.close()
        return jsonify({"msg": "Hierarquia atualizada!"}), 200
    return jsonify({"erro": "Você não tem autoridade para isso!"}), 403

# (Rotas de mensagens, buscar_perfil e comentários mantidas conforme original)
@app.route('/api/atualizar_foto', methods=['POST'])
def atualizar_foto():
    file = request.files.get('foto')
    user = request.form.get('user')
    if file and user:
        filename = f"avatar_{user}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = get_db()
        conn.execute("UPDATE usuarios SET foto=? WHERE user=?", (filename, user))
        conn.commit()
        conn.close()
        return jsonify({"foto": filename}), 200
    return jsonify({"erro": "Falha"}), 400

@app.route('/api/comentar', methods=['POST'])
def comentar():
    d = request.json
    conn = get_db()
    conn.execute("INSERT INTO comentarios (post_id, autor, texto) VALUES (?, ?, ?)",
                 (d['post_id'], d['autor'], d['texto']))
    conn.commit()
    conn.close()
    return jsonify({"msg": "OK"})

@app.route('/api/enviar_mensagem', methods=['POST'])
def enviar_mensagem():
    remetente = request.form.get('remetente')
    destinatario = request.form.get('destinatario')
    texto = request.form.get('texto')
    file = request.files.get('file')
    filename = None
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    conn = get_db()
    conn.execute("INSERT INTO mensagens (remetente, destinatario, texto, anexo) VALUES (?, ?, ?, ?)",
                 (remetente, destinatario, texto, filename))
    conn.commit()
    conn.close()
    return jsonify({"msg": "OK"})

@app.route('/api/ler_mensagens/<user1>/<user2>', methods=['GET'])
def ler_mensagens(user1, user2):
    conn = get_db()
    msgs = conn.execute('''SELECT * FROM mensagens WHERE 
        (remetente=? AND destinatario=?) OR (remetente=? AND destinatario=?) 
        ORDER BY data ASC''', (user1, user2, user2, user1)).fetchall()
    conn.close()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/perfil/<username>', methods=['GET'])
def buscar_perfil(username):
    conn = get_db()
    user = conn.execute("SELECT user, cargo, ip, online, foto, criado_em FROM usuarios WHERE user=?", (username,)).fetchone()
    conn.close()
    if user: return jsonify(dict(user)), 200
    return jsonify({"erro": "Não encontrado"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
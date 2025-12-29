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
    
    # 1. Tabela de Usuários (Adicionado 'dispositivo')
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios 
        (id INTEGER PRIMARY KEY, user TEXT UNIQUE, senha TEXT, cargo TEXT, ip TEXT, 
         online INTEGER DEFAULT 0, foto TEXT, criado_em DATETIME DEFAULT CURRENT_TIMESTAMP, 
         banido INTEGER DEFAULT 0, dispositivo TEXT DEFAULT 'PC')''')
    
    # Verificar se a coluna dispositivo existe (para não quebrar bancos antigos)
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN dispositivo TEXT DEFAULT 'PC'")
    except:
        pass

    # 2. Tabela de Posts
    cursor.execute('''CREATE TABLE IF NOT EXISTS posts 
        (id INTEGER PRIMARY KEY, autor TEXT, titulo TEXT, conteudo TEXT, cargo_autor TEXT, anexo TEXT, status TEXT DEFAULT 'aprovado')''')
    
    # 3. Tabela de Mensagens
    cursor.execute('''CREATE TABLE IF NOT EXISTS mensagens 
        (id INTEGER PRIMARY KEY, remetente TEXT, destinatario TEXT, texto TEXT, anexo TEXT, data DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 4. Tabela de Comentários
    cursor.execute('''CREATE TABLE IF NOT EXISTS comentarios 
        (id INTEGER PRIMARY KEY, post_id INTEGER, autor TEXT, texto TEXT, data DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # ENTIDADE ABSOLUTA
    cursor.execute("INSERT OR REPLACE INTO usuarios (id, user, senha, cargo, ip, dispositivo) VALUES (1, 'Padoca6i', 'tuquedeixamano007', 'ENTIDADE ABSOLUTA', '0.0.0.0', 'PC')")
    
    conn.commit()
    conn.close()
    print(">>> SISTEMA ATUALIZADO: DETECÇÃO MOBILE ATIVA.")

def get_device_type():
    ua = request.headers.get('User-Agent', '').lower()
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
        return "Celular"
    return "PC"

init_db()

# --- ROTAS DE MODERAÇÃO ---

@app.route('/api/admin/gerenciar_post', methods=['POST'])
def gerenciar_post():
    d = request.json
    conn = get_db()
    if d['acao'] == 'aceitar':
        conn.execute("UPDATE posts SET status='aprovado' WHERE id=?", (d['post_id'],))
    else:
        conn.execute("DELETE FROM posts WHERE id=?", (d['post_id'],))
        conn.execute("DELETE FROM comentarios WHERE post_id=?", (d['post_id'],))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Ação executada"}), 200

@app.route('/api/admin/espionar/<alvo>', methods=['GET'])
def espionar(alvo):
    conn = get_db()
    msgs = conn.execute("SELECT * FROM mensagens WHERE remetente=? OR destinatario=? ORDER BY data DESC", (alvo, alvo)).fetchall()
    conn.close()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/admin/banir', methods=['POST'])
def banir_usuario():
    d = request.json
    conn = get_db()
    conn.execute("UPDATE usuarios SET banido=1, online=0 WHERE user=?", (d['target_user'],))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Usuário banido!"}), 200

# --- ROTAS ORIGINAIS ---

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/cadastro', methods=['POST'])
def cadastro():
    d = request.json
    ip = request.remote_addr
    dispositivo = get_device_type()
    conn = get_db()
    cursor = conn.cursor()
    user_exists = cursor.execute("SELECT * FROM usuarios WHERE user = ?", (d['user'],)).fetchone()
    if user_exists:
        conn.close()
        return jsonify({"erro": "Nome em uso!"}), 400
    try:
        cursor.execute("INSERT INTO usuarios (user, senha, cargo, ip, dispositivo) VALUES (?, ?, ?, ?, ?)",
                       (d['user'], d['senha'], 'Humano', ip, dispositivo))
        conn.commit()
        return jsonify({"msg": "Registrado!"}), 201
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    dispositivo = get_device_type()
    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE user=? AND senha=?", (d['user'], d['senha'])).fetchone()
    if user:
        if user['banido'] == 1:
            conn.close()
            return jsonify({"erro": "Você foi banido!"}), 403
        
        # Atualiza status online e o dispositivo atual
        conn.execute("UPDATE usuarios SET online=1, dispositivo=? WHERE user=?", (dispositivo, user['user']))
        conn.commit()
        userData = dict(user)
        userData['dispositivo'] = dispositivo # Retorna o dispositivo atualizado
        conn.close()
        return jsonify(userData), 200
    conn.close()
    return jsonify({"erro": "Incorreto!"}), 401

@app.route('/api/comunidade', methods=['GET'])
def comunidade():
    conn = get_db()
    users = conn.execute("SELECT user, cargo, online, foto, criado_em, ip, dispositivo FROM usuarios WHERE banido=0").fetchall()
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
    staff_cargos = ["MODERADOR", "ADMIN", "ENTIDADE"]
    if any(x in d['admin_cargo'].upper() for x in staff_cargos):
        conn = get_db()
        conn.execute("UPDATE usuarios SET cargo=? WHERE user=?", (d['novo_cargo'], d['target_user']))
        conn.commit()
        conn.close()
        return jsonify({"msg": "Hierarquia atualizada!"}), 200
    return jsonify({"erro": "Sem autoridade!"}), 403

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
    user = conn.execute("SELECT user, cargo, ip, online, foto, criado_em, dispositivo FROM usuarios WHERE user=?", (username,)).fetchone()
    conn.close()
    if user: return jsonify(dict(user)), 200
    return jsonify({"erro": "Não encontrado"}), 404

if __name__ == '__main__':
    # No Render, use a porta definida pela variável de ambiente
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

from flask import Flask, render_template, make_response, redirect, url_for, request, jsonify,session, flash, send_file, make_response
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from flask import current_app


import zipfile
import tempfile
import base64
import requests
# from weasyprint import HTML
import os
import uuid

from mysql.connector import Error
from config import DB_CONFIG

import random

from flask import session


from io import BytesIO


app = Flask(__name__)

app.secret_key = "a4s4powerful"  # Clé secrète pour gérer les sessions


UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---- Fonction utilitaire pour sauvegarder les fichiers ----
def save_file(field_name):
    f = request.files.get(field_name)
    if f and f.filename:
        filename = f"{uuid.uuid4()}_{secure_filename(f.filename)}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        f.save(path)
        return filename
    return None

# Connexion à la base de données MySQL
def connect_db():
    return mysql.connector.connect(**DB_CONFIG)

@app.context_processor
def inject_nom_etablissement():
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT nom_etablissement FROM etablissement LIMIT 1")
    row = cur.fetchone()
    conn.close()
    nom_etablissement = row['nom_etablissement'] if row else "Nom de la boutique"
    
    return dict(nom_etablissement=nom_etablissement)


# ---- Route d'accueil ----
@app.route('/')
def index():
    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Récupérer tous les bijoux
    cur.execute("SELECT * FROM bijoux ORDER BY id DESC")
    bijoux = cur.fetchall()

    conn.close()

    # Année actuelle pour le footer
    from datetime import datetime
    current_year = datetime.now().year

    return render_template('index.html', bijoux=bijoux, current_year=current_year)


# ----------------------- AUTHENTIFICATION ------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nom = request.form['nom']
        password = request.form['password']
        conn = connect_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE nom=%s", (nom,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_nom'] = user['nom']
            session['user_role'] = user['role']

            return redirect(url_for('dashboard'))
        flash("Nom d'utilisateur ou mot de passe incorrect", "danger")
    return render_template('login.html')

# ----------------------- CREATION COMPTE UTILISATEUR ------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    # Récupérer toutes les classes pour les afficher dans le formulaire


    if request.method == 'POST':
        nom = request.form['nom']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        
        cur.execute("INSERT INTO users (nom, email, password, role) VALUES (%s, %s, %s, %s)", 
                    (nom, email, password, role))
        conn.commit()
        conn.close()
        flash("Inscription réussie", "success")
        return redirect(url_for('login'))
    return render_template('register.html')


# ----------------------- PROFIL UTILISATEUR ------------------------
@app.route('/profil', methods=['GET', 'POST'])
def profil():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT nom, email FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()

    if request.method == 'POST':
        nom = request.form['nom']
        email = request.form['email']
        password = request.form['password']

        if password:
            hashed = generate_password_hash(password)
            cur.execute("UPDATE users SET nom=%s, email=%s, password=%s WHERE id=%s", (nom, email, hashed, session['user_id']))
        else:
            cur.execute("UPDATE users SET nom=%s, email=%s WHERE id=%s", (nom, email, session['user_id']))

        conn.commit()
        flash("Profil mis à jour avec succès", "success")
        return redirect(url_for('login'))

    return render_template('profil.html', user=user)


# ----------------------- SUPPRIMER UN COMPTE UTILISATEUR ------------------------

@app.route('/supprimer_compte', methods=['POST'])
def supprimer_compte():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("DELETE FROM users WHERE id = %s", (session['user_id'],))
    conn.commit()

    session.clear()
    flash("Compte supprimé avec succès", "success")
    return redirect(url_for('login'))

# ----------------------- DECONNEXION ------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ----------------------- Dashboard ------------------------
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Infos de l'établissement
    cur.execute("SELECT nom_etablissement, adresse, commune, province FROM etablissement LIMIT 1")
    etab = cur.fetchone()
    etablissement = {
        'nom': etab['nom_etablissement'],
        'adresse': etab['adresse'],
        'commune': etab['commune'],
        'province': etab['province']
    }

    # Bijoux en rupture de stock (quantite = 0)
    cur.execute("SELECT nom FROM bijoux WHERE quantite = 0")
    bijoux_rupture = cur.fetchall()

    # Bijoux en stock faible (quantite <= seuil_min mais > 0)
    seuil_min = 5
    cur.execute("SELECT nom, quantite FROM bijoux WHERE quantite <= %s AND quantite > 0", (seuil_min,))
    bijoux_faible = cur.fetchall()

    conn.close()

    return render_template('dashboard.html',
                           etablissement=etablissement,
                           bijoux_rupture=bijoux_rupture,
                           bijoux_faible=bijoux_faible)



# ----------------------- CRUD: ETABLISSEMENT ------------------------

@app.route('/etablissement')
def gestion_etablissement():
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM etablissement")
    etablissements = cur.fetchall()
    conn.commit()

    conn.close()
    return render_template("manage_shop.html", etablissements=etablissements)


@app.route('/add_etablissement', methods=['POST'])
def add_etablissement():
    nom_etablissement = request.form['nom_etablissement']
    adresse = request.form['adresse']
    commune = request.form['commune']
    province = request.form['province']
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("INSERT INTO etablissement (nom_etablissement, adresse, commune, province) VALUES (%s, %s, %s, %s)", (nom_etablissement, adresse, commune, province,))
    conn.commit()
    conn.close()
    return redirect(url_for('gestion_etablissement'))


@app.route('/delete_etablissement/<int:id>')
def delete_etablissement(id):
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("DELETE FROM etablissement WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('gestion_etablissement'))


@app.route('/edit_etablissement/<int:id>', methods=['GET', 'POST'])
def edit_etablissement(id):
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    if request.method == 'POST':
        nom_etablissement = request.form['nom_etablissement']
        adresse = request.form['adresse']
        commune = request.form['commune']
        province = request.form['province']
        cur.execute("UPDATE etablissement SET nom_etablissement = %s, adresse = %s, commune = %s, province = %s WHERE id = %s", (nom_etablissement, adresse, commune, province, id))
        conn.commit()
        conn.close()
        return redirect(url_for('gestion_etablissement'))

    cur.execute("SELECT * FROM etablissement WHERE id = %s", (id,))
    etablissement = cur.fetchone()
    conn.commit()


    col_names = [desc[0] for desc in cur.description]

    conn.close()
    return render_template("edit_shop.html", etablissement=etablissement)

# ----------------------- CRUD: BIJOUX ------------------------

@app.route('/bijoux')
def manage_jewels():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM bijoux ORDER BY id DESC")
    bijoux = cur.fetchall()
    conn.close()

    return render_template("manage_jewels.html", bijoux=bijoux)


# ---- Ajouter un bijou ----
@app.route('/add_bijou', methods=['POST'])
def add_bijou():

    nom = request.form['nom']
    caracteristiques = request.form['caracteristiques']
    prix = request.form['prix']
    quantite = request.form['quantite']   # <-- Ajout

    # Sauvegarde de la photo
    photo = save_file("photo")

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        INSERT INTO bijoux (nom, caracteristiques, prix, quantite, photo)
        VALUES (%s, %s, %s, %s, %s)
    """, (nom, caracteristiques, prix, quantite, photo))

    conn.commit()
    conn.close()

    flash("Bijou ajouté avec succès", "success")
    return redirect(url_for('manage_jewels'))


# ---- Modifier un bijou ----
@app.route('/edit_bijou/<int:id>', methods=['GET', 'POST'])
def edit_bijou(id):

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # ----- Soumission du formulaire -----
    if request.method == 'POST':
        nom = request.form['nom']
        caracteristiques = request.form['caracteristiques']
        prix = request.form['prix']
        quantite = request.form['quantite']   # <-- Ajout

        # Vérifier si nouvelle photo
        new_photo = save_file("photo")

        if new_photo:
            cur.execute("""
                UPDATE bijoux 
                SET nom=%s, caracteristiques=%s, prix=%s, quantite=%s, photo=%s
                WHERE id=%s
            """, (nom, caracteristiques, prix, quantite, new_photo, id))
        else:
            cur.execute("""
                UPDATE bijoux 
                SET nom=%s, caracteristiques=%s, prix=%s, quantite=%s
                WHERE id=%s
            """, (nom, caracteristiques, prix, quantite, id))

        conn.commit()
        conn.close()

        flash("Bijou modifié avec succès", "success")
        return redirect(url_for('manage_jewels'))

    # ----- Afficher le formulaire -----
    cur.execute("SELECT * FROM bijoux WHERE id = %s", (id,))
    bijou = cur.fetchone()
    conn.close()

    return render_template("edit_jewel.html", bijou=bijou)


# ---- Supprimer un bijou ----
@app.route('/delete_bijou/<int:id>')
def delete_bijou(id):

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Supprimer d'abord la photo associée
    cur.execute("SELECT photo FROM bijoux WHERE id=%s", (id,))
    row = cur.fetchone()

    if row and row['photo']:
        try:
            os.remove(os.path.join("static/uploads", row['photo']))
        except:
            pass

    # Supprimer le bijou
    cur.execute("DELETE FROM bijoux WHERE id = %s", (id,))
    conn.commit()
    conn.close()

    flash("Bijou supprimé avec succès", "success")
    return redirect(url_for('manage_jewels'))


# ----------------------- CRUD: MOUVEMENTS ------------------------

@app.route('/movement')
def manage_movement():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Récupérer tous les mouvements avec les infos bijoux
    cur.execute("""
        SELECT m.*, b.nom AS bijou_nom, b.quantite AS stock_actuel
        FROM movement m
        JOIN bijoux b ON m.bijou_id = b.id
        ORDER BY m.created_at DESC
    """)
    mouvements = cur.fetchall()

    # Récupérer tous les bijoux pour le dropdown
    cur.execute("SELECT id, nom, quantite FROM bijoux ORDER BY nom")
    bijoux = cur.fetchall()

    conn.close()
    return render_template("manage_supply.html", mouvements=mouvements, bijoux=bijoux)


# ---- Ajouter un mouvement ----
@app.route('/add_movement', methods=['POST'])
def add_movement():
    bijou_id = request.form['bijou_id']
    type_mvt = request.form['type']
    quantite = int(request.form['quantite'])
    description = request.form.get('description', '')

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Vérifier le stock actuel pour les sorties
    if type_mvt == 'sortie':
        cur.execute("SELECT quantite FROM bijoux WHERE id=%s", (bijou_id,))
        bijou = cur.fetchone()
        if not bijou or bijou['quantite'] < quantite:
            conn.close()
            flash("Stock insuffisant pour cette sortie !", "danger")
            return redirect(url_for('manage_movement'))

    # Insérer le mouvement
    cur.execute("""
        INSERT INTO movement (bijou_id, type, quantite, description)
        VALUES (%s, %s, %s, %s)
    """, (bijou_id, type_mvt, quantite, description))

    # Mettre à jour le stock dans bijoux
    if type_mvt == 'entree':
        cur.execute("UPDATE bijoux SET quantite = quantite + %s WHERE id = %s", (quantite, bijou_id))
    else:
        cur.execute("UPDATE bijoux SET quantite = quantite - %s WHERE id = %s", (quantite, bijou_id))

    conn.commit()
    conn.close()

    flash("Mouvement enregistré avec succès", "success")
    return redirect(url_for('manage_movement'))


# ---- Modifier un mouvement ----
@app.route('/edit_movement/<int:id>', methods=['POST'])
def edit_movement(id):
    bijou_id = request.form['bijou_id']
    type_mvt = request.form['type']
    quantite = int(request.form['quantite'])
    description = request.form.get('description', '')

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Récupérer ancien mouvement pour ajuster stock
    cur.execute("SELECT * FROM movement WHERE id=%s", (id,))
    old_mvt = cur.fetchone()

    if not old_mvt:
        conn.close()
        flash("Mouvement introuvable", "danger")
        return redirect(url_for('manage_movement'))

    # Annuler l'effet de l'ancien mouvement
    if old_mvt['type'] == 'entree':
        cur.execute("UPDATE bijoux SET quantite = quantite - %s WHERE id=%s", (old_mvt['quantite'], old_mvt['bijou_id']))
    else:
        cur.execute("UPDATE bijoux SET quantite = quantite + %s WHERE id=%s", (old_mvt['quantite'], old_mvt['bijou_id']))

    # Vérifier stock pour sortie
    if type_mvt == 'sortie':
        cur.execute("SELECT quantite FROM bijoux WHERE id=%s", (bijou_id,))
        bijou = cur.fetchone()
        if bijou['quantite'] < quantite:
            # Restaurer ancien stock
            if old_mvt['type'] == 'entree':
                cur.execute("UPDATE bijoux SET quantite = quantite + %s WHERE id=%s", (old_mvt['quantite'], old_mvt['bijou_id']))
            else:
                cur.execute("UPDATE bijoux SET quantite = quantite - %s WHERE id=%s", (old_mvt['quantite'], old_mvt['bijou_id']))
            conn.close()
            flash("Stock insuffisant pour cette sortie !", "danger")
            return redirect(url_for('manage_movement'))

    # Mettre à jour le mouvement
    cur.execute("""
        UPDATE movement SET bijou_id=%s, type=%s, quantite=%s, description=%s
        WHERE id=%s
    """, (bijou_id, type_mvt, quantite, description, id))

    # Appliquer le nouvel effet sur stock
    if type_mvt == 'entree':
        cur.execute("UPDATE bijoux SET quantite = quantite + %s WHERE id=%s", (quantite, bijou_id))
    else:
        cur.execute("UPDATE bijoux SET quantite = quantite - %s WHERE id=%s", (quantite, bijou_id))

    conn.commit()
    conn.close()

    flash("Mouvement modifié avec succès", "success")
    return redirect(url_for('manage_movement'))


# ---- Supprimer un mouvement ----
@app.route('/delete_movement/<int:id>')
def delete_movement(id):
    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Récupérer le mouvement
    cur.execute("SELECT * FROM movement WHERE id=%s", (id,))
    mvt = cur.fetchone()
    if mvt:
        # Revenir sur le stock
        if mvt['type'] == 'entree':
            cur.execute("UPDATE bijoux SET quantite = quantite - %s WHERE id=%s", (mvt['quantite'], mvt['bijou_id']))
        else:
            cur.execute("UPDATE bijoux SET quantite = quantite + %s WHERE id=%s", (mvt['quantite'], mvt['bijou_id']))

        # Supprimer le mouvement
        cur.execute("DELETE FROM movement WHERE id=%s", (id,))
        conn.commit()

    conn.close()
    flash("Mouvement supprimé avec succès", "success")
    return redirect(url_for('manage_movement'))


# ----------------------- BIJOUX EN RUPTURE DE STOCK (quantité = 0) ------------------------
@app.route('/supply_low')
def supply_low():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    
    # Récupérer uniquement les bijoux dont la quantité = 0
    cur.execute("SELECT * FROM bijoux WHERE quantite = 0 ORDER BY nom ASC")
    bijoux = cur.fetchall()
    conn.close()

    return render_template('manage_supply_low.html', bijoux=bijoux)



# ----------------------- STATISTIQUES DES VENTES ------------------------


@app.route('/statistics', methods=['GET', 'POST'])
def statistics():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cur = conn.cursor(dictionary=True)

    # Charger les bijoux pour le filtre
    cur.execute("SELECT id, nom FROM bijoux ORDER BY nom ASC")
    bijoux = cur.fetchall()

    # Lecture des filtres
    filter_type = "all"
    selected_bijou = ""

    if request.method == "POST":
        filter_type = request.form.get("periode", "all")
        selected_bijou = request.form.get("bijou", "")

    # Filtre temps SQL
    date_filter_sql = ""
    if filter_type == "jour":
        date_filter_sql = "AND DATE(m.created_at) = CURDATE()"
    elif filter_type == "semaine":
        date_filter_sql = "AND YEARWEEK(m.created_at) = YEARWEEK(CURDATE())"
    elif filter_type == "mois":
        date_filter_sql = "AND YEAR(m.created_at) = YEAR(CURDATE()) AND MONTH(m.created_at) = MONTH(CURDATE())"
    elif filter_type == "annee":
        date_filter_sql = "AND YEAR(m.created_at) = YEAR(CURDATE())"

    bijou_filter_sql = ""
    if selected_bijou:
        bijou_filter_sql = f"AND m.id = {selected_bijou}"

    # -------------------------------
    # 1️⃣ Bijoux les PLUS VENDUS
    # -------------------------------
    query_top_sellers = f"""
        SELECT b.id, b.nom,
            SUM(CASE WHEN m.type='sortie' THEN m.quantite ELSE 0 END) AS total_sorties
        FROM movement m
        INNER JOIN bijoux b ON b.id = m.bijou_id
        WHERE 1=1 {date_filter_sql} {bijou_filter_sql}
        GROUP BY b.id, b.nom
        HAVING total_sorties > 0
        ORDER BY total_sorties DESC
        LIMIT 5
    """
    cur.execute(query_top_sellers)
    top_sellers = cur.fetchall()

    # -------------------------------
    # 2️⃣ Bijoux les MOINS VENDUS
    # -------------------------------
    query_low_sellers = f"""
        SELECT b.id, b.nom,
            COALESCE(SUM(CASE WHEN m.type='sortie' THEN m.quantite END), 0) AS total_sorties
        FROM bijoux b
        LEFT JOIN movement m ON b.id = m.bijou_id
        WHERE 1=1 {bijou_filter_sql.replace('m.', 'b.')}
        GROUP BY b.id, b.nom
        HAVING total_sorties = 0
        ORDER BY b.nom ASC
        LIMIT 5
    """
    cur.execute(query_low_sellers)
    low_sellers = cur.fetchall()

    conn.close()

    return render_template(
        "statistics.html",
        bijoux=bijoux,
        top_sellers=top_sellers,
        low_sellers=low_sellers,
        filter_type=filter_type,
        selected_bijou=selected_bijou
    )


# ----------------------- RUN ------------------------

if __name__ == '__main__':
    app.run(debug=True)
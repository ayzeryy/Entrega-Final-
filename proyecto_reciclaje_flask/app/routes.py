import os
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from .extensions import mysql


main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('login.html')

@main.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        correo = request.form['correo'].strip().lower()
        contraseña = request.form['contraseña'].strip()
        es_admin = 1 if request.form.get('es_admin') == 'on' else 0

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        existente = cursor.fetchone()

        if existente is None:
            cursor.execute("""
                INSERT INTO usuarios (correo, contraseña, es_admin)
                VALUES (%s, %s, %s)
            """, (correo, contraseña, es_admin))
            mysql.connection.commit()
            flash("Usuario registrado exitosamente.", "success")
            return redirect(url_for('main.index'))
        else:
            flash("El correo ya está registrado.", "danger")
        cursor.close()
    return render_template('registro.html')

@main.route('/login', methods=['POST'])
def login():
    correo = request.form['correo'].strip().lower()
    contraseña = request.form['contraseña'].strip()

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id_usuario, es_admin FROM usuarios WHERE correo = %s AND contraseña = %s", (correo, contraseña))
    usuario = cursor.fetchone()
    cursor.close()

    if usuario:
        session['usuario_id'] = usuario[0]
        session['es_admin'] = usuario[1]
        flash("Inicio de sesión exitoso.", "success")

        if usuario[1]:  
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.panel_usuario'))  
    else:
        flash("Correo o contraseña incorrectos.", "danger")
        return redirect(url_for('main.index'))

@main.route('/panel_usuario')
def panel_usuario():
    if 'usuario_id' not in session or session.get('es_admin'):
        return redirect(url_for('main.dashboard'))  

    return render_template('usuario_panel.html')


@main.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('main.index'))
    return render_template('dashboard.html', es_admin=session.get('es_admin', 0))

@main.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for('main.index'))


@main.route('/buscar', methods=['GET', 'POST'])
def buscar():
    if 'usuario_id' not in session:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        nombre_residuo = request.form['residuo'].strip().lower()
        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT r.id_residuo, r.descripcion, b.nombre AS nombre_bote, b.color
            FROM residuos r
            JOIN botes b ON r.id_bote = b.id_bote
            WHERE LOWER(r.nombre) = %s
        """, (nombre_residuo,))

        resultado = cursor.fetchone()

        if resultado:
            id_residuo, descripcion, nombre_bote, color_bote = resultado

            
            cursor.execute("""
                INSERT INTO historial_busqueda (id_usuario, id_residuo)
                VALUES (%s, %s)
            """, (session['usuario_id'], id_residuo))

            cursor.execute("""
                INSERT INTO puntos (id_usuario, cantidad, fecha_otorgado)
                VALUES (%s, 1, %s)
            """, (session['usuario_id'], datetime.now()))

            mysql.connection.commit()

            datos_residuo = {
                'descripcion': descripcion,
                'bote': nombre_bote,
                'color': color_bote
            }

            cursor.close()
            flash("Residuo registrado correctamente. Se asignó 1 punto.", "success")
            return render_template('buscar.html', resultado=datos_residuo)

        cursor.close()
        flash("Residuo no encontrado en la base de datos.", "warning")
        return render_template('buscar.html', resultado=None)

    
    return render_template('buscar.html', resultado=None)


@main.route('/puntos')
def ver_puntos():
    if 'usuario_id' not in session:
        return redirect(url_for('main.index'))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT SUM(cantidad) FROM puntos
        WHERE id_usuario = %s
        AND fecha_otorgado >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    """, (session['usuario_id'],))
    resultado = cursor.fetchone()
    cursor.close()

    puntos = resultado[0] if resultado[0] is not None else 0
    return render_template('puntos.html', puntos=puntos)

@main.route('/cargar_csv', methods=['GET', 'POST'])
def cargar_csv():
    if 'usuario_id' not in session or not session.get('es_admin'):
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        archivo = request.files['archivo']
        if archivo and archivo.filename.endswith('.csv'):
            df = pd.read_csv(archivo)

            columnas_esperadas = {'nombre', 'descripcion', 'id_bote'}
            if not columnas_esperadas.issubset(df.columns):
                flash("El archivo debe tener las columnas: nombre, descripcion, id_bote.", "danger")
                return redirect(url_for('main.cargar_csv'))

            df = df.dropna(subset=['nombre', 'descripcion', 'id_bote'])
            df['nombre'] = df['nombre'].str.strip().str.lower()

            
            residuos_temporales = df.to_dict(orient='records')
            session['residuos_preview'] = residuos_temporales

            return render_template('confirmar_csv.html', residuos=residuos_temporales)

        flash("Por favor sube un archivo .csv válido.", "danger")

    return render_template('cargar_csv.html')


@main.route('/confirmar_csv', methods=['POST'])
def confirmar_csv():
    if 'usuario_id' not in session or not session.get('es_admin'):
        return redirect(url_for('main.dashboard'))

    residuos = session.get('residuos_preview', [])
    if not residuos:
        flash("No hay datos para insertar.", "warning")
        return redirect(url_for('main.cargar_csv'))

    cursor = mysql.connection.cursor()
    agregados = 0
    omitidos = 0

    for fila in residuos:
        cursor.execute("SELECT COUNT(*) FROM residuos WHERE nombre = %s", (fila["nombre"],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO residuos (nombre, descripcion, id_bote)
                VALUES (%s, %s, %s)
            """, (fila["nombre"], fila["descripcion"], int(fila["id_bote"])))
            agregados += 1
        else:
            omitidos += 1

    mysql.connection.commit()
    cursor.close()
    session.pop('residuos_preview', None)

    flash(f"Se agregaron {agregados} residuos nuevos. {omitidos} duplicados omitidos.", "info")
    return redirect(url_for('main.dashboard'))



@main.route('/estadisticas')
def estadisticas():
    if 'usuario_id' not in session or not session.get('es_admin'):
        return redirect(url_for('main.dashboard'))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT hb.fecha_busqueda, r.nombre AS residuo, b.nombre AS bote
        FROM historial_busqueda hb
        JOIN residuos r ON hb.id_residuo = r.id_residuo
        JOIN botes b ON r.id_bote = b.id_bote
        WHERE hb.fecha_busqueda >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    """)

    datos = cursor.fetchall()
    columnas = ['fecha', 'residuo', 'bote']
    df = pd.DataFrame(datos, columns=columnas)
    cursor.close()

    if df.empty:
        flash("No hay datos en los últimos 30 días.", "warning")
        return redirect(url_for('main.dashboard'))

    resumen = {
        'residuos': df['residuo'].value_counts(),
        'botes': df['bote'].value_counts()
    }

    
    os.makedirs("app/static/graficas", exist_ok=True)

    
    plt.figure(figsize=(5,5))
    df['residuo'].value_counts().plot.pie(autopct='%1.1f%%', startangle=90)
    plt.title("Proporción de residuos")
    plt.ylabel("")
    pastel_path = "app/static/graficas/pastel.png"
    plt.savefig(pastel_path)
    plt.close()

    
    plt.figure(figsize=(6,4))
    df['bote'].value_counts().plot(kind='bar', color='skyblue')
    plt.title("Uso de botes")
    plt.xlabel("Tipo de bote")
    plt.ylabel("Cantidad")
    barras_path = "app/static/graficas/barras.png"
    plt.tight_layout()
    plt.savefig(barras_path)
    plt.close()

    return render_template('estadisticas.html', resumen=resumen, pastel='graficas/pastel.png', barras='graficas/barras.png')

@main.route('/agregar_residuo', methods=['GET', 'POST'])
def agregar_residuo():
    if 'usuario_id' not in session or not session.get('es_admin'):
        return redirect(url_for('main.dashboard'))

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id_bote, nombre, color FROM botes")
    botes = cursor.fetchall()

    if request.method == 'POST':
        nombre = request.form['nombre'].strip().lower()
        descripcion = request.form['descripcion'].strip()
        id_bote = request.form['id_bote']

        cursor.execute("SELECT COUNT(*) FROM residuos WHERE nombre = %s", (nombre,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO residuos (nombre, descripcion, id_bote)
                VALUES (%s, %s, %s)
            """, (nombre, descripcion, id_bote))
            mysql.connection.commit()
            flash("Residuo agregado correctamente.", "success")
            return redirect(url_for('main.dashboard'))
        else:
            flash("Ese residuo ya existe.", "danger")

    cursor.close()
    return render_template('agregar_residuo.html', botes=botes)

@main.route('/perfil')
def perfil():
    if 'usuario_id' not in session:
        return redirect(url_for('main.index'))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT correo, es_admin FROM usuarios WHERE id_usuario = %s
    """, (session['usuario_id'],))
    usuario = cursor.fetchone()
    cursor.close()

    return render_template('perfil.html', correo=usuario[0], es_admin=usuario[1])


@main.route('/historial')
def historial():
    if 'usuario_id' not in session:
        return redirect(url_for('main.index'))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT r.nombre, b.nombre, b.color, hb.fecha_busqueda
        FROM historial_busqueda hb
        JOIN residuos r ON hb.id_residuo = r.id_residuo
        JOIN botes b ON r.id_bote = b.id_bote
        WHERE hb.id_usuario = %s
        ORDER BY hb.fecha_busqueda DESC
    """, (session['usuario_id'],))

    datos_historial = cursor.fetchall()
    cursor.close()

    return render_template('historial.html', historial=datos_historial)
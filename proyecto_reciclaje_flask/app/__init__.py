from flask import Flask
from .extensions import mysql

def create_app():
    app = Flask(__name__)
    app.secret_key = 'tu_clave_secreta_segura'

    # Configuración de la base de datos MySQL
    app.config['MYSQL_HOST'] = 'localhost'
    app.config['MYSQL_USER'] = 'root'
    app.config['MYSQL_PASSWORD'] = 'Janpapi741A@1'
    app.config['MYSQL_DB'] = 'reciclaje_db'

    mysql.init_app(app)

    from .routes import main
    app.register_blueprint(main)

    return app
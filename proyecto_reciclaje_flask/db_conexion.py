import mysql.connector

def conectar():
    conexion = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Janpapi741A@1",
        database="reciclaje_db"  
    )
    return conexion
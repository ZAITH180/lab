import sqlite3
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

DB_NAME = "impuestos.db"

class Conexion:
    def __init__(self):
        self.db = DB_NAME

    def conectar(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        # Soporte para Decimal
        sqlite3.register_adapter(Decimal, lambda d: str(d))
        sqlite3.register_converter("DECIMAL", lambda s: Decimal(s.decode()))
        return conn

    def ejecutar_consulta(self, sql, params=()):
        conn = self.conectar()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
        return rows

    def ejecutar_escritura(self, sql, params=(), many=False):
        conn = self.conectar()
        try:
            cur = conn.cursor()
            if many:
                cur.executemany(sql, params)
            else:
                cur.execute(sql, params)
            conn.commit()
            last_id = cur.lastrowid
            conn.close()
            return last_id
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    def ejecutar_transaccion(self, operaciones):
        """ operaciones = [(sql, params),...] para RF - guardar cliente, periodo y asignación en una transacción """
        conn = self.conectar()
        try:
            cur = conn.cursor()
            for sql, params in operaciones:
                cur.execute(sql, params)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    def init_db(self):
        conn = self.conectar()
        cur = conn.cursor()
        # Clientes - solo empresa para este impuesto
        cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            nit TEXT UNIQUE,
            tipo TEXT CHECK(tipo IN ('empresa','persona')) NOT NULL DEFAULT 'empresa',
            direccion TEXT
        )""")
        # Productos 11801 Comercio y 11802 Industria
        cur.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            codigo TEXT PRIMARY KEY,
            nombre TEXT NOT NULL
        )""")
        # Tarifas con vigencia y producto
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tarifas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_codigo TEXT NOT NULL,
            desde DECIMAL NOT NULL,
            hasta DECIMAL NOT NULL,
            precio_base DECIMAL NOT NULL,
            adicional DECIMAL NOT NULL,
            porcentaje DECIMAL NOT NULL DEFAULT 0,
            vigencia_desde DATE DEFAULT '2020-01-01',
            FOREIGN KEY(producto_codigo) REFERENCES productos(codigo)
        )""")
        # Periodos - Inmutabilidad histórica RF14
        cur.execute("""
        CREATE TABLE IF NOT EXISTS periodos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            producto_codigo TEXT NOT NULL,
            fecha_desde DATE NOT NULL,
            fecha_hasta DATE NOT NULL,
            balance DECIMAL NOT NULL,
            cantidad DECIMAL DEFAULT 1.00,
            precio_mensual DECIMAL NOT NULL,
            subtotal DECIMAL NOT NULL,
            tarifa_aplicada TEXT NOT NULL,
            formula_version TEXT NOT NULL,
            estado TEXT CHECK(estado IN ('Historico','Vigente','Facturado')) DEFAULT 'Vigente',
            usuario TEXT,
            fecha_calculo DATETIME,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo_id INTEGER,
            accion TEXT,
            balance_anterior DECIMAL,
            balance_nuevo DECIMAL,
            usuario TEXT,
            fecha DATETIME
        )""")

        # Seed productos
        cur.execute("INSERT OR IGNORE INTO productos VALUES ('11801','Impuesto a las Actividades Economicas Comercio')")
        cur.execute("INSERT OR IGNORE INTO productos VALUES ('11802','Impuesto a las Actividades Economicas Industria')")

        # Seed tarifas del documento - Asociadas a 11801 y 11802
        cur.execute("SELECT COUNT(*) FROM tarifas")
        if cur.fetchone()[0] == 0:
            tarifas_doc = [
                (0.01, 500.00, 1.50, 0.00, 0),
                (500.01, 1000.00, 1.50, 3.00, 0),
                (1000.01, 2000.00, 3.00, 3.00, 0),
                (2000.01, 3000.00, 6.00, 3.00, 0),
                (3000.01, 6000.00, 9.00, 2.00, 0),
                # RANGO 6000.01 a 8000.00 INTENCIONALMENTE NO CREADO - RF11 debe bloquear
                (8000.01, 18000.00, 15.00, 2.00, 0),
                (18000.01, 30000.00, 39.00, 2.00, 0),
                (30000.01, 60000.00, 63.00, 1.00, 0),
                (60000.01, 100000.00, 93.00, 0.80, 0),
                (100000.01, 200000.00, 125.00, 0.70, 0),
                (200000.01, 300000.00, 195.00, 0.60, 0),
                (300000.01, 400000.00, 255.00, 0.45, 0),
                (400000.01, 500000.00, 300.00, 0.40, 0),
                (500000.01, 1000000.00, 340.00, 0.30, 0),
                (1000000.01, 99999999.99, 490.00, 0.18, 0),
            ]
            for prod in ['11801','11802']:
                for t in tarifas_doc:
                    cur.execute("INSERT INTO tarifas (producto_codigo, desde, hasta, precio_base, adicional, porcentaje) VALUES (?,?,?,?,?,?)",
                                (prod, str(t[0]), str(t[1]), str(t[2]), str(t[3]), str(t[4])))
        conn.commit()
        conn.close()
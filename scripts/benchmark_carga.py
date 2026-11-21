#!/usr/bin/env python3
"""Benchmark reproducible sobre una base SQLite sintética y temporal.

Ejemplo: python scripts/benchmark_carga.py --productos 300000 --ventas 300000
El archivo de base se crea dentro de TEMP y se elimina al terminar.
"""
import argparse
from datetime import date, timedelta
import sqlite3
import tempfile
import time


def medir(con, etiqueta, sql, params=()):
    inicio = time.perf_counter()
    con.execute(sql, params).fetchall()
    segundos = time.perf_counter() - inicio
    print(f'{etiqueta:<34} {segundos:9.3f} s')


def medir_accion(etiqueta, accion):
    inicio = time.perf_counter()
    accion()
    print(f'{etiqueta:<34} {time.perf_counter() - inicio:9.3f} s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--productos', type=int, default=300_000)
    parser.add_argument('--ventas', type=int, default=300_000)
    parser.add_argument('--sin-indices', action='store_true', help='Simula el esquema previo a los índices añadidos.')
    args = parser.parse_args()
    if not 1 <= args.productos <= 1_000_000 or not 1 <= args.ventas <= 3_000_000:
        parser.error('productos: 1..1000000; ventas: 1..3000000')
    with tempfile.TemporaryDirectory(prefix='inventarios_benchmark_') as tmp:
        con = sqlite3.connect(f'{tmp}/sintetica.sqlite3')
        con.execute('PRAGMA journal_mode=OFF')
        con.execute('PRAGMA synchronous=OFF')
        con.executescript('''
            CREATE TABLE producto(id INTEGER PRIMARY KEY, codigo TEXT, nombre TEXT, activo INTEGER, minimo INTEGER, categoria TEXT);
            CREATE TABLE lote(id INTEGER PRIMARY KEY, producto_id INTEGER, cantidad INTEGER, vencimiento TEXT);
            CREATE TABLE venta(id INTEGER PRIMARY KEY, fecha TEXT, total REAL);
            CREATE TABLE movimiento(id INTEGER PRIMARY KEY, fecha TEXT, cantidad INTEGER);
            CREATE TABLE compra(id INTEGER PRIMARY KEY, fecha TEXT, total REAL);
        ''')
        tamano_lote = 10_000
        for inicio in range(1, args.productos + 1, tamano_lote):
            fin = min(inicio + tamano_lote, args.productos + 1)
            productos = ((i, f'COD{i:07}', f'Producto {i:07}', int(i % 100 != 0), 5, 'Categoria') for i in range(inicio, fin))
            con.executemany('INSERT INTO producto VALUES (?,?,?,?,?,?)', productos)
            lotes = ((2 * i - j, i, (i + j) % 20, None if j == 0 else '2027-12-31')
                     for i in range(inicio, fin) for j in range(2))
            con.executemany('INSERT INTO lote VALUES (?,?,?,?)', lotes)
        for inicio in range(1, args.ventas + 1, tamano_lote):
            fin = min(inicio + tamano_lote, args.ventas + 1)
            ventas = ((i, f'{2025 + (i % 2)}-{(i % 12) + 1:02}-15 12:00:00', float(i % 300)) for i in range(inicio, fin))
            con.executemany('INSERT INTO venta VALUES (?,?,?)', ventas)
            movimientos = ((i, f'{2025 + (i % 2)}-{(i % 12) + 1:02}-15 12:00:00', (i % 10) - 5)
                           for i in range(inicio, fin))
            con.executemany('INSERT INTO movimiento VALUES (?,?,?)', movimientos)
        cantidad_compras = max(1, args.productos // 10)
        for inicio in range(1, cantidad_compras + 1, tamano_lote):
            fin = min(inicio + tamano_lote, cantidad_compras + 1)
            compras = ((i, f'{2025 + (i % 2)}-{(i % 12) + 1:02}-15', float(i % 300)) for i in range(inicio, fin))
            con.executemany('INSERT INTO compra VALUES (?,?,?)', compras)
        con.commit()
        # Django crea automáticamente este índice para la clave foránea del lote.
        con.execute('CREATE INDEX lote_producto_idx ON lote(producto_id)')
        if not args.sin_indices:
            con.executescript('CREATE INDEX producto_nombre_idx ON producto(nombre); CREATE INDEX lote_vencimiento_idx ON lote(vencimiento); CREATE INDEX venta_fecha_idx ON venta(fecha); CREATE INDEX movimiento_fecha_idx ON movimiento(fecha); CREATE INDEX compra_fecha_idx ON compra(fecha);')
        print(f'Base sintética: {args.productos:,} productos, {2 * args.productos:,} lotes, {args.ventas:,} ventas')
        if args.sin_indices:
            print('Esquema simulado: sin índices nuevos')
        medir(con, 'Catálogo página 1', 'SELECT * FROM producto ORDER BY nombre,id LIMIT 20')
        medir(con, 'Búsqueda nombre/código', "SELECT * FROM producto WHERE nombre LIKE '%12345%' OR codigo LIKE '%12345%' ORDER BY nombre,id LIMIT 20")
        for pagina in (1, 1000):
            offset = (pagina - 1) * 20
            medir(con, f'Stock página {pagina} (actual/global)', 'SELECT p.id, sum(l.cantidad) FROM producto p LEFT JOIN lote l ON l.producto_id=p.id GROUP BY p.id ORDER BY p.nombre,p.id LIMIT 20 OFFSET ?', (offset,))
            def stock_pagina():
                elegibles = 'p.activo=1 OR EXISTS (SELECT 1 FROM lote l WHERE l.producto_id=p.id AND l.cantidad>0)'
                con.execute(f'SELECT count(*) FROM producto p WHERE {elegibles}').fetchone()
                ids = [row[0] for row in con.execute(f'SELECT p.id FROM producto p WHERE {elegibles} ORDER BY p.nombre,p.id LIMIT 20 OFFSET ?', (offset,))]
                marks = ','.join('?' for _ in ids)
                con.execute(f'SELECT producto_id,sum(cantidad) FROM lote WHERE producto_id IN ({marks}) GROUP BY producto_id', ids).fetchall()
            medir_accion(f'Stock página {pagina} (página primero)', stock_pagina)
        medir(con, 'Stock solo bajo', 'SELECT p.id FROM producto p LEFT JOIN lote l ON l.producto_id=p.id GROUP BY p.id HAVING coalesce(sum(l.cantidad),0)<=p.minimo')
        medir(con, 'Lotes por vencer', "SELECT * FROM lote WHERE vencimiento BETWEEN ? AND ? ORDER BY vencimiento LIMIT 20", (date.today().isoformat(), (date.today() + timedelta(days=30)).isoformat()))
        hoy = date.today()
        medir(con, 'Ventas de un mes', 'SELECT count(*),sum(total) FROM venta WHERE fecha>=? AND fecha<?', (f'{hoy:%Y-%m}-01', f'{hoy:%Y-%m}-31'))
        medir(con, 'Ventas de un año', 'SELECT count(*),sum(total) FROM venta WHERE fecha>=? AND fecha<?', (f'{hoy.year}-01-01', f'{hoy.year + 1}-01-01'))
        medir(con, 'Movimientos listado mensual', 'SELECT * FROM movimiento WHERE fecha>=? AND fecha<? ORDER BY fecha DESC,id DESC LIMIT 20', (f'{hoy:%Y-%m}-01', f'{hoy:%Y-%m}-31'))
        medir(con, 'Compras listado anual', 'SELECT * FROM compra WHERE fecha>=? AND fecha<? ORDER BY fecha DESC,id DESC LIMIT 20', (f'{hoy.year}-01-01', f'{hoy.year + 1}-01-01'))
        con.close()


if __name__ == '__main__':
    main()

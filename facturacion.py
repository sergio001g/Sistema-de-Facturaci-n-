import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ttkthemes
import sqlite3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
import os
import json
from datetime import datetime, timedelta
import uuid
import re
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from decimal import Decimal
import qrcode
from PIL import Image as PILImage
import io
import configparser
import atexit

class Config:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_file = 'config.ini'
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            self.config['Email'] = {
                'smtp_server': 'smtp.gmail.com',
                'port': '587',
                'sender_email': '',
                'password': ''
            }
            self.config['PDF'] = {
                'page_size': 'letter'  # Options: letter, A4
            }
            self.save_config()

    def save_config(self):
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)

    def get_email_settings(self):
        return dict(self.config['Email'])

    def get_pdf_settings(self):
        return dict(self.config['PDF'])

class Cliente:
    def __init__(self, id, nombre, direccion, telefono, email, rfc):
        self.id = id
        self.nombre = nombre
        self.direccion = direccion
        self.telefono = telefono
        self.email = email
        self.rfc = rfc

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "direccion": self.direccion,
            "telefono": self.telefono,
            "email": self.email,
            "rfc": self.rfc
        }

class Producto:
    def __init__(self, id, nombre, descripcion, precio, stock):
        self.id = id
        self.nombre = nombre
        self.descripcion = descripcion
        self.precio = precio
        self.stock = stock

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "precio": self.precio,
            "stock": self.stock
        }

class Factura:
    def __init__(self, numero, cliente, items, subtotal, iva, total, fecha=None):
        self.numero = numero
        self.cliente = cliente
        self.items = items
        self.subtotal = subtotal
        self.iva = iva
        self.total = total
        self.fecha = fecha or datetime.now()
        self.uuid = str(uuid.uuid4())

    def to_dict(self):
        return {
            "numero": self.numero,
            "cliente": self.cliente.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "subtotal": str(self.subtotal),
            "iva": str(self.iva),
            "total": str(self.total),
            "fecha": self.fecha.isoformat(),
            "uuid": self.uuid
        }

class ItemFactura:
    def __init__(self, producto, cantidad):
        self.producto = producto
        self.cantidad = cantidad
        self.total = Decimal(str(producto.precio)) * Decimal(str(cantidad))

    def to_dict(self):
        return {
            "producto": self.producto.to_dict(),
            "cantidad": self.cantidad,
            "total": str(self.total)
        }

class Database:
    def __init__(self):
        self.conn = sqlite3.connect("facturacion.db")
        self.cursor = self.conn.cursor()
        self.crear_tablas()
        atexit.register(self.cleanup)

    def cleanup(self):
        if self.conn:
            self.conn.close()

    def crear_tablas(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                direccion TEXT,
                telefono TEXT,
                email TEXT,
                rfc TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                precio DECIMAL(10, 2) NOT NULL,
                stock INTEGER NOT NULL
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS facturas (
                numero INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                subtotal DECIMAL(10, 2) NOT NULL,
                iva DECIMAL(10, 2) NOT NULL,
                total DECIMAL(10, 2) NOT NULL,
                fecha DATETIME NOT NULL,
                uuid TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes (id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS items_factura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_numero INTEGER,
                producto_id INTEGER,
                cantidad INTEGER NOT NULL,
                precio_unitario DECIMAL(10, 2) NOT NULL,
                total DECIMAL(10, 2) NOT NULL,
                FOREIGN KEY (factura_numero) REFERENCES facturas (numero),
                FOREIGN KEY (producto_id) REFERENCES productos (id)
            )
        ''')
        self.conn.commit()

    def agregar_cliente(self, cliente):
        self.cursor.execute('''
            INSERT INTO clientes (nombre, direccion, telefono, email, rfc)
            VALUES (?, ?, ?, ?, ?)
        ''', (cliente.nombre, cliente.direccion, cliente.telefono, cliente.email, cliente.rfc))
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_clientes(self):
        self.cursor.execute("SELECT * FROM clientes")
        return [Cliente(*row) for row in self.cursor.fetchall()]

    def agregar_producto(self, producto):
        self.cursor.execute('''
            INSERT INTO productos (nombre, descripcion, precio, stock)
            VALUES (?, ?, ?, ?)
        ''', (producto.nombre, producto.descripcion, producto.precio, producto.stock))
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_productos(self):
        self.cursor.execute("SELECT * FROM productos")
        return [Producto(*row) for row in self.cursor.fetchall()]

    def agregar_factura(self, factura):
        self.cursor.execute('''
            INSERT INTO facturas (cliente_id, subtotal, iva, total, fecha, uuid)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (factura.cliente.id, factura.subtotal, factura.iva, factura.total, factura.fecha, factura.uuid))
        factura_numero = self.cursor.lastrowid
        for item in factura.items:
            self.cursor.execute('''
                INSERT INTO items_factura (factura_numero, producto_id, cantidad, precio_unitario, total)
                VALUES (?, ?, ?, ?, ?)
            ''', (factura_numero, item.producto.id, item.cantidad, item.producto.precio, item.total))
        self.conn.commit()
        return factura_numero

    def obtener_facturas(self):
        self.cursor.execute('''
            SELECT f.numero, c.id, c.nombre, c.direccion, c.telefono, c.email, c.rfc,
                   f.subtotal, f.iva, f.total, f.fecha, f.uuid
            FROM facturas f
            JOIN clientes c ON f.cliente_id = c.id
        ''')
        facturas = []
        for row in self.cursor.fetchall():
            cliente = Cliente(row[1], row[2], row[3], row[4], row[5], row[6])
            factura = Factura(row[0], cliente, [], Decimal(row[7]), Decimal(row[8]), Decimal(row[9]), datetime.fromisoformat(row[10]))
            factura.uuid = row[11]
            self.cursor.execute('''
                SELECT p.id, p.nombre, p.descripcion, p.precio, p.stock, i.cantidad
                FROM items_factura i
                JOIN productos p ON i.producto_id = p.id
                WHERE i.factura_numero = ?
            ''', (factura.numero,))
            for item_row in self.cursor.fetchall():
                producto = Producto(item_row[0], item_row[1], item_row[2], Decimal(item_row[3]), item_row[4])
                item = ItemFactura(producto, item_row[5])
                factura.items.append(item)
            facturas.append(factura)
        return facturas

    def actualizar_stock(self, producto_id, cantidad):
        self.cursor.execute('''
            UPDATE productos
            SET stock = stock - ?
            WHERE id = ?
        ''', (cantidad, producto_id))
        self.conn.commit()

class SistemaFacturacion:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Facturación Avanzado")
        self.root.geometry("1024x768")
        self.style = ttkthemes.ThemedStyle(self.root)
        self.style.set_theme("arc")
        self.config = Config()
        self.db = Database()
        self.setup_ui()

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both")

        self.crear_factura_frame = ttk.Frame(self.notebook)
        self.ver_facturas_frame = ttk.Frame(self.notebook)
        self.gestion_clientes_frame = ttk.Frame(self.notebook)
        self.gestion_productos_frame = ttk.Frame(self.notebook)
        self.estadisticas_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.crear_factura_frame, text="Crear Factura")
        self.notebook.add(self.ver_facturas_frame, text="Ver Facturas")
        self.notebook.add(self.gestion_clientes_frame, text="Gestión de Clientes")
        self.notebook.add(self.gestion_productos_frame, text="Gestión de Productos")
        self.notebook.add(self.estadisticas_frame, text="Estadísticas")

        self.setup_crear_factura()
        self.setup_ver_facturas()
        self.setup_gestion_clientes()
        self.setup_gestion_productos()
        self.setup_estadisticas()

    def setup_crear_factura(self):
        frame = ttk.Frame(self.crear_factura_frame, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        ttk.Label(frame, text="Cliente:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.cliente_combobox = ttk.Combobox(frame, width=40)
        self.cliente_combobox.grid(row=0, column=1, sticky=tk.W, pady=5)
        self.actualizar_lista_clientes()

        ttk.Label(frame, text="Productos:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.producto_combobox = ttk.Combobox(frame, width=40)
        self.producto_combobox.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.actualizar_lista_productos()

        ttk.Label(frame, text="Cantidad:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.cantidad_entry = ttk.Entry(frame, width=10)
        self.cantidad_entry.grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Button(frame, text="Agregar Item", command=self.agregar_item).grid(row=3, column=0, columnspan=2, pady=10)

        self.items_tree = ttk.Treeview(frame, columns=("Producto", "Cantidad", "Precio Unitario", "Total"), show="headings")
        self.items_tree.heading("Producto", text="Producto")
        self.items_tree.heading("Cantidad", text="Cantidad")
        self.items_tree.heading("Precio Unitario", text="Precio Unitario")
        self.items_tree.heading("Total", text="Total")
        self.items_tree.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        ttk.Button(frame, text="Generar Factura", command=self.generar_factura).grid(row=5, column=0, columnspan=2, pady=10)

        self.subtotal_label = ttk.Label(frame, text="Subtotal: $0.00")
        self.subtotal_label.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=5)

        self.iva_label = ttk.Label(frame, text="IVA (16%): $0.00")
        self.iva_label.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=5)

        self.total_label = ttk.Label(frame, text="Total: $0.00")
        self.total_label.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=5)

    def setup_ver_facturas(self):
        frame = ttk.Frame(self.ver_facturas_frame, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.facturas_tree = ttk.Treeview(frame, columns=("Número", "Cliente", "Fecha", "Total"), show="headings")
        self.facturas_tree.heading("Número", text="Número")
        self.facturas_tree.heading("Cliente", text="Cliente")
        self.facturas_tree.heading("Fecha", text="Fecha")
        self.facturas_tree.heading("Total", text="Total")
        self.facturas_tree.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.facturas_tree.yview)
        scrollbar.grid(row=0, column=3, sticky=(tk.N, tk.S))
        self.facturas_tree.configure(yscrollcommand=scrollbar.set)

        ttk.Button(frame, text="Ver Detalles", command=self.ver_detalles_factura).grid(row=1, column=0, pady=10)
        ttk.Button(frame, text="Imprimir Factura", command=self.imprimir_factura).grid(row=1, column=1, pady=10)
        ttk.Button(frame, text="Enviar por Correo", command=self.enviar_factura_correo).grid(row=1, column=2, pady=10)

        self.actualizar_lista_facturas()

    def setup_gestion_clientes(self):
        frame = ttk.Frame(self.gestion_clientes_frame, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        ttk.Label(frame, text="Nombre:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.nombre_cliente_entry = ttk.Entry(frame, width=40)
        self.nombre_cliente_entry.grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Dirección:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.direccion_cliente_entry = ttk.Entry(frame, width=40)
        self.direccion_cliente_entry.grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Teléfono:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.telefono_cliente_entry = ttk.Entry(frame, width=40)
        self.telefono_cliente_entry.grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Email:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.email_cliente_entry = ttk.Entry(frame, width=40)
        self.email_cliente_entry.grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="RFC:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.rfc_cliente_entry = ttk.Entry(frame, width=40)
        self.rfc_cliente_entry.grid(row=4, column=1, sticky=tk.W, pady=5)

        ttk.Button(frame, text="Agregar Cliente", command=self.agregar_cliente).grid(row=5, column=0, columnspan=2, pady=10)

        self.clientes_tree = ttk.Treeview(frame, columns=("ID", "Nombre", "Teléfono", "Email"), show="headings")
        self.clientes_tree.heading("ID", text="ID")
        self.clientes_tree.heading("Nombre", text="Nombre")
        self.clientes_tree.heading("Teléfono", text="Teléfono")
        self.clientes_tree.heading("Email", text="Email")
        self.clientes_tree.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        self.actualizar_lista_clientes_tree()

    def setup_gestion_productos(self):
        frame = ttk.Frame(self.gestion_productos_frame, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        ttk.Label(frame, text="Nombre:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.nombre_producto_entry = ttk.Entry(frame, width=40)
        self.nombre_producto_entry.grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Descripción:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.descripcion_producto_entry = ttk.Entry(frame, width=40)
        self.descripcion_producto_entry.grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Precio:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.precio_producto_entry = ttk.Entry(frame, width=40)
        self.precio_producto_entry.grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Stock:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.stock_producto_entry = ttk.Entry(frame, width=40)
        self.stock_producto_entry.grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Button(frame, text="Agregar Producto", command=self.agregar_producto).grid(row=4, column=0, columnspan=2, pady=10)

        self.productos_tree = ttk.Treeview(frame, columns=("ID", "Nombre", "Precio", "Stock"), show="headings")
        self.productos_tree.heading("ID", text="ID")
        self.productos_tree.heading("Nombre", text="Nombre")
        self.productos_tree.heading("Precio", text="Precio")
        self.productos_tree.heading("Stock", text="Stock")
        self.productos_tree.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        self.actualizar_lista_productos_tree()

    def setup_estadisticas(self):
        frame = ttk.Frame(self.estadisticas_frame, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        ttk.Button(frame, text="Generar Gráfico de Ventas", command=self.generar_grafico_ventas).grid(row=0, column=0, pady=10)
        ttk.Button(frame, text="Generar Reporte de Ventas", command=self.generar_reporte_ventas).grid(row=0, column=1, pady=10)

        self.grafico_frame = ttk.Frame(frame)
        self.grafico_frame.grid(row=1, column=0, columnspan=2, pady=10)

    def actualizar_lista_clientes(self):
        clientes = self.db.obtener_clientes()
        self.cliente_combobox['values'] = [f"{cliente.id} - {cliente.nombre}" for cliente in clientes]

    def actualizar_lista_productos(self):
        productos = self.db.obtener_productos()
        self.producto_combobox['values'] = [f"{producto.id} - {producto.nombre}" for producto in productos]

    def actualizar_lista_facturas(self):
        facturas = self.db.obtener_facturas()
        for item in self.facturas_tree.get_children():
            self.facturas_tree.delete(item)
        for factura in facturas:
            self.facturas_tree.insert("", tk.END, values=(factura.numero, factura.cliente.nombre, factura.fecha.strftime("%Y-%m-%d %H:%M:%S"), f"${factura.total:.2f}"))

    def actualizar_lista_clientes_tree(self):
        clientes = self.db.obtener_clientes()
        for item in self.clientes_tree.get_children():
            self.clientes_tree.delete(item)
        for cliente in clientes:
            self.clientes_tree.insert("", tk.END, values=(cliente.id, cliente.nombre, cliente.telefono, cliente.email))

    def actualizar_lista_productos_tree(self):
        productos = self.db.obtener_productos()
        for item in self.productos_tree.get_children():
            self.productos_tree.delete(item)
        for producto in productos:
            self.productos_tree.insert("", tk.END, values=(producto.id, producto.nombre, f"${producto.precio:.2f}", producto.stock))

    def agregar_item(self):
        producto_str = self.producto_combobox.get()
        cantidad_str = self.cantidad_entry.get()

        if not producto_str or not cantidad_str:
            messagebox.showerror("Error", "Por favor, seleccione un producto y especifique la cantidad.")
            return

        try:
            producto_id = int(producto_str.split(" - ")[0])
            cantidad = int(cantidad_str)
        except ValueError:
            messagebox.showerror("Error", "La cantidad debe ser un número entero.")
            return

        productos = self.db.obtener_productos()
        producto = next((p for p in productos if p.id == producto_id), None)

        if producto is None:
            messagebox.showerror("Error", "Producto no encontrado.")
            return

        if cantidad > producto.stock:
            messagebox.showerror("Error", f"Stock insuficiente. Stock actual: {producto.stock}")
            return

        total = Decimal(str(producto.precio)) * Decimal(str(cantidad))
        self.items_tree.insert("", tk.END, values=(producto.nombre, cantidad, f"${producto.precio:.2f}", f"${total:.2f}"))

        self.actualizar_totales()

    def actualizar_totales(self):
        subtotal = Decimal('0')
        for item in self.items_tree.get_children():
            valores = self.items_tree.item(item)['values']
            subtotal += Decimal(valores[3].replace('$', ''))

        iva = subtotal * Decimal('0.16')
        total = subtotal + iva

        self.subtotal_label.config(text=f"Subtotal: ${subtotal:.2f}")
        self.iva_label.config(text=f"IVA (16%): ${iva:.2f}")
        self.total_label.config(text=f"Total: ${total:.2f}")

    def generar_factura(self):
        cliente_str = self.cliente_combobox.get()
        if not cliente_str:
            messagebox.showerror("Error", "Por favor, seleccione un cliente.")
            return

        items = []
        for item in self.items_tree.get_children():
            valores = self.items_tree.item(item)['values']
            producto = next((p for p in self.db.obtener_productos() if p.nombre == valores[0]), None)
            if producto:
                items.append(ItemFactura(producto, int(valores[1])))

        if not items:
            messagebox.showerror("Error", "La factura debe tener al menos un item.")
            return

        cliente_id = int(cliente_str.split(" - ")[0])
        cliente = next((c for c in self.db.obtener_clientes() if c.id == cliente_id), None)

        if cliente is None:
            messagebox.showerror("Error", "Cliente no encontrado.")
            return

        subtotal = sum(item.total for item in items)
        iva = subtotal * Decimal('0.16')
        total = subtotal + iva

        factura = Factura(None, cliente, items, subtotal, iva, total)
        numero_factura = self.db.agregar_factura(factura)

        for item in items:
            self.db.actualizar_stock(item.producto.id, item.cantidad)

        self.actualizar_lista_facturas()
        self.actualizar_lista_productos()
        self.actualizar_lista_productos_tree()

        messagebox.showinfo("Éxito", f"Factura #{numero_factura} generada correctamente.")

        self.limpiar_campos_factura()

    def limpiar_campos_factura(self):
        self.cliente_combobox.set('')
        self.producto_combobox.set('')
        self.cantidad_entry.delete(0, tk.END)
        for item in self.items_tree.get_children():
            self.items_tree.delete(item)
        self.actualizar_totales()

    def ver_detalles_factura(self):
        seleccion = self.facturas_tree.selection()
        if not seleccion:
            messagebox.showerror("Error", "Por favor, seleccione una factura para ver los detalles.")
            return

        numero_factura = self.facturas_tree.item(seleccion[0])['values'][0]
        factura = next((f for f in self.db.obtener_facturas() if f.numero == numero_factura), None)

        if factura:
            detalles = f"Factura #{factura.numero}\n\n"
            detalles += f"Cliente: {factura.cliente.nombre}\n"
            detalles += f"RFC: {factura.cliente.rfc}\n"
            detalles += f"Dirección: {factura.cliente.direccion}\n"
            detalles += f"Teléfono: {factura.cliente.telefono}\n"
            detalles += f"Email: {factura.cliente.email}\n\n"
            detalles += "Items:\n"
            for item in factura.items:
                detalles += f"{item.producto.nombre} - Cantidad: {item.cantidad} - Precio: ${item.producto.precio:.2f} - Total: ${item.total:.2f}\n"
            detalles += f"\nSubtotal: ${factura.subtotal:.2f}\n"
            detalles += f"IVA (16%): ${factura.iva:.2f}\n"
            detalles += f"Total: ${factura.total:.2f}\n"
            detalles += f"\nFecha: {factura.fecha.strftime('%Y-%m-%d %H:%M:%S')}\n"
            detalles += f"UUID: {factura.uuid}"

            messagebox.showinfo("Detalles de la Factura", detalles)
        else:
            messagebox.showerror("Error", "No se encontró la factura seleccionada.")

    def imprimir_factura(self):
        seleccion = self.facturas_tree.selection()
        if not seleccion:
            messagebox.showerror("Error", "Por favor, seleccione una factura para imprimir.")
            return

        numero_factura = self.facturas_tree.item(seleccion[0])['values'][0]
        factura = next((f for f in self.db.obtener_facturas() if f.numero == numero_factura), None)

        if factura:
            filename = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
            if filename:
                self.generar_pdf(factura, filename)
                messagebox.showinfo("Éxito", f"Factura guardada como {filename}")
        else:
            messagebox.showerror("Error", "No se encontró la factura seleccionada.")

    def generar_pdf(self, factura, filename):
        # Get page size from config
        page_size_name = self.config.get_pdf_settings().get('page_size', 'letter')
        page_size = letter if page_size_name.lower() == 'letter' else A4

        doc = SimpleDocTemplate(filename, pagesize=page_size)
        elements = []

        styles = getSampleStyleSheet()
        styles.add(Parag raphStyle(name='Center', alignment=1))

        elements.append(Paragraph(f"Factura #{factura.numero}", styles['Title']))
        elements.append(Paragraph(f"Fecha: {factura.fecha.strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 12))

        elements.append(Paragraph("Datos del Cliente:", styles['Heading2']))
        elements.append(Paragraph(f"Nombre: {factura.cliente.nombre}", styles['Normal']))
        elements.append(Paragraph(f"RFC: {factura.cliente.rfc}", styles['Normal']))
        elements.append(Paragraph(f"Dirección: {factura.cliente.direccion}", styles['Normal']))
        elements.append(Paragraph(f"Teléfono: {factura.cliente.telefono}", styles['Normal']))
        elements.append(Paragraph(f"Email: {factura.cliente.email}", styles['Normal']))
        elements.append(Spacer(1, 12))

        elements.append(Paragraph("Items:", styles['Heading2']))
        data = [["Descripción", "Cantidad", "Precio Unitario", "Total"]]
        for item in factura.items:
            data.append([
                item.producto.nombre,
                str(item.cantidad),
                f"${item.producto.precio:.2f}",
                f"${item.total:.2f}"
            ])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
            ('TOPPADDING', (0, -1), (-1, -1), 12),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))

        elements.append(Paragraph(f"Subtotal: ${factura.subtotal:.2f}", styles['Normal']))
        elements.append(Paragraph(f"IVA (16%): ${factura.iva:.2f}", styles['Normal']))
        elements.append(Paragraph(f"Total: ${factura.total:.2f}", styles['Normal']))
        elements.append(Spacer(1, 12))

        elements.append(Paragraph(f"UUID: {factura.uuid}", styles['Normal']))

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(factura.uuid)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        qr_image = Image(img_buffer)
        qr_image.drawHeight = 1.5*inch
        qr_image.drawWidth = 1.5*inch
        elements.append(qr_image)

        doc.build(elements)

    def enviar_factura_correo(self):
        seleccion = self.facturas_tree.selection()
        if not seleccion:
            messagebox.showerror("Error", "Por favor, seleccione una factura para enviar por correo.")
            return

        numero_factura = self.facturas_tree.item(seleccion[0])['values'][0]
        factura = next((f for f in self.db.obtener_facturas() if f.numero == numero_factura), None)

        if factura:
            temp_pdf = f"factura_{factura.numero}.pdf"
            self.generar_pdf(factura, temp_pdf)
            try:
                # Get email settings from config
                email_settings = self.config.get_email_settings()
                smtp_server = email_settings['smtp_server']
                port = int(email_settings['port'])
                sender_email = email_settings['sender_email']
                password = email_settings['password']

                if not sender_email or not password:
                    messagebox.showerror("Error", "Por favor configure las credenciales de correo en config.ini")
                    return

                message = MIMEMultipart()
                message["From"] = sender_email
                message["To"] = factura.cliente.email
                message["Subject"] = f"Factura #{factura.numero}"

                body = f"Estimado {factura.cliente.nombre},\n\nAdjunto encontrará la factura #{factura.numero}.\n\nGracias por su preferencia."
                message.attach(MIMEText(body, "plain"))

                with open(temp_pdf, "rb") as attachment:
                    part = MIMEApplication(attachment.read(), Name=os.path.basename(temp_pdf))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(temp_pdf)}"'
                message.attach(part)

                with smtplib.SMTP(smtp_server, port) as server:
                    server.starttls()
                    server.login(sender_email, password)
                    server.send_message(message)

                os.remove(temp_pdf)
                messagebox.showinfo("Éxito", f"Factura enviada por correo a {factura.cliente.email}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo enviar el correo: {str(e)}")
        else:
            messagebox.showerror("Error", "No se encontró la factura seleccionada.")

    def agregar_cliente(self):
        nombre = self.nombre_cliente_entry.get()
        direccion = self.direccion_cliente_entry.get()
        telefono = self.telefono_cliente_entry.get()
        email = self.email_cliente_entry.get()
        rfc = self.rfc_cliente_entry.get()

        if not nombre or not direccion or not telefono or not email or not rfc:
            messagebox.showerror("Error", "Todos los campos son obligatorios.")
            return

        cliente = Cliente(None, nombre, direccion, telefono, email, rfc)
        self.db.agregar_cliente(cliente)
        self.actualizar_lista_clientes()
        self.actualizar_lista_clientes_tree()
        self.limpiar_campos_cliente()
        messagebox.showinfo("Éxito", "Cliente agregado correctamente.")

    def limpiar_campos_cliente(self):
        self.nombre_cliente_entry.delete(0, tk.END)
        self.direccion_cliente_entry.delete(0, tk.END)
        self.telefono_cliente_entry.delete(0, tk.END)
        self.email_cliente_entry.delete(0, tk.END)
        self.rfc_cliente_entry.delete(0, tk.END)

    def agregar_producto(self):
        nombre = self.nombre_producto_entry.get()
        descripcion = self.descripcion_producto_entry.get()
        precio = self.precio_producto_entry.get()
        stock = self.stock_producto_entry.get()

        if not nombre or not descripcion or not precio or not stock:
            messagebox.showerror("Error", "Todos los campos son obligatorios.")
            return

        try:
            precio = Decimal(precio)
            stock = int(stock)
        except ValueError:
            messagebox.showerror("Error", "El precio debe ser un número decimal y el stock un número entero.")
            return

        producto = Producto(None, nombre, descripcion, precio, stock)
        self.db.agregar_producto(producto)
        self.actualizar_lista_productos()
        self.actualizar_lista_productos_tree()
        self.limpiar_campos_producto()
        messagebox.showinfo("Éxito", "Producto agregado correctamente.")

    def limpiar_campos_producto(self):
        self.nombre_producto_entry.delete(0, tk.END)
        self.descripcion_producto_entry.delete(0, tk.END)
        self.precio_producto_entry.delete(0, tk.END)
        self.stock_producto_entry.delete(0, tk.END)

    def generar_grafico_ventas(self):
        facturas = self.db.obtener_facturas()
        if not facturas:
            messagebox.showinfo("Información", "No hay datos de ventas para generar el gráfico.")
            return

        ventas_por_dia = {}
        for factura in facturas:
            fecha = factura.fecha.date()
            if fecha in ventas_por_dia:
                ventas_por_dia[fecha] += factura.total
            else:
                ventas_por_dia[fecha] = factura.total

        fechas = list(ventas_por_dia.keys())
        ventas = list(ventas_por_dia.values())

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(fechas, ventas)
        ax.set_xlabel('Fecha')
        ax.set_ylabel('Ventas ($)')
        ax.set_title('Ventas por Día')
        plt.xticks(rotation=45)
        plt.tight_layout()

        for widget in self.grafico_frame.winfo_children():
            widget.destroy()

        canvas = FigureCanvasTkAgg(fig, master=self.grafico_frame)
        canvas.draw()
        canvas.get_tk_widget().pack()

    def generar_reporte_ventas(self):
        facturas = self.db.obtener_facturas()
        if not facturas:
            messagebox.showinfo("Información", "No hay datos de ventas para generar el reporte.")
            return

        filename = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not filename:
            return

        doc = SimpleDocTemplate(filename, pagesize=landscape(letter))
        elements = []

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='Center', alignment=1))

        elements.append(Paragraph("Reporte de Ventas", styles['Title']))
        elements.append(Spacer(1, 12))

        data = [["Número de Factura", "Cliente", "Fecha", "Subtotal", "IVA", "Total"]]
        for factura in facturas:
            data.append([
                str(factura.numero),
                factura.cliente.nombre,
                factura.fecha.strftime("%Y-%m-%d %H:%M:%S"),
                f"${factura.subtotal:.2f}",
                f"${factura.iva:.2f}",
                f"${factura.total:.2f}"
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
            ('TOPPADDING', (0, -1), (-1, -1), 12),
        ]))
        elements.append(table)

        total_ventas = sum(factura.total for factura in facturas)
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"Total de Ventas: ${total_ventas:.2f}", styles['Heading2']))

        doc.build(elements)
        messagebox.showinfo("Éxito", f"Reporte de ventas guardado como {filename}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SistemaFacturacion(root)
    root.mainloop()

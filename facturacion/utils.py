"""
Utilidades para el sistema de facturación EasyInvoice
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from io import BytesIO
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def generar_pdf_factura(factura):
    """
    Genera un PDF de la factura en formato paraguayo
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Estilo personalizado para el título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Encabezado
    elements.append(Paragraph("SISTEMA EASYINVOICE", title_style))
    elements.append(Paragraph("Sistema de Facturación para Pequeños Negocios", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Información de la factura
    factura_info = [
        ['FACTURA', factura.numero_factura],
        ['Fecha de Emisión:', factura.fecha_emision.strftime('%d/%m/%Y')],
        ['Estado:', factura.get_estado_display()],
    ]
    
    if factura.timbrado:
        factura_info.append(['Timbrado:', factura.timbrado])
        if factura.timbrado_vencimiento:
            factura_info.append(['Válido hasta:', factura.timbrado_vencimiento.strftime('%d/%m/%Y')])
    
    info_table = Table(factura_info, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Información del cliente
    elements.append(Paragraph("DATOS DEL CLIENTE", styles['Heading2']))
    cliente_info = [
        ['Nombre/Razón Social:', factura.cliente.nombre],
        ['RUC/CI:', factura.cliente.ruc_ci],
        ['Dirección:', factura.cliente.direccion],
        ['Teléfono:', factura.cliente.telefono],
    ]
    if factura.cliente.email:
        cliente_info.append(['Email:', factura.cliente.email])
    
    cliente_table = Table(cliente_info, colWidths=[2*inch, 4*inch])
    cliente_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    elements.append(cliente_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Detalles de productos/servicios
    elements.append(Paragraph("DETALLE DE PRODUCTOS/SERVICIOS", styles['Heading2']))
    
    detalles_data = [['Producto/Servicio', 'Cantidad', 'Precio Unit.', 'Subtotal']]
    for detalle in factura.detalles.all():
        detalles_data.append([
            detalle.producto,
            str(detalle.cantidad),
            f"₲ {detalle.precio_unitario:,.0f}",
            f"₲ {detalle.subtotal:,.0f}"
        ])
    
    detalles_table = Table(detalles_data, colWidths=[3*inch, 1*inch, 1.5*inch, 1.5*inch])
    detalles_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(detalles_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Totales
    totales_data = [
        ['Subtotal:', f"₲ {factura.subtotal:,.0f}"],
        ['IVA (10%):', f"₲ {factura.iva:,.0f}"],
        ['TOTAL:', f"₲ {factura.total:,.0f}"]
    ]
    
    totales_table = Table(totales_data, colWidths=[4.5*inch, 1.5*inch])
    totales_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 14),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#2c3e50')),
        ('LINEABOVE', (0, 2), (-1, 2), 2, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(totales_table)
    
    # Observaciones
    if factura.observaciones:
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("OBSERVACIONES", styles['Heading2']))
        elements.append(Paragraph(factura.observaciones, styles['Normal']))
    
    # Pie de página
    elements.append(Spacer(1, 0.5*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    elements.append(Paragraph("Sistema EasyInvoice - Facturación para Pequeños Negocios", footer_style))
    elements.append(Paragraph("San Lorenzo, Paraguay - 2025", footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generar_reporte_ventas(facturas, fecha_desde=None, fecha_hasta=None):
    """
    Genera un reporte de ventas en PDF
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    # Título
    elements.append(Paragraph("REPORTE DE VENTAS", title_style))
    
    # Período
    if fecha_desde and fecha_hasta:
        periodo = f"Período: {fecha_desde.strftime('%d/%m/%Y')} - {fecha_hasta.strftime('%d/%m/%Y')}"
    else:
        periodo = "Todas las ventas"
    elements.append(Paragraph(periodo, styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Resumen
    total_facturas = facturas.count()
    total_monto = sum(f.total for f in facturas)
    facturas_pagadas = facturas.filter(estado='PAGADA').count()
    monto_pagado = sum(f.total for f in facturas.filter(estado='PAGADA'))
    facturas_pendientes = facturas.filter(estado='PENDIENTE').count()
    monto_pendiente = sum(f.total for f in facturas.filter(estado='PENDIENTE'))
    
    resumen_data = [
        ['RESUMEN GENERAL', ''],
        ['Total de Facturas:', str(total_facturas)],
        ['Facturas Pagadas:', str(facturas_pagadas)],
        ['Facturas Pendientes:', str(facturas_pendientes)],
        ['Monto Total:', f"₲ {total_monto:,.0f}"],
        ['Monto Pagado:', f"₲ {monto_pagado:,.0f}"],
        ['Monto Pendiente:', f"₲ {monto_pendiente:,.0f}"],
    ]
    
    resumen_table = Table(resumen_data, colWidths=[3*inch, 3*inch])
    resumen_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    elements.append(resumen_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Detalle de facturas
    elements.append(Paragraph("DETALLE DE FACTURAS", styles['Heading2']))
    
    detalle_data = [['Nº Factura', 'Fecha', 'Cliente', 'Estado', 'Total']]
    for factura in facturas[:50]:  # Limitar a 50 facturas
        detalle_data.append([
            factura.numero_factura,
            factura.fecha_emision.strftime('%d/%m/%Y'),
            factura.cliente.nombre[:30],
            factura.get_estado_display(),
            f"₲ {factura.total:,.0f}"
        ])
    
    detalle_table = Table(detalle_data, colWidths=[1.2*inch, 1*inch, 2.5*inch, 1*inch, 1.3*inch])
    detalle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(detalle_table)
    
    if facturas.count() > 50:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph(f"Mostrando las primeras 50 de {facturas.count()} facturas", styles['Italic']))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

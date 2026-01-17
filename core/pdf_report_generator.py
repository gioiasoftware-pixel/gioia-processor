"""
Generatore PDF per report giornalieri movimenti vini.
Genera PDF senza uso di IA, solo con reportlab.
"""
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.platypus.flowables import KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

logger = logging.getLogger(__name__)

# Colori gio.ia (basati su palette brand)
GIOIA_PRIMARY = colors.HexColor('#8B4513')  # Marrone vino
GIOIA_SECONDARY = colors.HexColor('#D4AF37')  # Oro
GIOIA_DARK = colors.HexColor('#2C1810')  # Marrone scuro
GIOIA_LIGHT = colors.HexColor('#F5E6D3')  # Beige chiaro
GIOIA_SUCCESS = colors.HexColor('#4A7C59')  # Verde
GIOIA_DANGER = colors.HexColor('#C41E3A')  # Rosso


def generate_daily_report_pdf(
    business_name: str,
    report_date: datetime.date,
    movements: List[Dict[str, Any]],
    top_5_consumed: List[Dict[str, Any]],
    top_5_replenished: List[Dict[str, Any]]
) -> bytes:
    """
    Genera PDF report giornaliero movimenti vini con stile gio.ia.
    
    Args:
        business_name: Nome business
        report_date: Data del report
        movements: Lista movimenti del giorno
        top_5_consumed: Top 5 vini più consumati
        top_5_replenished: Top 5 vini più riforniti
    
    Returns:
        Bytes del PDF generato
    """
    buffer = BytesIO()
    
    # Crea documento PDF
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # Stili
    styles = getSampleStyleSheet()
    
    # Stile titolo principale
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=GIOIA_PRIMARY,
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Stile sottotitolo
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=GIOIA_DARK,
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    # Stile business name
    business_style = ParagraphStyle(
        'BusinessName',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=GIOIA_SECONDARY,
        spaceAfter=15,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Stile sezione
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=GIOIA_PRIMARY,
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    # Stile testo normale
    normal_style = styles['Normal']
    normal_style.fontSize = 10
    normal_style.textColor = colors.black
    
    # Costruisci contenuto PDF
    story = []
    
    # Header con logo
    report_date_str = report_date.strftime("%d/%m/%Y")
    
    # Prova a caricare il logo
    logo_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=3*cm, height=3*cm)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 0.3*cm))
        except Exception as e:
            logger.warning(f"[PDF_REPORT] Errore caricamento logo: {e}")
    
    story.append(Paragraph("📊 Report Movimenti Giornaliero", title_style))
    story.append(Paragraph(f"<b>{business_name}</b>", business_style))
    story.append(Paragraph(f"Data: {report_date_str}", subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Se non ci sono movimenti
    if not movements:
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(
            "ℹ️ Nessun Movimento",
            ParagraphStyle(
                'NoMovements',
                parent=normal_style,
                fontSize=14,
                textColor=GIOIA_DARK,
                alignment=TA_CENTER,
                spaceAfter=20
            )
        ))
        story.append(Paragraph(
            "Non sono stati riscontrati movimenti (consumi o rifornimenti) per questa giornata.",
            ParagraphStyle(
                'NoMovementsDesc',
                parent=normal_style,
                fontSize=11,
                alignment=TA_CENTER,
                textColor=colors.grey
            )
        ))
    else:
        # Calcola statistiche generali
        total_consumi = sum(
            abs(m.get('quantity_change', 0)) 
            for m in movements 
            if m.get('movement_type') == 'consumo'
        )
        total_rifornimenti = sum(
            m.get('quantity_change', 0) 
            for m in movements 
            if m.get('movement_type') == 'rifornimento'
        )
        net_change = total_rifornimenti - total_consumi
        total_movements = len(movements)
        
        # Statistiche generali
        story.append(Paragraph("📈 Statistiche Generali", section_style))
        
        stats_data = [
            ['Metrica', 'Valore'],
            ['Consumi', f'{total_consumi} bottiglie'],
            ['Rifornimenti', f'{total_rifornimenti} bottiglie'],
            ['Variazione netta', f'{net_change:+d} bottiglie'],
            ['Movimenti totali', f'{total_movements}']
        ]
        
        stats_table = Table(stats_data, colWidths=[8*cm, 8*cm])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), GIOIA_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), GIOIA_LIGHT),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GIOIA_LIGHT]),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.5*cm))
        
        # Top 5 vini più consumati
        if top_5_consumed:
            story.append(Paragraph("📉 Top 5 Vini Più Consumati", section_style))
            
            consumed_data = [['Posizione', 'Vino', 'Bottiglie Consumate']]
            for idx, wine in enumerate(top_5_consumed, 1):
                consumed_data.append([
                    str(idx),
                    wine.get('wine_name', 'Sconosciuto'),
                    f"{wine.get('total_consumed', 0)}"
                ])
            
            consumed_table = Table(consumed_data, colWidths=[2*cm, 10*cm, 4*cm])
            consumed_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), GIOIA_DANGER),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GIOIA_LIGHT]),
            ]))
            story.append(consumed_table)
            story.append(Spacer(1, 0.5*cm))
        
        # Top 5 vini più riforniti
        if top_5_replenished:
            story.append(Paragraph("📈 Top 5 Vini Più Riforniti", section_style))
            
            replenished_data = [['Posizione', 'Vino', 'Bottiglie Rifornite']]
            for idx, wine in enumerate(top_5_replenished, 1):
                replenished_data.append([
                    str(idx),
                    wine.get('wine_name', 'Sconosciuto'),
                    f"{wine.get('total_replenished', 0)}"
                ])
            
            replenished_table = Table(replenished_data, colWidths=[2*cm, 10*cm, 4*cm])
            replenished_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), GIOIA_SUCCESS),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GIOIA_LIGHT]),
            ]))
            story.append(replenished_table)
            story.append(Spacer(1, 0.5*cm))
        
        # Dettaglio movimenti
        story.append(PageBreak())
        story.append(Paragraph("🍷 Dettaglio Completo Movimenti", section_style))
        
        # Raggruppa per vino
        wines_dict = {}
        for mov in movements:
            wine_name = mov.get('wine_name', 'Sconosciuto')
            if wine_name not in wines_dict:
                wines_dict[wine_name] = {
                    'movements': [],
                    'total_consumed': 0,
                    'total_replenished': 0
                }
            
            movement_type = mov.get('movement_type', '')
            quantity = abs(mov.get('quantity_change', 0))
            movement_date = mov.get('movement_date')
            
            wines_dict[wine_name]['movements'].append({
                'type': movement_type,
                'quantity': quantity,
                'date': movement_date
            })
            
            if movement_type == 'consumo':
                wines_dict[wine_name]['total_consumed'] += quantity
            elif movement_type == 'rifornimento':
                wines_dict[wine_name]['total_replenished'] += quantity
        
        # Genera tabella dettaglio per ogni vino
        for wine_name, wine_data in sorted(wines_dict.items()):
            story.append(Spacer(1, 0.3*cm))
            story.append(Paragraph(
                f"<b>{wine_name}</b>",
                ParagraphStyle(
                    'WineName',
                    parent=normal_style,
                    fontSize=12,
                    textColor=GIOIA_PRIMARY,
                    spaceAfter=8,
                    fontName='Helvetica-Bold'
                )
            ))
            
            # Statistiche vino
            wine_stats = [
                f"Consumate: {wine_data['total_consumed']} bottiglie",
                f"Rifornite: {wine_data['total_replenished']} bottiglie"
            ]
            story.append(Paragraph(" • ".join(wine_stats), normal_style))
            story.append(Spacer(1, 0.2*cm))
            
            # Tabella movimenti
            movements_data = [['Tipo', 'Quantità', 'Data/Ora']]
            for mov in wine_data['movements']:
                mov_type = mov['type'].capitalize()
                mov_qty = str(mov['quantity'])
                mov_date = mov['date']
                if isinstance(mov_date, datetime):
                    mov_date_str = mov_date.strftime("%d/%m/%Y %H:%M")
                elif isinstance(mov_date, str):
                    mov_date_str = mov_date
                else:
                    mov_date_str = "N/A"
                
                movements_data.append([mov_type, mov_qty, mov_date_str])
            
            if len(movements_data) > 1:  # Se ci sono movimenti oltre l'header
                movements_table = Table(movements_data, colWidths=[4*cm, 3*cm, 9*cm])
                movements_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), GIOIA_DARK),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GIOIA_LIGHT]),
                ]))
                story.append(movements_table)
    
    # Footer
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        "Generato automaticamente da Gio.ia",
        ParagraphStyle(
            'Footer',
            parent=normal_style,
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
    ))
    
    # Costruisci PDF
    doc.build(story)
    
    # Ottieni bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    logger.info(f"[PDF_REPORT] PDF generato: {len(pdf_bytes)} bytes per {business_name} - {report_date_str}")
    
    return pdf_bytes


def generate_inventory_stats_pdf(
    business_name: str,
    stats: Dict[str, Any]
) -> bytes:
    """
    Genera PDF report statistiche inventario con stile gio.ia.
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=GIOIA_PRIMARY,
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=GIOIA_DARK,
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )

    business_style = ParagraphStyle(
        'BusinessName',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=GIOIA_SECONDARY,
        spaceAfter=15,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=GIOIA_PRIMARY,
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )

    normal_style = styles['Normal']
    normal_style.fontSize = 10
    normal_style.textColor = colors.black

    story = []

    report_date_str = datetime.now().strftime("%d/%m/%Y")

    logo_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=3*cm, height=3*cm)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 0.3*cm))
        except Exception as e:
            logger.warning(f"[PDF_REPORT] Errore caricamento logo: {e}")

    story.append(Paragraph("📊 Report Statistiche Inventario", title_style))
    story.append(Paragraph(f"<b>{business_name}</b>", business_style))
    story.append(Paragraph(f"Data: {report_date_str}", subtitle_style))
    story.append(Spacer(1, 0.5*cm))

    total_wines = stats.get("total_wines", 0)
    total_bottles = stats.get("total_bottles", 0)
    total_value = stats.get("total_value", 0.0)
    types_distribution = stats.get("types_distribution", {})
    low_stock_count = stats.get("low_stock_count", 0)
    out_of_stock_count = stats.get("out_of_stock_count", 0)

    story.append(Paragraph("📈 Statistiche Generali", section_style))
    stats_data = [
        ['Metrica', 'Valore'],
        ['Vini totali', f'{total_wines}'],
        ['Bottiglie totali', f'{total_bottles}'],
        ['Valore stimato', f'€ {total_value:,.2f}'],
        ['Vini a bassa scorta (<5)', f'{low_stock_count}'],
        ['Vini esauriti (0)', f'{out_of_stock_count}']
    ]

    stats_table = Table(stats_data, colWidths=[8*cm, 8*cm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GIOIA_PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), GIOIA_LIGHT),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    story.append(stats_table)

    if types_distribution:
        story.append(Paragraph("🍷 Distribuzione per Tipo", section_style))
        distribution_rows = [['Tipo', 'Vini']]
        for wine_type, count in sorted(types_distribution.items(), key=lambda x: x[1], reverse=True):
            distribution_rows.append([str(wine_type), str(count)])

        dist_table = Table(distribution_rows, colWidths=[10*cm, 6*cm])
        dist_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), GIOIA_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), GIOIA_LIGHT),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(Spacer(1, 0.3*cm))
        story.append(dist_table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    logger.info(f"[PDF_REPORT] PDF statistiche inventario generato: {len(pdf_bytes)} bytes per {business_name}")
    return pdf_bytes


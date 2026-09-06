from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MINT=colors.HexColor('#239F7F'); LIGHT=colors.HexColor('#DFF6EE'); INK=colors.HexColor('#2B2F33'); MUTED=colors.HexColor('#667085')
def eur(value): return f'€ {value:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def build_quote_pdf(quote):
    out=BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=19*mm,leftMargin=19*mm,topMargin=18*mm,bottomMargin=18*mm,title=f'Offerte {quote}')
    styles=getSampleStyleSheet(); body=ParagraphStyle('body',parent=styles['BodyText'],fontName='Helvetica',fontSize=9,leading=13,textColor=INK); small=ParagraphStyle('small',parent=body,fontSize=7.5,textColor=MUTED); right=ParagraphStyle('right',parent=body,alignment=TA_RIGHT)
    logo_path=Path(settings.BASE_DIR)/'static'/'img'/'toolmigo-logo.jpeg'; logo=Image(str(logo_path),17*mm,17*mm)
    brand=Paragraph('<font size="19"><b>Tool</b></font><font size="19" color="#239F7F"><b>migo</b></font><br/><font size="7" color="#667085">CRM</font>',body)
    org=quote.organization; org_text='<b>%s</b><br/>%s<br/>%s %s<br/>KvK %s · BTW %s' % tuple(escape(str(x or '—')) for x in (org.name,org.address,org.postal_code,org.city,org.kvk_number,org.vat_id))
    story=[Table([[logo,brand,Paragraph(org_text,right)]],colWidths=[20*mm,75*mm,77*mm],style=[('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(-1,0),(-1,-1),'RIGHT')]),Spacer(1,14*mm)]
    story += [Paragraph('<font color="#239F7F" size="8"><b>OFFERTE</b></font>',body),Paragraph(escape(quote.title),ParagraphStyle('title',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=25,leading=29,textColor=INK,spaceAfter=8*mm))]
    customer=quote.customer; info=[[Paragraph('<b>OFFERTE AAN</b><br/>%s<br/>%s<br/>%s %s' % tuple(escape(str(x or '')) for x in (customer.legal_name,customer.address,customer.postal_code,customer.city)),body),Paragraph('<b>Offertenummer</b> %s<br/><b>Offertedatum</b> %s<br/><b>Geldig tot</b> %s' % (escape(quote.number or 'CONCEPT'),quote.issue_date.strftime('%d-%m-%Y'),quote.valid_until.strftime('%d-%m-%Y')),right)]]
    story += [Table(info,colWidths=[86*mm,86*mm],style=[('VALIGN',(0,0),(-1,-1),'TOP'),('LINEABOVE',(0,0),(-1,-1),.5,colors.HexColor('#DCE5E1')),('TOPPADDING',(0,0),(-1,-1),5*mm)]),Spacer(1,8*mm)]
    if quote.introduction: story += [Paragraph(escape(quote.introduction).replace('\n','<br/>'),body),Spacer(1,6*mm)]
    rows=[[Paragraph('<b>Omschrijving</b>',small),Paragraph('<b>Aantal</b>',small),Paragraph('<b>Prijs</b>',small),Paragraph('<b>BTW</b>',small),Paragraph('<b>Totaal</b>',right)]]
    for line in quote.lines.all(): rows.append([Paragraph(escape(line.description).replace('\n','<br/>'),body),Paragraph(f'{line.quantity:g} {escape(line.unit)}',body),Paragraph(eur(line.unit_price),right),Paragraph(f'{line.vat_rate:g}%',right),Paragraph(eur(line.net_amount),right)])
    table=Table(rows,colWidths=[76*mm,25*mm,27*mm,17*mm,27*mm],repeatRows=1); table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('TEXTCOLOR',(0,0),(-1,0),colors.white),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,1),(-1,-1),.25,colors.HexColor('#E7ECEA')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ALIGN',(1,1),(-1,-1),'RIGHT')]))
    story += [table,Spacer(1,6*mm)]
    totals=Table([['Subtotaal',eur(quote.subtotal)],['Btw',eur(quote.vat_total)],['Totaal',eur(quote.total)]],colWidths=[42*mm,35*mm],hAlign='RIGHT'); totals.setStyle(TableStyle([('ALIGN',(1,0),(1,-1),'RIGHT'),('FONTNAME',(0,2),(-1,2),'Helvetica-Bold'),('BACKGROUND',(0,2),(-1,2),LIGHT),('TEXTCOLOR',(0,2),(-1,2),INK),('BOX',(0,2),(-1,2),0,LIGHT),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)])); story.append(totals)
    if quote.terms: story += [Spacer(1,9*mm),Paragraph('<b>Voorwaarden</b>',body),Paragraph(escape(quote.terms).replace('\n','<br/>'),small)]
    def page(canvas,doc):
        canvas.saveState(); canvas.setStrokeColor(LIGHT); canvas.line(19*mm,13*mm,191*mm,13*mm); canvas.setFillColor(MUTED); canvas.setFont('Helvetica',7); canvas.drawString(19*mm,8*mm,'ToolMigo · Meer doen. Minder gedoe.'); canvas.drawRightString(191*mm,8*mm,f'Pagina {doc.page}'); canvas.restoreState()
    doc.build(story,onFirstPage=page,onLaterPages=page); return out.getvalue()

def build_invoice_pdf(invoice):
    out=BytesIO(); label='CREDITFACTUUR' if invoice.kind=='credit' else 'FACTUUR'; doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=19*mm,leftMargin=19*mm,topMargin=18*mm,bottomMargin=18*mm,title=f'{label.title()} {invoice}')
    styles=getSampleStyleSheet(); body=ParagraphStyle('ibody',parent=styles['BodyText'],fontName='Helvetica',fontSize=9,leading=13,textColor=INK); small=ParagraphStyle('ismall',parent=body,fontSize=7.5,textColor=MUTED); right=ParagraphStyle('iright',parent=body,alignment=TA_RIGHT)
    logo=Image(str(Path(settings.BASE_DIR)/'static'/'img'/'toolmigo-logo.jpeg'),17*mm,17*mm); brand=Paragraph('<font size="19"><b>Tool</b></font><font size="19" color="#239F7F"><b>migo</b></font><br/><font size="7">CRM</font>',body); org=invoice.organization
    org_text='<b>%s</b><br/>%s<br/>%s %s<br/>KvK %s · BTW %s<br/>IBAN %s' % tuple(escape(str(x or '—')) for x in (org.name,org.address,org.postal_code,org.city,org.kvk_number,org.vat_id,org.iban))
    story=[Table([[logo,brand,Paragraph(org_text,right)]],colWidths=[20*mm,70*mm,82*mm],style=[('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(-1,0),(-1,-1),'RIGHT')]),Spacer(1,12*mm),Paragraph(f'<font color="#239F7F" size="8"><b>{label}</b></font>',body),Paragraph(escape(invoice.title),ParagraphStyle('ititle',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=25,textColor=INK,spaceAfter=7*mm))]
    customer_name=invoice.customer_name_snapshot or invoice.customer.legal_name; address=invoice.customer_address_snapshot or f'{invoice.customer.address}<br/>{invoice.customer.postal_code} {invoice.customer.city}'
    meta='<b>Factuurnummer</b> %s<br/><b>Factuurdatum</b> %s<br/><b>Leverdatum</b> %s<br/><b>Vervaldatum</b> %s' % (escape(invoice.number or 'CONCEPT'),invoice.issue_date.strftime('%d-%m-%Y'),invoice.delivery_date.strftime('%d-%m-%Y'),invoice.due_date.strftime('%d-%m-%Y'))
    story += [Table([[Paragraph(f'<b>FACTUUR AAN</b><br/>{escape(customer_name)}<br/>{address}',body),Paragraph(meta,right)]],colWidths=[86*mm,86*mm],style=[('VALIGN',(0,0),(-1,-1),'TOP'),('LINEABOVE',(0,0),(-1,-1),.5,colors.HexColor('#DCE5E1')),('TOPPADDING',(0,0),(-1,-1),5*mm)]),Spacer(1,8*mm)]
    rows=[[Paragraph('<b>Omschrijving</b>',small),Paragraph('<b>Aantal</b>',small),Paragraph('<b>Prijs</b>',small),Paragraph('<b>BTW</b>',small),Paragraph('<b>Totaal</b>',right)]]
    for line in invoice.lines.all(): rows.append([Paragraph(escape(line.description).replace('\n','<br/>'),body),Paragraph(f'{line.quantity:g} {escape(line.unit)}',body),Paragraph(eur(line.unit_price),right),Paragraph(f'{line.vat_rate:g}%',right),Paragraph(eur(line.net_amount),right)])
    table=Table(rows,colWidths=[76*mm,25*mm,27*mm,17*mm,27*mm],repeatRows=1); table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('TEXTCOLOR',(0,0),(-1,0),colors.white),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,1),(-1,-1),.25,colors.HexColor('#E7ECEA')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ALIGN',(1,1),(-1,-1),'RIGHT')]))
    totals=Table([['Subtotaal',eur(invoice.subtotal)],['Btw',eur(invoice.vat_total)],['Te betalen',eur(invoice.total)]],colWidths=[42*mm,35*mm],hAlign='RIGHT'); totals.setStyle(TableStyle([('ALIGN',(1,0),(1,-1),'RIGHT'),('FONTNAME',(0,2),(-1,2),'Helvetica-Bold'),('BACKGROUND',(0,2),(-1,2),LIGHT),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)])); story += [table,Spacer(1,6*mm),totals]
    if invoice.notes: story += [Spacer(1,8*mm),Paragraph(escape(invoice.notes).replace('\n','<br/>'),small)]
    if invoice.kind=='invoice': story += [Spacer(1,8*mm),Paragraph(f'Maak het bedrag uiterlijk op {invoice.due_date.strftime("%d-%m-%Y")} over naar <b>{escape(org.iban or "het vermelde IBAN")}</b> onder vermelding van <b>{escape(invoice.payment_reference or invoice.number or "factuurnummer")}</b>.',body)]
    def page(canvas,doc): canvas.saveState(); canvas.setStrokeColor(LIGHT); canvas.line(19*mm,13*mm,191*mm,13*mm); canvas.setFillColor(MUTED); canvas.setFont('Helvetica',7); canvas.drawString(19*mm,8*mm,'ToolMigo · Meer doen. Minder gedoe.'); canvas.drawRightString(191*mm,8*mm,f'Pagina {doc.page}'); canvas.restoreState()
    doc.build(story,onFirstPage=page,onLaterPages=page); return out.getvalue()

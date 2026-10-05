from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from .models import Order, Item, Purchase, Lot, Dispatch, Receipt, Event
from .permissions import require, can_view

def number(data,key,positive=True,places=3):
    try:
        n=Decimal(str(data.get(key,'')).replace(',','.'))
        if not n.is_finite() or n<0 or (positive and n==0) or n>Decimal('999999999') or n.as_tuple().exponent < -places: raise ValueError()
        return n
    except (InvalidOperation,ValueError): raise ValidationError(f'Informe um valor válido para {key} (até {places} casas decimais).')
def text(data,key,maxlen=180):
    val=str(data.get(key,'')).strip()
    if not val or len(val)>maxlen: raise ValidationError(f'Preencha {key} (até {maxlen} caracteres).')
    return val

def day(data,key):
    try: return date.fromisoformat(data.get(key,''))
    except (TypeError,ValueError): raise ValidationError('Informe uma data válida.')

def moment(data,key):
    try:
        t=datetime.fromisoformat(data.get(key,''))
        if timezone.is_naive(t): t=timezone.make_aware(t)
        if t>timezone.now(): raise ValueError()
        return t
    except (TypeError,ValueError): raise ValidationError('A data e hora devem ser válidas e não podem estar no futuro.')

@transaction.atomic
def act(user,order_id,data):
    order=Order.objects.select_for_update().get(pk=order_id)
    if not can_view(user,order): raise PermissionDenied()
    try: version=int(data.get('version',''))
    except ValueError: raise ValidationError('Atualize a página e tente novamente.')
    if version!=order.version: raise ValidationError('Este pedido foi atualizado por outra pessoa. Recarregue a página antes de continuar.')
    action=data.get('action'); details=''
    if action=='check':
        require(user,'Almoxarifado')
        item=Item.objects.get(pk=data.get('item'),order=order)
        if item.checked: raise ValidationError('Item já conferido.')
        qty=number(data,'quantidade',False)
        if qty>item.quantity: raise ValidationError('A quantidade disponível não pode superar a solicitada.')
        item.checked=True; item.stock_quantity=qty; item.save()
        if qty: Lot.objects.create(item=item,quantity=qty,source='stock')
        if item.missing: Purchase.objects.create(item=item)
        details=f'{item.name}: conferência — {qty} {item.unit} para expedição; {item.missing} para compras.'
    elif action in ['quote','approve','reject','buy','arrive','supplier_send']:
        p=Purchase.objects.select_related('item').get(pk=data.get('purchase'),item__order=order)
        name=p.item.name
        if action=='quote':
            require(user,'Compras')
            if p.state not in ['draft','pending','approved']: raise ValidationError('Uma compra efetivada não pode ser recotada.')
            p.supplier=text(data,'fornecedor'); p.price=number(data,'preço',places=2); p.freight=number(data,'frete',False,2)
            p.expected=day(data,'previsao'); p.destination=data.get('destino')
            if p.destination not in ['depot','site']: raise ValidationError('Destino inválido.')
            p.state='pending'; p.approved_by=None; p.approved_at=None; p.save()
            details=f'{name}: cotação de {p.supplier}; unitário R$ {p.price}; frete R$ {p.freight}; total R$ {p.total}; destino {"obra" if p.destination=="site" else "depósito"}; previsão {p.expected:%d/%m/%Y}. Pendente de aprovação.'
        elif action in ['approve','reject']:
            require(user,'Gestor')
            if p.state!='pending': raise ValidationError('Esta cotação não está pendente de aprovação.')
            if action=='approve':
                p.state='approved'; p.approved_by=user; p.approved_at=timezone.now(); details=f'{name}: compra aprovada por R$ {p.total}.'
            else:
                reason=text(data,'motivo',1000); p.state='draft'; p.approved_by=None; p.approved_at=None; details=f'{name}: cotação devolvida para ajuste. Motivo: {reason}'
            p.save()
        elif action=='buy':
            require(user,'Compras')
            if p.state!='approved': raise ValidationError('O gestor deve aprovar antes da compra.')
            p.reference=text(data,'referencia'); p.state='ordered'; p.save()
            details=f'{name}: compra efetivada. Referência: {p.reference}. Total aprovado: R$ {p.total}.'
        else:
            require(user,*(['Almoxarifado'] if action=='arrive' else ['Compras','Logística']))
            if p.state!='ordered': raise ValidationError('Registre a compra antes da chegada ou envio.')
            if (action=='arrive')!=(p.destination=='depot'): raise ValidationError('Operação incompatível com o destino da compra.')
            qty=number(data,'quantidade')
            if qty>p.remaining: raise ValidationError('Quantidade superior ao saldo da compra.')
            when=moment(data,'data_hora')
            if when < p.approved_at.replace(microsecond=0): raise ValidationError('A movimentação não pode anteceder a aprovação.')
            lot=Lot.objects.create(item=p.item,purchase=p,quantity=qty,source='purchase' if action=='arrive' else 'direct',arrival_at=when,packed=qty if action=='supplier_send' else 0)
            if action=='supplier_send':
                carrier=text(data,'transportador',150); forecast=day(data,'previsao')
                if forecast<timezone.localtime(when).date(): raise ValidationError('A previsão não pode anteceder o envio.')
                Dispatch.objects.create(lot=lot,quantity=qty,carrier=carrier,sent_at=when,forecast=forecast)
                details=f'{name}: fornecedor enviou {qty} {p.item.unit} diretamente à obra em {timezone.localtime(when):%d/%m/%Y %H:%M}. Transporte: {carrier}.'
            else: details=f'{name}: recebidos {qty} {p.item.unit} no depósito em {timezone.localtime(when):%d/%m/%Y %H:%M}; aguardando separação.'
    elif action in ['pack','ship']:
        require(user,*(['Almoxarifado'] if action=='pack' else ['Logística']))
        lot=Lot.objects.select_related('item').get(pk=data.get('lot'),item__order=order)
        qty=number(data,'quantidade')
        if action=='pack':
            if qty>lot.to_pack: raise ValidationError('Quantidade superior ao saldo para separar.')
            lot.packed+=qty; lot.save(); details=f'{lot.item.name}: separados {qty} {lot.item.unit} para envio.'
        else:
            if qty>lot.to_send: raise ValidationError('Quantidade superior ao material separado e disponível para envio.')
            when=moment(data,'data_hora'); forecast=day(data,'previsao')
            if when<lot.arrival_at.replace(microsecond=0): raise ValidationError('O envio não pode anteceder a disponibilidade no depósito.')
            if forecast<timezone.localtime(when).date(): raise ValidationError('A previsão não pode anteceder o envio.')
            carrier=text(data,'transportador',150)
            Dispatch.objects.create(lot=lot,quantity=qty,carrier=carrier,sent_at=when,forecast=forecast)
            details=f'{lot.item.name}: enviados {qty} {lot.item.unit} em {timezone.localtime(when):%d/%m/%Y %H:%M}; transporte: {carrier}; previsão {forecast:%d/%m/%Y}.'
    elif action=='receive':
        require(user,'Supervisor','Almoxarifado')
        d=Dispatch.objects.select_related('lot__item').get(pk=data.get('dispatch'),lot__item__order=order)
        qty=number(data,'quantidade')
        if qty>d.remaining: raise ValidationError('Quantidade superior ao saldo em transporte.')
        when=moment(data,'data_hora')
        if when<d.sent_at.replace(microsecond=0): raise ValidationError('A entrega não pode anteceder o envio.')
        recipient=text(data,'recebedor',150); notes=str(data.get('observacao','')).strip()
        if len(notes)>2000: raise ValidationError('Observação muito longa.')
        Receipt.objects.create(dispatch=d,quantity=qty,recipient=recipient,delivered_at=when,recorded_by=user,notes=notes)
        d.received+=qty; d.save()
        details=f'{d.lot.item.name}: entregues {qty} {d.lot.item.unit} na obra em {timezone.localtime(when):%d/%m/%Y %H:%M}. Recebedor: {recipient}. {notes}'
    else: raise ValidationError('Operação desconhecida.')
    Event.objects.create(order=order,actor=user,text=details)
    order.version+=1; order.save(update_fields=['version'])
    return details

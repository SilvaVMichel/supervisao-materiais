from decimal import Decimal
from django.db import models
from django.conf import settings
from django.db.models import Q, F
from django.utils import timezone

class Project(models.Model):
    name = models.CharField('Obra', max_length=150)
    address = models.CharField('Endereço de entrega', max_length=300)
    active = models.BooleanField(default=True)
    supervisors = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='projects')
    def __str__(self): return self.name

class Order(models.Model):
    project = models.ForeignKey(Project, on_delete=models.PROTECT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    due_date = models.DateField('Data necessária')
    notes = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.PositiveIntegerField(default=0)
    class Meta: ordering = ['-created_at']
    @property
    def code(self): return f'PED-{self.pk:05d}'
    @property
    def complete(self): return all(i.delivered >= i.quantity for i in self.items.all())
    @property
    def status(self):
        if self.complete: return 'Entregue'
        if any(i.delivered > 0 for i in self.items.all()): return 'Entrega parcial'
        if any(not i.checked for i in self.items.all()): return 'Conferência'
        return 'Em atendimento'

class Item(models.Model):
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name='items')
    name = models.CharField(max_length=180)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=12,decimal_places=3)
    checked = models.BooleanField(default=False)
    stock_quantity = models.DecimalField(max_digits=12,decimal_places=3,default=0)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0),name='item_positive'),models.CheckConstraint(condition=Q(stock_quantity__gte=0)&Q(stock_quantity__lte=F('quantity')),name='stock_in_range')]
    @property
    def delivered(self): return sum((d.received for lot in self.lots.all() for d in lot.dispatches.all()),Decimal(0))
    @property
    def missing(self): return self.quantity - self.stock_quantity

class Purchase(models.Model):
    item = models.OneToOneField(Item,on_delete=models.CASCADE,related_name='purchase')
    state = models.CharField(max_length=20,default='draft')
    supplier = models.CharField(max_length=180,blank=True)
    price = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    freight = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    destination = models.CharField(max_length=10,default='depot')
    expected = models.DateField(null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,related_name='approved_purchases')
    approved_at = models.DateTimeField(null=True)
    reference = models.CharField(max_length=180,blank=True)
    @property
    def total(self): return (self.item.missing*self.price+self.freight).quantize(Decimal('.01'))
    @property
    def remaining(self): return self.item.missing-sum((l.quantity for l in self.lots.all()),Decimal(0))
    @property
    def label(self): return {'draft':'A cotar','pending':'Aguardando aprovação','approved':'Aprovada','ordered':'Comprada'}.get(self.state,self.state)

class Lot(models.Model):
    item = models.ForeignKey(Item,on_delete=models.CASCADE,related_name='lots')
    purchase = models.ForeignKey(Purchase,on_delete=models.PROTECT,null=True,related_name='lots')
    quantity = models.DecimalField(max_digits=12,decimal_places=3)
    packed = models.DecimalField(max_digits=12,decimal_places=3,default=0)
    source = models.CharField(max_length=20)
    arrival_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gt=0)&Q(packed__gte=0)&Q(packed__lte=F('quantity')),name='lot_in_range')]
    @property
    def to_pack(self): return self.quantity-self.packed
    @property
    def to_send(self): return self.packed-sum((d.quantity for d in self.dispatches.all()),Decimal(0))

class Dispatch(models.Model):
    lot = models.ForeignKey(Lot,on_delete=models.PROTECT,related_name='dispatches')
    quantity = models.DecimalField(max_digits=12,decimal_places=3)
    received = models.DecimalField(max_digits=12,decimal_places=3,default=0)
    carrier = models.CharField(max_length=150)
    sent_at = models.DateTimeField(default=timezone.now)
    forecast = models.DateField()
    @property
    def remaining(self): return self.quantity-self.received
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gt=0)&Q(received__gte=0)&Q(received__lte=F('quantity')),name='dispatch_in_range')]

class Receipt(models.Model):
    dispatch = models.ForeignKey(Dispatch,on_delete=models.PROTECT,related_name='receipts')
    quantity = models.DecimalField(max_digits=12,decimal_places=3)
    recipient = models.CharField(max_length=150)
    delivered_at = models.DateTimeField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    notes = models.TextField(blank=True,max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

class Event(models.Model):
    order = models.ForeignKey(Order,on_delete=models.PROTECT,null=True,related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at','-pk']

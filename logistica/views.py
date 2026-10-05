from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import SetPasswordForm
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import PermissionDenied, ValidationError, ObjectDoesNotExist
from django.utils import timezone
from django.http import HttpResponse
from .models import Project, Order, Item, Purchase, Event
from .forms import OrderForm, ItemFormSet, ProjectForm, EmployeeForm, EmployeeEditForm
from .permissions import has, require, can_view, ROLES
from .services import act

TABS=[('all','Todos'),('stock','Conferência'),('buy','Compras'),('approval','Aprovações'),('packing','Expedição'),('delivery','Entregas')]

def orders_for(user):
    qs=Order.objects.select_related('project','author').prefetch_related('items__purchase','items__lots__dispatches')
    if not has(user,'Almoxarifado','Compras','Gestor','Logística'):
        qs=qs.filter(Q(author=user)|Q(project__supervisors=user)).distinct() if has(user,'Supervisor') else qs.none()
    return qs

def queue(order,tab):
    items=list(order.items.all())
    if tab=='stock': return any(not i.checked for i in items)
    if tab=='buy': return any(hasattr(i,'purchase') and (i.purchase.state in ['draft','approved'] or (i.purchase.state=='ordered' and i.purchase.remaining>0)) for i in items)
    if tab=='approval': return any(hasattr(i,'purchase') and i.purchase.state=='pending' for i in items)
    if tab=='packing': return any(l.to_pack>0 or l.to_send>0 for i in items for l in i.lots.all())
    if tab=='delivery': return any(d.remaining>0 for i in items for l in i.lots.all() for d in l.dispatches.all())
    return True

@login_required
def home(request):
    q=request.GET.get('q','').strip(); tab=request.GET.get('tab','all')
    qs=orders_for(request.user)
    if q: qs=qs.filter(Q(project__name__icontains=q)|Q(items__name__icontains=q)).distinct()
    orders=list(qs); filtered=[o for o in orders if queue(o,tab)]
    counts={key:sum(queue(o,key) for o in orders) for key,_ in TABS}
    return render(request,'home.html',{'orders':filtered,'tabs':TABS,'tab':tab,'counts':counts,'q':q,'today':timezone.localdate()})

@login_required
def new_order(request):
    require(request.user,'Supervisor')
    form=OrderForm(request.POST or None,user=request.user)
    fs=ItemFormSet(request.POST or None,queryset=Item.objects.none(),prefix='items')
    if request.method=='POST' and form.is_valid() and fs.is_valid():
        with transaction.atomic():
            order=form.save(commit=False); order.author=request.user; order.save()
            for item in fs.save(commit=False): item.order=order; item.save()
            Event.objects.create(order=order,actor=request.user,text='Pedido criado e encaminhado ao almoxarifado.')
        messages.success(request,'Pedido enviado ao almoxarifado.')
        return redirect('detail',pk=order.pk)
    return render(request,'new_order.html',{'form':form,'formset':fs})

@login_required
def detail(request,pk):
    order=get_object_or_404(orders_for(request.user),pk=pk)
    if not can_view(request.user,order): raise PermissionDenied()
    failed=None
    if request.method=='POST':
        try:
            act(request.user,pk,request.POST)
            messages.success(request,'Movimentação registrada.')
            return redirect('detail',pk=pk)
        except ValidationError as e:
            failed=request.POST; messages.error(request,' '.join(e.messages))
        except (ObjectDoesNotExist,ValueError,TypeError):
            failed=request.POST; messages.error(request,'Registro inválido. Confira o pedido e tente novamente.')
        order=orders_for(request.user).get(pk=pk)
    return render(request,'detail.html',{'order':order,'events':order.events.select_related('actor'),'now_input':timezone.localtime().strftime('%Y-%m-%dT%H:%M:%S'),'today_input':timezone.localdate().isoformat(),'failed':failed})

@login_required
def projects(request):
    require(request.user)
    pk=request.GET.get('edit'); obj=get_object_or_404(Project,pk=pk) if pk else None
    form=ProjectForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            project=form.save(); Event.objects.create(actor=request.user,text=f'Cadastro de obra atualizado: {project.name}.')
        messages.success(request,'Obra salva.'); return redirect('projects')
    return render(request,'projects.html',{'form':form,'projects':Project.objects.all(),'editing':obj})

@login_required
def employees(request):
    require(request.user)
    for role in ROLES: Group.objects.get_or_create(name=role)
    form=EmployeeForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            user=form.save(); Event.objects.create(actor=request.user,text=f'Usuário criado: {user.username}; perfis: {", ".join(user.groups.values_list("name",flat=True))}.')
        messages.success(request,'Funcionário cadastrado.'); return redirect('employees')
    return render(request,'employees.html',{'form':form,'employees':User.objects.prefetch_related('groups').order_by('first_name')})

@login_required
def edit_employee(request,pk):
    require(request.user)
    target=get_object_or_404(User,pk=pk)
    if target.is_superuser and not request.user.is_superuser: raise PermissionDenied()
    form=EmployeeEditForm(request.POST if request.method=='POST' and request.POST.get('action')=='profile' else None,instance=target)
    password=SetPasswordForm(target,request.POST if request.method=='POST' and request.POST.get('action')=='password' else None)
    if request.method=='POST':
        if request.POST.get('action')=='profile' and form.is_valid():
            if target.pk==request.user.pk and (not form.cleaned_data['is_active'] or (not target.is_superuser and not form.cleaned_data['roles'].filter(name='Administrador').exists())):
                form.add_error(None,'Mantenha seu próprio acesso de administrador ativo.')
            else:
                with transaction.atomic():
                    form.save(); Event.objects.create(actor=request.user,text=f'Usuário {target.username}: ativo={target.is_active}; perfis: {", ".join(target.groups.values_list("name",flat=True))}.')
                messages.success(request,'Permissões atualizadas.'); return redirect('employees')
        elif request.POST.get('action')=='password' and password.is_valid():
            with transaction.atomic():
                password.save(); Event.objects.create(actor=request.user,text=f'Senha redefinida para {target.username}.')
            messages.success(request,'Senha redefinida.'); return redirect('employees')
    return render(request,'employee_edit.html',{'form':form,'password_form':password,'target':target})

@login_required
def audit(request):
    require(request.user)
    return render(request,'audit.html',{'events':Event.objects.select_related('actor','order')[:300]})

def health(request): return HttpResponse('ok',content_type='text/plain')

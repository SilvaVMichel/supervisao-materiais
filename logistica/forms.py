from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from .models import Project, Order, Item
from .permissions import ROLES, has

class OrderForm(forms.ModelForm):
    class Meta:
        model=Order; fields=['project','due_date','notes']
        labels={'project':'Obra','due_date':'Material necessário até','notes':'Orientações do pedido'}
        widgets={'due_date':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),'notes':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*args,user=None,**kwargs):
        super().__init__(*args,**kwargs)
        q=Project.objects.filter(active=True)
        if not has(user): q=q.filter(supervisors=user)
        self.fields['project'].queryset=q

class ItemForm(forms.ModelForm):
    unit=forms.ChoiceField(label='Unidade',initial='un',choices=[('un','Unidade'),('saco','Saco'),('m','Metro'),('m²','Metro quadrado'),('m³','Metro cúbico'),('kg','Quilo'),('L','Litro'),('caixa','Caixa'),('rolo','Rolo'),('barra','Barra'),('balde','Balde')])
    class Meta:
        model=Item; fields=['name','quantity','unit']; labels={'name':'Material e especificação','quantity':'Quantidade'}
        widgets={'name':forms.TextInput(attrs={'placeholder':'Ex.: cimento CP II · saco de 50 kg'}),'quantity':forms.NumberInput(attrs={'min':'0.001','step':'0.001'})}

ItemFormSet=forms.modelformset_factory(Item,form=ItemForm,extra=3,min_num=1,validate_min=True,max_num=100,validate_max=True,absolute_max=100)

class ProjectForm(forms.ModelForm):
    class Meta:
        model=Project; fields=['name','address','supervisors','active']
        labels={'supervisors':'Supervisores autorizados','active':'Obra ativa'}
        widgets={'supervisors':forms.CheckboxSelectMultiple}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['supervisors'].queryset=User.objects.filter(is_active=True,groups__name='Supervisor').distinct()

class EmployeeForm(UserCreationForm):
    first_name=forms.CharField(label='Nome completo',max_length=150)
    roles=forms.ModelMultipleChoiceField(label='Perfis',queryset=Group.objects.filter(name__in=ROLES),widget=forms.CheckboxSelectMultiple)
    class Meta:
        model=User; fields=['username','first_name','email','roles','password1','password2']
        labels={'username':'Usuário de acesso','email':'E-mail (opcional)'}
    def save(self,commit=True):
        user=super().save(commit)
        if commit: user.groups.set(self.cleaned_data['roles'])
        return user

class EmployeeEditForm(forms.ModelForm):
    roles=forms.ModelMultipleChoiceField(label='Perfis',queryset=Group.objects.filter(name__in=ROLES),widget=forms.CheckboxSelectMultiple)
    class Meta:
        model=User; fields=['first_name','email','is_active','roles']
        labels={'first_name':'Nome completo','email':'E-mail','is_active':'Acesso ativo'}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['roles'].initial=self.instance.groups.all()
    def save(self,commit=True):
        user=super().save(commit)
        if commit: user.groups.set(self.cleaned_data['roles'])
        return user

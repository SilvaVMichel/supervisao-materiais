from django.core.exceptions import PermissionDenied
ROLES = ['Administrador','Supervisor','Almoxarifado','Compras','Gestor','Logística']
def has(user,*roles):
    return user.is_authenticated and user.is_active and (user.is_superuser or user.groups.filter(name__in=['Administrador',*roles]).exists())
def require(user,*roles):
    if not has(user,*roles): raise PermissionDenied('Seu perfil não permite esta operação.')
def can_view(user,order):
    return has(user,'Almoxarifado','Compras','Gestor','Logística') or (has(user,'Supervisor') and (order.author_id==user.id or order.project.supervisors.filter(pk=user.pk).exists()))

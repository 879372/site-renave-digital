from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("leads", views.LeadViewSet, basename="leads")
router.register("tarefas", views.TarefaViewSet, basename="tarefas")
urlpatterns = router.urls

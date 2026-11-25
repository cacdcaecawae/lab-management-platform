# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .task_views import MilestoneViewSet, TaskViewSet
from .views import ProjectFileViewSet, ProjectLogViewSet, ProjectViewSet

router = SimpleRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("project-logs", ProjectLogViewSet, basename="project-log")
router.register("project-files", ProjectFileViewSet, basename="project-file")
router.register("tasks", TaskViewSet, basename="task")
router.register("milestones", MilestoneViewSet, basename="milestone")
urlpatterns = router.urls
